#!/usr/bin/env python3
"""Kiss-cut sticker sheet for keyboard-color mapping.

Bifold card: 12" x 4" unfolded, vertical crease at x=6" -> 6" x 4" folded.
Left panel mirrors the left half of the keyboard; right panel the right half.
Split runs between Y/H/N and U/J/M so max row width is 6 on each side.

Each sticker is layered:
  1. Purple rounded rect at cut+bleed outward (frame + outer bleed)
  2. Color rounded rect at cut-border inward  (keycap interior)
  3. Centered letter/symbol
  4. Cut path (magenta 1pt) on its own named "cut" layer

Output: SVG with named "art" and "cut" layers (Inkscape-compatible).
Pass --pdf to also render a PDF via Inkscape (preserves OCG layers).
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from purple_tui.rooms.art_room import KEY_COLORS

OUT_SVG = Path(__file__).parent / "sticker-sheet.svg"
OUT_PDF = Path(__file__).parent / "sticker-sheet.pdf"

PX = 96.0  # SVG user units per inch
def IN(x: float) -> float:
    return x * PX

# Page.
PAGE_W_IN = 12.0
PAGE_H_IN = 4.0
FOLD_X_IN = 6.0

# Keyboard split: after 6/Y/H/N. Both panels end up 6 wide x 4 rows.
LEFT_ROWS  = [list("123456"), list("qwerty"), list("asdfgh"), list("zxcvbn")]
RIGHT_ROWS = [list("7890-="), list("uiop[]"), list("jkl;'"),  list("m,./")]

SHIFT_SYMBOLS = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^",
    "7": "&", "8": "×", "9": "(", "0": ")",
    ";": ":", "'": '"', "/": "?",
}

# Print-shop spec.
CUT_GAP_IN     = 0.25   # minimum distance between any two cut paths
BLEED_IN       = 0.125  # color extends this far past each cut path
CUT_STROKE_PT  = 1.0    # 1pt magenta stroke on cut paths

# Visual design.
STICKER_SIZE_IN   = 0.55   # ~14mm: fits 15-17mm keycaps universally
BORDER_VISIBLE_IN = 0.045  # purple ring width visible INSIDE the cut
CORNER_R_IN       = 0.09   # cut-path corner radius
PURPLE_HEX        = "#6633AA"  # border ring + bleed
TEXT_LIGHT        = "#FFFFFF"
TEXT_DARK         = "#000000"
TEXT_LIGHT_THRESH = 0.65       # bg luminance below this -> use TEXT_LIGHT

# Page layout.
OUTER_MARGIN_IN = 0.25     # must be >= BLEED so bleed stays on page

COLS = 6  # widest row on each panel
ROWS = 4

DISPLAY = {"=": "+", "/": "÷"}  # kid-math global remaps

# Per-key text color overrides (mid-gray number stickers read better as black).
TEXT_OVERRIDE = {"5": TEXT_DARK, "6": TEXT_DARK}


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

def text_color_for(bg_hex: str) -> str:
    return TEXT_DARK if luminance(bg_hex) > TEXT_LIGHT_THRESH else TEXT_LIGHT

def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def panel_placements(origin_x_in: float, rows, align_right: bool):
    """Yield (key, cut_x_in, cut_y_in, cut_size_in) for each sticker.

    Grid width is driven by STICKER_SIZE_IN; the remaining panel space
    becomes the fold-side gutter. Guarantees cut paths stay >=CUT_GAP
    from each other and from the adjacent panel across the fold.
    """
    panel_w = FOLD_X_IN

    grid_w = COLS * STICKER_SIZE_IN + (COLS - 1) * CUT_GAP_IN
    grid_h = ROWS * STICKER_SIZE_IN + (ROWS - 1) * CUT_GAP_IN

    if align_right:
        # Left panel: grid hugs the outer edge, gutter grows toward the fold.
        x0 = origin_x_in + OUTER_MARGIN_IN
    else:
        # Right panel: grid hugs the outer edge on the far side.
        x0 = origin_x_in + panel_w - OUTER_MARGIN_IN - grid_w

    y0 = (PAGE_H_IN - grid_h) / 2

    for r_idx, row in enumerate(rows):
        for col_idx, key in enumerate(row):
            # On left panel, right-align short rows (none here: all 6) toward
            # the fold. On right panel, left-align rows away from the fold.
            c_pos = col_idx + (COLS - len(row)) if align_right else col_idx
            cx = x0 + c_pos * (STICKER_SIZE_IN + CUT_GAP_IN)
            cy = y0 + r_idx * (STICKER_SIZE_IN + CUT_GAP_IN)
            yield key, cx, cy, STICKER_SIZE_IN


def rrect(x_in, y_in, w_in, h_in, r_in, fill=None, stroke=None, stroke_w_pt=None):
    attrs = [
        f'x="{IN(x_in):.3f}"', f'y="{IN(y_in):.3f}"',
        f'width="{IN(w_in):.3f}"', f'height="{IN(h_in):.3f}"',
        f'rx="{IN(r_in):.3f}"', f'ry="{IN(r_in):.3f}"',
    ]
    attrs.append(f'fill="{fill}"' if fill else 'fill="none"')
    if stroke:
        attrs.append(f'stroke="{stroke}"')
        attrs.append(f'stroke-width="{stroke_w_pt}"')
    else:
        attrs.append('stroke="none"')
    return f'<rect {" ".join(attrs)}/>'


def sticker_art(key: str, cx_in: float, cy_in: float, size_in: float) -> str:
    """Build the two nested rounded rects + label for one sticker."""
    outer_x = cx_in - BLEED_IN
    outer_y = cy_in - BLEED_IN
    outer_s = size_in + 2 * BLEED_IN
    outer_r = CORNER_R_IN + BLEED_IN

    inner_x = cx_in + BORDER_VISIBLE_IN
    inner_y = cy_in + BORDER_VISIBLE_IN
    inner_s = size_in - 2 * BORDER_VISIBLE_IN
    inner_r = max(CORNER_R_IN - BORDER_VISIBLE_IN, 0.01)

    bg = KEY_COLORS.get(key, "#AAAAAA")
    fg = TEXT_OVERRIDE.get(key, text_color_for(bg))
    label = DISPLAY.get(key, key.upper())

    font_px = IN(size_in) * 0.55
    shift = SHIFT_SYMBOLS.get(key)
    # If there's a shift symbol, slide the digit right so the symbol has
    # room on the left; otherwise keep the main glyph centered.
    if shift is not None:
        tx = cx_in + size_in * 0.62
    else:
        tx = cx_in + size_in / 2
    ty = cy_in + size_in / 2

    parts = [
        rrect(outer_x, outer_y, outer_s, outer_s, outer_r, fill=PURPLE_HEX),
        rrect(inner_x, inner_y, inner_s, inner_s, inner_r, fill=bg),
        (
            f'<text x="{IN(tx):.3f}" y="{IN(ty):.3f}" '
            f'fill="{fg}" font-family="Helvetica, Arial, sans-serif" '
            f'font-weight="bold" font-size="{font_px:.2f}" '
            f'text-anchor="middle" dominant-baseline="central">{xml_escape(label)}</text>'
        ),
    ]

    if shift is not None:
        shift_px = font_px * 0.6
        shift_x = cx_in + size_in * 0.24
        shift_y = cy_in + size_in / 2
        parts.append(
            f'<text x="{IN(shift_x):.3f}" y="{IN(shift_y):.3f}" '
            f'fill="{fg}" font-family="Helvetica, Arial, sans-serif" '
            f'font-weight="bold" font-size="{shift_px:.2f}" '
            f'text-anchor="middle" dominant-baseline="central">{xml_escape(shift)}</text>'
        )

    return "\n    ".join(parts)


def cut_rect(cx_in: float, cy_in: float, size_in: float) -> str:
    return rrect(cx_in, cy_in, size_in, size_in, CORNER_R_IN,
                 stroke="#FF00FF", stroke_w_pt=CUT_STROKE_PT)


def build_svg() -> str:
    placements = list(panel_placements(0.0, LEFT_ROWS, align_right=True))
    placements.extend(panel_placements(FOLD_X_IN, RIGHT_ROWS, align_right=False))

    art  = "\n    ".join(sticker_art(k, x, y, s) for k, x, y, s in placements)
    cuts = "\n    ".join(cut_rect(x, y, s)        for _, x, y, s in placements)

    fold_guide = (
        f'<line x1="{IN(FOLD_X_IN)}" y1="0" '
        f'x2="{IN(FOLD_X_IN)}" y2="{IN(PAGE_H_IN)}" '
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
    {art}
  </g>
  <g inkscape:groupmode="layer" inkscape:label="cut" id="cut">
    {cuts}
  </g>
</svg>
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true",
                    help="Also render PDF via Inkscape (preserves OCG layers).")
    args = ap.parse_args()

    OUT_SVG.write_text(build_svg())
    print(f"Wrote {OUT_SVG}")
    print(f"  sticker size : {STICKER_SIZE_IN:.3f}\" (~{STICKER_SIZE_IN*25.4:.1f}mm)")
    print(f"  cut gap      : {CUT_GAP_IN:.3f}\"")
    print(f"  bleed        : {BLEED_IN:.3f}\"")
    print(f"  purple border: {BORDER_VISIBLE_IN:.3f}\" visible + {BLEED_IN:.3f}\" bleed")

    if args.pdf:
        cmd = ["inkscape", str(OUT_SVG), f"--export-filename={OUT_PDF}"]
        try:
            subprocess.run(cmd, check=True)
            print(f"Wrote {OUT_PDF}")
        except FileNotFoundError:
            sys.exit("inkscape not found on PATH; install it or drop --pdf")


if __name__ == "__main__":
    main()
