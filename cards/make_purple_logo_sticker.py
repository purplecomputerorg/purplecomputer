#!/usr/bin/env python3
"""Kiss-cut Purple Computer logo sticker (silhouette die-cut).

Cut line traces the bot outline (body + antennae + feet) with a small
uniform buffer, so the sticker is the bot shape itself rather than a
disc around it. Bleed fill extends further outward per the print spec.

Output: cards/purple-logo-sticker.svg and .pdf (Inkscape).
"""

import argparse
import subprocess
import sys
from pathlib import Path

from shapely.geometry import Point, LineString
from shapely.ops import unary_union

OUT_SVG = Path(__file__).parent / "purple-logo-sticker.svg"
OUT_PDF = Path(__file__).parent / "purple-logo-sticker.pdf"

PX = 96.0
def IN(x: float) -> float:
    return x * PX

# Target: sticker is STICKER_H_IN tall overall (cut line to cut line).
STICKER_H_IN   = 3.0
PAD_IN         = 0.125  # silhouette -> cut line; print safety margin
PAGE_MARGIN_IN = 0.0    # page = cut/bleed bbox; no wasted whitespace
CUT_STROKE_PX  = 1.0    # printer spec: 1-pixel stroke on cut paths
BLEED_IN       = 0.125  # required when BG_COLOR is set (color extending to cut)
BG_COLOR       = "#ebe2fd"  # None for transparent; hex for filled badge

# Bot colors from logo.svg.
BOT_DARK   = "#5c2d91"
BOT_LIGHT  = "#9b59d0"
FACE_BG    = "#ebe2fd"
CUT_COLOR  = "#FF00FF"

# Bot geometry in the logo's native unit space (same as logo.svg).
# Matches stroke widths etc. so the silhouette hugs what's drawn.
def build_silhouette():
    """Union of every bot shape, in native logo-space units."""
    shapes = [
        Point(100, 110).buffer(45, resolution=64),              # body
        Point(85, 47).buffer(6, resolution=32),                 # L antenna ball
        Point(115, 47).buffer(6, resolution=32),                # R antenna ball
        # antenna stems (stroke-width=5 -> half-width 2.5, round caps)
        LineString([(85, 68), (85, 50)]).buffer(2.5, resolution=16, cap_style="round"),
        LineString([(115, 68), (115, 50)]).buffer(2.5, resolution=16, cap_style="round"),
        Point(85, 160).buffer(10, resolution=32),               # L foot
        Point(115, 160).buffer(10, resolution=32),              # R foot
    ]
    return unary_union(shapes)


def poly_to_svg_path(poly) -> str:
    """Polygon exterior -> SVG path data string."""
    coords = list(poly.exterior.coords)
    parts = [f"M {coords[0][0]:.3f} {coords[0][1]:.3f}"]
    for x, y in coords[1:]:
        parts.append(f"L {x:.3f} {y:.3f}")
    parts.append("Z")
    return " ".join(parts)


def build_svg() -> str:
    silhouette = build_silhouette()

    # Natural height spans roughly from the top of the antenna balls to the
    # bottom of the feet. Pick the unit-scale so (silhouette_h + 2*pad) = 3".
    minx, miny, maxx, maxy = silhouette.bounds
    native_h = maxy - miny
    # In the final SVG, 1 native unit -> `scale` pixels.
    scale = (IN(STICKER_H_IN) - 2 * IN(PAD_IN)) / native_h
    pad_units   = IN(PAD_IN)   / scale
    bleed_units = IN(BLEED_IN) / scale if BG_COLOR else 0.0

    cut_poly   = silhouette.buffer(pad_units, resolution=32, join_style="round")
    outer_poly = cut_poly.buffer(bleed_units, resolution=32, join_style="round") if BG_COLOR else cut_poly

    # Page spans the outer shape (cut + bleed if any) plus any margin.
    ominx, ominy, omaxx, omaxy = outer_poly.bounds
    page_w = (omaxx - ominx) * scale + 2 * IN(PAGE_MARGIN_IN)
    page_h = (omaxy - ominy) * scale + 2 * IN(PAGE_MARGIN_IN)

    tx = IN(PAGE_MARGIN_IN) - ominx * scale
    ty = IN(PAGE_MARGIN_IN) - ominy * scale
    group_transform = f"translate({tx:.3f} {ty:.3f}) scale({scale:.5f})"

    cut_path_d = poly_to_svg_path(cut_poly)
    bg_path_d  = poly_to_svg_path(outer_poly) if BG_COLOR else None

    bg_elem = f'<path d="{bg_path_d}" fill="{BG_COLOR}" stroke="none"/>' if BG_COLOR else ""
    # Art layer. If BG_COLOR is set, a filled badge extends to bleed edge;
    # otherwise the background is transparent (white vinyl shows as halo).
    art_inner = f'''{bg_elem}
<!-- Body -->
<path d="M 100 65 A 45 45 0 0 0 100 155 Z" fill="{BOT_DARK}"/>
<path d="M 100 65 A 45 45 0 0 1 100 155 Z" fill="{BOT_LIGHT}"/>
<!-- Face -->
<circle cx="100" cy="110" r="32" fill="{FACE_BG}"/>
<!-- Eyes -->
<circle cx="90" cy="106" r="5" fill="{BOT_DARK}"/>
<circle cx="110" cy="106" r="5" fill="{BOT_DARK}"/>
<!-- Smile -->
<path d="M 88 120 Q 100 128 112 120" stroke="{BOT_DARK}" stroke-width="3" stroke-linecap="round" fill="none"/>
<!-- Antennae -->
<line x1="85" y1="68" x2="85" y2="50" stroke="{BOT_DARK}" stroke-width="5" stroke-linecap="round"/>
<circle cx="85" cy="47" r="6" fill="{BOT_LIGHT}"/>
<line x1="115" y1="68" x2="115" y2="50" stroke="{BOT_LIGHT}" stroke-width="5" stroke-linecap="round"/>
<circle cx="115" cy="47" r="6" fill="{BOT_DARK}"/>
<!-- Feet -->
<circle cx="85" cy="160" r="10" fill="{BOT_DARK}"/>
<circle cx="115" cy="160" r="10" fill="{BOT_LIGHT}"/>
<!-- URL arc -->
<defs><path id="url-arc" d="M 63.76 126.92 A 40 40 0 0 0 136.24 126.92"/></defs>
<text fill="{FACE_BG}" font-family="Nunito, Helvetica, Arial, sans-serif"
      font-weight="700" font-size="7" letter-spacing="0.9">
  <textPath href="#url-arc" startOffset="50%" text-anchor="middle">purplecomputer.org</textPath>
</text>
'''

    cut_inner = f'<path d="{cut_path_d}" fill="none" stroke="{CUT_COLOR}" stroke-width="{CUT_STROKE_PX / scale:.4f}"/>'

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

    if args.pdf:
        cmd = ["inkscape", str(OUT_SVG), "--export-text-to-path", f"--export-filename={OUT_PDF}"]
        try:
            subprocess.run(cmd, check=True)
            print(f"Wrote {OUT_PDF}")
        except FileNotFoundError:
            sys.exit("inkscape not found on PATH; install it or drop --pdf")


if __name__ == "__main__":
    main()
