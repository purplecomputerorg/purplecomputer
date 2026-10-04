"""Blocks room: a floor seen from above and in front, where every letter drops a
block of its sticker color at the cursor. The cursor is a see-through block
that rests on top of its column; Space lifts it a level (for roofs, bridges
and tree tops) and Enter lets it rest again. Holding one letter while pressing
another mixes the two colors into the block. Tab turns the room a quarter
turn; arrows always move the way they point on screen."""

import time

import pygame

from ... import palette as P
from ...color_mixing import mix_colors_paint
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...palette import DEFAULT_BRUSH_COLOR
from ..gfx import hexcolor, mix, rgb
from ..ui import draw_keycap
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, CANVAS_ALT, CANVAS_BG, HOLD_ACCEL_MULTIPLIER, brush_for_key

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
SIZE, HEIGHT = 16, 10         # square floor, so every quarter turn looks the same size
SPIN_S = 0.18
ROW_DEPTH, BLOCK_RISE, ROW_SKEW, SLAB = 0.5, 0.7, 0.3, 0.35   # in cell widths
SEAM = hexcolor(mix(CANVAS_BG, "#000000", 0.3))
XRAY_ALPHA = 80
STEPS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
KEYS = (("Space", "up"), ("Enter", "down"), ("Tab", "turn"))
HINT = "Type to build! Hold one letter and press another to mix colors."


