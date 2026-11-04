#!/usr/bin/env python3
"""Writes purple_tui/canvas/images/instruments/<id>.svg and a 128px .png (needs inkscape),
the Letters switch's names and sounds pictures to images/letters/, and the Tab
switches' paint, notes, abc, front and back pictures to images/modes/, and pictures that stand
in for words in hint lines to images/hints/.
Drawn for the Music header's chips: every part at least ~3px at 24px (16 units of 128).
Usage: just python scripts/instrument_icons.py"""

import subprocess
from pathlib import Path

IMAGES = Path(__file__).resolve().parent.parent / "purple_tui" / "canvas" / "images"
OUT, LETTERS, MODES, HINTS = IMAGES / "instruments", IMAGES / "letters", IMAGES / "modes", IMAGES / "hints"
D, P1, P2, P3, P4, P5, P6 = "#2a1650", "#6a3fb0", "#8656d0", "#a379e8", "#c39cf7", "#dfc9ff", "#f6efff"
W1, W2, W3 = "#6e3560", "#b0628f", "#cc80ab"  # plum wood
U1, U2 = "#9a4e8e", "#dc93cf"  # orchid ukulele
V1 = "#5d5ad6"  # blue-violet accordion
O = f'stroke="{D}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"'
O5 = O.replace('"7"', '"5"')


def svg(body, width=128, height=128):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">{body}</svg>\n'


def stick(x1, y1, x2, y2, color, w=7):
    return stroke(f"M{x1} {y1} L{x2} {y2}", color, w)


def stroke(d, color, w):
    """A path drawn as a thick line with the dark outline around it."""
    line = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    return f'<path d="{d}" stroke="{D}" stroke-width="{w + 8}" {line}/><path d="{d}" stroke="{color}" stroke-width="{w}" {line}/>'


def marimba():
    out = [stick(18, 70, 10, 120, W1), stick(110, 70, 118, 120, W1)]
    for i in range(4):
        cx = 26 + i * 25.5
        out.append(f'<rect x="{cx-9}" y="66" width="18" height="{50 - i*9}" rx="8" fill="{P5}" {O}/>')
    out.append(f'<rect x="6" y="58" width="116" height="16" rx="6" fill="{W1}" {O}/>')
    for i in range(4):
        x, top = 12 + i * 26, 10 + i * 9
        out.append(f'<path d="M{x+5} {top} h22 l-5 {58-top} h-22 Z" fill="{(W2, W3)[i % 2]}" {O}/>')
        for dx, k in ((9, 0), (17, 1)):  # grain
            y0, y1 = top + 8 + k * 10, 52 - k * 6
            out.append(f'<path d="M{x+dx+5-(y0-top)*5/(58-top):.1f} {y0} q-3 {(y1-y0)/2:.1f} {-(y1-y0)*5/(58-top):.1f} {y1-y0}" fill="none" stroke="{W1}" stroke-width="5" stroke-linecap="round"/>')
    return svg("".join(out))


def ukulele():
    body = '<circle cx="64" cy="66" r="24"/><circle cx="64" cy="98" r="30"/>'
    return svg(f'<g transform="rotate(30 64 64) translate(0 -2)">'
               f'<rect x="51" y="-4" width="26" height="26" rx="8" fill="{U1}" {O}/>'
               f'<rect x="56" y="16" width="16" height="40" fill="{W1}" {O}/>'
               f'<g stroke="{D}" stroke-width="14" fill="{D}">{body}</g><g fill="{U2}">{body}</g>'
               f'<circle cx="64" cy="74" r="11" fill="{D}"/>'
               f'<rect x="48" y="104" width="32" height="9" rx="4" fill="{D}"/></g>')


