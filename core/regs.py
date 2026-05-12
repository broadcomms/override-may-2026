"""Docling regulation grounding — chunker + watsonx embedder + retrieval.

Pipeline (P2.5):

    PDF (cached locally, gitignored)
      → Docling extract (markdown)        chunk_markdown()
      → list[RegulationChunk]             embed_chunks() once at build time
      → JSON on disk                      save_chunks()
      → boot loads them                   load_chunks()
      → per-query                         retrieve_chunk()

Retrieval combines two signals (per roadmap P2.5 — "keyword and embedding-
based retrieval over extracted chunks"):

    score = 0.6 × cosine(query_embedding, chunk_embedding)
          + 0.4 × keyword_overlap(zone_type, chunk_text)

The grounding contract in `prompts/grounding.system.md` describes an
LLM-driven retriever as a fallback. This module is the **primary
deterministic path** — no LLM in the retrieval loop.

G-4 status — IMPORTANT: until the verification gate `G-4` closes (see
`docs/06-roadmap.md` §4 P2.5), the section choice that grounds these
chunks is *pending*. Persisted chunk files carry a top-level
`g4_status: "pending"` field and the loader exposes that status to
callers so the API can surface a banner ("Regulation grounding
unavailable — citations will be generic until verification completes").
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

import numpy as np

from ingest.schema import RegulationChunk, RegulationSource, ZoneType

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Embedding client abstraction (mirrors core.reasoning.WatsonxChatClient)
# ──────────────────────────────────────────────────────────────────────────────


class WatsonxEmbeddingClient(Protocol):
    """Minimal interface for embedding text into 768-dim vectors.

    Production: `WatsonxAIEmbeddingClient` (below). Tests: a fake that
    returns canned vectors for deterministic offline testing.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class WatsonxAIEmbeddingClient:
    """Real watsonx.ai embedding client for `ibm/granite-embedding-278m-multilingual`.

    768-dimensional output (see `models.json` and ADR-001 for the
    decision rationale + verification timestamp). Reads credentials
    from .env.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        self.model_id = model_id or os.environ.get(
            "GRANITE_EMBEDDING", "ibm/granite-embedding-278m-multilingual"
        )
        self.api_key = api_key or os.environ.get("WATSONX_API_KEY")
        self.url = url or os.environ.get("WATSONX_URL")
        self.project_id = project_id or os.environ.get("WATSONX_PROJECT_ID")

        if not all([self.api_key, self.url, self.project_id]):
            raise RuntimeError(
                "WatsonxAIEmbeddingClient: missing one of WATSONX_API_KEY / "
                "WATSONX_URL / WATSONX_PROJECT_ID — see .env.example."
            )

        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import Embeddings

        self._embedder = Embeddings(
            model_id=self.model_id,
            credentials=Credentials(api_key=self.api_key, url=self.url),
            project_id=self.project_id,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embedder.embed_documents(texts=texts)


# ──────────────────────────────────────────────────────────────────────────────
# Markdown chunker — Docling output → list[RegulationChunk]
# ──────────────────────────────────────────────────────────────────────────────


CHUNK_MAX_CHARS = 1000  # mirrors RegulationChunk.text constraint in schema §6
CHUNK_MIN_CHARS = 80    # below this, skip — too small to be useful

# Match heading lines: any leading "##" / "###" (Docling markdown).
_HEADING_RE = re.compile(r"^\s*(#+)\s+(.+?)\s*$", re.MULTILINE)
# Splits on blank lines (paragraph boundaries).
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
# Naive sentence splitter — sufficient for English regulation text.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
# Article markers — accepts "ARTICLE 5:", "ARTICLE C5:", and the FIA's
# Section-letter convention (e.g. C5, F1.2). Also tolerates whitespace
# Docling occasionally introduces around the dot separator.
_ARTICLE_RE = re.compile(
    r"\bARTICLE\s+([A-Z]?\d+(?:\s*\.\s*\d+)*)", re.IGNORECASE
)
# Section-code at the start of a heading: matches "5.1", "C5.18", "C5.2.14",
# tolerating "C5 . 18" variants from Docling.
_SECTION_CODE_RE = re.compile(r"^\s*([A-Z]?\d+(?:\s*\.\s*\d+){0,3})\b")


def _normalize_code(code: str) -> str:
    """Strip the whitespace Docling occasionally inserts around dots."""
    return re.sub(r"\s+", "", code)


# Subsection code in the body — pulls labels like "C5.18" out of bullets
# even when the chunk's nearest heading is a high-level document title
# (e.g. "## SECTION C: TECHNICAL REGULATIONS"). Anchored at line start
# OR after a list marker so we catch lines like "- C5.18.1 The MGU-K shall…".
_BODY_SECTION_CODE_RE = re.compile(
    r"(?:^|\n)\s*(?:[-*]\s+)?([A-Z]?\d+(?:\s*\.\s*\d+){1,3})\b",
    re.MULTILINE,
)


def _section_label(heading_text: str, body: str) -> str:
    """Extract a human-readable section label from a heading + nearby body.

    Per `04-schema.md §6` HARD RULE, this is **not** a hardcoded literal
    — it is read out of the Docling-extracted text at runtime. The
    returned string is what populates `RegulationSource.section`.

    Resolution order — prefer specific subsection codes from THIS chunk's
    text over heading-level fallbacks. Notably, ARTICLE patterns in body
    text are NOT used because they're usually cross-references ("subject
    to Article B7.2") rather than the chunk's own section.

      1. Section code at heading start (e.g. "## C5.18 MGU-K" → "C5.18")
      2. ARTICLE pattern in heading (e.g. "ARTICLE C5" → "Article C5")
      3. Subsection code in body's first ~400 chars (e.g. "- C5.18.1 …" → "C5.18.1")
         — this catches sub-articles under a too-generic heading like
         "## SECTION C: TECHNICAL REGULATIONS"
      4. Heading text itself (truncated, last resort)
    """
    # 1. heading section code wins
    m = _SECTION_CODE_RE.match(heading_text)
    if m:
        return _normalize_code(m.group(1))
    # 2. ARTICLE in heading (e.g. "ARTICLE C5: POWER UNIT")
    m = _ARTICLE_RE.search(heading_text)
    if m:
        return f"Article {_normalize_code(m.group(1))}"
    # 3. Subsection code in body — only multi-part codes (with at least
    #    one ".") qualify, so bullets like "- 1." don't pass.
    m = _BODY_SECTION_CODE_RE.search(body[:400])
    if m:
        return _normalize_code(m.group(1))
    # 4. Last resort — heading text
    return heading_text.strip()[:80] or "<unlabelled>"


def _split_long_paragraph(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """Split an over-long paragraph at sentence boundaries.

    If a single sentence exceeds max_chars, falls back to character
    truncation with a clear elision marker.
    """
    if len(text) <= max_chars:
        return [text]
    sentences = _SENTENCE_RE.split(text)
    out: list[str] = []
    buf = ""
    for s in sentences:
        if not s.strip():
            continue
        candidate = (buf + " " + s).strip() if buf else s.strip()
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                out.append(buf)
            if len(s) > max_chars:
                out.append(s[: max_chars - 3].rstrip() + "...")
                buf = ""
            else:
                buf = s.strip()
    if buf:
        out.append(buf)
    return out


def chunk_markdown(
    markdown: str,
    *,
    document_title: str,
    issue: str,
    public_url: str,
    fetched_at: Optional[datetime] = None,
    chunk_id_prefix: str = "c",
) -> list[RegulationChunk]:
    """Split a Docling-extracted markdown document into RegulationChunks.

    Strategy:
      1. Walk the heading hierarchy — each heading + its prose body
         becomes a candidate chunk, with the section label derived from
         the heading text.
      2. Drop tiny chunks (< CHUNK_MIN_CHARS) — usually empty stubs or
         single-line headings with no body.
      3. Split over-long chunks (> CHUNK_MAX_CHARS) at sentence
         boundaries (per §6 max-len constraint).
    """
    if not markdown.strip():
        return []
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc)

    # Find heading positions with their hierarchy level.
    headings = [
        (m.start(), m.end(), len(m.group(1)), m.group(2))
        for m in _HEADING_RE.finditer(markdown)
    ]
    if not headings:
        # No headings — treat whole doc as one section.
        headings = [(0, 0, 1, "(document)")]

    chunks: list[RegulationChunk] = []
    keyword_pool = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")

    for i, (start, end, level, heading) in enumerate(headings):
        body_start = end
        body_end = headings[i + 1][0] if i + 1 < len(headings) else len(markdown)
        body = markdown[body_start:body_end].strip()
        if not body:
            continue

        # Per-section default — used for chunks whose own text doesn't
        # contain a more specific subsection code AND no prior chunk in
        # this block has supplied one. We pass empty body here so this
        # is heading-only logic; per-chunk lookup happens below at flush
        # time.
        heading_section = _section_label(heading, "")

        # Carries the last-seen specific subsection code forward across
        # continuation chunks. When a chunk has no own subsection code,
        # it inherits this — so a chunk whose body continues a sub-article
        # from the previous chunk gets that sub-article's label rather
        # than the giant heading-block label.
        last_specific: Optional[str] = None

        def _make_source_for_chunk(chunk_text: str) -> RegulationSource:
            """Per-chunk section label — prefers a subsection code visible
            in this chunk's own text, then the most-recent code seen in
            this block, then the heading's generic label."""
            nonlocal last_specific
            chunk_section = _section_label(heading, chunk_text)
            if chunk_section != heading_section:
                last_specific = chunk_section
                section = chunk_section
            elif last_specific is not None:
                section = last_specific
            else:
                section = heading_section
            return RegulationSource(
                document_title=document_title,
                issue=issue,
                section=section,
                public_url=public_url,
                fetched_at=fetched_at,
            )

        # Heading + body together — the heading is informative context.
        combined = f"{heading}\n\n{body}".strip()
        # Split on paragraph breaks first, then merge runs into ≤ max-char buckets.
        paragraphs = [p.strip() for p in _PARAGRAPH_RE.split(combined) if p.strip()]
        buf = ""
        sub_idx = 0
        for p in paragraphs:
            for fragment in _split_long_paragraph(p):
                candidate = (buf + "\n\n" + fragment).strip() if buf else fragment
                if len(candidate) <= CHUNK_MAX_CHARS:
                    buf = candidate
                    continue
                # Flush buf if substantial.
                if len(buf) >= CHUNK_MIN_CHARS:
                    sub_idx += 1
                    chunks.append(
                        _make_chunk(
                            buf,
                            _make_source_for_chunk(buf),
                            chunk_id=f"{chunk_id_prefix}_{i:03d}_{sub_idx:02d}",
                            keyword_pool=keyword_pool,
                        )
                    )
                buf = fragment
        if buf and len(buf) >= CHUNK_MIN_CHARS:
            sub_idx += 1
            chunks.append(
                _make_chunk(
                    buf,
                    _make_source_for_chunk(buf),
                    chunk_id=f"{chunk_id_prefix}_{i:03d}_{sub_idx:02d}",
                    keyword_pool=keyword_pool,
                )
            )

    return chunks


