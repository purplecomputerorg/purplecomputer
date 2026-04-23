#!/usr/bin/env python3
"""Kiss-cut / die-cut sticker: cartoon T-Rex recolored to Purple Computer
shades, with silhouette cut line and optional URL text. Source artwork is
Twemoji's T-Rex emoji (U+1F996), CC-BY 4.0. Attribution belongs in README,
not on the sticker.

Output: cards/trex-sticker.svg + .pdf.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path as FsPath

from shapely.geometry import Polygon
from shapely.ops import unary_union
from svgelements import SVG, Path as SvgPath, Circle as SvgCircle

SRC_SVG = FsPath(__file__).parent / "trex-source.svg"
OUT_SVG = FsPath(__file__).parent / "trex-sticker.svg"
OUT_PDF = FsPath(__file__).parent / "trex-sticker.pdf"

PX = 96.0
def IN(x: float) -> float:
    return x * PX

# Sticker geometry.
STICKER_H_IN   = 3.0
PAD_IN         = 0.08
PAGE_MARGIN_IN = 0.0
CUT_STROKE_PX  = 1.0
BLEED_IN       = 0.125
BG_COLOR       = None         # None = transparent; hex = filled badge

# Twemoji green palette -> Purple Computer palette.
COLOR_MAP = {
    "#3E701E": "#3b1a5c",   # darkest green -> very dark purple
    "#3e701e": "#3b1a5c",
    "#5C913A": "#5c2d91",   # mid green    -> bot dark
    "#5c913a": "#5c2d91",
    "#77B155": "#9b59d0",   # light green  -> bot light
    "#77b155": "#9b59d0",
    "#292E32": "#1e1033",   # outline dark -> deep purple
    "#292e32": "#1e1033",
    "#292F33": "#1e1033",   # eye          -> deep purple
    "#292f33": "#1e1033",
    "#F4900C": "#ebe2fd",   # orange accent-> soft light (readable contrast)
    "#f4900c": "#ebe2fd",
}
CUT_COLOR = "#FF00FF"

# How finely to sample path curves into polygon vertices.
SAMPLES_PER_PATH = 240


def recolor(svg_text: str) -> str:
    out = svg_text
    for src, dst in COLOR_MAP.items():
        out = out.replace(src, dst)
    return out


def build_silhouette():
    """Union of every filled shape in the source trex SVG, in trex native units."""
    svg = SVG.parse(str(SRC_SVG))
    polys = []
    for el in svg.elements():
        if isinstance(el, SvgPath):
            pts = [(p.x, p.y) for p in (el.point(i / SAMPLES_PER_PATH)
                                        for i in range(SAMPLES_PER_PATH + 1))]
            if len(pts) >= 3:
                try:
                    poly = Polygon(pts)
                    if poly.is_valid and poly.area > 0:
                        polys.append(poly)
                    else:
                        polys.append(poly.buffer(0))
                except Exception:
                    pass
        elif isinstance(el, SvgCircle):
            cx = float(el.cx)
            cy = float(el.cy)
            r  = float(el.implicit_r)
            if r > 0:
                polys.append(Polygon([
                    (cx + r*__cos(t), cy + r*__sin(t))
                    for t in (i / 64 * 6.283185307179586 for i in range(65))
                ]))
    return unary_union(polys)


def __cos(t):
    import math; return math.cos(t)
def __sin(t):
    import math; return math.sin(t)


def poly_to_svg_path(poly) -> str:
    coords = list(poly.exterior.coords)
    parts = [f"M {coords[0][0]:.3f} {coords[0][1]:.3f}"]
    for x, y in coords[1:]:
        parts.append(f"L {x:.3f} {y:.3f}")
    parts.append("Z")
    return " ".join(parts)


def extract_inner_svg(src_text: str) -> str:
    """Return the children of the root <svg> element (as a string)."""
    m = re.search(r"<svg[^>]*>(.*)</svg>", src_text, re.DOTALL)
    return m.group(1) if m else src_text


def build_svg() -> str:
    src_raw = SRC_SVG.read_text()
    src_recolored = recolor(src_raw)
    trex_inner = extract_inner_svg(src_recolored)

    silhouette = build_silhouette()
    minx, miny, maxx, maxy = silhouette.bounds
    native_h = maxy - miny

    scale = (IN(STICKER_H_IN) - 2 * IN(PAD_IN)) / native_h
    pad_units   = IN(PAD_IN)   / scale
    bleed_units = IN(BLEED_IN) / scale if BG_COLOR else 0.0

    cut_poly   = silhouette.buffer(pad_units,   resolution=32, join_style="round")
    outer_poly = cut_poly.buffer(bleed_units,   resolution=32, join_style="round") if BG_COLOR else cut_poly

    ominx, ominy, omaxx, omaxy = outer_poly.bounds
    page_w = (omaxx - ominx) * scale + 2 * IN(PAGE_MARGIN_IN)
    page_h = (omaxy - ominy) * scale + 2 * IN(PAGE_MARGIN_IN)

    tx = IN(PAGE_MARGIN_IN) - ominx * scale
    ty = IN(PAGE_MARGIN_IN) - ominy * scale
    group_transform = f"translate({tx:.3f} {ty:.3f}) scale({scale:.5f})"

    cut_d = poly_to_svg_path(cut_poly)
    bg_elem = (
        f'<path d="{poly_to_svg_path(outer_poly)}" fill="{BG_COLOR}" stroke="none"/>'
        if BG_COLOR else ""
    )
    art_inner = f"{bg_elem}\n{trex_inner}"
    cut_inner = (
        f'<path d="{cut_d}" fill="none" stroke="{CUT_COLOR}" '
        f'stroke-width="{CUT_STROKE_PX / scale:.4f}"/>'
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{page_w/PX:.3f}in" height="{page_h/PX:.3f}in"
     viewBox="0 0 {page_w:.3f} {page_h:.3f}">
  <g inkscape:groupmode="layer" inkscape:label="art" id="art">
    <g transform="{group_transform}">{art_inner}</g>
  </g>
  <g inkscape:groupmode="layer" inkscape:label="cut" id="cut">
    <g transform="{group_transform}">{cut_inner}</g>
  </g>
</svg>
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true",
                    help="Also render PDF via Inkscape.")
    args = ap.parse_args()

    OUT_SVG.write_text(build_svg())
    print(f"Wrote {OUT_SVG}")
    print(f"  sticker height : {STICKER_H_IN:.2f}\"")
    print(f"  padding        : {PAD_IN:.3f}\" (~{PAD_IN*25.4:.1f}mm)")
    print(f"  bg             : {BG_COLOR or 'transparent'}")

    if args.pdf:
        cmd = ["inkscape", str(OUT_SVG), f"--export-filename={OUT_PDF}"]
        try:
            subprocess.run(cmd, check=True)
            print(f"Wrote {OUT_PDF}")
        except FileNotFoundError:
            sys.exit("inkscape not found on PATH; install it or drop --pdf")


if __name__ == "__main__":
    main()
