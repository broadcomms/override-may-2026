"""Tests for core.regs.

Coverage:
  - chunk_markdown: heading-driven splitting, length bounds, sentence
    fallback for over-long paragraphs, section-label extraction
  - embed_chunks: round-trips through a fake embedder, batching,
    immutable input/new output
  - retrieve_chunk: keyword overlap, cosine, combined score, threshold
    filtering, the no-chunks case, the all-below-threshold case
  - save_chunks / load_chunks: JSON round-trip with metadata + g4_status
  - One @pytest.mark.network test exercising the real watsonx Embeddings API
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from core.regs import (
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    COSINE_WEIGHT,
    KEYWORD_WEIGHT,
    chunk_markdown,
    embed_chunks,
    extract_harvest_cap_mj,
    load_chunks,
    retrieve_chunk,
    save_chunks,
)
from ingest.schema import RegulationChunk, RegulationSource, ZoneType


# ──────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ──────────────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


def _source(section: str = "Article 5") -> RegulationSource:
    return RegulationSource(
        document_title="FIA 2026 F1 Technical Regulations",
        issue="Issue 8 — 2024-06-24",
        section=section,
        public_url="https://www.fia.com/regulation/category/110",
        fetched_at=_now(),
    )


def _make_chunk(
    text: str,
    section: str = "Article 5",
    embedding: list[float] | None = None,
) -> RegulationChunk:
    return RegulationChunk(
        chunk_id=f"c_{abs(hash(text)) % 10_000:04d}",
        text=text,
        source=_source(section),
        keywords=[w for w in ["MGU-K", "deploy", "harvest", "ES"] if w.lower() in text.lower()],
        embedding=embedding,
    )


class FakeEmbeddingClient:
    """Returns deterministic, controllable vectors for offline testing.

    By default uses a tiny hand-crafted projection (3 dimensions) so test
    vectors are easy to reason about. `dim` can be raised when tests want
    to exercise the 768-dim path.
    """

    def __init__(
        self,
        *,
        dim: int = 3,
        target_text: str | None = None,
        target_vec: list[float] | None = None,
    ):
        self.dim = dim
        self.calls: list[list[str]] = []
        # Optional override: any text containing target_text returns target_vec.
        self.target_text = target_text
        self.target_vec = target_vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        out: list[list[float]] = []
        for t in texts:
            if self.target_text is not None and self.target_text in t and self.target_vec is not None:
                out.append(list(self.target_vec))
                continue
            # Cheap deterministic projection from text → 3-vec.
            h = abs(hash(t)) % 1000
            v = [(h % 7) / 10.0, ((h // 7) % 7) / 10.0, ((h // 49) % 7) / 10.0]
            v += [0.0] * (self.dim - len(v))
            out.append(v[: self.dim])
        return out


# ──────────────────────────────────────────────────────────────────────────────
# chunk_markdown
# ──────────────────────────────────────────────────────────────────────────────


def test_chunk_markdown_empty_input_returns_empty():
    assert chunk_markdown("", document_title="x", issue="y", public_url="z") == []


def test_chunk_markdown_basic_split_on_headings():
    md = """## ARTICLE 5: POWER UNIT

Some descriptive prose about power units. The MGU-K shall not exceed the per-lap cap.

### 5.1 Definitions

The Energy Store (ES) is defined as the rechargeable energy storage device.

### 5.2 Energy Recovery

Energy released from the ES into the MGU-K shall not exceed 8 MJ per lap.
Recovery braking is permitted under conditions specified in 5.2.1.
"""
    chunks = chunk_markdown(
        md,
        document_title="FIA 2026 F1 Technical Regulations",
        issue="Issue 8",
        public_url="https://www.fia.com/regulation/category/110",
        fetched_at=_now(),
    )
    assert len(chunks) >= 2
    # All chunks fit within the schema's max-len constraint
    for c in chunks:
        assert len(c.text) <= CHUNK_MAX_CHARS
        assert len(c.text) >= CHUNK_MIN_CHARS


def test_chunk_markdown_section_labels_use_article_pattern():
    md = """## ARTICLE 5: POWER UNIT

The MGU-K shall not exceed the per-lap deployment cap defined in this Article. The Energy Store shall be of an approved configuration. Recovery shall be regenerative-braking only.

## ARTICLE 6: GEARBOX

The gearbox shall be of homologated design. Shifts shall be sequential and the ratios shall not be modified during a Competition. Reverse gear shall be present.
"""
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    sections = {c.source.section for c in chunks}
    # "Article 5" and "Article 6" should appear, not the raw heading text
    assert "Article 5" in sections
    assert "Article 6" in sections


def test_chunk_markdown_section_labels_use_numbered_pattern():
    md = """## 5.4.2 Energy Release

