"""Blocks room: a floor seen from above and in front, where every letter drops a
block of its sticker color onto the cursor's column. Arrows move along the
floor, Space puts the pen down so arrows lay a trail, and Tab makes blocks
float at the height of the last one, for roofs, bridges and tree tops. A block
floated onto another mixes into it like paint, the way to green leaves."""

import pygame

from ... import palette as P
from ...color_mixing import mix_colors_paint
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...palette import DEFAULT_BRUSH_COLOR
from ..gfx import mix, rgb
from ..ui import draw_mode_switch
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, CANVAS_ALT, CANVAS_BG, HOLD_ACCEL_MULTIPLIER, brush_for_key

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
WIDTH, DEPTH, HEIGHT = 24, 12, 10
ROW_DEPTH, BLOCK_RISE, ROW_SKEW, SLAB = 0.5, 0.7, 0.3, 0.35   # in cell widths
STEPS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
HINTS = {
    "stack": "Type to build! Every letter is a color. Space puts the pen down.",
    "float": "Blocks float at this height. Tab to stack them again.",
    "pen": "Pen is down! Arrows lay blocks. Space lifts the pen.",
}


class BlocksRoom:
    """Blocks live in a dict keyed (x, z, y): x across, z away from the
    viewer, y up. The floor and blocks render into one cached surface that is
    rebuilt only when a block changes; the cursor is drawn over it."""

    name = "blocks"

    def __init__(self, app):
        self.app = app
        self._blocks: dict = {}
        self._x, self._z = WIDTH // 2, DEPTH // 2
        self._color = DEFAULT_BRUSH_COLOR
        self._pen_down = False
        self._floating = False
        self._level = 0
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._blink_on = True
        self._blink_timer = None
        self._c = 0
        self._origin = (0, 0)
        self._floor = self._scene = None
        self._sprites: dict = {}

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        self.app.set_legend(self._color, visible=True)
        if self._blink_timer is None:
            self._blink_timer = self.app.timers.every(0.4, self._blink)

    def on_leave(self):
        if self._blink_timer:
            self._blink_timer.stop()
            self._blink_timer = None

    def stop_sound(self):
        pass

    def open_code_panel(self):
        pass

    def close_code_panel(self):
        pass

    def hold_progress(self):
        return None

    def _blink(self):
        if self._pen_down:
            return
        self._blink_on = not self._blink_on
        self.app.invalidate()

    def _restart_blink(self):
        self._blink_on = True
        if self._blink_timer:
            self._blink_timer.reset()

    def cursor_fraction(self, vp):
        x, y = self._corner(self._x, self._z, 0)
        return (self._origin[0] + x - vp.x) / vp.w, (self._origin[1] + y - vp.y) / vp.h

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        state = {f"b:{x},{z},{y}": color for (x, z, y), color in self._blocks.items()}
        state.update(cursor=[self._x, self._z], color=self._color, floating=self._floating, level=self._level)
        return state

    def restore_timeline_state(self, state: dict):
        self._blocks = {tuple(int(n) for n in k[2:].split(",")): v for k, v in state.items() if k.startswith("b:")}
        self._x, self._z = state.get("cursor", [WIDTH // 2, DEPTH // 2])
        self._color = state.get("color", DEFAULT_BRUSH_COLOR)
        self._floating = bool(state.get("floating", False))
        self._level = state.get("level", 0)
        self._pen_down = False
        self._changed()

    def clear(self):
        self.restore_timeline_state({})

    def has_content(self) -> bool:
        return bool(self._blocks)

    # ---------------------------------------------------------------- blocks
    def _top(self) -> int:
        """Height a dropped block lands at: on top of the column's highest block."""
        return max((y + 1 for (x, z, y) in self._blocks if (x, z) == (self._x, self._z)), default=0)

    def _landing(self) -> int:
        return self._level if self._floating else self._top()

    def _place(self):
        y = self._landing()
        if y < HEIGHT:
            pos = (self._x, self._z, y)
            self._blocks[pos] = mix_colors_paint([self._blocks[pos], self._color]) if pos in self._blocks else self._color
            self._level = y
            self._changed()

    def _remove_top(self):
        y = self._top() - 1
        if y >= 0:
            self._blocks.pop((self._x, self._z, y), None)
            self._changed()

    def _changed(self):
        self._scene = None
        self.app.invalidate()

    def _set_color(self, char: str) -> bool:
        brush = brush_for_key(char)
        if brush:
            self._color = brush[1]
            self.app.set_legend(self._color, visible=True)
        return bool(brush)

    def _move(self, direction: str) -> bool:
        dx, dz = STEPS[direction]
        x, z = self._x + dx, self._z + dz
        if not (0 <= x < WIDTH and 0 <= z < DEPTH):
            return False
        self._x, self._z = x, z
        return True

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        if isinstance(action, ControlAction):
            if action.is_down and (not action.is_repeat or action.action == "backspace"):
                self._control(action.action)
        elif isinstance(action, NavigationAction):
            self._navigate(action)
        elif isinstance(action, CharacterAction):
            char = UNSHIFT_MAP.get(action.char, action.char) if action.shift_held else action.char
            if self._set_color(char) and not action.shift_held:
                self._place()
        self._restart_blink()
        self.app.invalidate()

    def _control(self, name: str):
        if name == "space":
            self._pen_down = not self._pen_down
            if self._pen_down:
                self._place()
        elif name == "tab":
            self._floating = not self._floating
        elif name == "backspace":
            self._remove_top()

    def _navigate(self, action):
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        laying = self._pen_down or (bool(action.char_held) and self._set_color(action.char_held))
        fast = not laying and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(HOLD_ACCEL_MULTIPLIER if fast else 1):
                if not self._move(direction):
                    break
                if laying:
                    self._place()

    # ---------------------------------------------------------------- drawing
    def _metrics(self):
        c = self._c
        return round(c * ROW_DEPTH), round(c * BLOCK_RISE), round(c * ROW_SKEW), round(c * SLAB)

    def _base(self) -> int:
        dz, hy, _, _ = self._metrics()
        return DEPTH * dz + HEIGHT * hy

    def _corner(self, x: int, z: int, y: int) -> tuple:
        """Front-left corner of cell (x, z) at height y, in scene pixels."""
        dz, hy, sx, _ = self._metrics()
        return x * self._c + z * sx, self._base() - z * dz - y * hy

    def _faces(self, px: int, py: int) -> tuple:
        """Top, front and right-side polygons of a block whose front-top-left
        corner is (px, py)."""
        c = self._c
        dz, hy, sx, _ = self._metrics()
        top = [(px, py), (px + c, py), (px + c + sx, py - dz), (px + sx, py - dz)]
        front = [(px, py), (px + c, py), (px + c, py + hy), (px, py + hy)]
        side = [(px + c, py), (px + c + sx, py - dz), (px + c + sx, py - dz + hy), (px + c, py + hy)]
        return top, front, side

    def _sprite(self, color: str) -> pygame.Surface:
        key = (color, self._c)
        if key not in self._sprites:
            dz, hy, sx, _ = self._metrics()
            s = pygame.Surface((self._c + sx + 1, dz + hy + 1), pygame.SRCALPHA)
            edge = mix(color, "#000000", 0.45)
            for poly, shade in zip(self._faces(0, dz), (mix(color, "#ffffff", 0.22), rgb(color), mix(color, "#000000", 0.32))):
                pygame.draw.polygon(s, shade, poly)
                pygame.draw.polygon(s, edge, poly, 1)
            self._sprites[key] = s
        return self._sprites[key]

    def _scene_size(self) -> tuple:
        dz, hy, sx, slab = self._metrics()
        return WIDTH * self._c + DEPTH * sx + 1, self._base() + slab + 1

    def _floor_surface(self) -> pygame.Surface:
        """Checkerboard floor on a slab, built once per cell size."""
        if self._floor is None or self._floor.get_size() != self._scene_size():
            dz, hy, sx, slab = self._metrics()
            s = pygame.Surface(self._scene_size())
            s.fill(rgb(P.SURFACE))
            base, w = self._base(), WIDTH * self._c
            edge = mix(CANVAS_BG, "#000000", 0.4)
            pygame.draw.polygon(s, edge, [(0, base), (w, base), (w, base + slab), (0, base + slab)])
            pygame.draw.polygon(s, mix(CANVAS_BG, "#000000", 0.55),
                                [(w, base), (w + DEPTH * sx, base - DEPTH * dz), (w + DEPTH * sx, base - DEPTH * dz + slab), (w, base + slab)])
            for x in range(WIDTH):
                for z in range(DEPTH):
                    top, _, _ = self._faces(*self._corner(x, z, 0))
                    pygame.draw.polygon(s, rgb(CANVAS_ALT if (x + z) % 2 else CANVAS_BG), top)
            self._floor = s
        return self._floor

    def _scene_surface(self) -> pygame.Surface:
        """Floor plus every block, far rows first, left to right, bottom up,
        so nearer faces paint over farther ones."""
        if self._scene is None or self._scene.get_size() != self._scene_size():
            dz, _, _, _ = self._metrics()
            s = self._floor_surface().copy()
            for x, z, y in sorted(self._blocks, key=lambda b: (-b[1], b[0], b[2])):
                px, py = self._corner(x, z, y + 1)
                s.blit(self._sprite(self._blocks[(x, z, y)]), (px, py - dz))
            self._scene = s
        return self._scene

    def draw(self, g, rect):
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = g.line_height(g.vh(1.9), "mono") + g.em(0.4)
        area = inner.inflate(0, -2 * (chrome_h + gap))
        c = max(6, int(min(area.w / (WIDTH + DEPTH * ROW_SKEW),
                           area.h / (DEPTH * ROW_DEPTH + HEIGHT * BLOCK_RISE + SLAB))))
        if c != self._c:
            self._c, self._sprites, self._scene = c, {}, None
        scene = self._scene_surface()
        ox = area.x + (area.w - scene.get_width()) // 2
        oy = area.y + (area.h - scene.get_height()) // 2
        self._origin = (ox, oy)
        g.surface.blit(scene, (ox, oy))
        if self._blink_on or self._pen_down:
            self._draw_cursor(g, ox, oy)
        draw_mode_switch(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h), ("Stack", "Float"),
                         1 if self._floating else 0, self._color, "to stack" if self._floating else "to float")
        hint = "pen" if self._pen_down else "float" if self._floating else "stack"
        g.draw_text(HINTS[hint], g.vh(1.9), inner.x, inner.bottom - chrome_h // 2, "mono", P.DIM, anchor="midleft")

    def _draw_cursor(self, g, ox, oy):
        """The floor cell under the cursor, plus a see-through block where the
        next one will land."""
        shift = lambda poly: [(ox + px, oy + py) for px, py in poly]
        floor_top, _, _ = self._faces(*self._corner(self._x, self._z, 0))
        pygame.draw.polygon(g.surface, rgb(P.TEXT), shift(floor_top), 2)
        y = self._landing()
        if y >= HEIGHT:
            return
        px, py = self._corner(self._x, self._z, y + 1)
        ghost = self._sprite(self._color).copy()
        ghost.set_alpha(120)
        g.surface.blit(ghost, (ox + px, oy + py - self._metrics()[0]))
        width = max(3, self._c // 10) if self._pen_down else 2
        for poly in self._faces(px, py):
            pygame.draw.polygon(g.surface, rgb(P.TEXT), shift(poly), width)
