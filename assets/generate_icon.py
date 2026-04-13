#!/usr/bin/env python3
"""生成 1024×1024 方形应用图标（居中安全区、1:1 比例）。运行: python3 generate_icon.py"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE / "icon.png"

S = 2048
BG = (13, 17, 23, 255)
ACCENT = (88, 166, 255, 255)
GREEN = (63, 185, 80, 255)
MUTED = (48, 54, 61, 255)


def thick_line(draw: ImageDraw.ImageDraw, p1: tuple[int, int], p2: tuple[int, int], fill: tuple, w: float) -> None:
    x1, y1 = p1
    x2, y2 = p2
    ang = math.atan2(y2 - y1, x2 - x1)
    perp = ang + math.pi / 2
    dx = math.cos(perp) * (w / 2)
    dy = math.sin(perp) * (w / 2)
    poly = [
        (x1 + dx, y1 + dy),
        (x2 + dx, y2 + dy),
        (x2 - dx, y2 - dy),
        (x1 - dx, y1 - dy),
    ]
    draw.polygon(poly, fill=fill)


def main() -> None:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, S - 1, S - 1], fill=BG)

    cx, cy = S // 2, S // 2
    ring_margin = int(S * 0.12)
    d.ellipse(
        [ring_margin, ring_margin, S - 1 - ring_margin, S - 1 - ring_margin],
        outline=MUTED,
        width=max(3, S // 256),
    )

    dist = int(S * 0.28)
    angles_deg = (90, 210, 330)
    nodes = []
    for ang in angles_deg:
        rad = math.radians(ang)
        nodes.append((cx + int(dist * math.cos(rad)), cy + int(dist * math.sin(rad))))

    line_w = max(16, int(S * 0.028))
    for i in range(3):
        thick_line(d, nodes[i], nodes[(i + 1) % 3], ACCENT, line_w)

    r_big = int(S * 0.065)
    for i, p in enumerate(nodes):
        col = GREEN if i == 0 else ACCENT
        d.ellipse([p[0] - r_big, p[1] - r_big, p[0] + r_big, p[1] + r_big], fill=col)
        d.ellipse(
            [p[0] - r_big, p[1] - r_big, p[0] + r_big, p[1] + r_big],
            outline=MUTED,
            width=max(2, S // 512),
        )

    r_hub = int(S * 0.055)
    d.ellipse([cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub], fill=(201, 209, 217, 255))
    d.ellipse(
        [cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub],
        outline=ACCENT,
        width=max(4, S // 400),
    )

    out = im.resize((1024, 1024), Image.Resampling.LANCZOS)
    out.save(OUT, format="PNG", optimize=True)
    print(f"Wrote {OUT} ({out.size[0]}×{out.size[1]})")


if __name__ == "__main__":
    main()
