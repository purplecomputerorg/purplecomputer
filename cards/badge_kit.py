"""Shared geometry, palette, and SVG helpers for the badge stickers.

`make_lid_badge.py` and `make_name_badge.py` draw the same 3.5" x 2.25"
kiss-cut card: same bleed, same cut spec, same purple ramp, same bot. All of
that lives here so the two cannot drift apart.

Coordinates in the drawing helpers are inches from the sticker's own
top-left corner, so a layout never has to think about the bleed.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

CARDS = Path(__file__).parent
ROOT = CARDS.parent

PX = 96.0
def IN(x: float) -> float:
    return x * PX

# Card: standard "hello my name is" badge, kiss-cut with a rounded corner.
STICKER_W_IN  = 3.5
STICKER_H_IN  = 2.25
CORNER_R_IN   = 0.1875
BLEED_IN      = 0.125   # the purple field runs to the cut, so it has to bleed
CUT_STROKE_PX = 1.0

PAGE_W_IN = STICKER_W_IN + 2 * BLEED_IN
PAGE_H_IN = STICKER_H_IN + 2 * BLEED_IN

# Palette (site tokens: light fill, primary, magenta accent, border).
FIELD     = "#ebe2fd"
INK       = "#5c2d91"
INK_DEEP  = "#3b1a5c"
RULE      = "#9b59d0"
BORDER    = "#c4aee0"
WHITE     = "#FFFFFF"
CUT_COLOR = "#FF00FF"

# Nunito is the print-card face; the rest are the site's own, copied from
# ~/landing/public/fonts into ~/.local/share/fonts to render locally. PDF
# export turns text into paths, so the print shop needs none of them.
NUNITO   = "Nunito, Helvetica, Arial, sans-serif"
SORA_XB  = "Sora ExtraBold, Sora, Helvetica, sans-serif"
SORA_SB  = "Sora SemiBold, Sora, Helvetica, sans-serif"
FIGTREE  = "Figtree Medium, Figtree, Helvetica, sans-serif"
SPECTRAL = "Spectral Medium, Georgia, serif"

# Bot bbox in logo.svg's native 200x200 space (antenna balls to feet).
BOT_BBOX = (55.0, 41.0, 145.0, 170.0)

# Bot recolors: the logo's own face is FIELD, which vanishes on a FIELD
# background, and its dark half vanishes on an INK band.
ON_FIELD = {FIELD: WHITE}
ON_INK   = {INK: FIELD, RULE: BORDER, FIELD: INK}


# ---------- drawing (sticker space: inches from the sticker's top-left) ----------

def px_x(v: float) -> float:
    return IN(BLEED_IN + v)

def px_y(v: float) -> float:
    return IN(BLEED_IN + v)


def rect(x_in, y_in, w_in, h_in, r_in=0.0, **attrs) -> str:
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    r = f' rx="{IN(r_in):.3f}" ry="{IN(r_in):.3f}"' if r_in else ""
    return (f'<rect x="{px_x(x_in):.3f}" y="{px_y(y_in):.3f}" '
            f'width="{IN(w_in):.3f}" height="{IN(h_in):.3f}"{r} {a}/>')


def rule_line(x1_in, x2_in, y_in, width_px=2.4, color=RULE) -> str:
    return (f'<line x1="{px_x(x1_in):.3f}" y1="{px_y(y_in):.3f}" '
            f'x2="{px_x(x2_in):.3f}" y2="{px_y(y_in):.3f}" '
            f'stroke="{color}" stroke-width="{width_px}" stroke-linecap="round"/>')


def text(s, x_in, y_in, size, weight=700, fill=INK, anchor="middle",
         tracking=None, font=NUNITO, italic=False) -> str:
    extra = f' letter-spacing="{tracking}"' if tracking else ""
    if italic:
        extra += ' font-style="italic"'
    return (f'<text x="{px_x(x_in):.3f}" y="{px_y(y_in):.3f}" fill="{fill}" '
            f'font-family="{font}" font-weight="{weight}" font-size="{size}" '
            f'text-anchor="{anchor}" dominant-baseline="central"{extra}>{s}</text>')


def bot(cx_in, cy_in, h_in, colors=ON_FIELD) -> str:
    """The logo bot, scaled to h_in tall and centered on (cx_in, cy_in)."""
    src = (ROOT / "assets/logo.svg").read_text()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", src, re.DOTALL).group(1)
    inner = re.sub(r"#[0-9a-fA-F]{6}",
                   lambda m: colors.get(m.group(0).lower(), m.group(0)), inner)
    minx, miny, maxx, maxy = BOT_BBOX
    scale = IN(h_in) / (maxy - miny)
    tx = px_x(cx_in) - (minx + maxx) / 2 * scale
    ty = px_y(cy_in) - (miny + maxy) / 2 * scale
    return f'<g transform="translate({tx:.3f} {ty:.3f}) scale({scale:.5f})">{inner}</g>'


# ---------- document ----------

def build_page(content: str, clip_id: str = "card") -> str:
    """Bleed, art and cut layers for one card, sized PAGE_W_IN x PAGE_H_IN."""
    card_r = IN(CORNER_R_IN)
    card = (f'<rect x="{IN(BLEED_IN):.3f}" y="{IN(BLEED_IN):.3f}" '
            f'width="{IN(STICKER_W_IN):.3f}" height="{IN(STICKER_H_IN):.3f}" '
            f'rx="{card_r:.3f}" ry="{card_r:.3f}"')
    return f'''  <defs>
    <clipPath id="{clip_id}">{card}/></clipPath>
  </defs>
  <g inkscape:groupmode="layer" inkscape:label="art" id="art">
    <rect x="0" y="0" width="{IN(PAGE_W_IN)}" height="{IN(PAGE_H_IN)}"
          rx="{card_r + IN(BLEED_IN):.3f}" ry="{card_r + IN(BLEED_IN):.3f}" fill="{FIELD}"/>
    <g clip-path="url(#{clip_id})">
      <rect x="{IN(BLEED_IN):.3f}" y="{IN(BLEED_IN):.3f}"
            width="{IN(STICKER_W_IN):.3f}" height="{IN(STICKER_H_IN):.3f}" fill="{FIELD}"/>
      {content}
    </g>
  </g>
  <g inkscape:groupmode="layer" inkscape:label="cut" id="cut">
    {card} fill="none" stroke="{CUT_COLOR}" stroke-width="{CUT_STROKE_PX}"/>
  </g>'''


def build_svg(content: str) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{PAGE_W_IN}in" height="{PAGE_H_IN}in"
     viewBox="0 0 {IN(PAGE_W_IN)} {IN(PAGE_H_IN)}">
{build_page(content)}
</svg>
'''


def build_sheet(layouts, names, cols=2, gap_in=0.3) -> str:
    """Every named layout tiled on one page, for picking between them."""
    rows = -(-len(names) // cols)
    w = cols * PAGE_W_IN + (cols + 1) * gap_in
    h = rows * PAGE_H_IN + (rows + 1) * gap_in
    tiles = []
    for i, name in enumerate(names):
        tx = IN(gap_in + (i % cols) * (PAGE_W_IN + gap_in))
        ty = IN(gap_in + (i // cols) * (PAGE_H_IN + gap_in))
        tiles.append(f'<g transform="translate({tx:.2f} {ty:.2f})">'
                     f'{build_page(layouts[name](), clip_id=f"card{i}")}</g>')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="{w}in" height="{h}in" viewBox="0 0 {IN(w)} {IN(h)}">
  <rect x="0" y="0" width="{IN(w)}" height="{IN(h)}" fill="#faf8f5"/>
  {"".join(tiles)}
</svg>
'''


def run_inkscape(cmd) -> None:
    try:
        subprocess.run(["inkscape", *cmd], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        sys.exit("inkscape not found on PATH")


def cli(layouts, prefix: str, doc: str = "", note: str = "") -> None:
    """Shared command line: write SVGs, and optionally PDFs, PNGs, a sheet."""
    ap = argparse.ArgumentParser(description=doc)
    ap.add_argument("variant", nargs="?", default="all", choices=[*layouts, "all"])
    ap.add_argument("--pdf", action="store_true", help="Also render PDF via Inkscape.")
    ap.add_argument("--png", metavar="DIR", help="Also render preview PNGs into DIR.")
    ap.add_argument("--sheet", metavar="PNG", help="Tile every variant onto one PNG.")
    args = ap.parse_args()

    names = list(layouts) if args.variant == "all" else [args.variant]
    print(f'sticker: {STICKER_W_IN}" x {STICKER_H_IN}", bleed {BLEED_IN}", '
          f'corner {CORNER_R_IN}"')
    if note:
        print(note)

    for name in names:
        svg = CARDS / f"{prefix}-{name}.svg"
        svg.write_text(build_svg(layouts[name]()))
        print(f"Wrote {svg.name}")
        if args.pdf:
            run_inkscape([str(svg), "--export-text-to-path",
                          f"--export-filename={CARDS / f'{prefix}-{name}.pdf'}"])
        if args.png:
            out = Path(args.png) / f"{prefix}-{name}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            run_inkscape([str(svg), "--export-type=png", "--export-width=900",
                          "--export-background=#faf8f5", f"--export-filename={out}"])

    if args.sheet:
        tmp = CARDS / f".{prefix}-sheet.svg"
        tmp.write_text(build_sheet(layouts, names))
        run_inkscape([str(tmp), "--export-type=png", "--export-width=1500",
                      f"--export-filename={args.sheet}"])
        tmp.unlink()
        print(f"Wrote {args.sheet}")
