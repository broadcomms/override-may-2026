#!/usr/bin/env python3
"""Build branded TORCS menu splash assets for OVERRIDE.

These replace TORCS's stock ``data/img/splash-*.png`` files with quieter
OVERRIDE-branded backgrounds while leaving the simulator's native menu logic
and widget layout untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT: Final = Path(__file__).resolve().parents[2]
BRAND_DIR: Final = ROOT / "assets" / "brand"
OUT_DIR: Final = BRAND_DIR / "torcs-menu"
SIZE: Final = 512

BG_TOP: Final = (12, 14, 18)
BG_BOTTOM: Final = (24, 18, 16)
ACCENT: Final = (255, 69, 0)
ACCENT_SOFT: Final = (255, 98, 36, 96)
AMBER: Final = (245, 158, 11)
TEXT_MAIN: Final = (245, 246, 248)
TEXT_MUTED: Final = (181, 185, 193)
PANEL_FILL: Final = (11, 13, 18, 168)
PANEL_STROKE: Final = (255, 116, 58, 88)

LABELS: Final[dict[str, str]] = {
    "splash-main.png": "COCKPIT READY",
    "splash-options.png": "SIM OPTIONS",
    "splash-qr.png": "QUICK RACE",
    "splash-practice.png": "PRACTICE",
    "splash-single-player.png": "SELECT RACE",
    "splash-raceopt.png": "RACE OPTIONS",
    "splash-run-practice.png": "LIVE RUN",
    "splash-dtm.png": "SERIES",
    "splash-dtmstart.png": "RACE START",
    "splash-result.png": "RESULTS",
    "splash-quit.png": "EXIT",
    "splash-graphic.png": "GRAPHICS",
    "splash-simucfg.png": "SIM CONFIG",
    "splash-filesel.png": "FILES",
}


def _load_logo(max_width: int) -> Image.Image:
    logo = Image.open(BRAND_DIR / "logo-on-dark.png").convert("RGBA")
    scale = min(1.0, max_width / logo.width)
    new_size = (max(1, int(logo.width * scale)), max(1, int(logo.height * scale)))
    return logo.resize(new_size, Image.Resampling.LANCZOS)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _vertical_gradient() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE))
    px = img.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        r = int(BG_TOP[0] * (1 - t) + BG_BOTTOM[0] * t)
        g = int(BG_TOP[1] * (1 - t) + BG_BOTTOM[1] * t)
        b = int(BG_TOP[2] * (1 - t) + BG_BOTTOM[2] * t)
        for x in range(SIZE):
            px[x, y] = (r, g, b, 255)
    return img


def _draw_background(draw: ImageDraw.ImageDraw) -> None:
    # Warm signal streaks, much quieter than the earlier blue treatment.
    for idx in range(6):
        x0 = -120 + idx * 86
        y0 = 72 + idx * 26
        x1 = x0 + 310
        y1 = y0 - 132
        width = 12 if idx % 2 == 0 else 6
        tone = (
            min(255, ACCENT[0]),
            max(40, ACCENT[1] + idx * 5),
            max(0, ACCENT[2] + idx * 2),
            58 if idx % 2 == 0 else 34,
        )
        draw.line((x0, y0, x1, y1), fill=tone, width=width)

    # Subtle track horizon lines.
    for y in (362, 404, 446):
        draw.rounded_rectangle((0, y, 512, y + 3), radius=2, fill=(90, 46, 24, 82))

    # A restrained stage panel behind the live TORCS menu widgets.
    draw.rounded_rectangle((118, 112, 394, 318), radius=28, fill=PANEL_FILL, outline=PANEL_STROKE, width=1)

    # Small top-right accent capsule to balance the wordmark.
    draw.rounded_rectangle((350, 30, 478, 56), radius=13, outline=(255, 125, 70, 150), width=1)
    draw.text((367, 38), "OVERRIDE", font=_font(10), fill=TEXT_MAIN)


def _draw_topline(draw: ImageDraw.ImageDraw, title: str) -> None:
    mono = _font(12)
    sans = _font(18)
    draw.text((28, 30), "OVERRIDE TORCS SURFACE", font=mono, fill=TEXT_MUTED)
    draw.text((28, 50), title, font=sans, fill=TEXT_MAIN)


def _draw_car_silhouette(draw: ImageDraw.ImageDraw) -> None:
    body = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)

    d.ellipse((268, 256, 428, 414), fill=(7, 11, 22, 170))
    d.polygon(
        [
            (242, 358),
            (268, 300),
            (320, 262),
            (394, 250),
            (438, 280),
            (460, 352),
            (446, 382),
            (410, 394),
            (286, 396),
        ],
        fill=(14, 20, 42, 220),
    )
    d.polygon(
        [(314, 286), (346, 254), (394, 250), (418, 280), (392, 312), (334, 314)],
        fill=(78, 44, 30, 132),
    )
    d.text((324, 328), "05", font=_font(48), fill=(255, 118, 56, 108))

    blurred = body.filter(ImageFilter.GaussianBlur(radius=1.2))
    draw.bitmap((0, 0), blurred)


def _draw_footer(draw: ImageDraw.ImageDraw) -> None:
    footer = _font(11)
    draw.text((28, 474), "Explainable 2026 hybrid energy strategy", font=footer, fill=(140, 132, 126))
    draw.text((360, 474), "Simulator skin", font=footer, fill=(140, 132, 126))


def build_asset(filename: str, title: str) -> None:
    base = _vertical_gradient()
    draw = ImageDraw.Draw(base, "RGBA")
    _draw_background(draw)
    _draw_car_silhouette(draw)
    _draw_topline(draw, title)
    _draw_footer(draw)

    logo = _load_logo(max_width=180)
    base.alpha_composite(logo, dest=(286, 64))

    out_path = OUT_DIR / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(out_path, format="PNG", optimize=True)
    print(f"wrote {out_path.relative_to(ROOT)}")


def main() -> None:
    for filename, title in LABELS.items():
        build_asset(filename, title)


if __name__ == "__main__":
    main()
