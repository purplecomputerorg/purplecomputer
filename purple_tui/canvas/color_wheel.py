"""Color bar for Art and Blocks: Backslash opens a strip of colors in the
header row, from the '[\\] (color wheel)' chip leftward, so the picture stays in
view. Left and Right go along the hues (wrapping round), Up and Down make the
whole strip lighter or darker, and the brush takes the color picked; the
footer shows each key beside a picture of what it does while the bar is up. Space or Enter keeps it, Esc puts the old
one back, and any other key keeps it and goes on to the room. Each room's bar
reopens on the last color kept from it, so a stray key never loses a hard-won
pick. The first cell is the grays, white to near black; a room with wheel_auto
set makes its white AUTO, half the theme's light ink and half its dark: back
to letters that turn light or dark to show up."""

import colorsys
import functools
import math

import pygame

from .. import palette as P
from ..color_mixing import rgb_to_hex
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from .gfx import rgb
from .ui import (AUTO, DOWN, LEFT, RIGHT, UP, Overlay, auto_inks, draw_key, header_pill, hint_row_h, keycap_size,
                 swatch_dot)

OPEN_KEY = "\\"
HUES, SHADES = 24, 6          # cell 0 is the grays, cells 1..HUES the hues
LIGHT, DARK, SAT = 0.85, 0.22, 0.7
GRAY_REACH = 0.88             # how far toward black the grays go


def bar_color(cell: int, shade: int) -> str:
    if cell == 0:
        v = round(255 * (1 - shade / (SHADES - 1) * GRAY_REACH))
        return rgb_to_hex(v, v, v)
    r, g, b = colorsys.hls_to_rgb((cell - 1) / HUES, LIGHT - shade * (LIGHT - DARK) / (SHADES - 1), SAT)
    return rgb_to_hex(round(r * 255), round(g * 255), round(b * 255))


def _place(color: str) -> tuple:
    """(cell, shade) nearest a color, so the bar opens on the brush's own color."""
    if color == AUTO:
        return 0, 0
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb(color)))
    if s < 0.15:
        return 0, max(0, min(SHADES - 1, round((1 - l) / GRAY_REACH * (SHADES - 1))))
    return round(h * HUES) % HUES + 1, max(0, min(SHADES - 1, round((LIGHT - l) / (LIGHT - DARK) * (SHADES - 1))))


def disc(d: int, auto: bool = False) -> pygame.Surface:
    """The chip's icon: the bar's colors as a little wheel."""
    return _disc(d, auto_inks() if auto else None)


@functools.lru_cache(maxsize=4)
def _disc(d: int, auto) -> pygame.Surface:
    """Pies from the rim inward, each ring painted over the last, drawn 2x and smoothed down."""
    s, rings = 2, SHADES + 1
    big = pygame.Surface((d * s, d * s), pygame.SRCALPHA)
    c = d * s / 2
    for ring in range(rings - 1, -1, -1):
        r = (ring + 1) / rings * c
        if ring == 0:
            pygame.draw.circle(big, rgb(bar_color(0, 0)), (c, c), r)
            continue
        for hue in range(HUES):
            arc = [(hue - 0.5 + i / 4) / HUES * 2 * math.pi for i in range(5)]
            pygame.draw.polygon(big, rgb(bar_color(hue + 1, ring - 1)), [(c, c)] + [(c + r * math.sin(a), c - r * math.cos(a)) for a in arc])
    small = pygame.transform.smoothscale(big, (d, d))
    if auto:
        center = swatch_dot(AUTO, round(d / rings))
        small.blit(center, center.get_rect(center=(d / 2, d / 2)))
    return small


def can_open(room) -> bool:
    return getattr(room, "wheel_ready", False) and not room.app._littles_mode


def chip(room) -> str | None:
    """How the header's '[\\] (color wheel)' chip shows: None hidden, "open" lit while the bar is up."""
    if room.app.has_overlay(ColorBar):
        return "open"
    return "ready" if can_open(room) else None


