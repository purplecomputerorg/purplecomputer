"""Blocks' guide: two quiet columns of pictures in the room's empty sides, how to build on the left and
how to look around on the right, each row the keys beside what they do. It is painted under the build,
at half strength, and a row comes up to full while its key is held. guides/blocks-cursor.md"""

import math
from functools import lru_cache

import pygame

from .. import palette as P
from ..gfx import rgb
from ..palette import get_key_color
from ..ui import DOWN, LEFT, RIGHT, UP, draw_key, keycap_size
from . import art_room
from .blocks_view import DEPTH, HEIGHT, REST_PITCH, WIDTH, Camera, Painter

QUIET, LIT = 150, 255          # a row's alpha, and while its key is held
MIN_W = 13                     # vw: a side narrower than this shows no column
REACH = 1.7                    # cells on screen from the cursor's middle to the right edge of its bubble and keys
BUILD, LOOK = "build", "look"
# Each row: (name, keys, picture, words). Keys are names, "+", "arrows" (the four, as on the keyboard),
# and "hold X"; a picture is an image name or a little scene: (blocks, wire boxes, cell it centers on, height,
# a drop: (how high the falling block is, its key), a lifted floor's height, and an arrow: (from, to) points),
# drawn as the room draws them. Rows sharing a name are one group: they light together, and a row without
# words or a picture leaves them to the next.
ROWS = {
    BUILD: ("Build", [
        ("type", ["A", "Z"], ({}, [], (1, 1), 1.5, (1.0, "a")), "letters drop blocks"),
        ("move", ["arrows"], ({}, [((0, 1, 0), 70), ((1, 1, 0), 255)], (0.5, 1), 0.5, None, None,
                  ((0.2, 0, 0.5), (1.9, 0, 0.5))), "move around the floor"),
        ("lift", ["Enter"], ({}, [((1, 1, 2), 255)], (1.6, 0.7), 1.5, None, 2, ((3.2, 0.2, -0.1), (3.2, 1.9, -0.1))), ""),
        ("lift", ["hold Shift", "+", UP, DOWN], None, "raise the floor"),
        ("lift", ["hold Enter"], None, "back down"),
    ]),
    LOOK: ("Look around", [
        ("turn", ["Tab"], "hints/turn.png", "tap to turn"),
        ("look", ["hold Tab", "+", "arrows"], "hints/look.png", "hold, press arrows"),
    ]),
}


def columns(size, code: bool, min_w: int, top: float, tilts: tuple) -> dict:
    """{column: rect} in the layer's pixels, in the sides the floor leaves free at every angle it can be
    seen from, so the columns hold still while the view moves: no Build while the code line takes the
    letters and arrows. Look stands clear of the cursor too where that leaves it room; Build doesn't, so
    its wider keys keep room for their pictures."""
    w, h = size
    pad = round(h * 0.03)
    left, right, cursor = _span(size, top, tilts)
    left, right = left - 2 * pad, cursor if w - cursor - pad >= min_w else right + 2 * pad
    spots = {BUILD: pygame.Rect(pad, pad, left - pad, h - 2 * pad), LOOK: pygame.Rect(right, pad, w - right - pad, h - 2 * pad)}
    return {k: r for k, r in spots.items() if r.w >= min_w and not (code and k == BUILD)}


@lru_cache(maxsize=4)
def _span(size, top: float, tilts: tuple) -> tuple:
    """How far left and right the floor, and right the cursor waiting over it, ever reach on screen:
    turned to a diagonal, where it is widest, at each tilt the view can stop at."""
    cams = [Camera(yaw, math.radians(tilt), *size, top=top, fit=yaw)
            for yaw in (0.0, math.pi / 4) for tilt in range(tilts[0], tilts[1] + 1, 15)]
    floor = [c.at(x, y, z)[0] for c in cams for x in (0, WIDTH) for z in (0, DEPTH) for y in (0, 1)]
    cursor = [c.at(x + 0.5, HEIGHT + 0.5, z + 0.5)[0] + REACH * c.cell(x, HEIGHT, z) for c in cams for x in range(WIDTH) for z in range(DEPTH)]
    return round(min(floor)), round(max(floor)), round(max(cursor))


