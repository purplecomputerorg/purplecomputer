#!/usr/bin/env python3
"""Writes purple_tui/canvas/images/instruments/<id>.svg and a 128px .png (needs inkscape),
the Letters switch's names and sounds pictures to images/letters/, and the Tab
switches' paint, notes, abc, front and back pictures to images/modes/, and pictures that stand
in for words in hint lines to images/hints/.
Drawn for the Music header's chips: every part at least ~3px at 24px (16 units of 128).
Usage: just python scripts/instrument_icons.py"""

import subprocess
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

IMAGES = Path(__file__).resolve().parent.parent / "purple_tui" / "canvas" / "images"
FONTS = {w: TTFont(IMAGES.parent / "fonts" / f"Figtree-{w}.ttf") for w in ("Bold", "SemiBold")}  # real type, not hand-drawn strokes
OUT, LETTERS, MODES, HINTS = IMAGES / "instruments", IMAGES / "letters", IMAGES / "modes", IMAGES / "hints"
D, P3, P5, P6 = "#2a1650", "#a379e8", "#dfc9ff", "#f6efff"
W1, W2, W3 = "#b98a72", "#e2ae8c", "#f0c9a6"  # soft wood
U1, U2 = "#d68fc4", "#f2bfe3"  # orchid ukulele
V1 = "#8fa4f0"  # periwinkle accordion


def svg(body, width=128, height=128):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">{body}</svg>\n'


def stick(x1, y1, x2, y2, color, w=7):
    return stroke(f"M{x1} {y1} L{x2} {y2}", color, w)


def stroke(d, color, w):
    """A path drawn as a thick round-ended line."""
    return f'<path d="{d}" stroke="{color}" stroke-width="{w}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'


def marimba():
    out = [stick(18, 70, 10, 120, W1), stick(110, 70, 118, 120, W1)]
    for i in range(4):
        cx = 26 + i * 25.5
        out.append(f'<rect x="{cx-9}" y="66" width="18" height="{50 - i*9}" rx="8" fill="{P5}"/>')
    out.append(f'<rect x="6" y="58" width="116" height="16" rx="6" fill="{W1}"/>')
    for i in range(4):
        x, top = 12 + i * 26, 10 + i * 9
        out.append(f'<path d="M{x+5} {top} h22 l-5 {58-top} h-22 Z" fill="{(W2, W3)[i % 2]}"/>')
        for dx, k in ((9, 0), (17, 1)):  # grain
            y0, y1 = top + 8 + k * 10, 52 - k * 6
            out.append(f'<path d="M{x+dx+5-(y0-top)*5/(58-top):.1f} {y0} q-3 {(y1-y0)/2:.1f} {-(y1-y0)*5/(58-top):.1f} {y1-y0}" fill="none" stroke="{W1}" stroke-width="5" stroke-linecap="round"/>')
    return svg("".join(out))


def ukulele():
    body = '<circle cx="64" cy="66" r="24"/><circle cx="64" cy="98" r="30"/>'
    return svg(f'<g transform="rotate(30 64 64) translate(0 -2)">'
               f'<rect x="51" y="-4" width="26" height="26" rx="8" fill="{U1}"/>'
               f'<rect x="56" y="16" width="16" height="40" fill="{W1}"/>'
               f'<g fill="{U2}">{body}</g>'
               f'<circle cx="64" cy="74" r="11" fill="{D}"/>'
               f'<rect x="48" y="104" width="32" height="9" rx="4" fill="{D}"/></g>')