# Common English starters that show up capitalized at sentence start but
# carry no domain signal. Filter from the auto-extracted keyword list.
_KEYWORD_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "and", "or", "but", "for", "to", "by", "in", "on", "at", "with",
        "from", "of", "this", "that", "these", "those", "it", "its",
        "as", "shall", "may", "must", "will", "would", "could", "can",
        "all", "any", "each", "every", "such", "no", "not", "if", "when",
        "where", "while", "during", "after", "before", "above", "below",
    }
)


def _make_chunk(
    text: str,
    source: RegulationSource,
    *,
    chunk_id: str,
    keyword_pool: re.Pattern,
) -> RegulationChunk:
    # Top ~12 capitalized / domain-looking tokens as lightweight keywords.
    candidates = [
        t
        for t in keyword_pool.findall(text)
        if not t.islower() and t.lower() not in _KEYWORD_STOPWORDS
    ]
    seen: set[str] = set()
    keywords: list[str] = []
    for t in candidates:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        keywords.append(t)
        if len(keywords) >= 12:
            break
    return RegulationChunk(
        chunk_id=chunk_id,
        text=text[:CHUNK_MAX_CHARS],
        source=source,
        keywords=keywords,
        embedding=None,  # populated by embed_chunks()
    )


# ──────────────────────────────────────────────────────────────────────────────
# Embedding chunks (build-time, batched)
# ──────────────────────────────────────────────────────────────────────────────


