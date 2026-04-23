#!/usr/bin/env python3
"""Kiss-cut sticker sheet (4"x6") of Twemoji characters recolored to purple.

Sheet design: solid purple field; each sticker sits in a white halo that
straddles the cut line (visible band both inside and outside the cut), with
the recolored emoji art on top. After kiss-cutting and peeling, each sticker
has the classic "white outline around character" look.

Twemoji source (CC-BY 4.0) attributed in README.
"""

import argparse
import math
import re
import subprocess
import sys
from pathlib import Path as FsPath

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from svgelements import SVG, Path as SvgPath, Circle as SvgCircle
from svgpathtools import parse_path as parse_d

CARDS = FsPath(__file__).parent
OUT_SVG = CARDS / "purple-sticker-sheet.svg"
OUT_PDF = CARDS / "purple-sticker-sheet.pdf"

PX = 96.0
def IN(x: float) -> float:
    return x * PX

# Sheet geometry.
SHEET_W_IN  = 4.0
SHEET_H_IN  = 6.0
CUT_GAP_IN  = 0.25          # printer minimum between cut paths
PAD_IN      = 0.07          # silhouette -> cut line
HALO_OUT_IN = 0.10          # cut line -> outer edge of white halo (bleed)
CUT_STROKE_PX = 1.0

# Palette.
SHEET_PURPLE = "#5c2d91"
WHITE        = "#FFFFFF"
CUT_COLOR    = "#FF00FF"

# Auto-recolor ramp (darkest -> lightest).
PURPLE_RAMP = ["#1e1033", "#3b1a5c", "#5c2d91", "#9b59d0", "#ebe2fd"]

# Per-path sampling density (points per continuous subpath).
SAMPLES_PER_SUBPATH = 400

# Stickers: (name, source-svg, center (in, in), max cut-bbox dimension in).
STICKERS = [
    ("trex",   CARDS / "trex-source.svg",    (1.0, 1.0), 1.60),
    ("planet", CARDS / "twemoji-1fa90.svg",  (3.0, 1.0), 1.60),
    ("earth",  CARDS / "twemoji-1f30e.svg",  (1.0, 2.9), 1.40),
    ("sun",    CARDS / "twemoji-1f31e.svg",  (3.0, 2.9), 1.40),
    ("turtle", CARDS / "twemoji-1f422.svg",  (2.0, 4.75), 2.50),
]


# ---------- color remap (luminance -> nearest purple-ramp shade) ----------

_HEX_RE = re.compile(r'#[0-9a-fA-F]{6}')

def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

def _nearest_purple(hex_color: str) -> str:
    t = luminance(hex_color)
    return min(PURPLE_RAMP, key=lambda p: abs(luminance(p) - t))

def recolor(svg_text: str) -> str:
    return _HEX_RE.sub(lambda m: _nearest_purple(m.group(0)), svg_text)


# ---------- silhouette extraction (subpath-aware) ----------

def build_silhouette(src_path: FsPath):
    """Union of every filled subpath + circle in the source SVG."""
    svg = SVG.parse(str(src_path))
    polys = []
    for el in svg.elements():
        if isinstance(el, SvgPath):
            # svgpathtools handles subpaths cleanly so arms/legs/spots
            # each become their own polygon before unioning.
            try:
                tp = parse_d(el.d())
            except Exception:
                continue
            for sub in tp.continuous_subpaths():
                ts = np.linspace(0, 1, SAMPLES_PER_SUBPATH, endpoint=True)
                pts = [(sub.point(t).real, sub.point(t).imag) for t in ts]
                if len(pts) < 3:
                    continue
                poly = Polygon(pts).buffer(0)
                if not poly.is_empty:
                    polys.append(poly)
        elif isinstance(el, SvgCircle):
            cx, cy, r = float(el.cx), float(el.cy), float(el.implicit_r)
            if r > 0:
                polys.append(Polygon([
                    (cx + r*math.cos(t), cy + r*math.sin(t))
                    for t in np.linspace(0, 2*math.pi, 65)
                ]))
    return unary_union(polys)


def poly_to_svg_path(poly) -> str:
    coords = list(poly.exterior.coords)
    parts = [f"M {coords[0][0]:.3f} {coords[0][1]:.3f}"]
    for x, y in coords[1:]:
        parts.append(f"L {x:.3f} {y:.3f}")
    parts.append("Z")
    return " ".join(parts)


def extract_inner_svg(svg_text: str) -> str:
    m = re.search(r"<svg[^>]*>(.*)</svg>", svg_text, re.DOTALL)
    return m.group(1) if m else svg_text


# ---------- per-sticker geometry ----------

