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

OUT_SVG = Path(__file__).parent / "keyboard-sticker-sheet.svg"
OUT_PDF = Path(__file__).parent / "keyboard-sticker-sheet.pdf"

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
CUT_GAP_IN     = 0.30   # distance between cut paths (printer min: 0.25")
BLEED_IN       = 0.125  # color extends this far past each cut path
CUT_STROKE_PT  = 1.0    # 1pt magenta stroke on cut paths

# Visual design.
STICKER_SIZE_IN   = 0.55   # ~14mm: fits 15-17mm keycaps universally
BORDER_VISIBLE_IN = 0.125  # purple ring inside the cut; meets print wobble tolerance
CORNER_R_IN       = 0.09   # cut-path corner radius
PURPLE_HEX        = "#6633AA"  # border ring + bleed
TEXT_LIGHT        = "#FFFFFF"
TEXT_DARK         = "#000000"

# Page layout.
OUTER_MARGIN_IN = 0.25     # must be >= BLEED so bleed stays on page

COLS = 6  # widest row on each panel
ROWS = 4

DISPLAY = {"=": "+", "/": "÷"}  # kid-math global remaps

# Per-key shift-symbol size multiplier (default 0.6 of digit size).
# Double-quote needs more glyph area to read as a pair of marks.
SHIFT_SIZE_OVERRIDE = {"'": 0.85, "5": 0.52, "2": 0.52, "1": 0.70, "/": 0.70}
# Per-key horizontal offset for the shift symbol (fraction of sticker size).
SHIFT_X_OVERRIDE = {"1": 0.30}