def embed_chunks(
    chunks: list[RegulationChunk],
    client: WatsonxEmbeddingClient,
    *,
    batch_size: int = 16,
) -> list[RegulationChunk]:
    """Populate `embedding` on each chunk. Returns NEW chunks (frozen pydantic).

    Run ONCE at build time, persisted via save_chunks(). Boot-time loader
    reads them with embeddings already populated. Per-query, only the
    zone-type query is embedded fresh (see retrieve_chunk).
    """
    if not chunks:
        return []
    out: list[RegulationChunk] = []
    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        texts = [c.text for c in batch]
        vecs = client.embed(texts)
        if len(vecs) != len(batch):
            raise RuntimeError(
                f"embed_chunks: client returned {len(vecs)} vectors for "
                f"{len(batch)} inputs"
            )
        for c, v in zip(batch, vecs):
            out.append(c.model_copy(update={"embedding": list(v)}))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Retrieval — keyword + embedding cosine, combined
# ──────────────────────────────────────────────────────────────────────────────


# Domain keyword sets per zone type. Retrieval hints, not citations —
# the regulation citation rendering stays dynamic per the §6 hard rule.
_ZONE_KEYWORDS: dict[ZoneType, list[str]] = {
    ZoneType.LOW_ROI_DEPLOY: [
        "MGU-K", "deploy", "deployment", "ES", "energy release",
        "kinetic energy", "release",
    ],
    ZoneType.LATE_RECHARGE: [
        "MGU-K", "harvest", "recover", "recovery", "regenerative",
        "braking", "ES", "recharge",
    ],
    ZoneType.OVER_HARVEST: [
        "harvest", "recovery", "limit", "cap", "exceed", "per lap",
        "MJ", "ES", "energy store",
    ],
    ZoneType.UNUSED_OVERRIDE: [
        "override", "overtake", "manual override", "boost",
        "second", "MGU-K", "deploy",
    ],
}