def build_sticker(src_path: FsPath, center_in, max_dim_in):
    silhouette = build_silhouette(src_path)
    raw       = src_path.read_text()
    recolored = recolor(raw)
    inner     = extract_inner_svg(recolored)

    minx, miny, maxx, maxy = silhouette.bounds
    native_w = maxx - minx
    native_h = maxy - miny
    native_side = max(native_w, native_h)

    # Fit cut bbox (silhouette + 2*PAD) to max_dim_in on the longer axis.
    scale = (IN(max_dim_in) - 2 * IN(PAD_IN)) / native_side
    pad_units  = IN(PAD_IN)      / scale
    halo_units = IN(HALO_OUT_IN) / scale

    cut_poly  = silhouette.buffer(pad_units,                 resolution=48, join_style="round")
    halo_poly = silhouette.buffer(pad_units + halo_units,    resolution=48, join_style="round")

    # Center cut bbox on the requested cell center.
    cminx, cminy, cmaxx, cmaxy = cut_poly.bounds
    bbox_cx = (cminx + cmaxx) / 2
    bbox_cy = (cminy + cmaxy) / 2
    cx_px, cy_px = IN(center_in[0]), IN(center_in[1])
    tx = cx_px - bbox_cx * scale
    ty = cy_px - bbox_cy * scale
    gt = f"translate({tx:.3f} {ty:.3f}) scale({scale:.5f})"

    halo_svg = (f'<g transform="{gt}">'
                f'<path d="{poly_to_svg_path(halo_poly)}" fill="{WHITE}" stroke="none"/></g>')
    art_svg  = f'<g transform="{gt}">{inner}</g>'
    cut_svg  = (f'<g transform="{gt}">'
                f'<path d="{poly_to_svg_path(cut_poly)}" fill="none" '
                f'stroke="{CUT_COLOR}" stroke-width="{CUT_STROKE_PX / scale:.4f}"/></g>')

    bbox_in = (
        (cx_px + (cminx - bbox_cx) * scale) / PX,
        (cy_px + (cminy - bbox_cy) * scale) / PX,
        (cx_px + (cmaxx - bbox_cx) * scale) / PX,
        (cy_px + (cmaxy - bbox_cy) * scale) / PX,
    )
    return halo_svg, art_svg, cut_svg, bbox_in


def build_svg() -> str:
    halos, arts, cuts, bboxes = [], [], [], []
    for (name, src, center, max_dim) in STICKERS:
        halo, art, cut, bbox = build_sticker(src, center, max_dim)
        halos.append(f"<!-- {name} -->\n    {halo}")
        arts.append(f"<!-- {name} -->\n    {art}")
        cuts.append(f"<!-- {name} -->\n    {cut}")
        bboxes.append((name, bbox))

    # Validate cut-to-cut gap.
    for i, (ni, bi) in enumerate(bboxes):
        for j in range(i + 1, len(bboxes)):
            nj, bj = bboxes[j]
            x_gap = max(bi[0] - bj[2], bj[0] - bi[2])
            y_gap = max(bi[1] - bj[3], bj[1] - bi[3])
            clear = max(x_gap, y_gap)
            if clear < CUT_GAP_IN:
                print(f"WARN: {ni}<->{nj} gap {clear:.3f}\" < {CUT_GAP_IN}\"",
                      file=sys.stderr)

    bg = (f'<rect x="0" y="0" width="{IN(SHEET_W_IN)}" height="{IN(SHEET_H_IN)}" '
          f'fill="{SHEET_PURPLE}"/>')
    page_border = (f'<rect x="0.5" y="0.5" '
                   f'width="{IN(SHEET_W_IN)-1:.3f}" '
                   f'height="{IN(SHEET_H_IN)-1:.3f}" '
                   f'fill="none" stroke="#CCCCCC" stroke-width="1"/>')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{SHEET_W_IN}in" height="{SHEET_H_IN}in"
     viewBox="0 0 {IN(SHEET_W_IN)} {IN(SHEET_H_IN)}">
  <g inkscape:groupmode="layer" inkscape:label="guides" id="guides">
    {page_border}
  </g>
  <g inkscape:groupmode="layer" inkscape:label="art" id="art">
    {bg}
    {"".join(halos)}
    {"".join(arts)}
  </g>
  <g inkscape:groupmode="layer" inkscape:label="cut" id="cut">
    {"".join(cuts)}
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
    print(f"  sheet  : {SHEET_W_IN:.1f}\" x {SHEET_H_IN:.1f}\" (kiss-cut)")
    print(f"  halo   : pad {PAD_IN:.3f}\" + bleed {HALO_OUT_IN:.3f}\"")

    if args.pdf:
        cmd = ["inkscape", str(OUT_SVG), f"--export-filename={OUT_PDF}"]
        try:
            subprocess.run(cmd, check=True)
            print(f"Wrote {OUT_PDF}")
        except FileNotFoundError:
            sys.exit("inkscape not found on PATH; install it or drop --pdf")


if __name__ == "__main__":
    main()
