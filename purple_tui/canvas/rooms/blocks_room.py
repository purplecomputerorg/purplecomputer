"""Blocks room: a floor seen from above and in front, where every letter (or
Space, in the current color) drops a block of its sticker color into the
cursor's column, then moves on the way the cursor last went: along an arrow,
or up after Enter or Shift+Up/Down. Enter (once already going up) walks the
cursor up a level at a time, starting over at the floor after a pause at the
top, and Shift with Up or Down moves it either way; that height stays put as
the arrows move, for building sideways. At the top, letters mix into the top
block.
Backspace takes blocks off the column top down from the cursor, then carries
on into the column to its left. A letter landing on a block, as a stack
reaches a floating one or a line crosses one, paint-mixes into it, and
holding one letter while pressing another mixes the two colors. Backslash
opens the color wheel, Tab flips to the back side, and holding Space opens
the code line."""

import asyncio
import math
import time
from functools import cache

import pygame

from ... import palette as P
from ...color_mixing import mix_colors_paint
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...palette import DEFAULT_BRUSH_COLOR
from .. import color_recipe, paper
from ..color_wheel import chip as wheel_chip, open_on as open_color_wheel
from ..gfx import mix, rgb
from ..panels import CodePanel, Echo, SpaceHold
from ..ui import draw_key_hint, draw_mode_switch
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, CANVAS_ALT, CANVAS_BG, HOLD_ACCEL_MULTIPLIER, brush_for_key
from .blocks_code import WORDS, BlocksCodeRunner

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
WIDTH, DEPTH, HEIGHT = 30, 12, 12
TURN_S = 0.5
TURN_DETAIL_BLOCKS = 600     # visible blocks; past this the half turn drops seams and shadows
ROW_DEPTH, BLOCK_RISE, ROW_SKEW, SLAB = 0.5, 0.7, 0.3, 0.35   # in cell widths
FRONT_ALPHA = 85              # rows nearer than the cursor's row fade to this when they hide the landing block
CEILING_ALPHA = {0: 70, 1: 30, 2: 12}   # by squared distance from the cursor's column
DEPTH_FADE = 0.3              # how far the back row's blocks lean toward the floor color
SHADOW_ALPHA = 140
STEM_ALPHA, STEM_DARKEN = 150, 0.35   # the line from a floating block down to its shadow
CAGE_PAD = 0.18               # in cells: the wire box around the landing block
# The direction arrow as (along, across) points in cells, from the box center outward.
POINTER = ((0.1, -0.09), (0.75, -0.09), (0.75, -0.3), (1.2, 0), (0.75, 0.3), (0.75, 0.09), (0.1, 0.09))
STEPS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
RISE, SINK = "rise", "sink"
SIZE = {"x": WIDTH, "z": DEPTH, "y": HEIGHT}
# Where typing goes next, by way: along the first axis; off its end, back to
# its start and one step along the second (a new line); off that, the third.
WRAP = {"right": (("x", 1), ("z", 1), ("y", 1)), "left": (("x", -1), ("z", 1), ("y", 1)),
        "up": (("z", 1), ("x", 1), ("y", 1)), "down": (("z", -1), ("x", 1), ("y", 1)),
        RISE: (("y", 1), ("x", 1), ("z", 1)), SINK: (("y", -1), ("x", 1), ("z", 1))}
HINT = "Type to build the way you last moved! {Enter} goes up."


@cache
def haze(color, row: int) -> tuple:
    return mix(color, CANVAS_BG, DEPTH_FADE * row / (DEPTH - 1))


@cache
def tint(color, toward: str, t: float) -> tuple:
    """`mix`, remembered: the half turn asks for the same few shades every frame."""
    return mix(color, toward, t)


