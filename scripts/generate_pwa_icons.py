"""Generate deterministic PNG icons for the J1 prediction PWA."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "docs" / "app" / "icons"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size, index=1 if bold else 0)
            except (OSError, ValueError):
                continue
    return ImageFont.load_default()


def _regular_polygon(cx: float, cy: float, radius: float, sides: int, rotation: float = 0) -> list[tuple[float, float]]:
    return [
        (
            cx + radius * math.cos(rotation + 2 * math.pi * index / sides),
            cy + radius * math.sin(rotation + 2 * math.pi * index / sides),
        )
        for index in range(sides)
    ]


def draw_icon(size: int, *, maskable: bool = False) -> Image.Image:
    image = Image.new("RGB", (size, size), "#102a43")
    draw = ImageDraw.Draw(image)
    inset = int(size * (0.10 if maskable else 0.045))
    radius = int(size * 0.20)

    draw.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=radius,
        fill="#0f766e",
    )
    draw.rounded_rectangle(
        (inset, int(size * 0.58), size - inset, size - inset),
        radius=radius,
        fill="#15803d",
    )

    ball_center = (size * 0.50, size * 0.39)
    ball_radius = size * 0.20
    draw.ellipse(
        (
            ball_center[0] - ball_radius,
            ball_center[1] - ball_radius,
            ball_center[0] + ball_radius,
            ball_center[1] + ball_radius,
        ),
        fill="#ffffff",
        outline="#102a43",
        width=max(2, size // 80),
    )
    pentagon = _regular_polygon(
        ball_center[0],
        ball_center[1],
        ball_radius * 0.42,
        5,
        rotation=-math.pi / 2,
    )
    draw.polygon(pentagon, fill="#102a43")
    for angle in (-math.pi / 2, -math.pi / 2 + 2.1, -math.pi / 2 + 4.2):
        outer = (
            ball_center[0] + ball_radius * 0.88 * math.cos(angle),
            ball_center[1] + ball_radius * 0.88 * math.sin(angle),
        )
        inner = (
            ball_center[0] + ball_radius * 0.42 * math.cos(angle),
            ball_center[1] + ball_radius * 0.42 * math.sin(angle),
        )
        draw.line((inner, outer), fill="#102a43", width=max(2, size // 55))

    label = "J1 AI"
    font = _font(max(18, int(size * 0.115)), bold=True)
    box = draw.textbbox((0, 0), label, font=font)
    text_width = box[2] - box[0]
    draw.text(
        ((size - text_width) / 2, size * 0.66),
        label,
        font=font,
        fill="#ffffff",
    )
    return image


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(ICON_DIR / "icon-192.png", optimize=True)
    draw_icon(512).save(ICON_DIR / "icon-512.png", optimize=True)
    draw_icon(512, maskable=True).save(ICON_DIR / "icon-maskable-512.png", optimize=True)
    print(f"Generated PWA icons in {ICON_DIR}")


if __name__ == "__main__":
    main()
