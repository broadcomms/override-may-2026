"""scripts/build_chunks.py — generate data/regs/extracted_chunks.sample.json.

Runs Docling against a cached FIA regulations PDF, chunks the markdown,
embeds each chunk via watsonx Granite Embedding, and persists everything
(with a top-level `g4_status` flag) to the canonical JSON path.

Run once at build time. Per-query reads are O(load JSON), not O(re-embed).

Pre-G-4 invocation (the chunks ship with `g4_status: "pending"`):

    .venv/bin/python scripts/build_chunks.py

Post-G-4, when docs/regulation-source.md is final, regenerate against the
verified section and pass `--g4-status closed --section-filter "<section>"`
to slice the markdown to just the energy-management section before chunking.

Notes
-----
- Uses PyPdfium backend + OCR off + table-structure off — see
  docs/plans/p2.5-docling-kicker.md for the rationale (~27 s for the full
  207-page Issue 8 doc on a CPU laptop).
- The default PDF is the 2024-06-24 Issue 8 of the Technical Regulations,
  which is the only one we've cached without renaming pitfalls. Override
  with --pdf if you have a newer version locally.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger(__name__)

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--pdf",
        type=Path,
        default=ROOT
        / "data/regs/FIA-2026-F1-Regulations-Section-C-_Technical_-Iss-12-2025-06-10.pdf",
        help=(
            "Cached FIA PDF (gitignored). Default: Section C Issue 12 (2025-06-10) "
            "— the canonical document for energy-management citations per G-4 / "
            "docs/regulation-source.md."
        ),
    )
    p.add_argument(
        "--document-title",
        default="FIA 2026 Formula 1 Technical Regulations — Section C",
        help="document_title written into RegulationSource for every chunk",
    )
    p.add_argument(
        "--issue",
        default="Issue 12 — 2025-06-10",
        help="issue label written into RegulationSource",
    )
    p.add_argument(
        "--public-url",
        default="https://www.fia.com/regulation/category/110",
        help="public_url written into RegulationSource",
    )
    p.add_argument(
        "--page-range",
        default="1,300",
        help="comma-separated 1-indexed inclusive range, e.g. '1,50' for the first 50 pages",
    )
    p.add_argument(
        "--g4-status",
        choices=["pending", "closed"],
        default="pending",
        help="top-level metadata flag in the output JSON",
    )
    p.add_argument(
        "--section-filter",
        default=None,
        help='regex pattern (case-insensitive); when set, only Markdown ranges '
             'whose heading matches the pattern are kept. Example: "ARTICLE\\s+5"',
    )
    p.add_argument(
        "--no-embed",
        action="store_true",
        help="skip watsonx embedding (chunks ship with embedding=None — useful for local debug)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data/regs/extracted_chunks.sample.json",
        help="output JSON path",
    )
    args = p.parse_args(argv)

    if not args.pdf.exists():
        log.error("PDF not found: %s", args.pdf)
        log.error("Run scripts/download_regulations.py to fetch it.")
        return 1

    page_start, page_end = (int(x) for x in args.page_range.split(","))

    # ── 1. Docling extraction ────────────────────────────────────────────────
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = False
    opts.do_table_structure = False
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=opts,
                backend=PyPdfiumDocumentBackend,
            )
        }
    )

    log.info("Extracting %s (pages %d–%d) …", args.pdf.name, page_start, page_end)
    t0 = time.time()
    result = converter.convert(args.pdf, page_range=(page_start, page_end), raises_on_error=False)
    elapsed = time.time() - t0
    if result.status.name != "SUCCESS":
        log.error("Docling extraction failed: status=%s", result.status.name)
        for e in result.errors:
            log.error("  %s", e)
        return 1
    markdown = result.document.export_to_markdown()
    log.info("  Docling done in %.1fs — %d chars markdown", elapsed, len(markdown))

    # ── 2. Optional section filter ───────────────────────────────────────────
    if args.section_filter:
        pattern = re.compile(args.section_filter, re.IGNORECASE)
        # Slice markdown to ranges whose heading matches
        heading_re = re.compile(r"^\s*(#+)\s+(.+?)\s*$", re.MULTILINE)
        headings = list(heading_re.finditer(markdown))
        keep_ranges: list[tuple[int, int]] = []
        for i, h in enumerate(headings):
            if pattern.search(h.group(2)):
                start = h.start()
                end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
                keep_ranges.append((start, end))
        if not keep_ranges:
            log.error(
                "section-filter %r matched no headings; aborting (would produce empty chunks)",
                args.section_filter,
            )
            return 1
        markdown = "\n\n".join(markdown[s:e] for s, e in keep_ranges)
        log.info("  section filter kept %d ranges (%d chars)", len(keep_ranges), len(markdown))

    # ── 3. Chunk ─────────────────────────────────────────────────────────────
    from core.regs import chunk_markdown, embed_chunks, save_chunks
    from core.regs import WatsonxAIEmbeddingClient

    chunks = chunk_markdown(
        markdown,
        document_title=args.document_title,
        issue=args.issue,
        public_url=args.public_url,
        fetched_at=datetime.now(timezone.utc),
    )
    log.info("  %d chunks (mean %d chars)", len(chunks), int(sum(len(c.text) for c in chunks) / max(1, len(chunks))))

    if not chunks:
        log.error("zero chunks produced — markdown structure may be wrong; aborting")
        return 1

    # ── 4. Embed (unless --no-embed) ─────────────────────────────────────────
    if args.no_embed:
        log.info("  --no-embed: chunks shipped without embeddings")
    else:
        log.info("  Embedding %d chunks via watsonx (%s) …", len(chunks), os.environ.get("GRANITE_EMBEDDING", "default"))
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")

        if not os.environ.get("WATSONX_API_KEY"):
            log.error("WATSONX_API_KEY not set; pass --no-embed to skip embedding")
            return 1

        client = WatsonxAIEmbeddingClient()
        t0 = time.time()
        chunks = embed_chunks(chunks, client, batch_size=16)
        elapsed = time.time() - t0
        log.info("  Embeddings done in %.1fs (dim=%d)", elapsed, len(chunks[0].embedding or []))

    # ── 5. Persist ───────────────────────────────────────────────────────────
    notes = (
        f"page_range={page_start}-{page_end}; "
        f"section_filter={args.section_filter or '(none)'}; "
        f"docling=PyPdfium+no-ocr+no-tables"
    )
    save_chunks(
        chunks,
        path=args.out,
        g4_status=args.g4_status,
        source_document_label=f"{args.document_title} ({args.issue})",
        notes=notes,
    )
    log.info("✓ wrote %d chunks → %s (g4_status=%s)", len(chunks), args.out, args.g4_status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
