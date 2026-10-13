"""Blocks room: a floor seen from above and in front, where every letter (or
Space, in the current color) drops a block of its sticker color into the
cursor's column. Enter walks the cursor up a level at a time, starting over
at the floor after a pause at the top, and Shift with Up or Down moves it
either way; that height stays put as the arrows move, for building sideways.
Backspace takes blocks off the column top down from the cursor, then carries
on into the column to its left. Holding one letter while pressing another
mixes the two colors, and Backslash opens the color wheel. Tab flips to the
back side."""

import math
import time

import pygame

from ... import palette as P
from ...color_mixing import mix_colors_paint
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...palette import DEFAULT_BRUSH_COLOR
from .. import paper
from ..color_wheel import open_on as open_color_wheel
from ..gfx import mix, rgb
from ..ui import draw_mode_switch
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, CANVAS_ALT, CANVAS_BG, HOLD_ACCEL_MULTIPLIER, brush_for_key

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
WIDTH, DEPTH, HEIGHT = 30, 12, 12
FLIP_S = 0.22                 # crossfade, for builds too big to turn smoothly
TURN_S = 0.5
TURN_MAX_BLOCKS = 400
ROW_DEPTH, BLOCK_RISE, ROW_SKEW, SLAB = 0.5, 0.7, 0.3, 0.35   # in cell widths
FRONT_ALPHA = 85              # rows nearer than the cursor's row fade to this, so its row is the front one
PLATE_ALPHA = {0: 60, 1: 26, 2: 10}     # the cursor's height, by squared distance from its column
STEPS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
HINT = "Type to build! Enter or Shift+Up/Down for height."
MIX_HINT = "Hold two letters to mix"