def accordion():
    out = []
    xs = [34 + i * 9.5 for i in range(7)]  # bellows: one light block, folds as zigzag edges and lines
    top = " ".join(f"{x:.1f},{(22, 14)[i % 2]}" for i, x in enumerate(xs))
    bottom = " ".join(f"{x:.1f},{(106, 114)[i % 2]}" for i, x in reversed(list(enumerate(xs))))
    out.append(f'<polygon points="{top} {bottom}" fill="{P5}" {O}/>')
    out += [f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{(22, 14)[i % 2]}" y2="{(106, 114)[i % 2]}" stroke="{D}" stroke-width="4"/>' for i, x in enumerate(xs[1:-1], 1)]
    for x in (4, 90):
        out.append(f'<rect x="{x}" y="10" width="34" height="108" rx="8" fill="{V1}" {O}/>')
    for y in (34, 64, 94):
        out.append(f'<circle cx="21" cy="{y}" r="8" fill="{P6}" {O5}/>')
    out.append(f'<rect x="97" y="18" width="20" height="92" rx="4" fill="{P6}" {O5}/>')
    for y in (36, 62, 88):
        out.append(f'<rect x="97" y="{y-6}" width="12" height="12" rx="2" fill="{D}"/>')
    return svg("".join(out))


def glockenspiel():
    out = [f'<path d="M6 22 L122 40 L122 104 L6 122 Z" fill="{P1}" {O}/>']
    for i in range(5):
        x, half = 14 + i * 21, 42 - i * 6.5
        out.append(f'<rect x="{x}" y="{72-half:.1f}" width="16" height="{2*half:.1f}" rx="5" fill="{P6}" {O5}/>')
        out.append(f'<rect x="{x+4}" y="{72-half+5:.1f}" width="4" height="{2*half-10:.1f}" rx="2" fill="#ffffff"/>')
    out.append(f'<path d="M106 0 L112 14 L126 20 L112 26 L106 40 L100 26 L86 20 L100 14 Z" fill="{P6}" stroke="{D}" stroke-width="5" stroke-linejoin="round"/>')
    return svg("".join(out))


INK, SKIN, HAIR, CHEEK = "#3b2470", "#f6efff", "#c08a64", "#f2b8d8"  # the calm set: flat, no outlines
TILES = ("#dfc9ff", "#f6c9e4", "#c9dcff")
A, B, C = "M16 52 L32 12 L48 52 M21 40 H43", "M20 14 V50 H35 A9 9 0 0 0 35 32 H20 M20 14 H33 A9 9 0 0 1 33 32", \
    "M46 21 A17 17 0 1 0 46 45"


def block(x, y, size, fill, letter):
    """An alphabet tile: a soft rounded square with a thin dark letter."""
    return f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{size // 4}" fill="{fill}"/>' + (
        f'<path d="{letter}" transform="translate({x + size * 0.1} {y + size * 0.1}) scale({size * 0.8 / 64})"'
        f' stroke="{INK}" stroke-width="7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')


def names():
    """Two alphabet tiles, A in front of B, B cut back so a clear gap runs round A."""
    return svg('<mask id="gap"><rect width="128" height="128" fill="#fff"/><rect x="0" y="40" width="88" height="88" rx="26"/></mask>'
               f'<g mask="url(#gap)">{block(50, 6, 70, TILES[1], B)}</g>' + block(8, 48, 72, TILES[0], A))


def abc():
    """Letters: three alphabet tiles in a row."""
    return svg("".join(block(4 + i * 84, 4, 72, TILES[i], d) for i, d in enumerate((A, B, C))), 248, 80)


def paint():
    """A painter's palette with dabs of paint and a thumb hole."""
    dabs = (("#ff8f8f", 34, 48), ("#ffd27a", 62, 32), ("#86c5ff", 92, 40), ("#8fdcaa", 100, 70))
    return svg(f'<path fill-rule="evenodd" fill="{TILES[0]}" d="M64 12 C106 12 122 40 118 66 C114 90 96 88 84 82'
               ' C72 76 62 86 70 100 C78 114 58 118 44 114 C18 106 6 86 8 62 C10 34 30 12 64 12 Z'
               ' M28 84 a10 10 0 1 0 20 0 a10 10 0 1 0 -20 0 Z"/>'
               + "".join(f'<circle cx="{x}" cy="{y}" r="11" fill="{c}"/>' for c, x, y in dabs))


def notes():
    """Two eighth notes joined by a beam."""
    return svg(f'<g fill="{TILES[0]}"><path d="M46 28 L110 14 V32 L46 46 Z"/>'
               '<rect x="46" y="28" width="9" height="70" rx="4"/><rect x="101" y="14" width="9" height="72" rx="4"/>'
               '<ellipse cx="38" cy="98" rx="18" ry="13" transform="rotate(-20 38 98)"/>'
               '<ellipse cx="93" cy="86" rx="18" ry="13" transform="rotate(-20 93 86)"/></g>')


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
    """The same face saying something out loud: an open mouth and soft sound waves."""
    wave = 'fill="none" stroke-width="7" stroke-linecap="round"'
    mouth = f'<ellipse cx="64" cy="92" rx="8" ry="6" fill="{INK}"/>'
    return svg(f'<g transform="translate(-4 10) scale(0.84)">{face(mouth)}</g>'
               f'<path d="M106 54 A8 14 0 0 1 106 82" stroke="{TILES[0]}" {wave}/>'
               f'<path d="M117 42 A13 26 0 0 1 117 94" stroke="{TILES[1]}" {wave}/>')


ROUND = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
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
    """Never mind, cancel, close: a turn-back arrow on a peach circle, partner of keep()."""
    return svg(f'<circle cx="64" cy="64" r="52" fill="#ffb899"/>'
               f'<path d="M86 86 V68 Q86 48 66 48 H42 M56 34 L42 48 L56 62" stroke="{INK}" stroke-width="11" {ROUND}/>')


def up():
    """Enter in Blocks: a block goes on top of a block."""
    return svg(f'<rect x="20" y="70" width="52" height="52" rx="12" fill="{TILES[2]}"/>'
               f'<rect x="20" y="10" width="52" height="52" rx="12" fill="{TILES[0]}" opacity="0.55"/>'
               f'<path d="M100 104 V24 M84 40 L100 24 L116 40" stroke="{RAINBOW[1]}" stroke-width="10" {ROUND}/>')


def loop():
    """Hold Enter in Music: round and round, an arrow chasing its tail."""
    return svg(f'<path d="M100 74 A38 38 0 1 1 88 36" stroke="{TILES[0]}" stroke-width="12" {ROUND}/>'
               f'<path d="M70 26 L94 30 L88 54 Z" fill="{TILES[0]}" stroke="{TILES[0]}" stroke-width="6" stroke-linejoin="round"/>')


def brush(lift):
    """A brush over a dab of paint, its tip lift units above it."""
    tip = (f'<g transform="translate(0 {-lift})"><path d="M100 30 L58 74" stroke="{W3}" stroke-width="12" {ROUND}/>'
           f'<path d="M60 64 L72 76 L50 100 C42 106 34 104 36 94 Z" fill="{TILES[0]}" stroke="{TILES[0]}" stroke-width="6"'
           f' stroke-linejoin="round"/><path d="M42 100 C38 104 46 108 50 102" fill="{RAINBOW[0]}"/></g>')
    return svg(f'<ellipse cx="46" cy="112" rx="38" ry="11" fill="{RAINBOW[0]}" opacity="{1 if not lift else 0.45}"/>' + tip)


def brush_down():
    """Space in Art: the brush tip down on a dab of paint."""
    return brush(0)


def brush_up():
    """Space with the brush down: it lifts off the paint."""
    return brush(22)


def new_line():
    """Enter in Art's writing: down and back to the start of the line."""
    return svg(f'<path d="M104 18 V70 Q104 82 92 82 H32 M52 60 L30 82 L52 104" stroke="{TILES[0]}" stroke-width="12" {ROUND}/>')


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
    for draw in (paint, notes, abc, front, back):
        render(draw, MODES)
    for draw in (rainbow, lighter, darker, keep, go_back, up, loop, brush_down, brush_up, new_line, play, stop):
        render(draw, HINTS)