The MGU-K shall not release more than the cap permits in a single lap.
"""
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    assert len(chunks) >= 1
    # Numbered pattern picks up "5.4.2"
    assert chunks[0].source.section == "5.4.2"


def test_chunk_markdown_drops_tiny_sections():
    md = """## A

x

## B

This section is long enough to pass the CHUNK_MIN_CHARS threshold. Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam.
"""
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    # Section "A" body is tiny → dropped. "B" survives.
    assert len(chunks) == 1


def test_chunk_markdown_splits_long_paragraphs_at_sentence_boundaries():
    long_para = " ".join([f"Sentence {i} is here." for i in range(200)])
    md = f"## Section 1\n\n{long_para}\n"
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= CHUNK_MAX_CHARS


def test_chunk_markdown_prefers_body_subsection_over_generic_heading():
    """When the heading is a high-level document title (no section code)
    but the body contains sub-article codes like 'C5.18.1', the chunk
    label should be the subsection code, not the generic heading.
    Reproduces the §-SECTION-C-TECHNICAL-REGULATIONS bug from P3.4 review.
    """
    md = """## SECTION C: TECHNICAL REGULATIONS

- C5.18.1 The MGU-K shall not exceed the deployment cap of 350 kW. The Energy Store shall be of an approved configuration. Recovery shall be regenerative-braking only.
"""
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    sections = {c.source.section for c in chunks}
    assert "C5.18.1" in sections
    assert "SECTION C: TECHNICAL REGULATIONS" not in sections


def test_chunk_markdown_body_subsection_skips_lone_digits():
    """Only multi-part codes (with at least one dot) qualify as
    subsection labels — stray '1', '2', '3' bullets shouldn't be picked."""
    md = """## SECTION X

- 1. First numbered item without any section code anywhere; the regulation prose continues here without a structured numbering scheme.
- 2. Second item also without a section code; this content is just bulleted prose and should not provide a label.
"""
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    sections = {c.source.section for c in chunks}
    # Single-digit bullets aren't section codes → fallback to heading text
    assert "SECTION X" in sections


def test_chunk_markdown_no_headings_treats_whole_doc_as_one():
    md = (
        "Just a long flat document with no headings. "
        + "More text. " * 50
    )
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    assert len(chunks) >= 1
    # Default section label when no heading found
    assert chunks[0].source.section == "(document)"


def test_chunk_markdown_keywords_populated_from_capitalized_terms():
    md = """## Section 5

The MGU-K and Energy Store interact via the Power Unit Control Module.
"""
    chunks = chunk_markdown(md, document_title="x", issue="y", public_url="z")
    keywords = chunks[0].keywords
    # Capitalized domain terms should appear; common lowercase words shouldn't
    assert any("MGU" in k for k in keywords)
    assert "the" not in [k.lower() for k in keywords]


# ──────────────────────────────────────────────────────────────────────────────
# embed_chunks
# ──────────────────────────────────────────────────────────────────────────────


def test_embed_chunks_populates_embedding_field():
    chunks = [
        _make_chunk("MGU-K deployment shall not exceed the cap."),
        _make_chunk("Energy Store recovery is limited per lap."),
    ]
    client = FakeEmbeddingClient(dim=3)
    out = embed_chunks(chunks, client)
    assert len(out) == 2
    for c in out:
        assert c.embedding is not None
        assert len(c.embedding) == 3


def test_embed_chunks_returns_new_chunks_does_not_mutate_input():
    """Pydantic frozen → embed must return new instances."""
    original = [_make_chunk("MGU-K deployment.")]
    client = FakeEmbeddingClient(dim=3)
    out = embed_chunks(original, client)
    assert original[0].embedding is None  # original unchanged
    assert out[0].embedding is not None    # new chunk has embedding


def test_embed_chunks_batches_inputs():
    chunks = [_make_chunk(f"chunk {i}") for i in range(35)]
    client = FakeEmbeddingClient(dim=3)
    embed_chunks(chunks, client, batch_size=10)
    # 35 chunks / 10-batch → 4 batches (10, 10, 10, 5)
    assert [len(b) for b in client.calls] == [10, 10, 10, 5]


def test_embed_chunks_empty_input_no_calls():
    client = FakeEmbeddingClient(dim=3)
    assert embed_chunks([], client) == []
    assert client.calls == []


