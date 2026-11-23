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
from .blocks_view import DEPTH, REST_PITCH, WIDTH, Camera, Painter

QUIET, LIT = 150, 255          # a row's alpha, and while its key is held
MIN_W = 13                     # vw: a side narrower than this shows no column
BUILD, LOOK = "build", "look"
# Each row: (name, keys, picture, words). Keys are names, "+", "arrows" (the four, as on the keyboard),
# and "hold X"; a picture is an image name or a little scene: (blocks, wire boxes, cell it centers on, height,
# and a drop: (how high the falling block is, its key, the waiting bubble's height)), drawn as the room draws them.
ROWS = {
    BUILD: ("Build", [
        ("type", ["A", "Z"], ({}, [((1, 1, 0), 255)], (1, 1), 2.3, (1.35, "a", 3.55)), "letters drop blocks"),
        ("move", ["arrows"], ({}, [((0, 1, 0), 70), ((1, 1, 0), 255)], (0.5, 1), 0.5), "move around the floor"),
        ("height", ["hold Shift", "+", UP, DOWN], ({(1, 1, 0): "a"}, [((1, 1, 1), 70), ((1, 1, 2), 255)], (1, 1), 1.6),
         "higher or lower"),
    ]),
    LOOK: ("Look around", [
        ("turn", ["Tab"], "hints/turn.png", "tap to turn"),
        ("look", ["hold Tab", "+", "arrows"], "hints/look.png", "hold, press arrows"),
    ]),
}


def columns(size, code: bool, min_w: int, top: float, tilts: tuple) -> dict:
    """{column: rect} in the layer's pixels, in the sides the floor leaves free at every angle it can be
    seen from, so the columns hold still while the view moves: no Build while the code line takes the
    letters and arrows."""
    w, h = size
    pad = round(h * 0.03)
    left, right = _floor_span(size, top, tilts)
    left, right = left - 2 * pad, right + 2 * pad
    spots = {BUILD: pygame.Rect(pad, pad, left - pad, h - 2 * pad), LOOK: pygame.Rect(right, pad, w - right - pad, h - 2 * pad)}
    return {k: r for k, r in spots.items() if r.w >= min_w and not (code and k == BUILD)}


@lru_cache(maxsize=4)
def _floor_span(size, top: float, tilts: tuple) -> tuple:
    """How far left and right the floor ever reaches on screen: turned to a diagonal, where it is widest,
    at each tilt the view can stop at."""
    xs = [Camera(yaw, math.radians(tilt), *size, top=top, fit=yaw).at(x, y, z)[0]
          for yaw in (0.0, math.pi / 4) for tilt in range(tilts[0], tilts[1] + 1, 15)
          for x in (0, WIDTH) for z in (0, DEPTH) for y in (0, 1)]
    return round(min(xs)), round(max(xs))


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
        side = max(px * 3, min(round(px * 6.5), size[0] - block - gap))
        key_h = keycap_size(g, "X", kpx)[1]
        with g.drawing_on(surf):
            y = g.draw_text(title, round(px * 1.25), 0, 0, "mono-bold", P.MUTED, anchor="topleft").bottom + round(gap * 1.2)
            for row, keys, pic, words in rows:
                rise = keycap_size(g, UP, round(kpx * 0.75))[1] + 2 if "arrows" in keys else 0     # Up stands over the rest
                with g.drawing_on(pygame.Surface((1, 1))):
                    words_h = g.draw_markup(words, small, 0, 0, "mono", P.MUTED, block)
                text_h = rise + key_h + gap // 2 + words_h
                h = max(side, text_h)
                layer = pygame.Surface((size[0], h), pygame.SRCALPHA)
                with g.drawing_on(layer):
                    top = (h - text_h) // 2
                    _keys(g, kpx, 0, top + rise + key_h // 2, keys)
                    g.draw_markup(words, small, 0, top + rise + key_h + gap // 2, "mono", P.MUTED, block)
                    picture = g.image(pic, round(side * 0.8)) if isinstance(pic, str) else _scene(side, *pic)
                    layer.blit(picture, picture.get_rect(center=(block + gap + side // 2, h // 2)))
                layer.set_alpha(LIT if row == lit else QUIET)
                surf.blit(layer, (0, y))
                y += h + round(gap * 1.6)
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


def _scene(side, blocks, boxes, focus, lift, drop=None) -> pygame.Surface:
    """A few cells of a build seen as the room sees it, on a patch of floor, `side` square: drawn twice
    the size and scaled down, so its edges are smooth. Block colors are keys' sticker colors. A drop adds
    the waiting bubble, the line down from it, and a block on its way down with a short fading trail."""
    big = 2 * side
    cam = Camera(0.55, REST_PITCH + 0.12, big, big, fit=0.55)
    (fx, fy) = cam.at(focus[0] + 0.5, lift, focus[1] + 0.5)
    zoom = 4 if drop else 6     # a drop is taller: the bubble over it has to fit
    cam = cam.zoomed(zoom, (fx - big / zoom / 2, fy - big / zoom / 2))
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    painter = Painter(cam, {p: get_key_color(k) for p, k in blocks.items()}, hazy=False)
    for x in range(3):
        for z in range(3):
            pygame.draw.polygon(surf, painter.tile(x, z), painter._tile_poly(x, z))
    painter.paint(surf, painter.items)
    line = max(2, big // 60)
    for (x, z, y), alpha in boxes:
        if drop:
            painter.shadow(surf, x, z, y, alpha=90)
        for _, poly in cam.box((x, y, z), (x + 1, y + 1, z + 1)):
            pygame.draw.polygon(surf, (*rgb(P.TEXT), alpha), poly, line)
    if drop:
        h, key, up = drop
        (x, z), low = focus, boxes[0][0][2] + 1
        pygame.draw.line(surf, (*rgb(P.TEXT), 150), cam.at(x + 0.5, low, z + 0.5), cam.at(x + 0.5, up, z + 0.5), max(1, line // 2))
        center, r = cam.at(x + 0.5, up + 0.5, z + 0.5), 0.62 * cam.cell(x, up, z)
        pygame.draw.circle(surf, (*rgb(P.TEXT), 34), center, r)
        pygame.draw.circle(surf, (*rgb(P.TEXT), 200), center, r, line)
        for lift_by, alpha in ((0.3, 80), (0, 255)):
            layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            painter.box(layer, x, z, h + lift_by, h + lift_by, get_key_color(key))
            layer.set_alpha(alpha)
            surf.blit(layer, (0, 0))
    return pygame.transform.smoothscale(surf, (side, side))
