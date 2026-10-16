"""Color wheel for Art and Blocks: Backslash opens a disc of every hue, white at
the center to dark at the rim. Arrows move a dot over it and the brush takes
the color under the dot; Space or Enter keeps it, Esc puts the old one back,
and any other key keeps it and goes on to the room. Each room's wheel reopens
on the last color kept from it, so a stray key never loses a hard-won pick.
A room with wheel_auto set swaps the white center for AUTO, half the theme's light ink and
half its dark: back to letters that turn light or dark to show up."""

import colorsys
import functools
import math

import pygame

from .. import palette as P
from ..color_mixing import rgb_to_hex
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from .gfx import rgb
from .ui import AUTO, Overlay, auto_inks, swatch_dot, arrow_key_metrics, arrow_keys_size, draw_arrow_keys, draw_keycap

OPEN_KEY = "\\"
HUES, RINGS = 36, 7          # ring 0 is the white center
LIGHT, DARK, SAT = 0.85, 0.22, 0.7
STEP = 0.5 / RINGS           # dot travel per arrow press, in disc radii
REACH = (RINGS - 0.5) / RINGS
MOVES = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def wheel_color(hue: int, ring: int) -> str:
    if ring == 0:
        return "#FFFFFF"
    r, g, b = colorsys.hls_to_rgb(hue / HUES, LIGHT - (ring - 1) * (LIGHT - DARK) / (RINGS - 2), SAT)
    return rgb_to_hex(round(r * 255), round(g * 255), round(b * 255))


def _cell(x: float, y: float) -> tuple:
    """(hue, ring) under (x, y), in disc radii from the center; hue 0 points up, going clockwise."""
    ring = min(RINGS - 1, int(math.hypot(x, y) * RINGS))
    return round(math.atan2(x, -y) / (2 * math.pi) * HUES) % HUES, ring


def _spot(color: str) -> tuple:
    """Where a color sits on the disc, so the dot starts on the brush's own color."""
    if color == AUTO:
        return 0.0, 0.0
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb(color)))
    if s < 0.15 or l > LIGHT:
        return 0.0, 0.0
    ring = max(1, min(RINGS - 1, 1 + round((LIGHT - l) / (LIGHT - DARK) * (RINGS - 2))))
    a, d = h * 2 * math.pi, (ring + 0.5) / RINGS
    return d * math.sin(a), -d * math.cos(a)


def disc(d: int, auto: bool = False) -> pygame.Surface:
    return _disc(d, auto_inks() if auto else None)


@functools.lru_cache(maxsize=4)
def _disc(d: int, auto) -> pygame.Surface:
    """Pies from the rim inward, each ring painted over the last, drawn 2x and smoothed down."""
    s = 2
    big = pygame.Surface((d * s, d * s), pygame.SRCALPHA)
    c = d * s / 2
    for ring in range(RINGS - 1, -1, -1):
        r = (ring + 1) / RINGS * c
        if ring == 0:
            pygame.draw.circle(big, rgb(wheel_color(0, 0)), (c, c), r)
            continue
        for hue in range(HUES):
            arc = [(hue - 0.5 + i / 4) / HUES * 2 * math.pi for i in range(5)]
            pygame.draw.polygon(big, rgb(wheel_color(hue, ring)), [(c, c)] + [(c + r * math.sin(a), c - r * math.cos(a)) for a in arc])
    small = pygame.transform.smoothscale(big, (d, d))
    if auto:
        center = swatch_dot(AUTO, round(d / RINGS))
        small.blit(center, center.get_rect(center=(d / 2, d / 2)))
    return small


def can_open(room) -> bool:
    return getattr(room, "wheel_ready", False) and not room.app._littles_mode


def chip(room) -> str | None:
    """How the header's '[\\] Colors' chip shows: None hidden, "open" lit while the wheel is up."""
    if room.app.has_overlay(ColorWheel):
        return "open"
    return "ready" if can_open(room) else None


def open_on(room, char: str = OPEN_KEY) -> bool:
    """Backslash opens the wheel over the room; True when it did."""
    if char != OPEN_KEY or not can_open(room):
        return False
    room.app.push(ColorWheel(room.app, room))
    return True


class ColorWheel(Overlay):
    """Floats beside the picture, on the side away from the cursor, so the
    brush and the header swatch show each color as the dot reaches it."""

    scrim = False

    def __init__(self, app, room):
        super().__init__(app)
        self.room = room
        self._was = room.brush_color
        spot = getattr(room, "wheel_spot", None)
        self._x, self._y = spot or _spot(self._was)
        if spot:
            self._move([])

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            self._move([action.direction, *(action.other_arrows_held or ())])
            return
        if not getattr(action, "is_down", True) or not isinstance(action, (CharacterAction, ControlAction)):
            return
        if isinstance(action, ControlAction) and action.action == "escape":
            self.room.set_brush_color(self._was)
        elif self.room.brush_color != self._was:
            self.room.wheel_spot = (self._x, self._y)
        self.close()
        passes_on = isinstance(action, CharacterAction) and action.char != OPEN_KEY or \
            isinstance(action, ControlAction) and action.action in ("backspace", "tab")
        if passes_on:
            await self.app._dispatch_keyboard_action(action)

    def _move(self, directions):
        for d in directions:
            dx, dy = MOVES[d]
            self._x, self._y = self._x + dx * STEP, self._y + dy * STEP
        far = math.hypot(self._x, self._y)
        if far > REACH:
            self._x, self._y = self._x * REACH / far, self._y * REACH / far
        hue, ring = _cell(self._x, self._y)
        auto = ring == 0 and getattr(self.room, "wheel_auto", False)
        self.room.set_brush_color(AUTO if auto else wheel_color(hue, ring))

    def draw(self, g):
        vp = self.app._viewport_rect()
        d, pad, px = round(vp.h * 0.6), g.em(1.0), g.vh(1.9)
        keys_w, keys_h = arrow_keys_size(g, px)
        box = pygame.Rect(0, 0, d + 2 * pad, d + 2 * pad + keys_h)
        box.centery = vp.centery
        if self.app._get_cursor_position()[0] < 0.5:
            box.right = vp.right - pad
        else:
            box.left = vp.left + pad
        radius = g.em(0.6)
        g.rect(P.SURFACE, box, radius=radius)
        g.rect(P.LINE, box, width=1, radius=radius)
        g.surface.blit(disc(d, getattr(self.room, "wheel_auto", False)), (box.x + pad, box.y + pad))
        cx, cy = box.x + pad + d / 2 + self._x * d / 2, box.y + pad + d / 2 + self._y * d / 2
        dot = max(4, d // 28)
        pygame.draw.circle(g.surface, rgb(P.ON_PRIMARY), (cx, cy), dot + max(2, dot // 2))
        pygame.draw.circle(g.surface, rgb(P.TEXT), (cx, cy), dot + max(1, dot // 4))
        fill = swatch_dot(self.room.brush_color, 2 * dot)
        g.surface.blit(fill, fill.get_rect(center=(cx, cy)))
        space_w = g.measure("Space", px, "mono")[0] + round(px * 1.4)
        x = box.centerx - (keys_w + px + space_w) // 2
        y = box.bottom - pad // 2 - arrow_key_metrics(g, px)[1] // 2
        draw_keycap(g, "Space", px, draw_arrow_keys(g, px, x, y).right + round(px * 1.7), y)