def _query_string_for_zone(zone_type: ZoneType) -> str:
    """The query text we embed for a given zone type.

    Combines the zone label and its keyword hints into a single short
    sentence that the embedding model can ground against the regulation
    chunks.
    """
    keywords = " ".join(_ZONE_KEYWORDS.get(zone_type, []))
    return f"2026 F1 energy management regulation: {zone_type.value}. {keywords}"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _keyword_overlap(zone_type: ZoneType, chunk_text: str) -> float:
    """Fraction of the zone's keywords that appear (case-insensitive) in
    the chunk text. Returns a value in [0, 1].

    Token-aware for single-word keywords (avoids false positives like
    'ES' matching inside 'design'); substring match for multi-word
    keywords (cheap-but-correct for the small zone vocabularies).
    """
    keywords = _ZONE_KEYWORDS.get(zone_type, [])
    if not keywords:
        return 0.0
    lower = chunk_text.lower()
    tokens = set(re.findall(r"[a-z][a-z0-9-]*", lower))
    hits = 0
    for k in keywords:
        kl = k.lower()
        if " " in kl:
            # multi-word phrase — substring is fine
            if kl in lower:
                hits += 1
        else:
            # single token — must match a whole token, not a substring
            if kl in tokens:
                hits += 1
    return hits / len(keywords)


COSINE_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4
DEFAULT_RELEVANCE_THRESHOLD = 0.4

# Front-matter / TOC chunks inherit the document-title section label
# ("SECTION C: TECHNICAL REGULATIONS") because the chunker can't find a
# more specific sub-article code in their body (cover page, table-of-
# contents rows starting with "|", abbreviations table). They still get
# embeddings, and they still appear in the corpus, but they must NOT
# compete in retrieval — they're metadata, not regulatory clauses.
#
# Matches: "SECTION C: TECHNICAL REGULATIONS", "Section A: REGULATIONS".
# Doesn't match: "C5.18", "Article C5", "APPENDIX C5: HOMOLOGATION".
# Test fixtures (custom labels like "Test Section") are unaffected.
_FRONT_MATTER_SECTION_RE = re.compile(
    r"^\s*SECTION\b.*\bREGULATIONS?\b",
    re.IGNORECASE,
)


def is_front_matter_section(section: str) -> bool:
    """True if `section` is the document-title label inherited by cover
    page / TOC / abbreviations chunks (e.g. "SECTION C: TECHNICAL
    REGULATIONS"), false for specific sub-article labels (e.g. "C5.18",
    "Article C5", "APPENDIX C5: ...").

    Used by both `retrieve_chunk` (excludes front-matter from per-zone
    citation candidates) and the session-level `regulation_source`
    selection in `core.pipeline` (picks the first non-front-matter chunk
    as the canonical document pointer, rather than `chunks[0]` which is
    almost always the cover page).
    """
    return bool(_FRONT_MATTER_SECTION_RE.match(section))


# Matches the leading article-level prefix of a section label:
#   "C5.18"          → "C5"
#   "C5.2.14"        → "C5"
#   "C5"             → "C5"
#   "Article C5"     → "C5"     (via the inner group)
#   "APPENDIX C5: …" → "C5"
#   "5.1"            → "5"
# Used to find the modal article scope of a corpus dynamically — the
# session-level `regulation_source.section` then points at the article
# the corpus is *predominantly* grounded against, not the first
# specific-but-incidental chunk that slipped past the build-time filter.
_ARTICLE_PREFIX_RE = re.compile(
    r"(?:Article\s+|APPENDIX\s+)?([A-Z]?\d+)\b",
    re.IGNORECASE,
)