def test_embed_chunks_dimension_mismatch_raises():
    chunks = [_make_chunk("MGU-K")]

    class BadClient:
        def embed(self, texts):
            return [[1.0]] * (len(texts) + 1)  # one too many

    with pytest.raises(RuntimeError, match="vectors for"):
        embed_chunks(chunks, BadClient())


# ──────────────────────────────────────────────────────────────────────────────
# retrieve_chunk
# ──────────────────────────────────────────────────────────────────────────────


def test_retrieve_chunk_returns_none_when_no_chunks():
    client = FakeEmbeddingClient(dim=3)
    assert retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, [], client) is None


def test_retrieve_chunk_returns_none_when_all_below_threshold():
    """All chunks have weak signals → None forces the pre-G-4 pathway."""
    chunks = [
        _make_chunk("totally unrelated text about gearbox bearings", embedding=[0.0, 0.0, 0.0]),
    ]
    client = FakeEmbeddingClient(dim=3)
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, chunks, client, threshold=0.5)
    assert out is None


def test_retrieve_chunk_keyword_signal_alone_can_pass_threshold():
    """A chunk with strong keyword overlap but mediocre cosine should still
    score above threshold via the 0.4 keyword weight."""
    chunks = [
        _make_chunk(
            "MGU-K deploy deployment ES energy release kinetic energy release event",
            embedding=[0.0, 0.0, 0.0],  # cosine == 0 vs query
        ),
    ]
    # 7/7 keywords match → kw=1.0 → score = 0.6*0 + 0.4*1.0 = 0.4 (just at threshold)
    client = FakeEmbeddingClient(dim=3, target_text="2026 F1 energy", target_vec=[0.0, 0.0, 0.0])
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, chunks, client, threshold=0.4)
    assert out is not None
    chunk, score = out
    assert score >= 0.4
    assert "MGU-K" in chunk.text


def test_retrieve_chunk_cosine_signal_alone_can_pass_threshold():
    """Strong cosine + zero keyword overlap should still pass."""
    target_vec = [1.0, 0.0, 0.0]
    chunks = [
        _make_chunk(
            "the gearbox shall be of an approved design and homologated",
            embedding=target_vec,
        ),
    ]
    client = FakeEmbeddingClient(
        dim=3, target_text="2026 F1 energy", target_vec=target_vec
    )
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, chunks, client, threshold=0.4)
    assert out is not None
    _, score = out
    # cosine=1, kw=0 → 0.6*1 + 0.4*0 = 0.6
    assert score == pytest.approx(0.6)


def test_retrieve_chunk_picks_highest_score_among_candidates():
    target_vec = [1.0, 0.0, 0.0]
    weak = _make_chunk("weak unrelated text", embedding=[0.0, 0.0, 1.0])
    strong = _make_chunk(
        "MGU-K deploy and ES handling per lap, with energy release semantics",
        embedding=target_vec,
    )
    client = FakeEmbeddingClient(
        dim=3, target_text="2026 F1 energy", target_vec=target_vec
    )
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, [weak, strong], client)
    assert out is not None
    chunk, _ = out
    assert chunk is strong


def test_retrieve_chunk_excludes_front_matter_chunks():
    """Chunks labelled with the document-title pattern ('SECTION C: TECHNICAL
    REGULATIONS') are document cover / TOC / abbreviations metadata, not
    regulatory clauses. They must never win retrieval even if their
    embedding+keyword score outranks a real sub-article chunk.

    Locks the fix for the live-pipeline failure where retrieval was landing
    on the TOC chunk whose body contained C5.18 / C5.19 / C5.20 in a markdown
    table — high keyword overlap, but no regulatory content.
    """
    target_vec = [1.0, 0.0, 0.0]
    # Front-matter chunk: deliberately strong embedding + matching keywords
    front_matter = _make_chunk(
        "MGU-K deployment Energy Store ES energy release kinetic energy release",
        embedding=target_vec,
        section="SECTION C: TECHNICAL REGULATIONS",
    )
    # Real sub-article chunk: weaker score (different keywords, weaker cosine)
    real_article = _make_chunk(
        "MGU-K deploy and ES handling per lap",
        embedding=[0.5, 0.5, 0.0],
        section="C5.18",
    )
    client = FakeEmbeddingClient(dim=3, target_text="2026 F1 energy", target_vec=target_vec)
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, [front_matter, real_article], client)
    assert out is not None, "expected the real sub-article chunk to win, not None"
    chunk, _ = out
    assert chunk is real_article, (
        f"front-matter chunk leaked into retrieval — got section={chunk.source.section!r}"
    )


