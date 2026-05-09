"""Build OVERRIDE logo asset suite.

Concept:
    Icon — a circular telemetry ring (slate) with a 120° amber sector
           highlighted (the 'override zone'). Two visual elements; reads at 16px.
    Wordmark — OVERRIDE in IBM Plex Mono Bold, letterforms outlined to paths.
    Lockup — icon + wordmark, used as the primary `logo` deliverable.

All glyphs are converted to SVG <path> data so the deliverables are
font-independent (no @font-face needed at render time).
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
import cairosvg

# ---------- palette ----------
SLATE_DARK = "#0F172A"   # primary dark — instrument panel
SLATE_LIGHT = "#F8FAFC"  # primary light — clean canvas
AMBER = "#F59E0B"        # signal accent — matches existing UI energy curve
NEUTRAL_RING = "#1E293B" # subtle ring on dark
NEUTRAL_RING_LIGHT = "#CBD5E1"  # subtle ring on light
BLACK = "#000000"
WHITE = "#FFFFFF"

# ---------- font ----------
FONT_PATH = "/tmp/override-fonts/IBMPlexMono-Bold.ttf"
WORD = "OVERRIDE"

font = TTFont(FONT_PATH)
glyph_set = font.getGlyphSet()
cmap = font.getBestCmap()
hmtx = font["hmtx"]
upem = font["head"].unitsPerEm  # 1000 for Plex Mono


def glyph_path(char: str) -> tuple[str, int]:
    """Return (svg_path_d, advance_width_in_font_units) for a single char."""
    glyph_name = cmap[ord(char)]
    glyph = glyph_set[glyph_name]
    pen = SVGPathPen(glyph_set)
    glyph.draw(pen)
    advance, _lsb = hmtx[glyph_name]
    return pen.getCommands(), advance


def render_word(
    text: str,
    font_size: float,
    x: float,
    y_baseline: float,
    fill: str,
) -> tuple[str, float]:
    """Render text as an SVG <g> of <path>s.

    Returns (svg_string, total_advance_px).
    Coordinate convention: SVG y-down. Plex Mono glyphs are y-up in font
    coordinates, so each glyph is wrapped in a transform that flips y and
    scales to the requested font_size.
    """
    scale = font_size / upem
    parts = [f'<g fill="{fill}" stroke="none">']
    cursor = x
    for ch in text:
        d, advance = glyph_path(ch)
        # transform: translate to (cursor, baseline), flip y, scale to font size
        parts.append(
            f'<path d="{d}" '
            f'transform="translate({cursor:.3f} {y_baseline:.3f}) '
            f'scale({scale:.6f} -{scale:.6f})"/>'
        )
        cursor += advance * scale
    parts.append("</g>")
    total_advance = cursor - x
    return "\n".join(parts), total_advance


# ---------- icon geometry ----------
# Two visual elements: outer slate ring + amber sector arc (120°, top→4 o'clock).
# Icon canvas 1024×1024. Ring radius 380. Stroke widths chosen for legibility
# at 16px while still feeling restrained at 1024px.

ICON_SIZE = 1024
ICON_CX = ICON_SIZE / 2
ICON_CY = ICON_SIZE / 2
RING_RADIUS = 380
RING_STROKE = 56          # thin neutral ring
SECTOR_STROKE = 80        # bold accent sector — visibly heavier than the ring
SECTOR_DEGREES = 120      # one F1 sector (≈1/3 of a lap)
SECTOR_START_COMPASS = 0  # 12 o'clock = 0° in compass terms
# Sector uses butt caps so the boundary reads as a clean step/tab in mono too.
SECTOR_LINECAP = "butt"

# anchor mark — small filled dot at the start of the sector (12 o'clock).
# Useful as a "start marker" in two-colour variants; suppressed in mono so the
# step-width difference between ring and sector carries the meaning instead.
ANCHOR_RADIUS = 32


def compass_to_xy(degrees: float, r: float) -> tuple[float, float]:
    """Compass degrees (0=top, clockwise) → SVG x,y coords."""
    rad = math.radians(degrees - 90)  # 0° compass = -90° math (top)
    return ICON_CX + r * math.cos(rad), ICON_CY + r * math.sin(rad)


def sector_arc_path() -> str:
    start_deg = SECTOR_START_COMPASS
    end_deg = SECTOR_START_COMPASS + SECTOR_DEGREES
    sx, sy = compass_to_xy(start_deg, RING_RADIUS)
    ex, ey = compass_to_xy(end_deg, RING_RADIUS)
    large_arc = 1 if SECTOR_DEGREES > 180 else 0
    return f"M {sx:.3f} {sy:.3f} A {RING_RADIUS} {RING_RADIUS} 0 {large_arc} 1 {ex:.3f} {ey:.3f}"


def icon_svg(
    ring_color: str,
    sector_color: str,
    anchor_color: str,
    bg: str | None = None,
    show_anchor: bool = True,
) -> str:
    bg_rect = f'<rect width="{ICON_SIZE}" height="{ICON_SIZE}" fill="{bg}"/>' if bg else ""
    anchor_x, anchor_y = compass_to_xy(SECTOR_START_COMPASS, RING_RADIUS)
    anchor = (
        f'<circle cx="{anchor_x:.3f}" cy="{anchor_y:.3f}" r="{ANCHOR_RADIUS}" fill="{anchor_color}"/>'
        if show_anchor
        else ""
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ICON_SIZE} {ICON_SIZE}" width="{ICON_SIZE}" height="{ICON_SIZE}">
{bg_rect}
<circle cx="{ICON_CX}" cy="{ICON_CY}" r="{RING_RADIUS}" fill="none" stroke="{ring_color}" stroke-width="{RING_STROKE}"/>
<path d="{sector_arc_path()}" fill="none" stroke="{sector_color}" stroke-width="{SECTOR_STROKE}" stroke-linecap="butt"/>
{anchor}
</svg>'''


# ---------- wordmark + lockup geometry ----------
# Canvas 2400×800. Within that:
#   - Icon block: 560 px tall, left side, vertically centered.
#   - Wordmark: Plex Mono Bold at font-size that fits the remaining width.
#   - Tagline (optional): mono caption below wordmark — kept off the primary
#     for cleanliness; available as a separate variant if asked.

LOCKUP_W = 2400
LOCKUP_H = 800

LOCKUP_PAD_L = 100
LOCKUP_PAD_R = 110
LOCKUP_GAP = 96
LOCKUP_ICON_SIZE = 480

LOCKUP_ICON_X = LOCKUP_PAD_L
LOCKUP_ICON_Y = (LOCKUP_H - LOCKUP_ICON_SIZE) / 2

LOCKUP_TEXT_X = LOCKUP_ICON_X + LOCKUP_ICON_SIZE + LOCKUP_GAP


def measure_word(text: str, font_size: float) -> float:
    scale = font_size / upem
    total = 0.0
    for ch in text:
        advance, _lsb = hmtx[cmap[ord(ch)]]
        total += advance * scale
    return total


# Solve font size so OVERRIDE fills the available width with right padding intact.
def fit_font_size(text: str, target_width: float) -> float:
    advance_units = sum(hmtx[cmap[ord(c)]][0] for c in text)
    return target_width * upem / advance_units


_avail_text_w = LOCKUP_W - LOCKUP_TEXT_X - LOCKUP_PAD_R
WORD_FONT_SIZE = round(fit_font_size(WORD, _avail_text_w))
WORD_WIDTH = measure_word(WORD, WORD_FONT_SIZE)
print(f"[layout] avail_w={_avail_text_w:.0f}  font_size={WORD_FONT_SIZE}  word_w={WORD_WIDTH:.1f}  end_x={LOCKUP_TEXT_X + WORD_WIDTH:.1f}")


def icon_block_svg(
    ring_color: str,
    sector_color: str,
    anchor_color: str,
    show_anchor: bool = True,
    x: float = LOCKUP_ICON_X,
    y: float = LOCKUP_ICON_Y,
    size: float = LOCKUP_ICON_SIZE,
) -> str:
    """Inline icon, scaled and translated to the requested box."""
    s = size / ICON_SIZE
    cx = x + size / 2
    cy = y + size / 2
    radius = RING_RADIUS * s
    ring_w = RING_STROKE * s
    sector_w = SECTOR_STROKE * s
    # recompute arc in lockup space
    start = compass_to_xy(SECTOR_START_COMPASS, RING_RADIUS)
    end = compass_to_xy(SECTOR_START_COMPASS + SECTOR_DEGREES, RING_RADIUS)
    sx = x + start[0] * s
    sy = y + start[1] * s
    ex = x + end[0] * s
    ey = y + end[1] * s
    large = 1 if SECTOR_DEGREES > 180 else 0
    arc_path = f"M {sx:.3f} {sy:.3f} A {radius:.3f} {radius:.3f} 0 {large} 1 {ex:.3f} {ey:.3f}"
    anchor_x = x + start[0] * s
    anchor_y = y + start[1] * s
    anchor = (
        f'<circle cx="{anchor_x:.3f}" cy="{anchor_y:.3f}" r="{ANCHOR_RADIUS * s:.3f}" fill="{anchor_color}"/>'
        if show_anchor
        else ""
    )
    return f'''<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{radius:.3f}" fill="none" stroke="{ring_color}" stroke-width="{ring_w:.3f}"/>
<path d="{arc_path}" fill="none" stroke="{sector_color}" stroke-width="{sector_w:.3f}" stroke-linecap="butt"/>
{anchor}'''


def lockup_svg(
    text_color: str,
    ring_color: str,
    sector_color: str,
    anchor_color: str,
    bg: str | None = None,
    show_anchor: bool = True,
) -> str:
    bg_rect = f'<rect width="{LOCKUP_W}" height="{LOCKUP_H}" fill="{bg}"/>' if bg else ""
    icon = icon_block_svg(ring_color, sector_color, anchor_color, show_anchor)
    # Use the font's actual cap height for vertical centring of the wordmark.
    cap_h = font["OS/2"].sCapHeight if hasattr(font["OS/2"], "sCapHeight") else 698
    scale = WORD_FONT_SIZE / upem
    text_baseline = LOCKUP_H / 2 + (cap_h * scale) / 2
    word_g, _ = render_word(WORD, WORD_FONT_SIZE, LOCKUP_TEXT_X, text_baseline, text_color)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {LOCKUP_W} {LOCKUP_H}" width="{LOCKUP_W}" height="{LOCKUP_H}">
{bg_rect}
{icon}
{word_g}
</svg>'''


# ---------- output ----------
ROOT = Path("/Users/patrickndille/overdrive-may-2026")
ASSETS = ROOT / "assets"
BRAND = ASSETS / "brand"
BRAND.mkdir(parents=True, exist_ok=True)


def write(path: Path, content: str) -> None:
    path.write_text(content)
    print(f"  wrote {path.relative_to(ROOT)} ({len(content):,} bytes)")


def rasterize(svg_path: Path, png_path: Path, width: int, height: int | None = None) -> None:
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=width,
        output_height=height,
    )
    size = png_path.stat().st_size
    print(f"  rasterized {png_path.relative_to(ROOT)} ({size:,} bytes)")


print("ICON master variants")
# Master icon = full-colour (works on either light or dark via transparent bg)
write(ASSETS / "logo-icon.svg",
      icon_svg(ring_color=SLATE_DARK, sector_color=AMBER, anchor_color=SLATE_DARK))

# Brand variants (icon)
write(BRAND / "icon-on-light.svg",
      icon_svg(ring_color=NEUTRAL_RING_LIGHT, sector_color=AMBER, anchor_color=SLATE_DARK))
write(BRAND / "icon-on-dark.svg",
      icon_svg(ring_color=NEUTRAL_RING, sector_color=AMBER, anchor_color=SLATE_LIGHT))
write(BRAND / "icon-mono-black.svg",
      icon_svg(ring_color=BLACK, sector_color=BLACK, anchor_color=BLACK, show_anchor=False))
write(BRAND / "icon-mono-white.svg",
      icon_svg(ring_color=WHITE, sector_color=WHITE, anchor_color=WHITE, show_anchor=False))
write(BRAND / "icon-mono-accent.svg",
      icon_svg(ring_color=AMBER, sector_color=AMBER, anchor_color=AMBER, show_anchor=False))

print("\nWORDMARK / lockup master variants")
# Primary wordmark = full-colour lockup on transparent (works on either bg)
write(ASSETS / "logo.svg",
      lockup_svg(text_color=SLATE_DARK, ring_color=NEUTRAL_RING_LIGHT,
                 sector_color=AMBER, anchor_color=SLATE_DARK))

# Brand variants (lockup)
write(BRAND / "logo-on-light.svg",
      lockup_svg(text_color=SLATE_DARK, ring_color=NEUTRAL_RING_LIGHT,
                 sector_color=AMBER, anchor_color=SLATE_DARK, bg=SLATE_LIGHT))
write(BRAND / "logo-on-dark.svg",
      lockup_svg(text_color=SLATE_LIGHT, ring_color=NEUTRAL_RING,
                 sector_color=AMBER, anchor_color=SLATE_LIGHT, bg=SLATE_DARK))
write(BRAND / "logo-mono-black.svg",
      lockup_svg(text_color=BLACK, ring_color=BLACK,
                 sector_color=BLACK, anchor_color=BLACK, show_anchor=False))
write(BRAND / "logo-mono-white.svg",
      lockup_svg(text_color=WHITE, ring_color=WHITE,
                 sector_color=WHITE, anchor_color=WHITE, show_anchor=False))
write(BRAND / "logo-mono-accent.svg",
      lockup_svg(text_color=AMBER, ring_color=AMBER,
                 sector_color=AMBER, anchor_color=AMBER, show_anchor=False))

print("\nRasterizing PNGs")
# Primary deliverables
rasterize(ASSETS / "logo-icon.svg", ASSETS / "logo-icon.png", 2048, 2048)  # 2× retina of 1024
rasterize(ASSETS / "logo.svg", ASSETS / "logo.png", 4800, 1600)             # 2× retina of 2400×800

# Brand variant PNGs
rasterize(BRAND / "icon-on-light.svg", BRAND / "icon-on-light.png", 2048, 2048)
rasterize(BRAND / "icon-on-dark.svg",  BRAND / "icon-on-dark.png",  2048, 2048)
rasterize(BRAND / "logo-on-light.svg", BRAND / "logo-on-light.png", 4800, 1600)
rasterize(BRAND / "logo-on-dark.svg",  BRAND / "logo-on-dark.png",  4800, 1600)

# Favicon-friendly icon (simple flat 256 + 64 + 32 + 16) — sanity check that it reads small
rasterize(ASSETS / "logo-icon.svg", BRAND / "icon-256.png", 256, 256)
rasterize(ASSETS / "logo-icon.svg", BRAND / "icon-16.png",  16, 16)
rasterize(ASSETS / "logo-icon.svg", BRAND / "icon-64.png",  64, 64)
rasterize(ASSETS / "logo-icon.svg", BRAND / "icon-32.png",  32, 32)

# Multi-size favicon.ico at repo root. Browsers, OS bookmark stores, and
# tab-bar renderers each pick the resolution that fits — bundle 16 → 256.
print("\nfavicon.ico (multi-size)")
import io
from PIL import Image

ico_sizes = [16, 32, 48, 64, 128, 256]
ico_images = []
for s in ico_sizes:
    png_bytes = cairosvg.svg2png(
        url=str(ASSETS / "logo-icon.svg"), output_width=s, output_height=s
    )
    ico_images.append(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))
ico_path = ROOT / "favicon.ico"
ico_images[-1].save(
    ico_path, format="ICO",
    sizes=[(s, s) for s in ico_sizes],
    append_images=ico_images[:-1],
)
print(f"  wrote {ico_path.relative_to(ROOT)} "
      f"({ico_path.stat().st_size:,} bytes, {len(ico_sizes)} embedded sizes)")

print("\nDone.")