def open_on(room, char: str = OPEN_KEY, on_close=None) -> bool:
    """Backslash opens the bar over the room; True when it did. on_close gets
    the color kept, or None on Esc."""
    if char != OPEN_KEY or not can_open(room):
        return False
    room.app.push(ColorBar(room.app, room), on_close=on_close)
    return True


def _fill(g, color: str, rect: pygame.Rect):
    """A cell; AUTO splits it into the theme's light and dark ink."""
    if color != AUTO:
        g.rect(color, rect)
        return
    light, dark = auto_inks()
    half = rect.w // 2
    g.rect(light, (rect.x, rect.y, half, rect.h))
    g.rect(dark, (rect.x + half, rect.y, rect.w - half, rect.h))


def _strip(g, colors, rect: pygame.Rect, down: bool = False):
    """Colors in equal cells across rect, or top to bottom when down."""
    n, (start, size) = len(colors), (rect.y, rect.h) if down else (rect.x, rect.w)
    for i, color in enumerate(colors):
        a, b = round(start + i * size / n), round(start + (i + 1) * size / n)
        _fill(g, color, pygame.Rect(rect.x, a, rect.w, b - a) if down else pygame.Rect(a, rect.y, b - a, rect.h))


def _draw_graded(g, glyphs, px: int, x: int, ys):
    """Glyphs centered at (x, y) for each y, filled with one gradient from white at the
    top of the first's ink to near black at the bottom of the last's."""
    marks = []
    for glyph, y in zip(glyphs, ys):
        s = g.text(glyph, px, "mono", "#ffffff").copy()
        marks.append((s, s.get_rect(center=(x, y))))
    top = marks[0][1].y + marks[0][0].get_bounding_rect().top
    span = max(1, marks[-1][1].y + marks[-1][0].get_bounding_rect().bottom - top)
    for s, r in marks:
        for y in range(r.h):
            v = round(255 * (1 - max(0.0, min(1.0, (r.y + y - top) / span)) * GRAY_REACH))
            s.fill((v, v, v, 255), (0, y, r.w, 1), special_flags=pygame.BLEND_RGBA_MULT)
        g.surface.blit(s, r)