class Guide:
    """Draws the columns, remembering each until its size, lit row or the theme changes."""

    def __init__(self):
        self._kept = {}

    def paint(self, g, surf, spots: dict, lit: str | None, clip=None):
        for name, rect in spots.items():
            key = (name, rect.size, lit, P.TEXT, art_room.CANVAS_BG)
            if self._kept.get(name, (None,))[0] != key:
                self._kept[name] = key, self._column(g, name, rect.size, lit)
            pic = self._kept[name][1]
            spot = pic.get_rect(topleft=rect.topleft)
            if clip is None or spot.colliderect(clip):
                surf.blit(pic, spot)

    def _column(self, g, name, size, lit):
        """The title, then each row: its keys, its words right under them, and its picture just to their
        right, the pictures lined up in one column. Rows stand further apart than anything inside one."""
        title, rows = ROWS[name]
        surf = pygame.Surface(size, pygame.SRCALPHA)
        px, gap = g.vh(1.75), g.vh(1.75)
        small, kpx = round(px * 0.92), round(px * 0.85)      # words, and keys a size under them so pictures get the room
        with g.drawing_on(pygame.Surface((1, 1))):
            block = max(_keys(g, kpx, 0, 0, keys) for _, keys, _, _ in rows)
        side = min(round(px * 6.5), size[0] - block - gap)
        if block > size[0]:
            return surf         # too narrow for even its keys: nothing rather than cut off
        if side < px * 3:
            side = 0            # too narrow for pictures beside the keys: the keys and words alone
        key_h = keycap_size(g, "X", kpx)[1]
        with g.drawing_on(surf):
            y = g.draw_text(title, round(px * 1.25), 0, 0, "mono-bold", P.MUTED, anchor="topleft").bottom + round(gap * 1.2)
            for i, (row, keys, pic, words) in enumerate(rows):
                rise = keycap_size(g, UP, round(kpx * 0.75))[1] + 2 if "arrows" in keys else 0     # Up stands over the rest
                with g.drawing_on(pygame.Surface((1, 1))):
                    under = gap // 2 + g.draw_markup(words, small, 0, 0, "mono", P.MUTED, block) if words else 0
                text_h = rise + key_h + under
                h = max(side if pic else 0, text_h)
                pic = pic if side else None
                layer = pygame.Surface((size[0], h), pygame.SRCALPHA)
                with g.drawing_on(layer):
                    top = (h - text_h) // 2
                    _keys(g, kpx, 0, top + rise + key_h // 2, keys)
                    if words:
                        g.draw_markup(words, small, 0, top + rise + key_h + gap // 2, "mono", P.MUTED, block)
                    if pic:     # a row without one adds to the row above it
                        picture = g.image(pic, round(side * 0.8)) if isinstance(pic, str) else _scene(side, *pic)
                        layer.blit(picture, picture.get_rect(center=(block + gap + side // 2, h // 2)))
                layer.set_alpha(LIT if row == lit else QUIET)
                surf.blit(layer, (0, y))
                joins = i + 1 < len(rows) and rows[i + 1][0] == row
                y += h + round(gap * (0.7 if joins else 1.6))
        return surf


def _keys(g, px, x, cy, keys) -> int:
    """A row's keys left to right from x, all on one line centered at cy: names, "+", the arrow keys (their
    bottom row on that line, Up over it), sticker-colored letters. Returns the right edge."""
    for part in keys:
        if part == "arrows":
            x = _cluster(g, round(px * 0.75), x, cy) + px // 3
        elif part == "+":
            x = g.draw_text("+", px, x, cy, "mono", P.MUTED, anchor="midleft").right + px // 3
        elif len(part) == 1 and part.isalpha():
            x = draw_key(g, part, px, x, cy, fill=get_key_color(part.lower()), ink=art_room.CANVAS_BG).right + px // 3
        else:
            x = draw_key(g, part, px, x, cy).right + px // 3
    return x


def _cluster(g, px, x, cy) -> int:
    """The arrow keys as they sit on the keyboard, Left, Down and Right centered on cy, Up over Down. Returns their right edge."""
    w, h = keycap_size(g, UP, px)
    gap = 2
    draw_key(g, UP, px, x + w + gap, cy - h - gap)
    for i, key in enumerate((LEFT, DOWN, RIGHT)):
        draw_key(g, key, px, x + i * (w + gap), cy)
    return x + 3 * w + 2 * gap


def _scene(side, blocks, boxes, focus, lift, drop=None, glass=None, arrow=None) -> pygame.Surface:
    """A few cells of a build seen as the room sees it, `side` square: drawn twice
    the size and scaled down, so its edges are smooth. Block colors are keys' sticker colors. A drop adds
    a block on its way down, echoes fading up behind it and its shadow where it lands; glass,
    a patch of lifted floor at that height, as Shift shows it; an arrow, which way the cursor goes."""
    big = 2 * side
    cam = Camera(0.55, REST_PITCH + 0.12, big, big, fit=0.55)
    (fx, fy) = cam.at(focus[0] + 0.5, lift, focus[1] + 0.5)
    zoom = 7 if drop else 4.5 if glass else 6
    cam = cam.zoomed(zoom, (fx - big / zoom / 2, fy - big / zoom / 2))
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    painter = Painter(cam, {p: get_key_color(k) for p, k in blocks.items()}, hazy=False)
    painter.paint(surf, painter.items)
    line = max(2, big // 60)
    if glass:
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        for x in range(3):
            for z in range(3):
                tile = [cam.at(x + a, glass, z + b) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))]
                pygame.draw.polygon(layer, (*rgb(P.TEXT), 70 if (x + z) % 2 else 40), tile)
        pygame.draw.polygon(layer, (*rgb(P.TEXT), 190), [cam.at(a, glass, b) for a, b in ((0, 0), (3, 0), (3, 3), (0, 3))], line)
        surf.blit(layer, (0, 0))
    for (x, z, y), alpha in boxes:
        for _, poly in cam.box((x, y, z), (x + 1, y + 1, z + 1)):
            pygame.draw.polygon(surf, (*rgb(P.TEXT), alpha), poly, line)
    if drop:            # its shadow dark on the spot it lands, and two fading echoes above it
        (h, key), (x, z) = drop, focus
        painter.shadow(surf, x, z, 0, alpha=160)
        for k, alpha in ((2, 35), (1, 80), (0, 255)):
            layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            painter.box(layer, x, z, h + 0.45 * k, h + 0.45 * k, get_key_color(key))
            layer.set_alpha(alpha)
            surf.blit(layer, (0, 0))
    if arrow:
        _arrow(surf, *(pygame.Vector2(cam.at(*p)) for p in arrow), line)
    return pygame.transform.smoothscale(surf, (side, side))


def _arrow(surf, a, b, line):
    """One solid shape: a shaft `line` * 2 wide, and a head twice as wide as long."""
    d = (b - a).normalize()
    n, w, head = d.rotate(90), line, line * 4.5
    neck = b - d * head
    pts = [a + n * w, neck + n * w, neck + n * head, b, neck - n * head, neck - n * w, a - n * w]
    pygame.draw.polygon(surf, (*rgb(P.TEXT), 200), pts)
