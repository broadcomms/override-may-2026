"""scripts/download_regulations.py — fetch the FIA 2026 regulations PDF locally.

PDFs are NOT committed (data/regs/*.pdf is gitignored). This script
formalizes the local download path so a clean machine can populate
data/regs/ before P2.5 (Docling extraction + gate G-4).

The exact document selected by G-4 is recorded in docs/regulation-source.md
post-verification. Until then this script ships two known-public candidates:

  - F1 2026 Technical Regulations (latest issue) — Power Unit chapter
  - F1 2026 Sporting Regulations

Both are public on fia.com/regulation/category/110. Newer issues replace
older ones; the script always fetches the index page first to discover
the latest URL rather than hardcoding a versioned link that rots.

Usage:
    .venv/bin/python scripts/download_regulations.py
    .venv/bin/python scripts/download_regulations.py --doc technical
    .venv/bin/python scripts/download_regulations.py --doc sporting

Per docs/04-schema.md §6 hard rule, no article numbers or section strings
are extracted here. Article identification happens at G-4 via Docling.
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


# Known FIA index pages. The actual PDF URL is parsed out of these at runtime
# rather than hardcoded — FIA posts new issues mid-season (per .bob/AGENTS.md
# strategic anchor: "FIA tweaked Albert Park harvest limits mid-2026").
INDEX_URLS = {
    "technical": "https://www.fia.com/regulation/category/110",
    "sporting": "https://www.fia.com/regulation/category/110",
}

REGS_DIR = Path(__file__).resolve().parent.parent / "data" / "regs"


def fetch_pdf(url: str, dest: Path) -> Path:
    """Download `url` to `dest`. Streams to disk to avoid memory spikes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("downloading %s → %s", url, dest)
    with urllib.request.urlopen(url, timeout=60) as resp:
        if resp.status != 200:
            raise RuntimeError(f"GET {url} returned status {resp.status}")
        with dest.open("wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
    return dest


def discover_pdf_url(doc: Literal["technical", "sporting"]) -> str:
    """Resolve the latest issue PDF URL from the FIA regulation index.

    Best-effort HTML scrape — FIA's site is reasonably stable but not an
    API. If parsing fails, the user can pass --pdf-url directly to skip
    discovery.
    """
    import re

    index = INDEX_URLS[doc]
    logger.info("fetching FIA index %s …", index)
    with urllib.request.urlopen(index, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    # Match links to PDFs whose filename mentions "technical" or "sporting"
    # plus "2026" plus ".pdf".
    pattern = re.compile(
        rf'href="([^"]+\.pdf)"[^>]*>[^<]*?{doc}[^<]*?2026',
        re.IGNORECASE,
    )
    matches = pattern.findall(html)
    if not matches:
        # Fallback: any 2026 PDF on the page
        pattern = re.compile(r'href="([^"]+2026[^"]+\.pdf)"', re.IGNORECASE)
        matches = pattern.findall(html)
    if not matches:
        raise RuntimeError(
            f"could not find a 2026 {doc} regulations PDF link on {index}. "
            "Pass --pdf-url directly or refresh this scraper."
        )
    href = matches[0]
    if href.startswith("/"):
        href = "https://www.fia.com" + href
    return href


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--doc",
        choices=["technical", "sporting"],
        default="technical",
        help="which 2026 regulations document to fetch (default: technical)",
    )
    p.add_argument(
        "--pdf-url",
        help="skip discovery; fetch this URL directly (useful when the FIA index changes)",
    )
    p.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="destination path (default: data/regs/<doc>-2026-<basename>)",
    )
    args = p.parse_args(argv)

    url = args.pdf_url or discover_pdf_url(args.doc)
    if args.dest is None:
        # Use the URL's basename so we keep the FIA's issue identifier.
        basename = url.rsplit("/", 1)[-1]
        dest = REGS_DIR / basename
    else:
        dest = args.dest

    if dest.exists() and dest.stat().st_size > 0:
        logger.info("already present: %s (%d bytes) — skipping", dest, dest.stat().st_size)
        return 0

    fetch_pdf(url, dest)
    size = dest.stat().st_size
    logger.info("✓ saved %s (%d bytes)", dest, size)
    if size < 100_000:
        logger.warning(
            "PDF is suspiciously small (%d bytes) — verify the discovery picked "
            "the right link. Consider passing --pdf-url manually.",
            size,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