class BlocksRoom:
    """Blocks live in a dict keyed by world (x, z, y), y up. Drawing and the
    arrows work in view coordinates, which are world (x, z) mirrored when the
    room shows its back. The floor and blocks render into two cached surfaces
    split at the cursor's row, rebuilt when a block changes, the room flips or
    the cursor changes rows: the rows from the cursor's back, solid, then the
    cursor, then the rows in front of it, faded."""

    name = "blocks"
    LANDSCAPE = True
    HAS_CODE = True
    wheel_ready = True

    def __init__(self, app):
        self.app = app
        self._blocks: dict = {}
        self._x, self._z = WIDTH // 2, DEPTH // 2
        self._back = False
        self._hover = 0               # chosen cursor height; 0 = resting on the column
        self._color = DEFAULT_BRUSH_COLOR
        self._key = ""
        self._last_mix = None         # color_recipe.made() for the mix just made, until the next brush
        self._last = None             # (pos, key) of the block just dropped
        self._next = None             # where the next letter goes after it, even onto a floating block
        self._dir = "right"           # the way typing builds: a key of WRAP
        self._fade_start = self._fade_timer = None
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._blink_on = True
        self._blink_timer = None
        self._c = 0
        self._origin = (0, 0)
        self._floor = self._scene = None
        self._front = self._scene_row = None
        self._sprites: dict = {}
        self.space = SpaceHold(app, self._space_tap, self._space_hold_fired)
        self.echo = Echo()
        self.code_panel = None

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        self.app.set_legend(self._color, visible=True)
        if self._blink_timer is None:
            self._blink_timer = self.app.timers.every(0.4, self._blink)

    def on_leave(self):
        self.code_panel = None
        if self._blink_timer:
            self._blink_timer.stop()
            self._blink_timer = None

    def stop_sound(self):
        pass

    def open_code_panel(self):
        if self.code_panel is None and self.app._code_panel_enabled:
            self.code_panel = CodePanel(self.app, "blocks", self.echo.take())
            self.app.set_panel(self.code_panel)

    def close_code_panel(self):
        if self.code_panel is not None:
            self.code_panel = None
            self.app.set_panel(None)

    def _space_hold_fired(self):
        if self.code_panel is None:
            self.open_code_panel()
        else:
            self.close_code_panel()

    def _space_tap(self):
        if self.code_panel is not None:
            self.code_panel.field.insert(" ")
        else:
            self._control("space")
        self.app.invalidate()

    async def run_code(self, lines: list):
        try:
            runner = BlocksCodeRunner(self)
            await runner.run(lines)
            if runner.corrections and self.code_panel:
                self.code_panel.set_correction(*runner.corrections[-1])
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        self.app.invalidate()

    def hold_progress(self):
        return self.space.status(self.code_panel is not None)

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
        state.update(cursor=[self._x, self._z], color=self._color, hover=self._hover)   # front or back is just a view
        return state

    def restore_timeline_state(self, state: dict):
        # Older builds had a bigger floor; their steps may hold blocks past today's walls.
        blocks = {tuple(int(n) for n in k[2:].split(",")): v for k, v in state.items() if k.startswith("b:")}
        self._blocks = {p: c for p, c in blocks.items() if all(0 <= n < SIZE[a] for n, a in zip(p, "xzy"))}
        x, z = state.get("cursor", [WIDTH // 2, DEPTH // 2])
        self._x, self._z = min(max(x, 0), WIDTH - 1), min(max(z, 0), DEPTH - 1)
        self._color = state.get("color", DEFAULT_BRUSH_COLOR)
        self._hover = state.get("hover", 0)
        self._last = self._next = self._last_mix = None
        self._dir = "right"
        self.echo.reset()
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
        """Where the block just dropped sent it, so a stack never skips past a
        floating block; otherwise the first free level at or above the chosen
        height. Never above the top level: a full column puts it on the top block."""
        if self._next and self._next[:2] == (self._x, self._z):
            return self._next[2]
        return next(iter(self._free(range(self._hover, HEIGHT))), HEIGHT - 1)

    def _place(self, y=None):
        """A block at height y (the cursor's by default), paint-mixed into one already there."""
        y = self._cursor_y() if y is None else y
        pos = (self._x, self._z, y)
        old = self._blocks.get(pos)
        self._blocks[pos] = mix_colors_paint([old, self._color]) if old else self._color
        self._last = (pos, self._key)
        self._changed()

    def _build(self):
        """A typed block, then on to the next cell the way the cursor last went."""
        y = self._cursor_y()
        self._place(y)
        self._advance(y)

    def _advance(self, y: int):
        """On from the cursor's column at height y the way it last went, wrapping at the walls like lines of text."""
        pos = self._spot(y)
        for axis, step in WRAP[self._dir]:
            pos[axis] += step
            if 0 <= pos[axis] < SIZE[axis]:
                break
            pos[axis] = 0 if step > 0 else SIZE[axis] - 1
        self._x, self._z = self._view(pos["x"], pos["z"])
        self._next = (self._x, self._z, pos["y"])

    def _spot(self, y=None) -> dict:
        """The cursor in view coordinates, at height y or its own."""
        vx, vz = self._view(self._x, self._z)
        return {"x": vx, "z": vz, "y": self._cursor_y() if y is None else y}

    def _face(self, way: str):
        """Typing goes the way the cursor walked, unless a wall is right there,
        since the kid walked to it on purpose: then along it, right, or left
        in the right-hand corner. Wrapping is for runs typing carries to a wall."""
        def room_ahead(w):
            axis, step = WRAP[w][0]
            return 0 <= self._spot()[axis] + step < SIZE[axis]
        self._dir = next((w for w in (way, "right", "left") if room_ahead(w)), way)

    # What code drives: the same moves as the keys, minus the echo.
    def set_way(self, way: str):
        self._dir = way

    build = _build

    def build_letter(self, ch: str) -> bool:
        if not self._set_color(ch):
            return False
        self._build()
        return True

    def skip(self):
        self._advance(self._cursor_y())

    def _mix_into_last(self, held_key: str) -> bool:
        """A chord: the block the held key just dropped takes the new color
        mixed in. Holding on, each next key mixes in too."""
        if not self._last or self._last[1] != held_key or self._last[0] not in self._blocks:
            return False
        pos, before = self._last[0], self._blocks[self._last[0]]
        self._color = self._blocks[pos] = mix_colors_paint([before, self._color])
        self._last_mix = color_recipe.made(held_key, before, self._key, self._color)
        self._last = (pos, self._key)
        self.app.set_legend(self._color, visible=True)
        self._changed()
        return True

    def _step_height(self, rise: int, wrap: bool = False):
        """The next free level up or down; with `wrap`, past the top starts over from the floor."""
        y, self._next = self._cursor_y(), None
        free = self._free(range(y + rise, HEIGHT if rise > 0 else -1, rise))
        if not free and wrap:
            free = self._free(range(HEIGHT))
        if free:
            self._hover = free[0]

    def _erase(self):
        """Backspace: the highest block at or below the cursor goes, and the cursor
        drops to its spot. With none left there, step left and take that column's top."""
        below = [y for y in self._column() if y <= self._cursor_y()]
        self._next = None
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
        self._key, self._color, self._last_mix = key, color, None
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
        self._next = None
        return True

    def _view(self, x: int, z: int) -> tuple:
        """World to view and back: the back side is the front mirrored both ways."""
        return (WIDTH - 1 - x, DEPTH - 1 - z) if self._back else (x, z)

    # ---------------------------------------------------------------- flipping
    def turn_around(self):
        """Tab, here or in Time Travel: a live half turn, one at a time."""
        if self._fade_progress() is not None:
            return
        self._back = not self._back
        self._fade_start = time.monotonic()
        if self._fade_timer is None:
            self._fade_timer = self.app.timers.every(1 / 60, self._fade_tick)
        self._changed()

    def _fade_tick(self):
        if self._fade_progress() is None:
            self._fade_timer.stop()
            self._fade_timer = None
        self.app.invalidate()

    def _fade_progress(self):
        if self._fade_start is None:
            return None
        p = (time.monotonic() - self._fade_start) / TURN_S
        if p >= 1:
            self._fade_start = None
            return None
        return p

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        if isinstance(action, ControlAction) and action.action == "space" and self.space.route(action):
            return
        self.space.other_key()
        if self.code_panel is not None:
            result = await self.code_panel.handle(action)
            if result == "tab_fallthrough":
                self.turn_around()
            elif result == "close":
                self.close_code_panel()
            return
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
        if held and self._mix_into_last(held[0]):
            return
        if char.isalpha():
            self.echo.letter(WORDS[self._dir], char)
        else:
            self.echo.flush()       # a digit would read as a count
        self._build()

    def _lay(self, way: str):
        """A block in the brush color, written down as code too."""
        self.echo.color(self._color)
        self.echo.step(WORDS[way])

    def _control(self, name: str, is_repeat: bool = False):
        if name != "space":
            self.echo.flush()
        if name == "space":
            self._lay(self._dir)
            self._build()
        elif name == "enter" and self._dir != RISE:
            self._dir = RISE                            # first, just turn typing upward
        elif name == "enter":
            self._step_height(1, wrap=not is_repeat)    # a held Enter stops at the top
        elif name == "backspace":
            self._erase()
        elif name == "tab":
            self.turn_around()

    def _navigate(self, action):
        if action.shift_held and action.direction in ("up", "down"):
            self.echo.flush()
            self._step_height(STEPS[action.direction][1])
            self._face(RISE if action.direction == "up" else SINK)
            return
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        laying = (bool(action.char_held) and self._set_color(action.char_held)) or action.space_held
        if not laying:
            self.echo.flush()
        fast = not laying and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(HOLD_ACCEL_MULTIPLIER if fast else 1):
                if not self._move(direction):
                    break
                if laying:
                    self._lay(direction)
                    self._place(self._hover)        # a line keeps its height, mixing into blocks in its way
                    self._next = (self._x, self._z, self._hover)
        self._face(action.direction)

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
    def _sprite(self, color: str, alpha: int = 255, row=None) -> pygame.Surface:
        """A block; with `row`, hazed toward the floor color the farther back it sits."""
        key = (color, self._c, alpha, row)
        if key not in self._sprites:
            if alpha < 255:
                s = self._sprite(color, row=row).copy()
                s.set_alpha(alpha)
            else:
                dz, hy, sx, _ = self._metrics()
                s = pygame.Surface((self._c + sx + 1, dz + hy + 1), pygame.SRCALPHA)
                if row is not None:
                    color = haze(color, row)
                for poly, shade in zip(self._faces(0, dz), (mix(color, "#ffffff", 0.22), rgb(color), mix(color, "#000000", 0.32))):
                    pygame.draw.polygon(s, shade, poly)
                    pygame.draw.polygon(s, rgb(P.LINE), poly, 1)
            self._sprites[key] = s
        return self._sprites[key]

    def _shadow_sprite(self, gap: int, color: str) -> pygame.Surface:
        """A dark square on the surface below a floating block, and a line in the block's color up to it."""
        key = ("shadow", self._c, gap, color)
        if key not in self._sprites:
            dz, hy, sx, _ = self._metrics()
            s = pygame.Surface((self._c + sx + 1, dz + hy + 1 + gap * hy), pygame.SRCALPHA)
            pygame.draw.polygon(s, (0, 0, 0, SHADOW_ALPHA), self._faces(0, dz + gap * hy)[0])
            cx, cy = (self._c + sx) / 2, dz / 2 + gap * hy
            if gap:
                pygame.draw.line(s, (*mix(color, "#000000", STEM_DARKEN), STEM_ALPHA), (cx, cy), (cx, cy - gap * hy), 2)
            self._sprites[key] = s
        return self._sprites[key]

    def _shadow(self, s, vx, vz, ground, y, color):
        r = self._sprite_rect(vx, vz, ground - 1)
        s.blit(self._shadow_sprite(y - ground, color), (r.x, r.y - (y - ground) * self._metrics()[1]))

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
        self._front.set_alpha(FRONT_ALPHA if self._front_covers_cursor() else 255)
        return self._scene, self._front

    def _front_covers_cursor(self) -> bool:
        """Whether a nearer block hides the landing block's top; any block just in front hides its front face."""
        vx, vz = self._view(self._x, self._z)
        xs, ys = zip(*self._faces(*self._corner(vx, vz, self._cursor_y() + 1))[0])
        spot = pygame.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).inflate(-2, -2)
        return any(b[1] < vz and self._sprite_rect(*b[:3]).colliderect(spot) for b in self._placed())

    def _mark_row(self, s, row) -> pygame.Surface:
        stripe = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        for x in range(WIDTH):
            top, _, _ = self._faces(*self._corner(x, row, 0))
            pygame.draw.polygon(stripe, (*rgb(P.TEXT), 22), top)
        s.blit(stripe, (0, 0))
        return s

    def _stack(self, s, placed, haze: bool = True) -> pygame.Surface:
        """Far rows first, left to right, bottom up, so nearer faces paint over
        farther ones. A floating block's shadow goes right after whatever it falls on."""
        occupied = {b[:3] for b in placed}
        items = []
        for vx, vz, y, color in placed:
            sprite, rect = self._sprite(color, row=vz if haze else None), self._sprite_rect(vx, vz, y)
            items.append(((-vz, vx, y, 1), lambda sprite=sprite, rect=rect: s.blit(sprite, rect)))
            if y and (vx, vz, y - 1) not in occupied:
                ground = max((h + 1 for h in range(y) if (vx, vz, h) in occupied), default=0)
                items.append(((-vz, vx, ground - 1, 2), lambda vx=vx, vz=vz, g=ground, y=y, c=color: self._shadow(s, vx, vz, g, y, c)))
        for _, paint in sorted(items, key=lambda i: i[0]):
            paint()
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
            return self._stack(floor, self._placed(), haze=False)
        finally:
            self._c, self._sprites = screen

    def draw(self, g, rect):
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = g.line_height(g.vh(1.9), "mono") + g.em(0.4)
        foot_h = 0 if self.app._panel is not None else chrome_h + gap
        area = pygame.Rect(inner.x, inner.y + chrome_h + gap, inner.w, inner.h - chrome_h - gap - foot_h)
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
            self._draw_hold_badge(g, ox, oy, area)
        else:
            self._draw_turning(g, ox, oy, p)
        draw_mode_switch(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h), ("Front", "Back"),
                         1 if self._back else 0, self._color, wheel=wheel_chip(self))
        if foot_h:
            foot = pygame.Rect(inner.x, inner.bottom - chrome_h, inner.w, chrome_h)
            draw_key_hint(g, HINT, g.vh(1.9), foot.x, foot.centery)
            color_recipe.draw_foot_right(g, foot, self.app._code_panel_enabled, color_recipe.hint_row(self._key, self._last_mix))

    def _draw_hold_badge(self, g, ox, oy, area):
        held = self._last and self.app._panel is None and color_recipe.held_key(self.app, self._last[1])
        if held:
            bx, bz, by = self._last[0]
            x, y = self._corner(*self._view(bx, bz), by + 1)
            top = pygame.Rect(ox + x, oy + y - self._metrics()[0], self._c, self._metrics()[0])
            color_recipe.draw_hold_badge(g, held, g.vh(1.9), top, area)

    def _draw_turning(self, g, ox, oy, p):
        """One frame of the half turn: the world spun about the floor's center
        and drawn through the same slanted projection as the resting view, so
        both ends land exactly on the front and back pictures, checkerboard,
        haze, shadows and all; only the cursor sits it out. Zooms out mid-turn
        so the long floor, end-on, still fits."""
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

        sides = []                                      # (normal, corner offsets, darkness) for the sides facing the viewer
        for nx, nz, quad in ((0, -1, ((0, 0), (1, 0))), (1, 0, ((1, 0), (1, 1))),
                             (0, 1, ((1, 1), (0, 1))), (-1, 0, ((0, 1), (0, 0)))):
            rnx, rnz = nx * cos - nz * sin, nx * sin + nz * cos
            if rnz - ROW_SKEW * rnx < 0:
                sides.append(((nx, nz), quad, round(0.32 * max(0.0, rnx), 2)))   # rounded so `tint` remembers few shades

        def shape(w, h, d):
            """A w by h by d box's visible faces as (normal, screen offsets from its low corner, darkness); (0, 0) is the top."""
            def off(x, y, z):
                return x * ex[0] + z * ez[0], x * ex[1] + z * ez[1] - y * hy
            return [(n, [off(w * ax, 0, d * az), off(w * bx, 0, d * bz), off(w * bx, h, d * bz), off(w * ax, h, d * az)], dark)
                    for n, ((ax, az), (bx, bz)), dark in sides] + [((0, 0), [off(0, h, 0), off(w, h, 0), off(w, h, d), off(0, h, d)], None)]

        def box(x, y, z, faces, top, side, seam=None, shown=None):
            px, py = at(x, y, z)
            for n, offsets, dark in faces:
                if shown is None or n in shown:
                    poly = [(px + a, py + b) for a, b in offsets]
                    pygame.draw.polygon(g.surface, top if dark is None else side(dark), poly)
                    if seam:
                        pygame.draw.polygon(g.surface, seam, poly, 1)

        slab_bg, seam = mix(CANVAS_BG, "#000000", 0.4), rgb(P.LINE)
        box(0, -SLAB / BLOCK_RISE, 0, shape(WIDTH, SLAB / BLOCK_RISE, DEPTH), rgb(CANVAS_BG), lambda dark: tint(slab_bg, "#000000", dark))
        tiles = rgb(CANVAS_BG), rgb(CANVAS_ALT)
        for x in range(WIDTH):
            for z in range(DEPTH):
                pygame.draw.polygon(g.surface, tiles[(x + z) % 2], [at(x, 0, z), at(x + 1, 0, z), at(x + 1, 0, z + 1), at(x, 0, z + 1)])
        def depth(x, z, y):
            dx, dz_ = x + 0.5 - cx, z + 0.5 - cz
            return (dx * sin + dz_ * cos) - ROW_SKEW * (dx * cos - dz_ * sin) - y * ROW_DEPTH / BLOCK_RISE

        def row(x, z):
            """The view row a world cell is passing through, for its haze."""
            return min(DEPTH - 1, max(0, round((x + 0.5 - cx) * sin + (z + 0.5 - cz) * cos + cz - 0.5)))

        def top(x, z, y):
            """Color of the surface at height y over (x, z): a block's top face or a floor tile."""
            below = self._blocks.get((x, z, y - 1))
            return tint(haze(below, row(x, z)), "#ffffff", 0.22) if below else tiles[(x + z) % 2]

        cube = shape(1, 1, 1)

        def block(x, z, y, color, shown):
            hazed = haze(color, row(x, z))
            box(x, y, z, cube, tint(hazed, "#ffffff", 0.22), lambda dark: tint(hazed, "#000000", dark), seam, shown)

        def shadow(x, z, y, ground, color):
            pygame.draw.polygon(g.surface, tint(top(x, z, ground), "#000000", SHADOW_ALPHA / 255),
                                [at(x, ground, z), at(x + 1, ground, z), at(x + 1, ground, z + 1), at(x, ground, z + 1)])
            line = tint(tint(haze(color, row(x, z)), "#000000", STEM_DARKEN), CANVAS_BG, 1 - STEM_ALPHA / 255)
            pygame.draw.line(g.surface, line, at(x + 0.5, ground, z + 0.5), at(x + 0.5, y, z + 0.5), 2)

        items = []
        for (x, z, y), color in self._blocks.items():
            shown = [n for n, _, _ in cube if (x + n[0], z + n[1], y + (n == (0, 0))) not in self._blocks]
            if shown:                                   # a face against a neighbor is hidden by it
                items.append((depth(x, z, y), block, (x, z, y, color, shown)))
        if len(items) > TURN_DETAIL_BLOCKS:
            seam = None                                 # too many to draw in full every frame: plain shapes only
        else:
            items += self._turning_shadows(depth, shadow)
        for _, paint, args in sorted(items, key=lambda i: i[0], reverse=True):
            paint(*args)

    def _turning_shadows(self, depth, shadow) -> list:
        items = []
        for (x, z, y), color in self._blocks.items():
            if y and (x, z, y - 1) not in self._blocks:
                ground = max((h + 1 for h in range(y) if (x, z, h) in self._blocks), default=0)
                items.append((depth(x, z, ground - 1) - 1e-6, shadow, (x, z, y, ground, color)))
        return items

    def _draw_cursor(self, g, ox, oy, front):
        """A blinking glass column from the ceiling down onto the see-through
        landing block, with its shadow on whatever it would land on; then the
        faded rows in front; then a patch of ceiling fading out around the
        column, the column's edges faint through it, its outline on down to the
        floor through any blocks below, a ring around each block in it, and a
        wire box around the landing block on top of everything."""
        vx, vz = self._view(self._x, self._z)
        y = self._cursor_y()
        layer = pygame.Surface(self._scene_size(), pygame.SRCALPHA)
        column = self._faces(*self._corner(vx, vz, HEIGHT), levels=HEIGHT - 1 - y)
        fill, edge = (40, 150) if self._blink_on else (16, 70)
        self._outline(layer, column, edge, fill)
        self._shadow(layer, vx, vz, self._ground(y), y, self._color)
        d = self._step()
        ghost, behind = self._ghost(vx + d["x"], vz + d["z"], y + d["y"]), d["z"] > d["x"] + d["y"]
        if behind:
            layer.blit(ghost, (0, 0))
        layer.blit(self._sprite(self._color, 170 if self._blink_on else 100, vz), self._sprite_rect(vx, vz, y))
        if not behind:
            layer.blit(ghost, (0, 0))
        layer.blit(front, (0, 0))
        g.surface.blit(layer, (ox, oy))
        layer.fill((0, 0, 0, 0))                # draw calls replace pixels rather than blend, so the see-through top goes on fresh
        self._ceiling_patch(layer, vx, vz, 0.3 if y == HEIGHT - 1 else 1)   # faint when the box is up against it
        self._outline(layer, column, edge // 3)
        if y:                                   # the column carries on down through whatever is below, to the floor
            self._outline(layer, self._faces(*self._corner(vx, vz, y), levels=y)[1:], edge * 3 // 4, fill)
        for h in self._column():                # its blocks, ringed so they read as part of it among many columns
            for poly in self._faces(*self._corner(vx, vz, h + 1)):
                pygame.draw.polygon(layer, (*rgb(P.TEXT), 220 if self._blink_on else 120), poly, 2)
        self._cage(layer, vx, vz, y)
        self._pointer(layer, vx, vz, y)
        g.surface.blit(layer, (ox, oy))

    def _outline(self, layer, polys, edge, fill=0):
        for poly in polys:
            if fill:
                pygame.draw.polygon(layer, (*rgb(self._color), fill), poly)
            pygame.draw.polygon(layer, (*rgb(P.TEXT), edge), poly, 1)

    def _ground(self, y: int) -> int:
        """The level the cursor's block would rest on below height y."""
        return max((h + 1 for h in self._column() if h < y), default=0)

    def _ceiling_patch(self, layer, vx, vz, strength=1.0):
        cells = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if 0 <= vx + dx < WIDTH and 0 <= vz + dz < DEPTH]
        for dx, dz in cells:
            top, _, _ = self._faces(*self._corner(vx + dx, vz + dz, HEIGHT))
            pygame.draw.polygon(layer, (*rgb(P.TEXT), round(CEILING_ALPHA[dx * dx + dz * dz] * strength)), top)

    def _cage(self, layer, vx, vz, y):
        """Twelve wire edges a little outside the landing block, the three hidden ones fainter."""
        lo, hi = -CAGE_PAD, 1 + CAGE_PAD
        corners = [(a, b, h) for a in (lo, hi) for b in (lo, hi) for h in (lo, hi)]
        hidden = (lo, hi, lo)                           # back, left, bottom: behind the block
        for i, p in enumerate(corners):
            for q in corners[i + 1:]:
                if sum(m != n for m, n in zip(p, q)) == 1:
                    ends = [self._corner(vx + a, vz + b, y + h) for a, b, h in (p, q)]
                    pygame.draw.line(layer, (*rgb(P.TEXT), 90 if hidden in (p, q) else 230), *ends, 1 if hidden in (p, q) else 2)

    def _step(self) -> dict:
        axis, step = WRAP[self._dir][0]
        return {a: (step if a == axis else 0) for a in SIZE}

    def _ghost(self, vx, vz, y) -> pygame.Surface:
        """A faint box where the next typed block goes, on its own surface so it blends."""
        ghost = pygame.Surface(self._scene_size(), pygame.SRCALPHA)
        if 0 <= vx < WIDTH and 0 <= vz < DEPTH and 0 <= y < HEIGHT:
            self._outline(ghost, self._faces(*self._corner(vx, vz, y + 1)), 160, 70)
        return ghost

    def _pointer(self, layer, vx, vz, y):
        """An arrow out of the wire box's top (or bottom, going down) the way
        the next typed block goes, laid flat in the scene so depth foreshortens it."""
        d = self._step()
        across = {"x": 0, "z": 1} if d["x"] else {"x": 1, "z": 0}
        base = y - CAGE_PAD if self._dir == SINK else y + 1 + CAGE_PAD
        arrow = [self._corner(vx + 0.5 + u * d["x"] + v * across["x"], vz + 0.5 + u * d["z"] + v * across["z"], base + u * d["y"])
                 for u, v in POINTER]
        pygame.draw.polygon(layer, (*rgb(P.TEXT), 240), arrow)
        pygame.draw.polygon(layer, (*rgb(CANVAS_BG), 200), arrow, 1)