def test_retrieve_chunk_excludes_front_matter_returns_none_when_only_front_matter():
    """If every available chunk is front-matter / TOC, retrieval correctly
    returns None — caller then falls into the citation=null pathway per
    FR-4.3, rather than silently citing the document title."""
    target_vec = [1.0, 0.0, 0.0]
    chunks = [
        _make_chunk(
            "MGU-K Energy Store ES kinetic energy release deploy",
            embedding=target_vec,
            section="SECTION C: TECHNICAL REGULATIONS",
        ),
    ]
    client = FakeEmbeddingClient(dim=3, target_text="2026 F1 energy", target_vec=target_vec)
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, chunks, client)
    assert out is None


def test_retrieve_chunk_allows_article_header_and_appendix_labels():
    """The exclusion is narrow — only the document-title 'SECTION ...
    REGULATIONS' pattern. Article headers ('Article C5') and appendix
    labels ('APPENDIX C5: HOMOLOGATION') remain retrievable; they're
    specific enough to be useful citations."""
    target_vec = [1.0, 0.0, 0.0]
    chunks = [
        _make_chunk(
            "MGU-K deploy ES energy release kinetic energy release",
            embedding=target_vec,
            section="Article C5",
        ),
    ]
    client = FakeEmbeddingClient(dim=3, target_text="2026 F1 energy", target_vec=target_vec)
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, chunks, client)
    assert out is not None
    assert out[0].source.section == "Article C5"


def test_retrieve_chunk_handles_chunks_without_embedding():
    """A chunk with embedding=None should contribute cos=0.0 (still allowed)."""
    chunks = [
        _make_chunk(
            "MGU-K deploy deployment ES energy release kinetic energy release",
            embedding=None,
        ),
    ]
    client = FakeEmbeddingClient(dim=3, target_text="2026 F1 energy", target_vec=[1, 0, 0])
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, chunks, client, threshold=0.3)
    assert out is not None  # kw alone (1.0 * 0.4 = 0.4) clears threshold


def test_retrieve_chunk_combined_score_in_zero_to_one():
    """No matter how the score lands, it must stay in [0, 1] for prompt
    contract compatibility (grounding.system.md threshold range)."""
    chunks = [
        _make_chunk("MGU-K deploy", embedding=[1.0, 0.0, 0.0]),
        _make_chunk("ES recovery", embedding=[0.0, 1.0, 0.0]),
        _make_chunk("Overtake Mode", embedding=[0.0, 0.0, 1.0]),
    ]
    client = FakeEmbeddingClient(dim=3)
    out = retrieve_chunk(ZoneType.LOW_ROI_DEPLOY, chunks, client, threshold=0.0)
    assert out is not None
    _, score = out
    assert 0.0 <= score <= 1.0


def test_retrieve_chunk_score_weights_sum_to_1():
    """Sanity: 0.6 cosine + 0.4 keyword = 1.0 max, which keeps scores in [0,1]."""
    assert pytest.approx(COSINE_WEIGHT + KEYWORD_WEIGHT) == 1.0


# ──────────────────────────────────────────────────────────────────────────────
# save_chunks / load_chunks round-trip
# ──────────────────────────────────────────────────────────────────────────────


def test_save_and_load_chunks_round_trip(tmp_path: Path):
    chunks = [
        _make_chunk("MGU-K deploy.", embedding=[0.1, 0.2, 0.3]),
        _make_chunk("ES recovery.", embedding=[0.4, 0.5, 0.6]),
    ]
    p = tmp_path / "chunks.json"
    save_chunks(
        chunks,
        path=p,
        g4_status="pending",
        source_document_label="FIA 2026 F1 Technical Regulations Issue 8",
        notes="initial sample committed pre-G-4",
    )
    loaded, meta = load_chunks(p)
    assert len(loaded) == 2
    assert loaded[0].text == chunks[0].text
    assert loaded[0].embedding == [0.1, 0.2, 0.3]
    assert meta["g4_status"] == "pending"
    assert meta["n_chunks"] == 2
    assert meta["embedding_dimensions"] == 3


def test_save_chunks_records_empty_embedding_dim_when_none(tmp_path: Path):
    chunks = [_make_chunk("no embedding here", embedding=None)]
    p = tmp_path / "chunks.json"
    save_chunks(chunks, path=p)
    _, meta = load_chunks(p)
    assert meta["embedding_dimensions"] is None


def test_load_chunks_missing_file_returns_empty_with_status(tmp_path: Path):
    chunks, meta = load_chunks(tmp_path / "does-not-exist.json")
    assert chunks == []
    assert meta["g4_status"] == "missing"