def accordion():
    out = []
    xs = [34 + i * 9.5 for i in range(7)]  # bellows: one light block, folds as zigzag edges and lines
    top = " ".join(f"{x:.1f},{(22, 14)[i % 2]}" for i, x in enumerate(xs))
    bottom = " ".join(f"{x:.1f},{(106, 114)[i % 2]}" for i, x in reversed(list(enumerate(xs))))
    out.append(f'<polygon points="{top} {bottom}" fill="{P5}"/>')
    out += [f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{(22, 14)[i % 2]}" y2="{(106, 114)[i % 2]}" stroke="{D}" stroke-width="4"/>' for i, x in enumerate(xs[1:-1], 1)]
    for x in (4, 90):
        out.append(f'<rect x="{x}" y="10" width="34" height="108" rx="8" fill="{V1}"/>')
    for y in (34, 64, 94):
        out.append(f'<circle cx="21" cy="{y}" r="8" fill="{P6}"/>')
    out.append(f'<rect x="97" y="18" width="20" height="92" rx="4" fill="{P6}"/>')
    for y in (36, 62, 88):
        out.append(f'<rect x="97" y="{y-6}" width="12" height="12" rx="2" fill="{D}"/>')
    return svg("".join(out))


def glockenspiel():
    out = [f'<path d="M6 22 L122 40 L122 104 L6 122 Z" fill="{P3}"/>']
    for i in range(5):
        x, half = 14 + i * 21, 42 - i * 6.5
        out.append(f'<rect x="{x}" y="{72-half:.1f}" width="16" height="{2*half:.1f}" rx="5" fill="{P6}"/>')
        out.append(f'<rect x="{x+4}" y="{72-half+5:.1f}" width="4" height="{2*half-10:.1f}" rx="2" fill="#ffffff"/>')
    out.append(f'<path d="M106 0 L112 14 L126 20 L112 26 L106 40 L100 26 L86 20 L100 14 Z" fill="{P6}"/>')
    return svg("".join(out))


ROUND = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
WAVE = f'stroke-width="8" {ROUND}'
INK, SKIN, HAIR, CHEEK = "#3b2470", "#f6efff", "#c08a64", "#f2b8d8"  # the calm set: flat, no outlines
TILES = ("#dfc9ff", "#f6c9e4", "#c9dcff")


def glyph(ch, cx, cy, cap, fill, weight="Bold"):
    """One letter in Figtree, its capitals cap units tall, centered on (cx, cy)."""
    font = FONTS[weight]
    glyphs = font.getGlyphSet()
    shape = glyphs[font.getBestCmap()[ord(ch)]]
    k, bounds = cap / font["OS/2"].sCapHeight, BoundsPen(glyphs)
    shape.draw(bounds)
    x0, y0, x1, y1 = bounds.bounds
    pen = SVGPathPen(glyphs)
    shape.draw(TransformPen(pen, (k, 0, 0, -k, cx - (x0 + x1) / 2 * k, cy + (y0 + y1) / 2 * k)))
    return f'<path d="{pen.getCommands()}" fill="{fill}"/>'


def block(x, y, size, fill, letter):
    """An alphabet tile: a soft rounded square with a dark letter."""
    return (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{size // 4}" fill="{fill}"/>'
            + glyph(letter, x + size / 2, y + size / 2, size * 0.5, INK))


def names():
    """Two alphabet tiles, A in front of B, B cut back so a clear gap runs round A."""
    return svg('<mask id="gap"><rect width="128" height="128" fill="#fff"/><rect x="0" y="40" width="88" height="88" rx="26"/></mask>'
               f'<g mask="url(#gap)">{block(50, 6, 70, TILES[1], "B")}</g>' + block(8, 48, 72, TILES[0], "A"))


def abc(fill=TILES[0]):
    """Letters in the Tab switches: A B C written out, all the same size, no tiles (that's Names)."""
    return svg("".join(glyph(ch, 22 + i * 32, 35, 36, fill, "SemiBold") for i, ch in enumerate("ABC")), 108, 70)


def abc_dark():
    """The same letters for the alert, whose light plate washes out the light ones."""
    return abc("#5b3a9e")


def paint():
    """A painter's palette, wide, with dabs of paint and a thumb hole."""
    dabs = (("#ff8f8f", 34, 48), ("#ffd27a", 62, 32), ("#86c5ff", 92, 40), ("#8fdcaa", 100, 70))
    return svg(f'<path fill-rule="evenodd" fill="{TILES[0]}" transform="scale(1.3 1) translate(-4 -8)"'
               ' d="M64 12 C106 12 122 40 118 66 C114 90 96 88 84 82 C72 76 62 86 70 100 C78 114 58 118 44 114'
               ' C18 106 6 86 8 62 C10 34 30 12 64 12 Z M28 84 a10 10 0 1 0 20 0 a10 10 0 1 0 -20 0 Z"/>'
               + "".join(f'<circle cx="{(x - 4) * 1.3:.0f}" cy="{y - 8}" r="11" fill="{c}"/>' for c, x, y in dabs), 156, 112)


def notes():
    """Three eighth notes joined by a beam, climbing: wide enough to sit beside A B C."""
    stems = ((40, 34, 100), (92, 24, 90), (144, 14, 80))
    return svg(f'<g fill="{TILES[0]}"><path d="M40 34 L153 14 V30 L40 50 Z"/>'
               + "".join(f'<rect x="{x}" y="{top}" width="9" height="{foot - top}" rx="4"/>'
                         f'<ellipse cx="{x - 8}" cy="{foot}" rx="17" ry="12.5" transform="rotate(-20 {x - 8} {foot})"/>'
                         for x, top, foot in stems) + '</g>', 172)


def clip(x, y, turn):
    """A little hair clip; it swaps sides when the head turns round."""
    return f'<rect x="{x - 9}" y="{y - 5}" width="18" height="10" rx="5" fill="{CHEEK}" transform="rotate({turn} {x} {y})"/>'


def pigtails():
    """Two bunches out the sides, the same from the front and the back."""
    return "".join(f'<ellipse cx="{x}" cy="78" rx="11" ry="17" fill="{HAIR}" transform="rotate({t} {x} 78)"/>'
                   f'<circle cx="{x + d}" cy="64" r="6" fill="{CHEEK}"/>' for x, t, d in ((16, 18, 6), (112, -18, -6)))


def face(mouth):
    """A calm face under a bob of hair: dot eyes, rosy cheeks, a clip, and mouth."""
    return (pigtails() + f'<rect x="22" y="16" width="84" height="82" rx="40" fill="{HAIR}"/>'
            f'<circle cx="64" cy="70" r="34" fill="{SKIN}"/>'
            f'<path d="M28 66 C26 18 102 18 100 66 C88 52 76 48 64 52 C52 48 40 52 28 66 Z" fill="{HAIR}"/>'
            f'<circle cx="52" cy="74" r="4.5" fill="{INK}"/><circle cx="76" cy="74" r="4.5" fill="{INK}"/>'
            f'<circle cx="43" cy="86" r="6" fill="{CHEEK}"/><circle cx="85" cy="86" r="6" fill="{CHEEK}"/>'
            + clip(40, 40, -30) + mouth)


def front():
    """Blocks seen from the front: a smiling face."""
    return svg(face(f'<path d="M55 89 Q64 97 73 89" stroke="{INK}" stroke-width="4.5" fill="none" stroke-linecap="round"/>'))


def back():
    """Blocks seen from the back: the same head from behind, all hair over the neck, the clip on the other side."""
    return svg('<rect x="50" y="90" width="28" height="28" rx="12" fill="#e6d8fb"/>' + pigtails()
               + f'<rect x="22" y="16" width="84" height="88" rx="40" fill="{HAIR}"/>' + clip(88, 40, 30))


def sounds():
    """Letter sounds: the A tile from Names, saying its sound."""
    return svg(block(6, 28, 72, TILES[0], "A") + f'<path d="M92 50 A8 14 0 0 1 92 78" stroke="{TILES[1]}" {WAVE}/>'
               f'<path d="M106 38 A13 26 0 0 1 106 90" stroke="{TILES[2]}" {WAVE}/>')


RAINBOW = ("#ff8f8f", "#ffd27a", "#8fdcaa", "#86c5ff", "#c39cf7")


def rainbow():
    """Left and Right in the color bar: along the colors."""
    return svg("".join(f'<path d="M{64 - r} 66 A{r} {r} 0 0 1 {64 + r} 66" stroke="{c}" stroke-width="9" {ROUND}/>'
                       for c, r in zip(RAINBOW, (56, 46, 36, 26, 16))), 128, 72)


def sun_at(r, rays, color, width):
    spokes = "".join(f'M{64 + rays[0] * dx:.1f} {64 + rays[0] * dy:.1f} L{64 + rays[1] * dx:.1f} {64 + rays[1] * dy:.1f} '
                     for dx, dy in ((1, 0), (0.71, 0.71), (0, 1), (-0.71, 0.71), (-1, 0), (-0.71, -0.71), (0, -1), (0.71, -0.71)))
    return svg(f'<circle cx="64" cy="64" r="{r}" fill="{color}"/><path d="{spokes}" stroke="{color}" stroke-width="{width}" {ROUND}/>')


def lighter():
    """Up in the color bar: a big bright sun."""
    return sun_at(26, (38, 56), "#ffd27a", 9)


def darker():
    """Down in the color bar: a small dim sun."""
    return sun_at(15, (24, 34), "#a99a7a", 7)


def keep():
    """Keep, yes, open: a check on a mint circle, partner of go_back()."""
    return svg(f'<circle cx="64" cy="64" r="52" fill="{RAINBOW[2]}"/><path d="M40 66 L57 82 L90 46" stroke="{INK}" stroke-width="11" {ROUND}/>')


def go_back():
    """Never mind, cancel, close: a turn-back arrow on a lavender circle, partner of keep()."""
    return svg(f'<circle cx="64" cy="64" r="52" fill="{RAINBOW[4]}"/>'
               f'<path d="M86 86 V68 Q86 48 66 48 H42 M56 34 L42 48 L56 62" stroke="{INK}" stroke-width="11" {ROUND}/>')


def up():
    """Enter in Blocks: a block goes on top of a block."""
    return svg(f'<rect x="8" y="70" width="52" height="52" rx="12" fill="{TILES[2]}"/>'
               f'<rect x="8" y="10" width="52" height="52" rx="12" fill="{TILES[0]}" opacity="0.55"/>'
               f'<path d="M104 104 V24 M88 40 L104 24 L120 40" stroke="{RAINBOW[4]}" stroke-width="10" {ROUND}/>')


def loop():
    """Hold Enter in Music: two rounded arrows chasing each other round, a music player's repeat."""
    return svg(f'<path d="M14 40 V34 Q14 14 34 14 H104 M94 2 L108 14 L94 26" stroke="{TILES[0]}" stroke-width="10" {ROUND}/>'
               f'<path d="M122 56 V62 Q122 82 102 82 H32 M42 70 L28 82 L42 94" stroke="{TILES[0]}" stroke-width="10" {ROUND}/>', 136, 96)


def new_line():
    """Enter in Art's writing: down and back to the start of the line."""
    return svg(f'<path d="M92 32 V68 Q92 76 84 76 H42 M56 62 L41 76 L56 90" stroke="{TILES[0]}" stroke-width="9" {ROUND}/>')


def play():
    """Space while Music records: play it back."""
    return svg(f'<path d="M40 22 L104 64 L40 106 Z" fill="{RAINBOW[2]}" stroke="{RAINBOW[2]}" stroke-width="14" stroke-linejoin="round"/>')


def stop():
    """Esc while Music records or loops: stop."""
    return svg(f'<rect x="26" y="26" width="76" height="76" rx="18" fill="{RAINBOW[0]}"/>')


def render(draw, folder):
    folder.mkdir(exist_ok=True)
    svg_path = folder / f"{draw.__name__}.svg"
    svg_path.write_text(draw())
    subprocess.run(["inkscape", str(svg_path), "-h", "128", "-o", str(svg_path.with_suffix(".png"))],
                   check=True, capture_output=True)


if __name__ == "__main__":
    for draw in (marimba, ukulele, accordion, glockenspiel):
        render(draw, OUT)
    for draw in (names, sounds):
        render(draw, LETTERS)
    for draw in (paint, notes, abc, abc_dark, front, back):
        render(draw, MODES)
    for draw in (rainbow, lighter, darker, keep, go_back, up, loop, new_line, play, stop):
        render(draw, HINTS)