class BlocksRoom:
    """Blocks live in a dict keyed by world (x, z, y), y up. Drawing and the
    arrows work in view coordinates, which are world (x, z) mirrored when the
    room shows its back. The floor and blocks render into two cached surfaces
    split at the cursor's row, rebuilt when a block changes, the room flips or
    the cursor changes rows: the rows from the cursor's back, solid, then the
    cursor, then the rows in front of it, faded."""

    name = "blocks"
    LANDSCAPE = True

    def __init__(self, app):
        self.app = app
        self._blocks: dict = {}
        self._x, self._z = WIDTH // 2, DEPTH // 2
        self._back = False
        self._hover = 0               # chosen cursor height; 0 = resting on the column
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
        self._front = self._scene_row = None
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
    def _column(self) -> list:
        return [y for (x, z, y) in self._blocks if (x, z) == (self._x, self._z)]

    def _free(self, ys) -> list:
        return [y for y in ys if (self._x, self._z, y) not in self._blocks]

    def _cursor_y(self) -> int:
        """The first free level at or above the chosen height, so the cursor never sits inside a block."""
        return next(iter(self._free(range(self._hover, HEIGHT))), HEIGHT)

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

    def _step_height(self, rise: int, wrap: bool = False):
        """The next free level up or down; with `wrap`, past the top starts over from the floor."""
        y = self._cursor_y()
        free = self._free(range(y + rise, HEIGHT if rise > 0 else -1, rise))
        if not free and wrap:
            free = self._free(range(HEIGHT))
        if free:
            self._hover = free[0]

    def _erase(self):
        """Backspace: the highest block below the cursor goes, and the cursor
        drops to its spot. With none left there, step left and take that column's top."""
        below = [y for y in self._column() if y < self._cursor_y()]
        if not below:
            if not self._move("left"):
                return
            below = self._column()
        self._hover = max(below, default=0)
        if below:
            del self._blocks[(self._x, self._z, self._hover)]
            self._changed()

    def _changed(self):
        self._scene = None
        self.app.invalidate()

    @property
    def brush_color(self) -> str:
        return self._color

    def set_brush_color(self, color: str, key: str = ""):
        self._key, self._color = key, color
        self.app.set_legend(color, visible=True)

    def _set_color(self, char: str):
        brush = brush_for_key(char)
        if brush:
            self.set_brush_color(brush[1], brush[0])
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
        """Turn around: a live half turn, or a crossfade when the build is too big to redraw every frame."""
        self._fade_from = self._composite() if self._c and len(self._blocks) > TURN_MAX_BLOCKS else None
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
        p = (time.monotonic() - self._fade_start) / (FLIP_S if self._fade_from is not None else TURN_S)
        if p >= 1:
            self._fade_start = None
            return None
        return p

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        if isinstance(action, ControlAction):
            if action.is_down and (not action.is_repeat or action.action in ("backspace", "enter")):
                self._control(action.action, action.is_repeat)
        elif isinstance(action, NavigationAction):
            self._navigate(action)
        elif isinstance(action, CharacterAction) and not action.is_repeat:
            self._character(action)
        self._restart_blink()
        self.app.invalidate()

    def _character(self, action):
        char = UNSHIFT_MAP.get(action.char, action.char) if action.shift_held else action.char
        if open_color_wheel(self, char) or not self._set_color(char) or action.shift_held:
            return
        held = brush_for_key(action.char_held) if action.char_held else None
        if not (held and self._mix_into_last(held[0])):
            self._place()

    def _control(self, name: str, is_repeat: bool = False):
        if name == "space":
            self._place()
        elif name == "enter":
            self._step_height(1, wrap=not is_repeat)    # a held Enter stops at the top
        elif name == "backspace":
            self._erase()
        elif name == "tab":
            self._flip()

    def _navigate(self, action):
        if action.shift_held and action.direction in ("up", "down"):
            self._step_height(STEPS[action.direction][1])
            return
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        laying = (bool(action.char_held) and self._set_color(action.char_held)) or action.space_held
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

    # ---------------------------------------------------------------- drawing
    def _sprite(self, color: str, alpha: int = 255) -> pygame.Surface:
        key = (color, self._c, alpha)
        if key not in self._sprites:
            if alpha < 255:
                s = self._sprite(color).copy()
                s.set_alpha(alpha)
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

    def _placed(self) -> list:
        return [(*self._view(x, z), y, color) for (x, z, y), color in self._blocks.items()]

    def _scene_surfaces(self) -> tuple:
        """(floor with the cursor's row marked plus the blocks from that row back, faded blocks in front of it)."""
        row = self._view(self._x, self._z)[1]
        if self._scene is None or self._scene.get_size() != self._scene_size() or row != self._scene_row:
            self._scene_row = row
            back = [b for b in self._placed() if b[1] >= row]
            self._scene = self._stack(self._mark_row(self._floor_surface().copy(), row), back)
            self._front = self._stack(pygame.Surface(self._scene_size(), pygame.SRCALPHA),
                                      [b for b in self._placed() if b[1] < row])
            self._front.set_alpha(FRONT_ALPHA)
        return self._scene, self._front

    def _mark_row(self, s, row) -> pygame.Surface:
        stripe = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        for x in range(WIDTH):
            top, _, _ = self._faces(*self._corner(x, row, 0))
            pygame.draw.polygon(stripe, (*rgb(P.TEXT), 22), top)
        s.blit(stripe, (0, 0))
        return s

    def _composite(self) -> pygame.Surface:
        return self._stack(self._scene_surfaces()[0].copy(), [b for b in self._placed() if b[1] < self._scene_row])

    def _stack(self, s, placed) -> pygame.Surface:
        """Far rows first, left to right, bottom up, so nearer faces paint over farther ones."""
        for vx, vz, y, color in sorted(placed, key=lambda b: (-b[1], b[0], b[2])):
            s.blit(self._sprite(color), self._sprite_rect(vx, vz, y))
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
            return self._stack(floor, self._placed())
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
        scene, front = self._scene_surfaces()
        ox = area.x + (area.w - scene.get_width()) // 2
        oy = area.y + (area.h - scene.get_height()) // 2
        self._origin = (ox, oy)
        p = self._fade_progress()
        if p is None:
            g.surface.blit(scene, (ox, oy))
            self._draw_cursor(g, ox, oy, front)
        elif self._fade_from is not None:
            g.surface.blit(scene, (ox, oy))
            g.surface.blit(front, (ox, oy))
            self._fade_from.set_alpha(round(255 * (1 - p)))
            g.surface.blit(self._fade_from, (ox, oy))
        else:
            self._draw_turning(g, ox, oy, p)
        draw_mode_switch(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h), ("Front", "Back"),
                         1 if self._back else 0, self._color, "to turn around")
        foot_y = inner.bottom - chrome_h // 2
        g.draw_text(HINT, g.vh(1.9), inner.x, foot_y, "mono", P.DIM, anchor="midleft")
        g.draw_text(MIX_HINT, g.vh(1.9), inner.right, foot_y, "mono", P.DIM, anchor="midright")

    def _draw_turning(self, g, ox, oy, p):
        """One frame of the half turn: the world spun about the floor's center
        and drawn through the same slanted projection as the resting view, so
        both ends land exactly on the front and back pictures. Flat faces, no
        checkerboard, since nothing holds still long enough to see it. Zooms out
        mid-turn so the long floor, end-on, still fits."""
        dz, hy, sx, slab = self._metrics()
        c = self._c
        angle = math.pi * ((p * p * (3 - 2 * p)) + (0 if self._back else 1))
        cos, sin = math.cos(angle), math.sin(angle)
        ex = (cos * c + sin * sx, -sin * dz)            # one world step in x, on screen
        ez = (-sin * c + cos * sx, -cos * dz)           # one world step in z
        corners = [(a * WIDTH / 2, b * DEPTH / 2) for a in (-1, 1) for b in (-1, 1)]
        xs = [a * ex[0] + b * ez[0] for a, b in corners]
        ys = [a * ex[1] + b * ez[1] for a, b in corners]
        half_w, half_d = WIDTH / 2 * c, DEPTH / 2 * dz
        k = min(1.0, (half_w + DEPTH / 2 * sx) / max(max(xs), -min(xs)), (half_d + slab) / (max(ys) + slab),
                (half_d + HEIGHT * hy) / (-min(ys) + HEIGHT * hy))
        ex, ez, hy = (ex[0] * k, ex[1] * k), (ez[0] * k, ez[1] * k), hy * k
        cx, cz = WIDTH / 2, DEPTH / 2
        center = (ox + cx * c + cz * sx, oy + self._base() - cz * dz)

        def at(x, y, z):
            return (center[0] + (x - cx) * ex[0] + (z - cz) * ez[0],
                    center[1] + (x - cx) * ex[1] + (z - cz) * ez[1] - y * hy)

        sides = []                                      # (corner offsets, darkness) for the sides facing the viewer
        for nx, nz, quad in ((0, -1, ((0, 0), (1, 0))), (1, 0, ((1, 0), (1, 1))),
                             (0, 1, ((1, 1), (0, 1))), (-1, 0, ((0, 1), (0, 0)))):
            rnx, rnz = nx * cos - nz * sin, nx * sin + nz * cos
            if rnz - ROW_SKEW * rnx < 0:
                sides.append((quad, 0.32 * max(0.0, rnx)))

        def box(x0, y0, z0, x1, y1, z1, top, side, seam=None):
            pts = []
            for (ax, az), (bx, bz) in (q for q, _ in sides):
                pts.append([at(x0 + (x1 - x0) * ax, y0, z0 + (z1 - z0) * az), at(x0 + (x1 - x0) * bx, y0, z0 + (z1 - z0) * bz),
                            at(x0 + (x1 - x0) * bx, y1, z0 + (z1 - z0) * bz), at(x0 + (x1 - x0) * ax, y1, z0 + (z1 - z0) * az)])
            pts.append([at(x0, y1, z0), at(x1, y1, z0), at(x1, y1, z1), at(x0, y1, z1)])
            for poly, color in zip(pts, [side(dark) for _, dark in sides] + [top]):
                pygame.draw.polygon(g.surface, color, poly)
                if seam:
                    pygame.draw.polygon(g.surface, seam, poly, 1)

        slab_bg, seam = mix(CANVAS_BG, "#000000", 0.4), rgb(P.LINE)
        box(0, -SLAB / BLOCK_RISE, 0, WIDTH, 0, DEPTH, rgb(CANVAS_BG), lambda dark: mix(slab_bg, "#000000", dark))
        shades: dict = {}

        def shade(color, dark):
            if (color, dark) not in shades:
                shades[(color, dark)] = mix(color, "#000000", dark)
            return shades[(color, dark)]

        def depth(b):
            (x, z, y), _ = b
            dx, dz_ = x + 0.5 - cx, z + 0.5 - cz
            return (dx * sin + dz_ * cos) - ROW_SKEW * (dx * cos - dz_ * sin) - y * ROW_DEPTH / BLOCK_RISE

        for (x, z, y), color in sorted(self._blocks.items(), key=depth, reverse=True):
            box(x, y, z, x + 1, y + 1, z + 1, mix(color, "#ffffff", 0.22), lambda dark, col=color: shade(col, dark), seam)

    def _draw_cursor(self, g, ox, oy, front):
        """A blinking glass column over the cursor's cell, the landing block's
        shadow on whatever it would land on, a plate fading out around it at
        its height, and the see-through block itself; then the faded rows in
        front, and the landing block's outline on top of everything."""
        vx, vz = self._view(self._x, self._z)
        y = self._cursor_y()
        layer = pygame.Surface(self._scene_size(), pygame.SRCALPHA)
        fill, edge = (40, 150) if self._blink_on else (16, 70)
        for poly in self._faces(*self._corner(vx, vz, HEIGHT), levels=HEIGHT):
            pygame.draw.polygon(layer, (*rgb(self._color), fill), poly)
            pygame.draw.polygon(layer, (*rgb(P.TEXT), edge), poly, 1)
        if y < HEIGHT:
            self._shadow(layer, vx, vz, y)
            self._plate(layer, vx, vz, y)
            layer.blit(self._sprite(self._color, 170 if self._blink_on else 100), self._sprite_rect(vx, vz, y))
        layer.blit(front, (0, 0))
        if y < HEIGHT:
            for poly in self._faces(*self._corner(vx, vz, y + 1)):
                pygame.draw.polygon(layer, rgb(P.TEXT), poly, 2)
        g.surface.blit(layer, (ox, oy))

    def _shadow(self, layer, vx, vz, y):
        """A dark square on the floor or block under the landing spot, and a thread down to it when it floats."""
        ground = max((h + 1 for h in self._column() if h < y), default=0)
        top, _, _ = self._faces(*self._corner(vx, vz, ground))
        pygame.draw.polygon(layer, (0, 0, 0, 110), top)
        if ground < y:
            cx = (top[0][0] + top[2][0]) / 2
            cy = (top[0][1] + top[2][1]) / 2
            pygame.draw.line(layer, (*rgb(P.TEXT), 110), (cx, cy), (cx, cy - (y - ground) * self._metrics()[1]), 1)

    def _plate(self, layer, vx, vz, y):
        cells = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if 0 <= vx + dx < WIDTH and 0 <= vz + dz < DEPTH]
        for dx, dz in cells:
            top, _, _ = self._faces(*self._corner(vx + dx, vz + dz, y))
            pygame.draw.polygon(layer, (*rgb(P.TEXT), PLATE_ALPHA[dx * dx + dz * dz]), top)
