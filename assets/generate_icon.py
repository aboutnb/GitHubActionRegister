#!/usr/bin/env python3
"""生成 1024×1024 macOS 风格应用图标。运行: python3 generate_icon.py"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
OUT = HERE / "icon.png"
OUT_ICO = HERE / "icon.ico"

S = 2048
CANVAS = (0, 0, 0, 0)
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
    im = Image.new("RGBA", (S, S), CANVAS)

    # 标准应用图标安全区：不要满铺到边缘。
    inset = int(S * 0.11)
    radius = int(S * 0.23)
    tile_box = [inset, inset, S - inset, S - inset]

    shadow = Image.new("RGBA", (S, S), CANVAS)
    ds = ImageDraw.Draw(shadow)
    shadow_box = [tile_box[0], tile_box[1] + int(S * 0.028), tile_box[2], tile_box[3] + int(S * 0.028)]
    ds.rounded_rectangle(shadow_box, radius=radius, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(S * 0.03)))
    im.alpha_composite(shadow)

    tile = Image.new("RGBA", (S, S), CANVAS)
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle(tile_box, radius=radius, fill=BG)

    cx, cy = S // 2, S // 2 + int(S * 0.012)
    ring_margin = int(S * 0.23)
    d.ellipse(
        [ring_margin, ring_margin, S - 1 - ring_margin, S - 1 - ring_margin],
        outline=MUTED,
        width=max(3, S // 256),
    )

    dist = int(S * 0.215)
    angles_deg = (90, 210, 330)
    nodes = []
    for ang in angles_deg:
        rad = math.radians(ang)
        nodes.append((cx + int(dist * math.cos(rad)), cy + int(dist * math.sin(rad))))

    line_w = max(16, int(S * 0.024))
    for i in range(3):
        thick_line(d, nodes[i], nodes[(i + 1) % 3], ACCENT, line_w)

    r_big = int(S * 0.056)
    for i, p in enumerate(nodes):
        col = GREEN if i == 0 else ACCENT
        d.ellipse([p[0] - r_big, p[1] - r_big, p[0] + r_big, p[1] + r_big], fill=col)
        d.ellipse(
            [p[0] - r_big, p[1] - r_big, p[0] + r_big, p[1] + r_big],
            outline=MUTED,
            width=max(2, S // 512),
        )

    r_hub = int(S * 0.048)
    d.ellipse([cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub], fill=(201, 209, 217, 255))
    d.ellipse(
        [cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub],
        outline=ACCENT,
        width=max(4, S // 400),
    )

    im.alpha_composite(tile)

    out = im.resize((1024, 1024), Image.Resampling.LANCZOS)
    out.save(OUT, format="PNG", optimize=True)
    out.save(OUT_ICO, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Wrote {OUT} ({out.size[0]}×{out.size[1]})")
    print(f"Wrote {OUT_ICO}")


if __name__ == "__main__":
    main()
