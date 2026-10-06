"""Color wheel for Art and Blocks: Backslash opens a disc of every hue, white at
the center to dark at the rim. Arrows move a dot over it and the brush takes
the color under the dot; Space or Enter keeps it, Esc puts the old one back,
and any other key keeps it and goes on to the room."""

import colorsys
import functools
import math

import pygame

from .. import palette as P
from ..color_mixing import rgb_to_hex
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from .gfx import rgb
from .ui import Overlay

OPEN_KEY = "\\"
HUES, RINGS = 36, 7          # ring 0 is the white center
LIGHT, DARK, SAT = 0.85, 0.22, 0.7
STEP = 0.5 / RINGS           # dot travel per arrow press, in disc radii
REACH = (RINGS - 0.5) / RINGS
MOVES = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
HINT = "Arrows pick. Space keeps it."


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
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb(color)))
    if s < 0.15 or l > LIGHT:
        return 0.0, 0.0
    ring = max(1, min(RINGS - 1, 1 + round((LIGHT - l) / (LIGHT - DARK) * (RINGS - 2))))
    a, d = h * 2 * math.pi, (ring + 0.5) / RINGS
    return d * math.sin(a), -d * math.cos(a)


@functools.lru_cache(maxsize=2)
def _disc(d: int) -> pygame.Surface:
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
    return pygame.transform.smoothscale(big, (d, d))


def open_on(room, char: str) -> bool:
    """Backslash opens the wheel over the room; True when it did."""
    if char != OPEN_KEY or room.app._littles_mode:
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
        self._x, self._y = _spot(self._was)

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            self._move([action.direction, *(action.other_arrows_held or ())])
            return
        if not getattr(action, "is_down", True) or not isinstance(action, (CharacterAction, ControlAction)):
            return
        if isinstance(action, ControlAction) and action.action == "escape":
            self.room.set_brush_color(self._was)
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
        self.room.set_brush_color(wheel_color(*_cell(self._x, self._y)))

    def draw(self, g):
        vp = self.app._viewport_rect()
        d, pad, px = round(vp.h * 0.6), g.em(1.0), g.vh(1.9)
        box = pygame.Rect(0, 0, d + 2 * pad, d + 2 * pad + g.line_height(px, "mono"))
        box.centery = vp.centery
        if self.app._get_cursor_position()[0] < 0.5:
            box.right = vp.right - pad
        else:
            box.left = vp.left + pad
        radius = g.em(0.6)
        g.rect(P.SURFACE, box, radius=radius)
        g.rect(P.LINE, box, width=1, radius=radius)
        g.surface.blit(_disc(d), (box.x + pad, box.y + pad))
        cx, cy = box.x + pad + d / 2 + self._x * d / 2, box.y + pad + d / 2 + self._y * d / 2
        dot = max(4, d // 28)
        pygame.draw.circle(g.surface, rgb(P.ON_PRIMARY), (cx, cy), dot + max(2, dot // 2))
        pygame.draw.circle(g.surface, rgb(P.TEXT), (cx, cy), dot + max(1, dot // 4))
        pygame.draw.circle(g.surface, rgb(self.room.brush_color), (cx, cy), dot)
        g.draw_text(HINT, px, box.centerx, box.bottom - pad // 2 - g.line_height(px, "mono") // 2, "mono", P.MUTED, anchor="center")
