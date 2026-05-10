"""Build the split-screen graphic for video segment 1 (cold open).

Per docs/plans/video-script.md §Segment 1:
    "Fade in: split-screen — left side a clean simple SoC line (pre-2026
    hybrid era), right side a dense 2026-era multi-zone energy map."

Both halves are original generated graphics (not screenshots, no F1 broadcast
imagery) per CLAUDE.md and the submission guidelines. The composition shares
the dark-slate / Plex Mono / override-orange visual language used elsewhere
in the deck, so segment-1 cuts cleanly into the rest of the video.

Outputs (rasterized at 1× and 2× for the video editor):
    assets/video/segment_01_split.svg
    assets/video/segment_01_split.png        (1920×1080)
    assets/video/segment_01_split@2x.png     (3840×2160)
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import cairosvg
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

# ---------- canvas / palette ----------
W, H = 1920, 1080
DIVIDER_X = W // 2

# Mirror the UI tokens (ui/src/styles/tokens.css) so the video segment cuts
# cleanly into Engineer-mode footage in segment 3.
BG = "#0A0A0A"
SURFACE = "#141414"
GRID = "#1F1F1F"
GRID_BOLD = "#2A2A2A"
TEXT = "#F5F5F5"
TEXT_MUTED = "#9A9A9A"
TEXT_DIM = "#5A5A5A"
ACCENT = "#FF4500"      # override-orange — the live signal
GRANITE = "#3B6BD9"     # lifted granite-blue (more legible on dark than #052FAD)
SUCCESS = "#00C853"
WARNING = "#F9A825"

# ---------- font ----------
FONT_PATH = "/tmp/override-fonts/IBMPlexMono-Bold.ttf"
FONT_PATH_MED = "/tmp/override-fonts/IBMPlexMono-Medium.ttf"
font_bold = TTFont(FONT_PATH)
font_med = TTFont(FONT_PATH_MED)
upem_bold = font_bold["head"].unitsPerEm
upem_med = font_med["head"].unitsPerEm


def _glyph_path(f: TTFont, char: str) -> tuple[str, int]:
    cmap = f.getBestCmap()
    glyph_name = cmap[ord(char)] if ord(char) in cmap else cmap[ord(" ")]
    glyph = f.getGlyphSet()[glyph_name]
    pen = SVGPathPen(f.getGlyphSet())
    glyph.draw(pen)
    advance, _ = f["hmtx"][glyph_name]
    return pen.getCommands(), advance


def text_paths(text: str, x: float, y: float, size: float, fill: str,
               weight: str = "bold", anchor: str = "start", letter_spacing: float = 0.0) -> str:
    """Render text as outlined SVG paths (font-independent at render time)."""
    f = font_bold if weight == "bold" else font_med
    upem = upem_bold if weight == "bold" else upem_med
    scale = size / upem
    # measure for anchor
    total = 0.0
    for ch in text:
        _, adv = f["hmtx"][f.getBestCmap()[ord(ch)] if ord(ch) in f.getBestCmap() else f.getBestCmap()[ord(" ")]]
        total += adv * scale + letter_spacing
    if anchor == "middle":
        x -= total / 2
    elif anchor == "end":
        x -= total
    parts = [f'<g fill="{fill}" stroke="none">']
    cursor = x
    for ch in text:
        d, advance = _glyph_path(f, ch)
        parts.append(
            f'<path d="{d}" '
            f'transform="translate({cursor:.3f} {y:.3f}) scale({scale:.6f} -{scale:.6f})"/>'
        )
        cursor += advance * scale + letter_spacing
    parts.append("</g>")
    return "\n".join(parts)


# ---------- chart frame helpers ----------
# Each half is laid out as: header band (era label) on top, big chart in the
# middle, subtle annotations below. Margins generous — this is going to be on
# screen for ~14 s with text overlays competing for attention.

CHART_TOP = 220
CHART_BOTTOM = 880
CHART_HEIGHT = CHART_BOTTOM - CHART_TOP

LEFT_X = 120
LEFT_W = DIVIDER_X - LEFT_X - 80           # 80 px breathing room before divider
RIGHT_X = DIVIDER_X + 80
RIGHT_W = W - RIGHT_X - 120


def chart_grid(x0: float, y0: float, w: float, h: float, color: str = GRID) -> str:
    """5 horizontal gridlines at 0/25/50/75/100 SoC."""
    out = []
    for pct in (0, 25, 50, 75, 100):
        y = y0 + h - (pct / 100) * h
        out.append(
            f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + w}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="1" stroke-dasharray="2 4"/>'
        )
        out.append(text_paths(f"{pct}", x0 - 14, y + 5, 16, TEXT_DIM,
                              weight="medium", anchor="end"))
    # baseline
    out.append(
        f'<line x1="{x0}" y1="{y0 + h}" x2="{x0 + w}" y2="{y0 + h}" '
        f'stroke="{GRID_BOLD}" stroke-width="1.5"/>'
    )
    return "\n".join(out)


def soc_path(points: list[tuple[float, float]], x0: float, y0: float,
             w: float, h: float, smooth: bool = True) -> str:
    """Convert (t∈[0,1], soc∈[0,1]) → SVG path d-attribute."""
    if not points:
        return ""
    pts = [(x0 + t * w, y0 + h - s * h) for t, s in points]
    if not smooth:
        return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
    # Catmull-Rom-ish: cubic Beziers using neighbor tangents
    d = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C {c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f}")
    return " ".join(d)


# ---------- LEFT: pre-2026 single-MGU smooth descent ----------
def left_soc() -> list[tuple[float, float]]:
    """Single MGU-K smooth descent with one mild harvest spike."""
    pts = []
    for i in range(61):
        t = i / 60
        # Base linear-ish descent 0.78 → 0.30
        base = 0.78 - 0.48 * t
        # One subtle harvest bump around t=0.55
        bump = 0.04 * math.exp(-((t - 0.55) ** 2) / 0.012)
        # tiny noise so it's not robotic
        n = 0.005 * math.sin(t * 18)
        pts.append((t, base + bump + n))
    return pts


# ---------- RIGHT: 2026 multi-zone jagged trace + zone bands ----------
ZONES = [
    # (kind, t_start, t_end, label)
    ("harvest",  0.05, 0.12, "harvest"),
    ("deploy",   0.16, 0.25, "deploy"),
    ("harvest",  0.28, 0.35, "harvest"),
    ("override", 0.41, 0.52, "override window"),  # hero zone
    ("harvest",  0.56, 0.63, "harvest"),
    ("deploy",   0.67, 0.76, "deploy"),
    ("harvest",  0.80, 0.88, "harvest"),
    ("deploy",   0.91, 0.97, "deploy"),
]
ZONE_COLOR = {
    "deploy":   ACCENT,
    "harvest":  GRANITE,
    "override": ACCENT,
}
ZONE_OPACITY = {
    "deploy":   0.10,
    "harvest":  0.10,
    "override": 0.22,    # the hero zone reads stronger
}


def right_soc() -> list[tuple[float, float]]:
    """Jagged multi-event SoC trace driven by ZONES."""
    # Event-driven model: SoC starts at 0.80, each zone applies a deltaSoC
    # smoothly across its window (cosine ramp).
    deltas = {
        "deploy":   -0.07,
        "harvest":  +0.05,
        "override": -0.13,
    }
    soc = 0.80
    pts = [(0.0, soc)]
    timeline_n = 240  # samples
    rng = random.Random(2026)
    for i in range(1, timeline_n + 1):
        t = i / timeline_n
        # find current zone
        delta_now = 0.0
        for kind, t0, t1, _ in ZONES:
            if t0 <= t <= t1:
                # cosine-shaped derivative so the trace ramps smoothly into and
                # out of each event without sharp corners
                phase = (t - t0) / (t1 - t0)
                delta_now += deltas[kind] * (math.pi / (t1 - t0)) * math.sin(math.pi * phase) / timeline_n / 2
        soc += delta_now
        # ambient background drift downward (general consumption between events)
        soc -= 0.0005
        # small high-freq jitter (telemetry texture)
        soc += rng.uniform(-0.0015, 0.0015)
        pts.append((t, max(0.05, min(0.95, soc))))
    return pts


# ---------- compose ----------
def left_panel() -> str:
    out = []
    # era marker bar
    out.append(text_paths("2014  —  2025", LEFT_X, 110, 30, TEXT_MUTED,
                          weight="medium", letter_spacing=2.0))
    out.append(text_paths("single  hybrid  era", LEFT_X, 148, 18, TEXT_DIM,
                          weight="medium", letter_spacing=1.5))
    # axis caption
    out.append(text_paths("SoC  %", LEFT_X - 60, CHART_TOP - 14, 14, TEXT_DIM,
                          weight="medium"))
    # grid
    out.append(chart_grid(LEFT_X, CHART_TOP, LEFT_W, CHART_HEIGHT))
    # the trace
    pts = left_soc()
    out.append(
        f'<path d="{soc_path(pts, LEFT_X, CHART_TOP, LEFT_W, CHART_HEIGHT)}" '
        f'stroke="{GRANITE}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    )
    # caption below chart
    out.append(text_paths(
        "1  MGU - K  ·  smooth deploy  ·  single decision per lap",
        LEFT_X, CHART_BOTTOM + 56, 18, TEXT_MUTED,
        weight="medium", letter_spacing=1.0,
    ))
    # decision count badge
    out.append(text_paths("decisions per lap", LEFT_X, CHART_BOTTOM + 130, 14,
                          TEXT_DIM, weight="medium", letter_spacing=1.0))
    out.append(text_paths("1", LEFT_X, CHART_BOTTOM + 188, 64, GRANITE,
                          weight="bold"))
    return "\n".join(out)


def right_panel() -> str:
    out = []
    # era marker bar
    out.append(text_paths("2026  →", RIGHT_X, 110, 30, TEXT,
                          weight="bold", letter_spacing=2.0))
    out.append(text_paths(
        "hybrid  +  override  regulations",
        RIGHT_X, 148, 18, ACCENT, weight="medium", letter_spacing=1.5,
    ))
    # axis caption
    out.append(text_paths("SoC  %", RIGHT_X - 60, CHART_TOP - 14, 14, TEXT_DIM,
                          weight="medium"))
    # grid
    out.append(chart_grid(RIGHT_X, CHART_TOP, RIGHT_W, CHART_HEIGHT))

    # zone bands (drawn before the trace so they sit underneath)
    for kind, t0, t1, label in ZONES:
        x = RIGHT_X + t0 * RIGHT_W
        bw = (t1 - t0) * RIGHT_W
        color = ZONE_COLOR[kind]
        op = ZONE_OPACITY[kind]
        out.append(
            f'<rect x="{x:.2f}" y="{CHART_TOP}" width="{bw:.2f}" height="{CHART_HEIGHT}" '
            f'fill="{color}" fill-opacity="{op}" />'
        )
        # zone-edge ticks for the override zone — read as "marked sector"
        if kind == "override":
            for edge_x in (x, x + bw):
                out.append(
                    f'<line x1="{edge_x:.2f}" y1="{CHART_TOP - 6}" '
                    f'x2="{edge_x:.2f}" y2="{CHART_BOTTOM + 6}" '
                    f'stroke="{ACCENT}" stroke-width="1.5" stroke-opacity="0.7"/>'
                )
            # band label above
            out.append(text_paths(
                label.upper(), x + bw / 2, CHART_TOP - 18, 16, ACCENT,
                weight="bold", letter_spacing=2.5, anchor="middle",
            ))

    # the SoC trace
    pts = right_soc()
    out.append(
        f'<path d="{soc_path(pts, RIGHT_X, CHART_TOP, RIGHT_W, CHART_HEIGHT)}" '
        f'stroke="{ACCENT}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    )

    # vertical mini-bars at the bottom showing instantaneous deploy/harvest
    # rate — a second visual layer for "density"
    bar_y = CHART_BOTTOM + 24
    bar_h_max = 48
    rng = random.Random(7)
    for i in range(80):
        t = (i + 0.5) / 80
        in_zone = next(((kind, t0, t1) for kind, t0, t1, _ in ZONES if t0 <= t <= t1), None)
        if not in_zone:
            continue
        kind, t0, t1 = in_zone
        intensity = math.sin(math.pi * (t - t0) / (t1 - t0))
        h = bar_h_max * (0.5 + 0.5 * intensity) * (1.0 if kind == "override" else 0.55)
        x = RIGHT_X + t * RIGHT_W - 3
        color = ZONE_COLOR[kind]
        op = 0.85 if kind == "override" else 0.55
        out.append(
            f'<rect x="{x:.2f}" y="{bar_y}" width="6" height="{h:.2f}" '
            f'fill="{color}" fill-opacity="{op}"/>'
        )

    # caption below chart
    out.append(text_paths(
        "MGU - K  +  MGU - H  +  override  ·  many decisions per lap",
        RIGHT_X, CHART_BOTTOM + 130, 18, TEXT_MUTED,
        weight="medium", letter_spacing=1.0,
    ))
    # decision count badge
    out.append(text_paths("decisions per lap", RIGHT_X, CHART_BOTTOM + 130 + 60 - 60, 14,
                          TEXT_DIM, weight="medium", letter_spacing=1.0))
    # we want "decisions per lap" to sit above the big number, like the left.
    # Replace the placement above and below into clearer order:
    return "\n".join(out)


def right_panel_v2() -> str:
    """Re-do right panel with the same structure as left for visual rhyme."""
    out = []
    # era marker bar — bolder than left
    out.append(text_paths("2026", RIGHT_X, 110, 30, TEXT,
                          weight="bold", letter_spacing=2.0))
    out.append(text_paths(
        "hybrid  +  override  regulations",
        RIGHT_X, 148, 18, ACCENT, weight="medium", letter_spacing=1.5,
    ))
    # axis caption
    out.append(text_paths("SoC  %", RIGHT_X - 60, CHART_TOP - 14, 14, TEXT_DIM,
                          weight="medium"))
    # grid
    out.append(chart_grid(RIGHT_X, CHART_TOP, RIGHT_W, CHART_HEIGHT))

    # zone bands (under trace)
    for kind, t0, t1, label in ZONES:
        x = RIGHT_X + t0 * RIGHT_W
        bw = (t1 - t0) * RIGHT_W
        color = ZONE_COLOR[kind]
        op = ZONE_OPACITY[kind]
        out.append(
            f'<rect x="{x:.2f}" y="{CHART_TOP}" width="{bw:.2f}" height="{CHART_HEIGHT}" '
            f'fill="{color}" fill-opacity="{op}" />'
        )
        if kind == "override":
            for edge_x in (x, x + bw):
                out.append(
                    f'<line x1="{edge_x:.2f}" y1="{CHART_TOP - 6}" '
                    f'x2="{edge_x:.2f}" y2="{CHART_BOTTOM + 6}" '
                    f'stroke="{ACCENT}" stroke-width="1.5" stroke-opacity="0.75"/>'
                )
            out.append(text_paths(
                label.upper(), x + bw / 2, CHART_TOP - 18, 16, ACCENT,
                weight="bold", letter_spacing=2.5, anchor="middle",
            ))

    # SoC trace (override-orange)
    pts = right_soc()
    out.append(
        f'<path d="{soc_path(pts, RIGHT_X, CHART_TOP, RIGHT_W, CHART_HEIGHT)}" '
        f'stroke="{ACCENT}" stroke-width="3" fill="none" stroke-linecap="round"/>'
    )

    # density bars below the chart
    bar_y = CHART_BOTTOM + 22
    bar_h_max = 44
    for i in range(96):
        t = (i + 0.5) / 96
        in_zone = next(((kind, t0, t1) for kind, t0, t1, _ in ZONES if t0 <= t <= t1), None)
        if not in_zone:
            continue
        kind, t0, t1 = in_zone
        intensity = math.sin(math.pi * (t - t0) / (t1 - t0))
        h = bar_h_max * (0.45 + 0.55 * intensity) * (1.0 if kind == "override" else 0.6)
        x = RIGHT_X + t * RIGHT_W - 3
        color = ZONE_COLOR[kind]
        op = 0.85 if kind == "override" else 0.55
        out.append(
            f'<rect x="{x:.2f}" y="{bar_y}" width="6" height="{h:.2f}" '
            f'fill="{color}" fill-opacity="{op}"/>'
        )

    # caption mirrors the left side
    out.append(text_paths(
        "MGU - K  +  MGU - H  +  override  ·  many decisions per lap",
        RIGHT_X, CHART_BOTTOM + 100, 18, TEXT_MUTED,
        weight="medium", letter_spacing=1.0,
    ))
    out.append(text_paths("decisions per lap", RIGHT_X, CHART_BOTTOM + 130, 14,
                          TEXT_DIM, weight="medium", letter_spacing=1.0))
    out.append(text_paths(f"{len(ZONES)}", RIGHT_X, CHART_BOTTOM + 188, 64, ACCENT,
                          weight="bold"))
    return "\n".join(out)


# ---------- assemble ----------
def build() -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        # subtle radial vignette so the centre divider feels intentional
        f'<defs><radialGradient id="vig" cx="50%" cy="50%" r="80%">'
        f'<stop offset="0%" stop-color="#0F0F10"/>'
        f'<stop offset="100%" stop-color="#050505"/>'
        f'</radialGradient></defs>',
        f'<rect width="{W}" height="{H}" fill="url(#vig)"/>',
        # left + right panels
        left_panel(),
        right_panel_v2(),
        # divider — 1px slate hairline + a soft glow so it reads at distance
        f'<line x1="{DIVIDER_X}" y1="80" x2="{DIVIDER_X}" y2="{H - 80}" '
        f'stroke="{GRID_BOLD}" stroke-width="1"/>',
        f'<line x1="{DIVIDER_X}" y1="{CHART_TOP - 30}" x2="{DIVIDER_X}" '
        f'y2="{CHART_BOTTOM + 30}" stroke="{TEXT_DIM}" stroke-width="1" '
        f'stroke-opacity="0.4"/>',
        '</svg>',
    ]
    return "\n".join(parts)


# ---------- output ----------
ROOT = Path("/Users/patrickndille/overdrive-may-2026")
OUT = ROOT / "assets" / "video"
OUT.mkdir(parents=True, exist_ok=True)

svg = build()
svg_path = OUT / "segment_01_split.svg"
svg_path.write_text(svg)
print(f"wrote {svg_path.relative_to(ROOT)} ({len(svg):,} bytes)")

for suffix, scale in [("", 1), ("@2x", 2)]:
    png_path = OUT / f"segment_01_split{suffix}.png"
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=W * scale,
        output_height=H * scale,
    )
    print(f"wrote {png_path.relative_to(ROOT)} "
          f"({W*scale}×{H*scale}, {png_path.stat().st_size:,} bytes)")

# Also export each half independently for editor flexibility
# (e.g. fade left then right, or use one alone for transitions).
LEFT_SVG = svg.replace(  # quick clip via viewBox crop on a wrapper
    f'viewBox="0 0 {W} {H}"', f'viewBox="0 0 {DIVIDER_X} {H}"'
).replace(f'width="{W}"', f'width="{DIVIDER_X}"')
RIGHT_SVG_TEMPL = svg.replace(
    f'viewBox="0 0 {W} {H}"', f'viewBox="{DIVIDER_X} 0 {DIVIDER_X} {H}"'
).replace(f'width="{W}"', f'width="{DIVIDER_X}"')

for name, half_svg, half_w in [("segment_01_left", LEFT_SVG, DIVIDER_X),
                                ("segment_01_right", RIGHT_SVG_TEMPL, DIVIDER_X)]:
    half_path = OUT / f"{name}.svg"
    half_path.write_text(half_svg)
    png_path = OUT / f"{name}.png"
    cairosvg.svg2png(url=str(half_path), write_to=str(png_path),
                     output_width=half_w, output_height=H)
    print(f"wrote {png_path.relative_to(ROOT)}")

print("\nDone.")