class BlocksRoom:
    """Blocks live in a dict keyed by world (x, z, y), y up. Drawing and the
    arrows work in view coordinates: world (x, z) turned self._turn quarter
    turns. The floor and blocks render into one cached surface, rebuilt when a
    block changes, the room turns, or the blocks in front of the cursor
    change; the cursor is drawn over it."""

    name = "blocks"

    def __init__(self, app):
        self.app = app
        self._blocks: dict = {}
        self._x, self._z = SIZE // 2, SIZE // 2
        self._turn = 0
        self._hover = 0               # lifted cursor height; 0 = resting on the column
        self._color = DEFAULT_BRUSH_COLOR
        self._last = None             # (pos, key) of the last block dropped, for chords
        self._spin_from = self._spin_start = self._spin_timer = None
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
        state.update(cursor=[self._x, self._z], color=self._color, hover=self._hover, turn=self._turn)
        return state

    def restore_timeline_state(self, state: dict):
        self._blocks = {tuple(int(n) for n in k[2:].split(",")): v for k, v in state.items() if k.startswith("b:")}
        self._x, self._z = state.get("cursor", [SIZE // 2, SIZE // 2])
        self._color = state.get("color", DEFAULT_BRUSH_COLOR)
        self._hover = state.get("hover", 0)
        self._turn = state.get("turn", 0)
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

    def _place(self, key: str):
        y = self._cursor_y()
        if y < HEIGHT:
            self._blocks[(self._x, self._z, y)] = self._color
            self._last = ((self._x, self._z, y), key)
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

    def _remove_top(self):
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
            self._color = brush[1]
            self.app.set_legend(self._color, visible=True)
        return brush[0] if brush else None

    def _move(self, direction: str) -> bool:
        dx, dz = STEPS[direction]
        vx, vz = self._view(self._x, self._z)
        vx, vz = vx + dx, vz + dz
        if not (0 <= vx < SIZE and 0 <= vz < SIZE):
            return False
        self._x, self._z = _rotate(vx, vz, -self._turn)
        return True

    def _view(self, x: int, z: int) -> tuple:
        return _rotate(x, z, self._turn)

    # ---------------------------------------------------------------- turning
    def _spin(self):
        """Quarter turn, shown as the picture squashing to a sliver and
        opening back out from the new side."""
        self._spin_from = self._scene_surface() if self._c else None
        self._turn = (self._turn + 1) % 4
        self._spin_start = time.monotonic()
        if self._spin_timer is None:
            self._spin_timer = self.app.timers.every(1 / 60, self._spin_tick)
        self._changed()

    def _spin_tick(self):
        if self._spin_progress() is None:
            self._spin_timer.stop()
            self._spin_timer = self._spin_from = None
        self.app.invalidate()

    def _spin_progress(self):
        if self._spin_start is None:
            return None
        p = (time.monotonic() - self._spin_start) / SPIN_S
        if p >= 1:
            self._spin_start = None
            return None
        return p

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        if isinstance(action, ControlAction):
            if action.is_down and (not action.is_repeat or action.action == "backspace"):
                self._control(action.action)
        elif isinstance(action, NavigationAction):
            self._navigate(action)
        elif isinstance(action, CharacterAction) and not action.is_repeat:
            self._character(action)
        self._restart_blink()
        self.app.invalidate()

    def _character(self, action):
        char = UNSHIFT_MAP.get(action.char, action.char) if action.shift_held else action.char
        key = self._set_color(char)
        if not key or action.shift_held:
            return
        held = brush_for_key(action.char_held) if action.char_held else None
        if not (held and self._mix_into_last(held[0])):
            self._place(key)

    def _control(self, name: str):
        if name == "space":
            self._hover = min(HEIGHT - 1, self._cursor_y() + 1)
        elif name == "enter":
            self._hover = 0
        elif name == "tab":
            self._spin()
        elif name == "backspace":
            self._remove_top()

    def _navigate(self, action):
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        key = self._set_color(action.char_held) if action.char_held else None
        fast = not key and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(HOLD_ACCEL_MULTIPLIER if fast else 1):
                if not self._move(direction):
                    break
                if key:
                    self._place(key)

    # ---------------------------------------------------------------- geometry
    def _metrics(self):
        c = self._c
        return round(c * ROW_DEPTH), round(c * BLOCK_RISE), round(c * ROW_SKEW), round(c * SLAB)

    def _base(self) -> int:
        dz, hy, _, _ = self._metrics()
        return SIZE * dz + HEIGHT * hy

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
                seam = max(1, round(self._c / 20))
                for poly, shade in zip(self._faces(0, dz), (mix(color, "#ffffff", 0.22), rgb(color), mix(color, "#000000", 0.32))):
                    pygame.draw.polygon(s, shade, poly)
                    pygame.draw.polygon(s, rgb(SEAM), poly, seam)
            self._sprites[key] = s
        return self._sprites[key]

    def _scene_size(self) -> tuple:
        dz, hy, sx, slab = self._metrics()
        return SIZE * self._c + SIZE * sx + 1, self._base() + slab + 1

    def _floor_surface(self) -> pygame.Surface:
        """Checkerboard floor on a slab, built once per cell size."""
        if self._floor is None or self._floor.get_size() != self._scene_size():
            dz, hy, sx, slab = self._metrics()
            s = pygame.Surface(self._scene_size())
            s.fill(rgb(P.SURFACE))
            base, w = self._base(), SIZE * self._c
            pygame.draw.polygon(s, mix(CANVAS_BG, "#000000", 0.4), [(0, base), (w, base), (w, base + slab), (0, base + slab)])
            pygame.draw.polygon(s, mix(CANVAS_BG, "#000000", 0.55),
                                [(w, base), (w + SIZE * sx, base - SIZE * dz), (w + SIZE * sx, base - SIZE * dz + slab), (w, base + slab)])
            for x in range(SIZE):
                for z in range(SIZE):
                    top, _, _ = self._faces(*self._corner(x, z, 0))
                    pygame.draw.polygon(s, rgb(CANVAS_ALT if (x + z) % 2 else CANVAS_BG), top)
            self._floor = s
        return self._floor

    def _xray(self, placed) -> frozenset:
        """Blocks nearer the viewer than the cursor's column that cover it on screen."""
        cvx, cvz = self._view(self._x, self._z)
        col = self._column_rect()
        return frozenset((vx, vz, y) for vx, vz, y, _ in placed
                         if vz < cvz and self._sprite_rect(vx, vz, y).colliderect(col))

    def _scene_surface(self) -> pygame.Surface:
        """Floor plus every block, far rows first, left to right, bottom up,
        so nearer faces paint over farther ones."""
        placed = [(*self._view(x, z), y, color) for (x, z, y), color in self._blocks.items()]
        xray = self._xray(placed)
        if self._scene is None or self._scene.get_size() != self._scene_size() or xray != self._scene_xray:
            s = self._floor_surface().copy()
            for vx, vz, y, color in sorted(placed, key=lambda b: (-b[1], b[0], b[2])):
                s.blit(self._sprite(color, (vx, vz, y) in xray), self._sprite_rect(vx, vz, y))
            self._scene, self._scene_xray = s, xray
        return self._scene

    def draw(self, g, rect):
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = g.line_height(g.vh(1.9), "mono") + g.em(0.4)
        area = inner.inflate(0, -2 * (chrome_h + gap))
        c = max(6, int(min(area.w / (SIZE * (1 + ROW_SKEW)),
                           area.h / (SIZE * ROW_DEPTH + HEIGHT * BLOCK_RISE + SLAB))))
        if c != self._c:
            self._c, self._sprites, self._scene = c, {}, None
        p = self._spin_progress()
        scene = self._scene_surface() if p is None or p >= 0.5 or self._spin_from is None else self._spin_from
        ox = area.x + (area.w - scene.get_width()) // 2
        oy = area.y + (area.h - scene.get_height()) // 2
        self._origin = (ox, oy)
        if p is None:
            g.surface.blit(scene, (ox, oy))
            self._draw_cursor(g, ox, oy)
        else:
            w, h = scene.get_size()
            sw = max(1, round(w * abs(2 * p - 1)))
            g.surface.blit(pygame.transform.scale(scene, (sw, h)), (ox + (w - sw) // 2, oy))
        self._draw_header(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h))
        g.draw_text(HINT, g.vh(1.9), inner.x, inner.bottom - chrome_h // 2, "mono", P.DIM, anchor="midleft")

    def _draw_header(self, g, r):
        """Brush swatch on the left; the three keys and what they do on the right."""
        px = g.vh(1.9)
        sw = round(r.h * 0.5)
        g.rect(self._color, (r.x, r.centery - sw // 2, sw, sw))
        x = r.right
        for key, label in reversed(KEYS):
            x = g.draw_text(label, px, x, r.centery, "mono", P.MUTED, anchor="midright").left - int(px * 0.9)
            x = draw_keycap(g, key, px, x, r.centery, anchor="midright").left - int(px * 1.6)

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


def _rotate(x: int, z: int, turns: int) -> tuple:
    for _ in range(turns % 4):
        x, z = SIZE - 1 - z, x
    return x, z