def _article_prefix(section: str) -> Optional[str]:
    """Extract the leading article-level code from a section label, or None.
    "C5.18" → "C5"; "Article C5" → "C5"; "APPENDIX C5: …" → "C5";
    "5.1" → "5"; "SECTION C: …" → None (caught by is_front_matter_section
    upstream); arbitrary test labels → None.
    """
    m = _ARTICLE_PREFIX_RE.search(section)
    return m.group(1).upper() if m else None


def primary_article_scope(chunks: list[RegulationChunk]) -> Optional[str]:
    """Return the most common article-level prefix across non-front-matter
    chunks (e.g. "C5" for a corpus built with --section-filter '\\bC5\\b').

    Derived dynamically from the chunks themselves — per the HARD RULE
    in `ingest/schema.py` `RegulationSource`, no article number is ever
    hardcoded in code. When the FIA publishes a different article scope
    in a future Issue, the modal prefix shifts automatically without a
    code change.

    Returns None when no chunk has a parseable article prefix (e.g. all
    chunks are front-matter, or the corpus is empty).
    """
    if not chunks:
        return None
    counter: Counter[str] = Counter()
    for c in chunks:
        if is_front_matter_section(c.source.section):
            continue
        prefix = _article_prefix(c.source.section)
        if prefix:
            counter[prefix] += 1
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def section_matches_scope(section: str, scope: str) -> bool:
    """True if `section`'s leading article-level prefix equals `scope`
    (both case-insensitive). Used to filter chunks down to those that
    sit within the corpus's primary article scope.
    """
    p = _article_prefix(section)
    return p is not None and p == scope.upper()


def retrieve_chunk(
    zone_type: ZoneType,
    chunks: list[RegulationChunk],
    client: WatsonxEmbeddingClient,
    *,
    threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
) -> Optional[tuple[RegulationChunk, float]]:
    """Return the highest-scoring chunk for a zone type, or None if no
    chunk meets the threshold.

    Scoring: 0.6 × cosine(query, chunk) + 0.4 × keyword_overlap(zone, chunk).
    Front-matter / TOC chunks (whose section label matches the document
    title rather than a specific sub-article) are excluded from scoring —
    they're metadata, not regulatory clauses.

    Per FR-4.3: when no chunk passes the threshold, return None and the
    reasoning step receives `regulation=None`, which forces the prompt's
    pre-G-4-style pathway (citation=null, confidence=low).
    """
    from api.observability import traced_span

    if not chunks:
        return None

    with traced_span(
        "regs.retrieve_chunk",
        zone_type=zone_type.value,
        n_chunks=len(chunks),
        threshold=threshold,
    ) as span:
        query = _query_string_for_zone(zone_type)
        query_vec = np.asarray(client.embed([query])[0], dtype=np.float64)

        best: Optional[tuple[RegulationChunk, float]] = None
        for chunk in chunks:
            if is_front_matter_section(chunk.source.section):
                continue
            cos = 0.0
            if chunk.embedding is not None:
                cos = _cosine(query_vec, np.asarray(chunk.embedding, dtype=np.float64))
            kw = _keyword_overlap(zone_type, chunk.text)
            score = COSINE_WEIGHT * cos + KEYWORD_WEIGHT * kw
            if best is None or score > best[1]:
                best = (chunk, score)

        if best is None or best[1] < threshold:
            if span is not None:
                span.set_attribute("override.match", False)
            return None
        if span is not None:
            span.set_attribute("override.match", True)
            span.set_attribute("override.cited_section", best[0].source.section)
            span.set_attribute("override.score", round(best[1], 4))
        return best


# ──────────────────────────────────────────────────────────────────────────────
# Persistence — load/save chunk JSON
# ──────────────────────────────────────────────────────────────────────────────


DEFAULT_CHUNKS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "regs" / "extracted_chunks.sample.json"
)


# ──────────────────────────────────────────────────────────────────────────────
# Regulation-text parsing — extract the per-lap harvest cap
# ──────────────────────────────────────────────────────────────────────────────

