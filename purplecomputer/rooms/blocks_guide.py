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
        ("type", ["A", "Z"], ({}, [((1, 1, 0), 255)], (1, 1), 2.0, (1.45, "a", 3.0)), "each letter drops a block"),
        ("move", ["arrows"], ({}, [((0, 1, 0), 70), ((1, 1, 0), 255)], (0.5, 1), 0.5), "move around the floor"),
        ("height", ["hold Shift", "+", UP, DOWN], ({(1, 1, 0): "a"}, [((1, 1, 1), 70), ((1, 1, 2), 255)], (1, 1), 1.6),
         "higher or lower"),
    ]),
    LOOK: ("Look around", [
        ("turn", ["Tab"], "hints/turn.png", "tap: turn the build"),
        ("look", ["hold Tab", "+", "arrows"], "hints/look.png", "keep holding, press arrows"),
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
        """The title, then each row as one unit: its picture, its keys right under it and their words under
        those. Rows stand further apart than anything inside one, so it's clear what goes together."""
        title, rows = ROWS[name]
        surf = pygame.Surface(size, pygame.SRCALPHA)
        px = g.vh(1.6)
        keys_h, words_h, gap = 2 * keycap_size(g, UP, round(px * 0.75))[1], g.line_height(round(px * 0.9)), round(px * 1.5)
        top = round(px * 1.8)
        side = min(round(px * 6), (size[1] - top - len(rows) * (keys_h + words_h + gap)) // len(rows))
        y = top
        with g.drawing_on(surf):
            g.draw_text(title, px, 0, 0, "sans-bold", P.MUTED, anchor="topleft")
            for row, keys, pic, words in rows:
                layer = pygame.Surface((size[0], side + keys_h + words_h), pygame.SRCALPHA)
                with g.drawing_on(layer):
                    picture = g.image(pic, round(side * 0.8)) if isinstance(pic, str) else _scene(side, *pic)
                    layer.blit(picture, picture.get_rect(midleft=(0, side // 2)))
                    _keys(g, px, 0, side + keys_h // 2, keys)
                    g.draw_text(words, round(px * 0.9), 0, side + keys_h, "sans", P.MUTED, anchor="topleft")
                layer.set_alpha(LIT if row == lit else QUIET)
                surf.blit(layer, (0, y))
                y += layer.get_height() + gap
        return surf


def _keys(g, px, x, cy, keys) -> int:
    """A row's keys left to right from x: names, "+", the arrow keys, sticker-colored letters. Returns the right edge."""
    for part in keys:
        if part == "arrows":
            x = _cluster(g, round(px * 0.75), x, cy) + px // 2
        elif part == "+":
            x = g.draw_text("+", px, x, cy, "sans", P.MUTED, anchor="midleft").right + px // 3
        elif len(part) == 1 and part.isalpha():
            x = draw_key(g, part, px, x, cy, fill=get_key_color(part.lower()), ink=art_room.CANVAS_BG).right + px // 3
        else:
            x = draw_key(g, part, px, x, cy).right + px // 3
    return x


def _cluster(g, px, x, cy) -> int:
    """The arrow keys as they sit on the keyboard, Up over Down. Returns their right edge."""
    w, h = keycap_size(g, UP, px)
    gap = max(2, px // 6)
    draw_key(g, UP, px, x + w + gap, cy - (h + gap) // 2)
    for i, key in enumerate((LEFT, DOWN, RIGHT)):
        draw_key(g, key, px, x + i * (w + gap), cy + (h + gap) // 2)
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
