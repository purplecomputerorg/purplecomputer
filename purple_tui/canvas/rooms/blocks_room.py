"""Blocks room: a floor seen from above and in front, where every letter (or
Space, in the current color) drops a block of its sticker color on top of the
cursor's column. Enter lifts the block just dropped a level and Backspace
lowers it, then removes it; away from that block they move the see-through
cursor instead, and the next block goes in at its height. Holding one letter
while pressing another mixes the two colors. Tab flips to the back side."""

import time

import pygame

from ... import palette as P
from ...color_mixing import mix_colors_paint
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...palette import DEFAULT_BRUSH_COLOR
from .. import paper
from ..gfx import mix, rgb
from ..ui import draw_mode_switch
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, CANVAS_ALT, CANVAS_BG, HOLD_ACCEL_MULTIPLIER, brush_for_key

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
WIDTH, DEPTH, HEIGHT = 24, 12, 8
FLIP_S = 0.22
ROW_DEPTH, BLOCK_RISE, ROW_SKEW, SLAB = 0.5, 0.7, 0.3, 0.35   # in cell widths
XRAY_ALPHA = 80
STEPS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
HINT = "Type to build! Enter lifts a block, Backspace lowers it."
MIX_HINT = "Hold two letters to mix"


class BlocksRoom:
    """Blocks live in a dict keyed by world (x, z, y), y up. Drawing and the
    arrows work in view coordinates, which are world (x, z) mirrored when the
    room shows its back. The floor and blocks render into one cached surface,
    rebuilt when a block changes, the room flips, or the blocks in front of
    the cursor change; the cursor is drawn over it."""

    name = "blocks"
    LANDSCAPE = True

    def __init__(self, app):
        self.app = app
        self._blocks: dict = {}
        self._x, self._z = WIDTH // 2, DEPTH // 2
        self._back = False
        self._hover = 0               # lifted cursor height; 0 = resting on the column
        self._color = DEFAULT_BRUSH_COLOR
        self._key = ""
        self._last = None             # (pos, key) of the block just dropped
        self._fade_from = self._fade_start = self._fade_timer = None
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._blink_on = True
        self._blink_timer = None
        self._c = 0
        self._origin = (0, 0)
        self._floor = self._scene = None
        self._scene_xray = None
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
        self._blink_on = not self._blink_on
        self.app.invalidate()

    def _restart_blink(self):
        self._blink_on = True
        if self._blink_timer:
            self._blink_timer.reset()

    def cursor_fraction(self, vp):
        x, y = self._corner(*self._view(self._x, self._z), 0)
        return (self._origin[0] + x - vp.x) / vp.w, (self._origin[1] + y - vp.y) / vp.h

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        state = {f"b:{x},{z},{y}": color for (x, z, y), color in self._blocks.items()}
        state.update(cursor=[self._x, self._z], color=self._color, hover=self._hover, back=self._back)
        return state

    def restore_timeline_state(self, state: dict):
        self._blocks = {tuple(int(n) for n in k[2:].split(",")): v for k, v in state.items() if k.startswith("b:")}
        self._x, self._z = state.get("cursor", [WIDTH // 2, DEPTH // 2])
        self._color = state.get("color", DEFAULT_BRUSH_COLOR)
        self._hover = state.get("hover", 0)
        self._back = bool(state.get("back", False))
        self._last = None
        self._changed()

    def clear(self):
        self.restore_timeline_state({})

    def has_content(self) -> bool:
        return bool(self._blocks)

    # ---------------------------------------------------------------- blocks
    def _top(self) -> int:
        return max((y + 1 for (x, z, y) in self._blocks if (x, z) == (self._x, self._z)), default=0)

    def _cursor_y(self) -> int:
        """The cursor never sinks into a block: it rides on top of the column."""
        return max(self._top(), self._hover)

    def _held_block(self):
        """The block just dropped, while the cursor is still over it."""
        if self._last and self._last[0] in self._blocks and self._last[0][:2] == (self._x, self._z):
            return self._last[0]
        return None

    def _place(self):
        y = self._cursor_y()
        if y < HEIGHT:
            self._blocks[(self._x, self._z, y)] = self._color
            self._last = ((self._x, self._z, y), self._key)
            self._changed()

    def _mix_into_last(self, held_key: str) -> bool:
        """A chord: the block the held key just dropped takes the new color mixed in."""
        if not self._last or self._last[1] != held_key or self._last[0] not in self._blocks:
            return False
        pos = self._last[0]
        self._color = self._blocks[pos] = mix_colors_paint([self._blocks[pos], self._color])
        self.app.set_legend(self._color, visible=True)
        self._changed()
        return True

    def _shift_held_block(self, pos, dy: int) -> bool:
        """Move the block just dropped one level; False when it can't go."""
        x, z, y = pos
        dest = (x, z, y + dy)
        if not 0 <= dest[2] < HEIGHT or dest in self._blocks:
            return False
        self._blocks[dest] = self._blocks.pop(pos)
        self._last = (dest, self._last[1])
        self._hover = dest[2]
        self._changed()
        return True

    def _lift(self):
        pos = self._held_block()
        if pos:
            self._shift_held_block(pos, 1)
        else:
            self._hover = min(HEIGHT - 1, self._cursor_y() + 1)

    def _lower(self):
        """Backspace: down a level first, then remove."""
        pos = self._held_block()
        if pos and not self._shift_held_block(pos, -1):
            del self._blocks[pos]
            self._last, self._hover = None, 0
            self._changed()
        elif not pos and self._hover > self._top():
            self._hover -= 1
        elif not pos:
            self._hover = 0
            y = self._top() - 1
            if y >= 0:
                self._blocks.pop((self._x, self._z, y), None)
                self._changed()

    def _changed(self):
        self._scene = None
        self.app.invalidate()

    def _set_color(self, char: str):
        brush = brush_for_key(char)
        if brush:
            self._key, self._color = brush
            self.app.set_legend(self._color, visible=True)
        return bool(brush)

    def _move(self, direction: str) -> bool:
        dx, dz = STEPS[direction]
        vx, vz = self._view(self._x, self._z)
        vx, vz = vx + dx, vz + dz
        if not (0 <= vx < WIDTH and 0 <= vz < DEPTH):
            return False
        self._x, self._z = self._view(vx, vz)
        return True

    def _view(self, x: int, z: int) -> tuple:
        """World to view and back: the back side is the front mirrored both ways."""
        return (WIDTH - 1 - x, DEPTH - 1 - z) if self._back else (x, z)

    # ---------------------------------------------------------------- flipping
    def _flip(self):
        self._fade_from = self._scene_surface() if self._c else None
        self._back = not self._back
        self._fade_start = time.monotonic()
        if self._fade_timer is None:
            self._fade_timer = self.app.timers.every(1 / 60, self._fade_tick)
        self._changed()

    def _fade_tick(self):
        if self._fade_progress() is None:
            self._fade_timer.stop()
            self._fade_timer = self._fade_from = None
        self.app.invalidate()

    def _fade_progress(self):
        if self._fade_start is None:
            return None
        p = (time.monotonic() - self._fade_start) / FLIP_S
        if p >= 1:
            self._fade_start = None
            return None
        return p

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        if isinstance(action, ControlAction):
            if action.is_down and (not action.is_repeat or action.action in ("backspace", "enter")):
                self._control(action.action)
        elif isinstance(action, NavigationAction):
            self._navigate(action)
        elif isinstance(action, CharacterAction) and not action.is_repeat:
            self._character(action)
        self._restart_blink()
        self.app.invalidate()

    def _character(self, action):
        char = UNSHIFT_MAP.get(action.char, action.char) if action.shift_held else action.char
        if not self._set_color(char) or action.shift_held:
            return
        held = brush_for_key(action.char_held) if action.char_held else None
        if not (held and self._mix_into_last(held[0])):
            self._place()

    def _control(self, name: str):
        if name == "space":
            self._place()
        elif name == "enter":
            self._lift()
        elif name == "backspace":
            self._lower()
        elif name == "tab":
            self._flip()

    def _navigate(self, action):
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        laying = (bool(action.char_held) and self._set_color(action.char_held)) or action.space_held
        if not laying:
            self._hover = 0               # a lifted height carries along a line being laid, not a walk
        fast = not laying and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(HOLD_ACCEL_MULTIPLIER if fast else 1):
                if not self._move(direction):
                    break
                if laying:
                    self._place()

    # ---------------------------------------------------------------- geometry
    def _metrics(self):
        c = self._c
        return round(c * ROW_DEPTH), round(c * BLOCK_RISE), round(c * ROW_SKEW), round(c * SLAB)

    def _base(self) -> int:
        dz, hy, _, _ = self._metrics()
        return DEPTH * dz + HEIGHT * hy

    def _corner(self, x: int, z: int, y: int) -> tuple:
        """Front-left corner of view cell (x, z) at height y, in scene pixels."""
        dz, hy, sx, _ = self._metrics()
        return x * self._c + z * sx, self._base() - z * dz - y * hy

    def _faces(self, px: int, py: int, levels: int = 1) -> tuple:
        """Top, front and right-side polygons of a box `levels` blocks tall
        whose front-top-left corner is (px, py)."""
        c = self._c
        dz, hy, sx, _ = self._metrics()
        h = hy * levels
        top = [(px, py), (px + c, py), (px + c + sx, py - dz), (px + sx, py - dz)]
        front = [(px, py), (px + c, py), (px + c, py + h), (px, py + h)]
        side = [(px + c, py), (px + c + sx, py - dz), (px + c + sx, py - dz + h), (px + c, py + h)]
        return top, front, side

    def _sprite_rect(self, vx: int, vz: int, y: int) -> pygame.Rect:
        dz, hy, sx, _ = self._metrics()
        px, py = self._corner(vx, vz, y + 1)
        return pygame.Rect(px, py - dz, self._c + sx + 1, dz + hy + 1)

    def _column_rect(self) -> pygame.Rect:
        vx, vz = self._view(self._x, self._z)
        return self._sprite_rect(vx, vz, HEIGHT - 1).union(self._sprite_rect(vx, vz, 0))

    # ---------------------------------------------------------------- drawing
    def _sprite(self, color: str, faded: bool = False) -> pygame.Surface:
        key = (color, self._c, faded)
        if key not in self._sprites:
            if faded:
                s = self._sprite(color).copy()
                s.set_alpha(XRAY_ALPHA)
            else:
                dz, hy, sx, _ = self._metrics()
                s = pygame.Surface((self._c + sx + 1, dz + hy + 1), pygame.SRCALPHA)
                for poly, shade in zip(self._faces(0, dz), (mix(color, "#ffffff", 0.22), rgb(color), mix(color, "#000000", 0.32))):
                    pygame.draw.polygon(s, shade, poly)
                    pygame.draw.polygon(s, rgb(P.LINE), poly, 1)
            self._sprites[key] = s
        return self._sprites[key]

    def _scene_size(self) -> tuple:
        dz, hy, sx, slab = self._metrics()
        return WIDTH * self._c + DEPTH * sx + 1, self._base() + slab + 1

    def _floor_surface(self) -> pygame.Surface:
        """Checkerboard floor on a slab, built once per cell size."""
        if self._floor is None or self._floor.get_size() != self._scene_size():
            self._floor = self._build_floor(P.SURFACE, CANVAS_BG, CANVAS_ALT, mix(CANVAS_BG, "#000000", 0.4),
                                            mix(CANVAS_BG, "#000000", 0.55))
        return self._floor

    def _build_floor(self, ground, tile, alt, slab_front, slab_side) -> pygame.Surface:
        dz, hy, sx, slab = self._metrics()
        s = pygame.Surface(self._scene_size())
        s.fill(rgb(ground))
        base, w = self._base(), WIDTH * self._c
        pygame.draw.polygon(s, rgb(slab_front), [(0, base), (w, base), (w, base + slab), (0, base + slab)])
        pygame.draw.polygon(s, rgb(slab_side),
                            [(w, base), (w + DEPTH * sx, base - DEPTH * dz), (w + DEPTH * sx, base - DEPTH * dz + slab), (w, base + slab)])
        for x in range(WIDTH):
            for z in range(DEPTH):
                top, _, _ = self._faces(*self._corner(x, z, 0))
                pygame.draw.polygon(s, rgb(alt if (x + z) % 2 else tile), top)
        return s

    def _xray(self, placed) -> frozenset:
        """Blocks nearer the viewer than the cursor's column that cover it on screen."""
        cvz = self._view(self._x, self._z)[1]
        col = self._column_rect()
        return frozenset((vx, vz, y) for vx, vz, y, _ in placed
                         if vz < cvz and self._sprite_rect(vx, vz, y).colliderect(col))

    def _scene_surface(self) -> pygame.Surface:
        """Floor plus every block, far rows first, left to right, bottom up,
        so nearer faces paint over farther ones."""
        placed = [(*self._view(x, z), y, color) for (x, z, y), color in self._blocks.items()]
        xray = self._xray(placed)
        if self._scene is None or self._scene.get_size() != self._scene_size() or xray != self._scene_xray:
            self._scene, self._scene_xray = self._stack(self._floor_surface().copy(), placed, xray), xray
        return self._scene

    def _stack(self, s, placed, xray=frozenset()) -> pygame.Surface:
        for vx, vz, y, color in sorted(placed, key=lambda b: (-b[1], b[0], b[2])):
            s.blit(self._sprite(color, (vx, vz, y) in xray), self._sprite_rect(vx, vz, y))
        return s

    def _fit(self, w, h) -> int:
        return max(6, int(min(w / (WIDTH + DEPTH * ROW_SKEW), h / (DEPTH * ROW_DEPTH + HEIGHT * BLOCK_RISE + SLAB))))

    def paper(self, g, size):
        """The build for printing, on a pale floor, nothing see-through and no cursor."""
        if not self._blocks:
            return None
        screen = self._c, self._sprites
        self._c, self._sprites = self._fit(*size), {}
        try:
            floor = self._build_floor(paper.WHITE, "#f1f1f1", "#e4e4e4", "#c8c8c8", "#b4b4b4")
            return self._stack(floor, [(*self._view(x, z), y, color) for (x, z, y), color in self._blocks.items()])
        finally:
            self._c, self._sprites = screen

    def draw(self, g, rect):
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = g.line_height(g.vh(1.9), "mono") + g.em(0.4)
        area = inner.inflate(0, -2 * (chrome_h + gap))
        c = self._fit(area.w, area.h)
        if c != self._c:
            self._c, self._sprites, self._scene = c, {}, None
        scene = self._scene_surface()
        ox = area.x + (area.w - scene.get_width()) // 2
        oy = area.y + (area.h - scene.get_height()) // 2
        self._origin = (ox, oy)
        g.surface.blit(scene, (ox, oy))
        p = self._fade_progress()
        if p is None:
            self._draw_cursor(g, ox, oy)
        elif self._fade_from is not None:
            self._fade_from.set_alpha(round(255 * (1 - p)))
            g.surface.blit(self._fade_from, (ox, oy))
        draw_mode_switch(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h), ("Front", "Back"),
                         1 if self._back else 0, self._color, "to turn around")
        foot_y = inner.bottom - chrome_h // 2
        g.draw_text(HINT, g.vh(1.9), inner.x, foot_y, "mono", P.DIM, anchor="midleft")
        g.draw_text(MIX_HINT, g.vh(1.9), inner.right, foot_y, "mono", P.DIM, anchor="midright")

    def _draw_cursor(self, g, ox, oy):
        """A faint glass column over the cursor's cell, and in it a see-through
        block where the next one will land."""
        vx, vz = self._view(self._x, self._z)
        col = self._column_rect()
        glass = pygame.Surface(col.size, pygame.SRCALPHA)
        shift = lambda poly, dx, dy: [(px + dx, py + dy) for px, py in poly]
        for poly in self._faces(*self._corner(vx, vz, HEIGHT), levels=HEIGHT):
            pygame.draw.polygon(glass, (*rgb(P.TEXT), 22), shift(poly, -col.x, -col.y))
            pygame.draw.polygon(glass, (*rgb(P.TEXT), 60), shift(poly, -col.x, -col.y), 1)
        g.surface.blit(glass, (ox + col.x, oy + col.y))
        y = self._cursor_y()
        if y >= HEIGHT:
            return
        r = self._sprite_rect(vx, vz, y)
        ghost = self._sprite(self._color).copy()
        ghost.set_alpha(150 if self._blink_on else 90)
        g.surface.blit(ghost, (ox + r.x, oy + r.y))
        for poly in self._faces(*self._corner(vx, vz, y + 1)):
            pygame.draw.polygon(g.surface, rgb(P.TEXT), shift(poly, ox, oy), 2)