def test_save_chunks_g4_status_closed_round_trips(tmp_path: Path):
    p = tmp_path / "chunks.json"
    save_chunks([], path=p, g4_status="closed")
    _, meta = load_chunks(p)
    assert meta["g4_status"] == "closed"


# ──────────────────────────────────────────────────────────────────────────────
# Live integration test — only runs with `pytest -m network`
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# extract_harvest_cap_mj
# ──────────────────────────────────────────────────────────────────────────────


def test_extract_harvest_cap_finds_canonical_phrasing():
    """C5.2.10's exact phrasing: 'must not exceed 8.5MJ in each lap'."""
    chunks = [
        _make_chunk(
            "C5.2.10 The energy harvested by the ERS-K, as measured at the CU-K HV "
            "DC Bus, must not exceed 8.5MJ in each lap, subject to the following...",
            section="C5.2.10",
        ),
    ]
    assert extract_harvest_cap_mj(chunks) == 8.5


def test_extract_harvest_cap_returns_max_when_multiple_candidates():
    """Same chunk lists 8.5 MJ default + 8 MJ + 5 MJ reductions —
    return the unconditional cap (the largest)."""
    chunks = [
        _make_chunk(
            "must not exceed 8.5MJ in each lap. "
            "Exceptionally, this limit may be reduced to 8MJ at Competitions where "
            "the FIA determines... may be further reduced to no less than 5MJ for "
            "Sprint Qualifying...",
            section="C5.2.10",
        ),
    ]
    assert extract_harvest_cap_mj(chunks) == 8.5


def test_extract_harvest_cap_handles_decimal_and_integer():
    chunks = [
        _make_chunk("must not exceed 8MJ in each lap", section="C5.2.10"),
    ]
    assert extract_harvest_cap_mj(chunks) == 8.0


def test_extract_harvest_cap_with_space_between_number_and_unit():
    chunks = [
        _make_chunk("must not exceed 8.5 MJ in each lap", section="C5.2.10"),
    ]
    assert extract_harvest_cap_mj(chunks) == 8.5


def test_extract_harvest_cap_returns_none_when_no_cap_found():
    chunks = [
        _make_chunk("C5.18 MGU-K. The MGU-K shall not exceed 350 kW.", section="C5.18"),
    ]
    assert extract_harvest_cap_mj(chunks) is None


def test_extract_harvest_cap_returns_none_for_empty_input():
    assert extract_harvest_cap_mj([]) is None


def test_extract_harvest_cap_ignores_unrelated_mj_values():
    """C5.2.3 says 'fuel energy flow must not exceed 3000MJ/h' — that's
    fuel/hour, not harvest/lap. Don't pick it up."""
    chunks = [
        _make_chunk(
            "C5.2.3 Fuel energy flow must not exceed 3000MJ/h. "
            "C5.2.4 Below 10500rpm the fuel energy flow must not exceed EF(MJ/h)=...",
            section="C5.2.3",
        ),
    ]
    # No "in each lap" qualifier on the 3000 MJ/h value → primary regex misses
    # → fallback regex requires "harvest" near MJ → also misses
    assert extract_harvest_cap_mj(chunks) is None


def test_extract_harvest_cap_fallback_pattern_for_loose_phrasing():
    """If the strict 'must not exceed' phrasing isn't there, fall back to
    'harvest ... <N> MJ ... per lap' form."""
    chunks = [
        _make_chunk(
            "Energy harvested by the ERS-K is limited to 8.5 MJ per lap.",
            section="C5.2.10",
        ),
    ]
    assert extract_harvest_cap_mj(chunks) == 8.5


@pytest.mark.network
def test_embed_chunks_live_watsonx_returns_768_dim():
    """Hit the real watsonx Granite Embedding model. Confirms the
    `models.json` claim of dim=768 still holds."""
    from dotenv import load_dotenv
    from core.regs import WatsonxAIEmbeddingClient

    load_dotenv()
    if not os.environ.get("WATSONX_API_KEY"):
        pytest.skip("WATSONX_API_KEY not set; skipping live embedding test")

    chunks = [
        _make_chunk("Energy released from the ES into the MGU-K shall not exceed the per-lap cap."),
        _make_chunk("Sporting Regulations govern Overtake Mode availability."),
    ]
    client = WatsonxAIEmbeddingClient()
    out = embed_chunks(chunks, client, batch_size=8)
    assert len(out) == 2
    for c in out:
        assert c.embedding is not None
        assert len(c.embedding) == 768