def _rel_luminance(hex_color: str) -> float:
    """WCAG relative luminance (sRGB, gamma-corrected)."""
    h = hex_color.lstrip("#")
    def ch(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = ch(int(h[0:2], 16)), ch(int(h[2:4], 16)), ch(int(h[4:6], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def text_color_for(bg_hex: str) -> str:
    """Pick whichever of black/white has the higher WCAG contrast ratio."""
    l_bg = _rel_luminance(bg_hex)
    contrast_white = 1.05 / (l_bg + 0.05)
    contrast_black = (l_bg + 0.05) / 0.05
    return TEXT_LIGHT if contrast_white >= contrast_black else TEXT_DARK

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

    # Center the grid horizontally within its panel -> equal outer and fold
    # margins, so neither side feels crowded.
    x0 = origin_x_in + (panel_w - grid_w) / 2
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
    """Build the bleed rect, inner color tile, and label for one sticker."""
    outer_x = cx_in - BLEED_IN
    outer_y = cy_in - BLEED_IN
    outer_s = size_in + 2 * BLEED_IN
    outer_r = CORNER_R_IN + BLEED_IN

    inner_x = cx_in + BORDER_VISIBLE_IN
    inner_y = cy_in + BORDER_VISIBLE_IN
    inner_s = size_in - 2 * BORDER_VISIBLE_IN
    inner_r = CORNER_R_IN * (inner_s / size_in)

    bg = KEY_COLORS.get(key, "#AAAAAA")
    fg = text_color_for(bg)
    label = DISPLAY.get(key, key.upper())

    shift = SHIFT_SYMBOLS.get(key)
    # Font sized against the inner tile so glyphs fit the color area.
    # Shift-symbol keys get a tighter size to make room for two glyphs.
    font_px = IN(inner_s) * (0.72 if shift is not None else 0.88)
    inner_cx = inner_x + inner_s / 2
    if shift is not None:
        tx = inner_x + inner_s * 0.73
    else:
        tx = inner_cx
    # Nunito glyphs ride high in the em box; nudge down so they read centered.
    if key in ("[", "]"):
        ty_frac = 0.54
    elif key == "=":
        ty_frac = 0.55
    else:
        ty_frac = 0.60
    ty = inner_y + inner_s * ty_frac

    parts = [
        rrect(outer_x, outer_y, outer_s, outer_s, outer_r, fill=PURPLE_HEX),
        rrect(inner_x, inner_y, inner_s, inner_s, inner_r, fill=bg),
        (
            f'<text x="{IN(tx):.3f}" y="{IN(ty):.3f}" '
            f'fill="{fg}" font-family="Nunito, Helvetica, Arial, sans-serif" '
            f'font-weight="800" font-size="{font_px:.2f}" '
            f'text-anchor="middle" dominant-baseline="central">{xml_escape(label)}</text>'
        ),
    ]

    if shift is not None:
        shift_scale = SHIFT_SIZE_OVERRIDE.get(key, 0.6)
        shift_px = font_px * shift_scale
        shift_x = inner_x + inner_s * SHIFT_X_OVERRIDE.get(key, 0.27)
        shift_y = inner_y + inner_s * 0.40
        parts.append(
            f'<text x="{IN(shift_x):.3f}" y="{IN(shift_y):.3f}" '
            f'fill="{fg}" font-family="Nunito, Helvetica, Arial, sans-serif" '
            f'font-weight="800" font-size="{shift_px:.2f}" '
            f'text-anchor="middle" dominant-baseline="central">{xml_escape(shift)}</text>'
        )

    return "\n    ".join(parts)


def cut_rect(cx_in: float, cy_in: float, size_in: float) -> str:
    return rrect(cx_in, cy_in, size_in, size_in, CORNER_R_IN,
                 stroke="#FF00FF", stroke_w_pt=CUT_STROKE_PT)


def wordmark() -> str:
    """Light-purple branding text in the empty lower-right grid cells of
    the right panel (m,./ row, cols 4-5)."""
    grid_w = COLS * STICKER_SIZE_IN + (COLS - 1) * CUT_GAP_IN
    grid_h = ROWS * STICKER_SIZE_IN + (ROWS - 1) * CUT_GAP_IN
    x0 = FOLD_X_IN + (FOLD_X_IN - grid_w) / 2
    y0 = (PAGE_H_IN - grid_h) / 2
    step = STICKER_SIZE_IN + CUT_GAP_IN
    # Bounding box spans cols 4-5 of row 3.
    box_x = x0 + 4 * step
    box_y = y0 + 3 * step
    box_w = 2 * STICKER_SIZE_IN + CUT_GAP_IN
    box_h = STICKER_SIZE_IN
    cx = box_x + box_w / 2
    cy = box_y + box_h / 2
    title_px = 17
    url_px   = 13
    return (
        f'<text x="{IN(cx):.3f}" y="{IN(cy):.3f}" fill="#F2E8FA" '
        f'font-family="Nunito, Helvetica, Arial, sans-serif" font-weight="bold" '
        f'font-size="{title_px}" text-anchor="middle" '
        f'dominant-baseline="central" dy="-0.45em">Purple Computer</text>'
        f'<text x="{IN(cx):.3f}" y="{IN(cy):.3f}" fill="#F2E8FA" '
        f'font-family="Nunito, Helvetica, Arial, sans-serif" '
        f'font-size="{url_px}" text-anchor="middle" '
        f'dominant-baseline="central" dy="0.75em">purplecomputer.org</text>'
    )


def build_svg() -> str:
    placements = list(panel_placements(0.0, LEFT_ROWS, align_right=True))
    placements.extend(panel_placements(FOLD_X_IN, RIGHT_ROWS, align_right=False))

    sheet_bg = (
        f'<rect x="0" y="0" width="{IN(PAGE_W_IN)}" height="{IN(PAGE_H_IN)}" '
        f'fill="{PURPLE_HEX}"/>'
    )
    art  = sheet_bg + "\n    " + "\n    ".join(
        sticker_art(k, x, y, s) for k, x, y, s in placements
    ) + "\n    " + wordmark()
    cuts = "\n    ".join(cut_rect(x, y, s)        for _, x, y, s in placements)

    fold_guide = (
        f'<line x1="{IN(FOLD_X_IN)}" y1="0" '
        f'x2="{IN(FOLD_X_IN)}" y2="{IN(PAGE_H_IN)}" '
        f'stroke="#CCCCCC" stroke-width="0.5" stroke-dasharray="4,4"/>'
    )
    page_border = (
        f'<rect x="0.5" y="0.5" '
        f'width="{IN(PAGE_W_IN)-1}" height="{IN(PAGE_H_IN)-1}" '
        f'fill="none" stroke="#CCCCCC" stroke-width="1"/>'
    )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{PAGE_W_IN}in" height="{PAGE_H_IN}in"
     viewBox="0 0 {IN(PAGE_W_IN)} {IN(PAGE_H_IN)}">
  <g inkscape:groupmode="layer" inkscape:label="guides" id="guides">
    {page_border}
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
        cmd = ["inkscape", str(OUT_SVG), "--export-text-to-path", f"--export-filename={OUT_PDF}"]
        try:
            subprocess.run(cmd, check=True)
            print(f"Wrote {OUT_PDF}")
        except FileNotFoundError:
            sys.exit("inkscape not found on PATH; install it or drop --pdf")


if __name__ == "__main__":
    main()
