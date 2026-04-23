#!/usr/bin/env python3
"""Kiss-cut sticker sheet for keyboard-color mapping.

Bifold card: 12" x 4" unfolded, vertical crease at x=6" -> 6" x 4" folded.
Left panel mirrors the left half of the keyboard; right panel the right half.

Output: SVG with a named "cut" layer (Inkscape-compatible) for kiss-cut
printing. Cut paths are 1pt strokes; artwork bleeds 0.125" past each cut
path; cut paths are at least 0.25" apart.

Optional: pass --pdf to also shell out to Inkscape and produce a PDF whose
OCG layers preserve the SVG layer names.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from purple_tui.rooms.art_room import KEY_COLORS

OUT_SVG = Path(__file__).parent / "sticker-sheet.svg"
OUT_PDF = Path(__file__).parent / "sticker-sheet.pdf"

# SVG user units: 1 px = 1/96 inch (SVG default).
PX = 96.0
def IN(x: float) -> float:
    return x * PX

PAGE_W_IN = 12.0
PAGE_H_IN = 4.0
FOLD_X_IN = 6.0

LEFT_ROWS  = [list("qwert"),   list("asdfg"),  list("zxcvb")]
RIGHT_ROWS = [list("yuiop[]"), list("hjkl;'"), list("nm,./")]

COLS = 7          # widest row (right panel's top row)
ROWS = 3

# Printer spec.
CUT_GAP_IN  = 0.25    # minimum distance between any two cut paths
BLEED_IN    = 0.125   # color extends this far past each cut path
CUT_STROKE_PT = 1.0   # 1pt stroke on cut paths

# Layout margins (all in inches).
OUTER_MARGIN_IN = 0.25  # >= BLEED so bleed doesn't run off the page
FOLD_GUTTER_IN  = 0.15  # per-panel; combined 0.30" across fold > CUT_GAP

CORNER_R_IN = 0.1

DISPLAY = {"[": "[", "]": "]", ";": ";", "'": "'", ",": ",", ".": ".", "/": "/"}

def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

def text_color_for(bg_hex: str) -> str:
    return "#000000" if luminance(bg_hex) > 0.6 else "#FFFFFF"


def panel_sticker_positions(origin_x_in: float, rows, align_right: bool):
    """Yield (key, cx_in, cy_in, size_in) for each sticker in a panel.

    Coordinates are in inches; cy grows downward (SVG convention).
    """
    panel_w = FOLD_X_IN
    panel_h = PAGE_H_IN

    # Reserve outer margin and fold gutter.
    if align_right:
        # Left panel: fold is at the panel's right edge.
        usable_left  = origin_x_in + OUTER_MARGIN_IN
        usable_right = origin_x_in + panel_w - FOLD_GUTTER_IN
    else:
        # Right panel: fold is at the panel's left edge.
        usable_left  = origin_x_in + FOLD_GUTTER_IN
        usable_right = origin_x_in + panel_w - OUTER_MARGIN_IN

    usable_w = usable_right - usable_left
    usable_h = panel_h - 2 * OUTER_MARGIN_IN

    sticker_w = (usable_w - (COLS - 1) * CUT_GAP_IN) / COLS
    sticker_h = (usable_h - (ROWS - 1) * CUT_GAP_IN) / ROWS
    size = min(sticker_w, sticker_h)

    grid_w = COLS * size + (COLS - 1) * CUT_GAP_IN
    grid_h = ROWS * size + (ROWS - 1) * CUT_GAP_IN

    # Vertically center the grid within the panel.
    y0 = (panel_h - grid_h) / 2

    if align_right:
        # Push grid toward the fold (right edge of usable area).
        x0 = usable_right - grid_w
    else:
        x0 = usable_left

    for r_idx, row in enumerate(rows):
        for col_idx, key in enumerate(row):
            if align_right:
                # Right-align short rows within the grid so they hug the fold.
                c_pos = col_idx + (COLS - len(row))
            else:
                c_pos = col_idx
            cx = x0 + c_pos * (size + CUT_GAP_IN)
            cy = y0 + r_idx * (size + CUT_GAP_IN)
            yield key, cx, cy, size


def svg_sticker_art(key: str, cx_in: float, cy_in: float, size_in: float) -> str:
    """Rounded rect with color bleed extending BLEED past the cut path,
    plus the centered letter/symbol."""
    bleed = BLEED_IN
    bx = cx_in - bleed
    by = cy_in - bleed
    bw = size_in + 2 * bleed
    bh = size_in + 2 * bleed
    # Corner radius scales a bit so the bleed rect stays smooth.
    r  = CORNER_R_IN + bleed

    bg = KEY_COLORS.get(key, "#AAAAAA")
    fg = text_color_for(bg)
    label = DISPLAY.get(key, key.upper())

    # Font size: ~55% of sticker edge.
    font_px = IN(size_in) * 0.55
    tx = cx_in + size_in / 2
    ty = cy_in + size_in / 2

    return (
        f'<rect x="{IN(bx):.3f}" y="{IN(by):.3f}" '
        f'width="{IN(bw):.3f}" height="{IN(bh):.3f}" '
        f'rx="{IN(r):.3f}" ry="{IN(r):.3f}" '
        f'fill="{bg}" stroke="none"/>'
        f'<text x="{IN(tx):.3f}" y="{IN(ty):.3f}" '
        f'fill="{fg}" font-family="Helvetica, Arial, sans-serif" '
        f'font-weight="bold" font-size="{font_px:.2f}" '
        f'text-anchor="middle" dominant-baseline="central">{label}</text>'
    )


def svg_cut_path(cx_in: float, cy_in: float, size_in: float) -> str:
    return (
        f'<rect x="{IN(cx_in):.3f}" y="{IN(cy_in):.3f}" '
        f'width="{IN(size_in):.3f}" height="{IN(size_in):.3f}" '
        f'rx="{IN(CORNER_R_IN):.3f}" ry="{IN(CORNER_R_IN):.3f}" '
        f'fill="none" stroke="#FF00FF" stroke-width="{CUT_STROKE_PT}"/>'
    )


def build_svg() -> str:
    panels = [
        (0.0, LEFT_ROWS, True),
        (FOLD_X_IN, RIGHT_ROWS, False),
    ]
    placements = []
    for origin, rows, align_right in panels:
        placements.extend(panel_sticker_positions(origin, rows, align_right))

    art_elems = "\n    ".join(svg_sticker_art(k, x, y, s) for k, x, y, s in placements)
    cut_elems = "\n    ".join(svg_cut_path(x, y, s)       for _, x, y, s in placements)

    fold_guide = (
        f'<line x1="{IN(FOLD_X_IN)}" y1="0" x2="{IN(FOLD_X_IN)}" y2="{IN(PAGE_H_IN)}" '
        f'stroke="#CCCCCC" stroke-width="0.5" stroke-dasharray="4,4"/>'
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{PAGE_W_IN}in" height="{PAGE_H_IN}in"
     viewBox="0 0 {IN(PAGE_W_IN)} {IN(PAGE_H_IN)}">
  <g inkscape:groupmode="layer" inkscape:label="guides" id="guides">
    {fold_guide}
  </g>
  <g inkscape:groupmode="layer" inkscape:label="art" id="art">
    {art_elems}
  </g>
  <g inkscape:groupmode="layer" inkscape:label="cut" id="cut">
    {cut_elems}
  </g>
</svg>
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true",
                    help="Also render PDF via Inkscape (preserves layers as OCG).")
    args = ap.parse_args()

    OUT_SVG.write_text(build_svg())
    print(f"Wrote {OUT_SVG}")

    if args.pdf:
        cmd = ["inkscape", str(OUT_SVG), f"--export-filename={OUT_PDF}"]
        try:
            subprocess.run(cmd, check=True)
            print(f"Wrote {OUT_PDF}")
        except FileNotFoundError:
            sys.exit("inkscape not found on PATH; install it or drop --pdf")


if __name__ == "__main__":
    main()