class ColorBar(Overlay):
    """Draws where the room left room for it: the room sets bar_row (the
    header from its left edge to the chip) and bar_foot (its hint row) as it
    draws; without them the bar sits at the top of the viewport and its hint
    just under it."""

    scrim = False

    def __init__(self, app, room):
        super().__init__(app)
        self.room = room
        self._was = room.brush_color
        spot = getattr(room, "wheel_spot", None)
        self._cell, self._shade = spot or _place(self._was)
        if spot:
            self._move([])

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            self._move([action.direction, *(action.other_arrows_held or ())])
            return
        if not getattr(action, "is_down", True) or not isinstance(action, (CharacterAction, ControlAction)):
            return
        kept = None
        if isinstance(action, ControlAction) and action.action == "escape":
            self.room.set_brush_color(self._was)
        else:
            kept = self.room.brush_color
            if kept != self._was:
                self.room.wheel_spot = (self._cell, self._shade)
        self.close(kept)
        passes_on = isinstance(action, CharacterAction) and action.char != OPEN_KEY or \
            isinstance(action, ControlAction) and action.action in ("backspace", "tab")
        if passes_on:
            await self.app._dispatch_keyboard_action(action)

    def _move(self, directions):
        for d in directions:
            if d in ("left", "right"):
                self._cell = (self._cell + (1 if d == "right" else -1)) % (HUES + 1)
            else:
                self._shade = max(0, min(SHADES - 1, self._shade + (1 if d == "down" else -1)))
        self.room.set_brush_color(self._color(self._cell, self._shade))

    def _color(self, cell: int, shade: int) -> str:
        auto = cell == 0 and shade == 0 and getattr(self.room, "wheel_auto", False)
        return AUTO if auto else bar_color(cell, shade)

    def draw(self, g):
        px = g.vh(1.9)
        row = getattr(self.room, "bar_row", None)
        if row is None:
            vp = self.app._viewport_rect()
            row = pygame.Rect(vp.x + g.em(0.7), vp.y + g.em(0.7), vp.w // 2, hint_row_h(g))
        bar = self._draw_bar(g, px, row)
        foot = getattr(self.room, "bar_foot", None)
        if foot is None:
            with g.drawing_on(pygame.Surface((1, 1))):
                w = self._draw_legend(g, px, 0, 0)
            box = pygame.Rect(bar.x, bar.bottom + g.em(0.3), w + g.em(1.2), keycap_size(g, "X", px)[1] + g.em(0.4))
            g.rect(P.SURFACE, box, radius=g.em(0.4))
            g.rect(P.LINE, box, width=1, radius=g.em(0.4))
            self._draw_legend(g, px, box.x + g.em(0.6), box.centery)
            return
        g.rect(P.SURFACE, foot.inflate(0, g.em(0.6)))
        self._draw_legend(g, px, foot.x, foot.centery)

    def _draw_legend(self, g, px: int, x: int, cy: int) -> int:
        """The footer in pictures, no words: the arrows beside the colors and shades they walk
        through, Space beside the color it keeps, Esc beside the one it goes back to. Returns its right."""
        h = keycap_size(g, "X", px)[1]
        hues = pygame.Rect(0, cy - h // 3, px * 5, 2 * (h // 3)), [self._color(c, self._shade) for c in range(HUES + 1)], False
        shades = pygame.Rect(0, cy - h // 2, round(px * 0.9), h), [self._color(self._cell, s) for s in range(SHADES)], True
        for keys, pic in (((LEFT, RIGHT), hues), ((UP, DOWN), shades), (("Space",), self.room.brush_color), (("Esc",), self._was)):
            for key in keys:
                x = draw_key(g, key, px, x, cy, fill=P.MUTED).right + px // 4
            x += px // 4
            if isinstance(pic, str):
                dot = swatch_dot(pic, h)
                x = g.surface.blit(dot, dot.get_rect(midleft=(x, cy))).right
            else:
                rect, colors, down = pic
                rect.x = x
                _strip(g, colors, rect, down)
                g.rect(P.LINE, rect, width=1)
                x = rect.right
            x += px * 2
        return x - px * 2

    def _draw_bar(self, g, px: int, row: pygame.Rect) -> pygame.Rect:
        """'< cells > shades ^v' in one pill the chip's height; the picked cell
        stands out above and below it."""
        gap = px // 2
        pill, pad = header_pill(g, px, row.w - 2 * round(px * 0.35), row.right, row.centery, False)
        h = pill.h
        inner = pill.inflate(-2 * pad, -2 * pad)
        x = g.draw_text(LEFT, px, pill.x + h // 3, pill.centery, "mono", P.MUTED, anchor="midleft").right + gap
        shades = pygame.Rect(0, inner.y, round(px * 0.9), inner.h)
        ud_px = round(px * 0.75)
        ud_x = pill.right - h // 3 - ud_px // 2
        _draw_graded(g, (UP, DOWN), ud_px, ud_x, (pill.centery - inner.h // 4, pill.centery + inner.h // 4))
        shades.right = ud_x - ud_px // 2 - gap // 2
        right = g.draw_text(RIGHT, px, shades.x - gap, pill.centery, "mono", P.MUTED, anchor="midright").x - gap
        cw = (right - x) / (HUES + 1)
        _strip(g, [self._color(cell, self._shade) for cell in range(HUES + 1)], pygame.Rect(x, inner.y, right - x, inner.h))
        sh = shades.h / SHADES
        _strip(g, [self._color(self._cell, s) for s in range(SHADES)], shades, down=True)
        mark = pygame.Rect(shades.x, round(shades.y + self._shade * sh), shades.w, round(sh)).inflate(4, 4)
        g.rect(P.TEXT, mark, width=2)
        picked = pygame.Rect(round(x + self._cell * cw), inner.y, max(1, round(cw)), inner.h).inflate(round(px * 0.5), round(px * 0.7))
        g.rect(P.ON_PRIMARY, picked.inflate(4, 4), radius=round(px * 0.25))
        g.rect(P.TEXT, picked.inflate(2, 2), radius=round(px * 0.25))
        _fill(g, self.room.brush_color, picked)
        return pill
