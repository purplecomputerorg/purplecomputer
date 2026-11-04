#!/usr/bin/env python3
"""Writes purple_tui/canvas/images/instruments/<id>.svg and a 128px .png (needs inkscape).
Drawn for the Music header's chips: every part at least ~3px at 24px (16 units of 128).
Usage: just python scripts/instrument_icons.py"""

import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "purple_tui" / "canvas" / "images" / "instruments"
D, P1, P2, P3, P4, P5, P6 = "#2a1650", "#6a3fb0", "#8656d0", "#a379e8", "#c39cf7", "#dfc9ff", "#f6efff"
W1, W2, W3 = "#6e3560", "#b0628f", "#cc80ab"  # plum wood
U1, U2 = "#9a4e8e", "#dc93cf"  # orchid ukulele
V1 = "#5d5ad6"  # blue-violet accordion
O = f'stroke="{D}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"'
O5 = O.replace('"7"', '"5"')


def svg(body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">{body}</svg>\n'


def stick(x1, y1, x2, y2, color, w=7):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{D}" stroke-width="{w + 8}" stroke-linecap="round"/>'
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>')


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


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for draw in (marimba, ukulele, accordion, glockenspiel):
        svg_path = OUT / f"{draw.__name__}.svg"
        svg_path.write_text(draw())
        subprocess.run(["inkscape", str(svg_path), "-w", "128", "-h", "128", "-o", str(svg_path.with_suffix(".png"))],
                       check=True, capture_output=True)