# Match a numeric MJ value near a per-lap cap clause. Issue 12 wording:
#   "energy harvested by the ERS-K, ... must not exceed 8.5MJ in each lap"
# Issue 18 wording:
#   "C5.2.10 Recharge, as measured at the CU-K HV DC Bus, must not exceed a
#    limit of 8.5MJ in each lap"
# The regex tolerates "exceed (a limit of)? <N> MJ (in )?each lap".
_HARVEST_CAP_PRIMARY_RE = re.compile(
    r"must\s+not\s+exceed\s+(?:a\s+limit\s+of\s+)?(\d+(?:\.\d+)?)\s*MJ\s+(?:in\s+)?each\s+lap",
    re.IGNORECASE,
)
# Fallback: looser harvest/recharge near MJ near per-lap.
_HARVEST_CAP_FALLBACK_RE = re.compile(
    r"(?:harvest|recharge|recover)[^.]{0,200}?(\d+(?:\.\d+)?)\s*MJ[^.]{0,80}?(each\s+lap|per\s+lap)",
    re.IGNORECASE,
)


def extract_harvest_cap_mj(chunks: list[RegulationChunk]) -> Optional[float]:
    """Find the verified per-lap ERS-K harvest cap from the regulation chunks.

    Looks first for the strict pattern "must not exceed <N> MJ in each lap"
    (the C5.2.10 phrasing as of Issue 12). Falls back to a softer
    harvest-near-MJ-per-lap pattern. Returns the largest cap value found
    (the default per-Article-C5.2.10 race cap is the upper bound; FIA
    refinements are written as conditional reductions).

    Returns None when no cap can be parsed — the caller passes
    `cap_mj=None` to the validator, which keeps `harvest_cap` as a NOOP.
    """
    if not chunks:
        return None
    candidates: list[float] = []
    for chunk in chunks:
        text = chunk.text
        for m in _HARVEST_CAP_PRIMARY_RE.finditer(text):
            try:
                candidates.append(float(m.group(1)))
            except ValueError:
                continue
        if not candidates:
            for m in _HARVEST_CAP_FALLBACK_RE.finditer(text):
                try:
                    candidates.append(float(m.group(1)))
                except ValueError:
                    continue
    if not candidates:
        return None
    # Use the maximum — the primary cap is the upper bound; conditional
    # reductions (8.0, 5.0) appear in the same chunk but are explicitly
    # introduced as "may be reduced to..." — the unconditional cap is the
    # one we want for the validator's normal-race default.
    return max(candidates)


def save_chunks(
    chunks: list[RegulationChunk],
    path: Path = DEFAULT_CHUNKS_PATH,
    *,
    g4_status: str = "pending",
    source_document_label: Optional[str] = None,
    notes: Optional[str] = None,
) -> Path:
    """Persist chunks to disk as JSON with a top-level metadata block.

    `g4_status` is "pending" or "closed". Pre-G-4 commits ship as
    "pending" — see the module docstring + ADR-001.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "g4_status": g4_status,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "source_document_label": source_document_label,
        "notes": notes,
        "n_chunks": len(chunks),
        "embedding_dimensions": (
            len(chunks[0].embedding) if chunks and chunks[0].embedding else None
        ),
        "chunks": [c.model_dump(mode="json") for c in chunks],
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    logger.info("save_chunks: wrote %d chunks → %s (g4_status=%s)", len(chunks), path, g4_status)
    return path


def load_chunks(
    path: Path = DEFAULT_CHUNKS_PATH,
) -> tuple[list[RegulationChunk], dict[str, Any]]:
    """Load chunks + the top-level metadata block.

    Returns `(chunks, metadata)`. The API uses `metadata["g4_status"]`
    to decide whether to surface the "regulation grounding unavailable"
    banner (per `04-ui-ux-design.md §7`).
    """
    if not path.exists():
        return [], {"g4_status": "missing", "n_chunks": 0}
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    chunks = [RegulationChunk.model_validate(c) for c in payload.get("chunks", [])]
    metadata = {k: v for k, v in payload.items() if k != "chunks"}
    return chunks, metadata


__all__ = [
    "WatsonxEmbeddingClient",
    "WatsonxAIEmbeddingClient",
    "CHUNK_MAX_CHARS",
    "CHUNK_MIN_CHARS",
    "COSINE_WEIGHT",
    "KEYWORD_WEIGHT",
    "DEFAULT_RELEVANCE_THRESHOLD",
    "DEFAULT_CHUNKS_PATH",
    "chunk_markdown",
    "embed_chunks",
    "retrieve_chunk",
    "save_chunks",
    "load_chunks",
    "extract_harvest_cap_mj",
]
