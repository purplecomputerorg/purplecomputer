"""Blocks room: a floor seen from above and in front, where every letter (or
Space, in the current color) drops a block of its sticker color into the
cursor's column, then moves on the way the cursor last went: along an arrow,
or up after Enter or Shift+Up/Down. Enter (once already going up) walks the
cursor up a level at a time, onto blocks too (typing there mixes into
them), starting over at the floor after a pause at the top, and Shift with
Up or Down moves it either way; that height stays put as
the arrows move, for building sideways. At the top, letters mix into the top
block.
Every block goes in the first free spot at or above the cursor's height, so
a line climbs over whatever is in its way and a stack passes floating
blocks; only the code line keeps the height it reached when it moves on.
Backspace takes blocks off the column top down from the cursor, then carries
on into the column to its left. Holding one letter while pressing another
mixes the two colors. Backslash
opens the color bar, Tab flips to the back side and holding it tilts the view
to look down from above, and the code line opens from the Esc menu."""

import asyncio
import math
import time
from functools import cache, lru_cache

import pygame

from ... import palette as P
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...palette import DEFAULT_BRUSH_COLOR
from .. import color_recipe, paper
from ..color_wheel import chip as wheel_chip, open_on as open_color_wheel
from ..gfx import mix, rgb
from ..panels import CodePanel, Echo
from ..ui import DOWN, MOVE_HINT, PICK_HINT, UP, HeldKey, draw_key_hint, draw_mode_switch, hint_row_h, hold_status
from .base import Room
from . import art_room
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, HOLD_ACCEL_MULTIPLIER, brush_for_key, onto_grid
from .blocks_code import WORDS, BlocksCodeRunner

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
WIDTH, DEPTH, HEIGHT = 30, 12, 12
TURN_S, TILT_S = 0.5, 0.3
TURN_DETAIL_BLOCKS = 600     # visible blocks; past this the half turn drops seams and shadows
TURN_FRAME_BUDGET_S = 0.012  # a detailed turn frame slower than this lowers that limit to its block count
SLAB = 0.35                   # in cell widths
REST, PEEK = (0.5, 0.7, 0.3), (0.9, 0.25, 0.1)   # (row depth, block rise, row skew) in cell widths: held Tab looks down
SIDES = (("Front", "modes/front.png"), ("Back", "modes/back.png"))  # the Tab switch's words and pictures
FRAME_ALPHA = 90              # the outline standing up around the cursor's row
FRONT_ALPHA = 40              # front towers in the way of the cursor's glass column or landing block fade to this
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
PEEK_PIC = "{hints/peek.png}"
HINT = f"Type to build!  {{Enter}} {{hints/up.png}}   {{hold Tab}} {PEEK_PIC}"
SHIFT_HINT = f"{PICK_HINT}   {UP} {DOWN} {{hints/up_down.png}}"


@cache
def haze(color, row: int) -> tuple:
    return mix(color, art_room.CANVAS_BG, DEPTH_FADE * row / (DEPTH - 1))


@lru_cache(maxsize=256)
def metrics(c: int, shape: tuple = REST) -> tuple:
    """(row depth, block rise, row skew, slab) in pixels for cell width c."""
    return *(round(c * k) for k in shape), round(c * SLAB)


def scene_size(c: int, shape: tuple) -> tuple:
    dz, hy, sx, slab = metrics(c, shape)
    return WIDTH * c + DEPTH * sx + 1, DEPTH * dz + HEIGHT * hy + slab + 1


def fit(w: int, h: int, shape: tuple) -> int:
    row_depth, rise, skew = shape
    return max(6, int(min(w / (WIDTH + DEPTH * skew), h / (DEPTH * row_depth + HEIGHT * rise + SLAB))))


def centered(area, size) -> tuple:
    return area.x + (area.w - size[0]) // 2, area.y + (area.h - size[1]) // 2


def ease(p: float) -> float:
    return p * p * (3 - 2 * p)


@cache
def tint(color, toward: str, t: float) -> tuple:
    """`mix`, remembered: the half turn asks for the same few shades every frame."""
    return mix(color, toward, t)


class BlocksRoom(Room):
    """Blocks live in a dict keyed by world (x, z, y), y up. Drawing and the
    arrows work in view coordinates, which are world (x, z) mirrored when the
    room shows its back. The floor and blocks render into two cached surfaces
    split at the cursor's row, rebuilt when a block changes, the room flips or
    the cursor changes rows: the rows from the cursor's back, then the cursor,
    then the rows in front of it, with the towers in the way faded."""

    name, label, icon = "blocks", "Blocks", ICON_CUBE
    LANDSCAPE = True
    has_code_panel = True
    wheel_ready = True

    def __init__(self, app):
        super().__init__(app)
        self._blocks: dict = {}
        self._x, self._z = WIDTH // 2, DEPTH // 2
        self._back = False
        self._hover = 0               # chosen cursor height; 0 = resting on the column
        self._color = DEFAULT_BRUSH_COLOR
        self._key = ""
        self._mix = color_recipe.NO_MIX   # (keycaps, color) of the last chord
        self._badge = color_recipe.HoldBadge()
        self._mixed = None                # (keycaps, color) of the last block that mixed
        self._last = None             # (pos, key) of the block just dropped
        self._next = None             # where a run up or down the column (or a code run) goes on from
        self._dir = "right"           # the way typing builds: a key of WRAP
        self._shape = REST
        self._motion = None           # (start, seconds, (half turns, tilt) from, to) while the view moves
        self._motion_timer = None
        self._tab = HeldKey(app, lambda: self._tilt(True))
        self._turn_detail_limit = TURN_DETAIL_BLOCKS
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._c = 0
        self._origin = (0, 0)
        self._floor = self._scene = None
        self._front = self._solid_front = self._scene_row = None
        self._front_blocks, self._faded, self._fade_key = [], frozenset(), None
        self._rects, self._fade_area, self._redo = {}, None, None
        self._composed = self._layer = None
        self._sprites: dict = {}
        self.echo = Echo()
        self.code_panel = None
        self._space_pending = False

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        self.app.set_legend(self._color, visible=True)

    def on_leave(self):
        self.code_panel = None
        self._tab.other_key()
        self._tilt(False)

    def hold_progress(self):
        held = self._tab.progress()
        return None if held is None else hold_status(held, "Tab", PEEK_PIC, "look from above")

    def open_code_panel(self):
        if self.code_panel is None and self.app._code_panel_enabled:
            self.code_panel = CodePanel(self.app, "blocks", self.echo.take())
            self.app.set_panel(self.code_panel)

    def close_code_panel(self):
        if self.code_panel is not None:
            self.code_panel = None
            self.app.set_panel(None)

    async def run_code(self, lines: list):
        try:
            runner = BlocksCodeRunner(self)
            await self.run_shown(runner, lines)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        self.app.invalidate()

    def arrow_hint(self) -> str:
        return MOVE_HINT

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
        self._last = self._next = self._mixed = None
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

    def _stacks(self) -> list:
        """(bottom, top) of each run of touching blocks in the cursor's column."""
        runs = []
        for y in sorted(self._column()):
            if runs and runs[-1][1] == y - 1:
                runs[-1][1] = y
            else:
                runs.append([y, y])
        return runs

    def _free(self, ys) -> list:
        return [y for y in ys if (self._x, self._z, y) not in self._blocks]

    def _cursor_y(self) -> int:
        """The first free level at or above the chosen height, or on from where
        a run left off, the way it goes. Never above the top level: a full
        column puts it on the top block. A run already going through blocks
        mixes into them, as Art paints over its own lines, rather than climbing."""
        run = []
        if self._next and self._next[:2] == (self._x, self._z):
            _, _, y, inside = self._next
            if inside:
                return y
            if self._dir == SINK:
                return next(iter(self._free(range(y, -1, -1))), y)
            run = self._free(range(y, HEIGHT))
        return next(iter(run or self._free(range(self._hover, HEIGHT))), HEIGHT - 1)

    def _place(self, y=None):
        """A block at height y (the cursor's by default), paint-mixed into one already there."""
        y = self._cursor_y() if y is None else y
        pos = (self._x, self._z, y)
        old = self._blocks.get(pos)
        self._mixed = color_recipe.dab(old, self._mix, (self._key, self._color))
        self._blocks[pos] = self._mixed[1] if self._mixed else self._color
        self._last = (pos, self._key)
        self._badge.dabbed()
        self._changed()
        return bool(old)

    def _build(self, keep_height: bool = False):
        """A typed block, then on to the next cell the way the cursor last went."""
        y = self._cursor_y()
        self._advance(y, keep_height, inside=self._place(y))

    def _advance(self, y: int, keep_height: bool = False, inside: bool = False):
        """On from the cursor's column at height y the way it last went,
        wrapping at the walls like lines of text. Typing into a new column
        starts again from the chosen height; code keeps the height it reached."""
        pos = self._spot(y)
        for axis, step in WRAP[self._dir]:
            pos[axis] += step
            if 0 <= pos[axis] < SIZE[axis]:
                break
            pos[axis] = 0 if step > 0 else SIZE[axis] - 1
        column = (self._x, self._z)
        self._x, self._z = self._view(pos["x"], pos["z"])
        keep = keep_height or column == (self._x, self._z)
        self._next = (self._x, self._z, pos["y"], inside) if keep else None

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
        """Turning straight back after a run starts on its last block, like Art's."""
        if self._next and self._last:
            pos = self._spot(self._next[2])
            axis, step = WRAP[way][0]
            pos[axis] += step
            back = (*self._view(pos["x"], pos["z"]), pos["y"])
            if back == self._last[0]:
                self._x, self._z = back[:2]
                self._next = (*back, True)
        self._dir = way

    def build(self):
        self._build(keep_height=True)

    def build_letter(self, ch: str) -> bool:
        if not self._set_color(ch):
            return False
        self.build()
        return True

    def skip(self):
        self._advance(self._cursor_y(), keep_height=True)

    def _chord_color(self, held_key: str, char: str) -> bool:
        """A key pressed while another color key is down: the brush becomes the
        held brush mixed with this key's color. Holding on, each next key mixes in too."""
        brush = brush_for_key(char)
        if not brush or not self._set_color(held_key, hold=True):
            return False
        self._mix = color_recipe.chord(self._mix, (self._key, self._color), brush)
        self.set_brush_color(self._mix[1], brush[0])
        return True

    def _step_height(self, rise: int, wrap: bool = False):
        """One level up or down, onto a block if one is there; with `wrap`, past the end starts over from the other one."""
        y = self._cursor_y() + rise
        if 0 <= y < HEIGHT or wrap:
            self._hover = y % HEIGHT
            self._next = (self._x, self._z, self._hover, True)

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
        self._key, self._color = key, color
        self.app.set_legend(color, visible=True)

    def _set_color(self, char: str, hold: bool = False):
        """With `hold`, a key still down keeps its brush, so a chord's mix keeps going."""
        brush = brush_for_key(char)
        if brush and not (hold and brush[0] == self._key):
            self.set_brush_color(brush[1], brush[0])
        return bool(brush)

    def _move(self, direction: str, wrap: bool = False) -> bool:
        dx, dz = STEPS[direction]
        vx, vz = self._view(self._x, self._z)
        spot = onto_grid(vx + dx, vz + dz, WIDTH, DEPTH, wrap)
        if not spot:
            return False
        self._x, self._z = self._view(*spot)
        self._next = None
        return True

    def _view(self, x: int, z: int) -> tuple:
        """World to view and back: the back side is the front mirrored both ways."""
        return (WIDTH - 1 - x, DEPTH - 1 - z) if self._back else (x, z)

    # ---------------------------------------------------------------- flipping
    def turn_around(self):
        """Tab, here or in Time Travel: a live half turn, one at a time."""
        if self._camera() is not None:
            return
        self._move_camera(TURN_S, lambda half, tilt: (half + 1, tilt))
        self._back = not self._back
        self.announce(*SIDES[self._back])

    def _tilt(self, peek: bool):
        """Held Tab eases the view up to look down from above; letting go eases it back."""
        if peek == (self._shape == PEEK):
            return
        self._move_camera(TILT_S, lambda half, tilt: (self._motion[3][0] if self._motion else half, float(peek)))
        self._shape = PEEK if peek else REST
        self._sprites, self._scene, self._floor = {}, None, None

    def _move_camera(self, seconds: float, to):
        """From wherever the view is now, even mid-move, to `to` of it."""
        start = self._camera() or (float(self._back), float(self._shape == PEEK))
        self._motion = (time.monotonic(), seconds, start, to(*start))
        if self._motion_timer is None:
            self._motion_timer = self.app.timers.every(1 / 60, self._motion_tick)
        self._changed()

    def _motion_tick(self):
        if self._camera() is None:
            self._motion_timer.stop()
            self._motion_timer = None
        self.app.invalidate()

    def _camera(self):
        """(half turns, tilt) while the view is moving, else None."""
        if self._motion is None:
            return None
        start, seconds, frm, to = self._motion
        p = (time.monotonic() - start) / seconds
        if p >= 1:
            self._motion = None
            return None
        return tuple(a + (b - a) * ease(p) for a, b in zip(frm, to))

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        if self.code_panel is None and isinstance(action, ControlAction) and action.action == "space":
            return self._space(action)
        if isinstance(action, ControlAction) and action.action == "tab" and (self.code_panel is None or self._tab.fired):
            return self._tab_key(action)
        stacking = isinstance(action, ControlAction) and action.action == "enter" and action.space_held
        if stacking and self.code_panel is None:
            self._dir = RISE    # Space + Enter lays a column, as Space + arrows lay a line
        self._lay_pending()
        if self.code_panel is not None:
            result = await self.code_panel.handle(action)
            if result == "tab_fallthrough":
                self.turn_around()
            elif result == "close":
                self.close_code_panel()
            return
        if isinstance(action, ControlAction):
            if action.is_down and (not action.is_repeat or action.action in ("backspace", "enter")):
                self._control("space" if stacking else action.action, action.is_repeat)
        elif isinstance(action, NavigationAction):
            self._navigate(action)
        elif isinstance(action, CharacterAction):
            self._character(action)
        self.app.invalidate()

    def _space(self, action):
        """Space's block waits for release or the next key, so Space + Enter knows to go up first."""
        if action.is_down and not action.is_repeat:
            self._space_pending = True
        elif not action.is_down:
            self._lay_pending()

    def _tab_key(self, action):
        """A tap of Tab turns around once it is let go; a hold looks down until then."""
        if action.is_down and not action.is_repeat:
            self._tab.down()
        elif not action.is_down:
            if self._tab.up():
                self.turn_around()
            self._tilt(False)

    def _lay_pending(self):
        if self._space_pending:
            self._space_pending = False
            self._control("space")
            self.app.invalidate()

    def _character(self, action):
        char = UNSHIFT_MAP.get(action.char, action.char) if action.with_shift else action.char
        if open_color_wheel(self, char):
            return
        chord = bool(action.char_held) and not action.with_shift and self._chord_color(action.char_held, char)
        if not (chord or self._set_color(char, hold=action.is_repeat)) or action.with_shift:
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

    def _navigate(self, action):
        if action.with_shift and action.direction in ("up", "down"):
            self.echo.flush()
            self._step_height(STEPS[action.direction][1], wrap=not action.is_repeat)
            self._face(RISE if action.direction == "up" else SINK)
            return
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        laying = (bool(action.char_held) and self._set_color(action.char_held, hold=True)) or action.space_held
        if not laying:
            self.echo.flush()
        fast = not laying and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(HOLD_ACCEL_MULTIPLIER if fast else 1):
                if not self._move(direction, wrap=not action.is_repeat):
                    break
                if laying:
                    self._lay(direction)
                    self._place()
        self._face(action.direction)

    # ---------------------------------------------------------------- geometry
    def _metrics(self):
        return metrics(self._c, self._shape)

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
    def _sprite(self, color: str, alpha: int = 255, row=None, ribbon: bool = False) -> pygame.Surface:
        """A block; with `row`, hazed toward the floor color the farther back it sits;
        with `ribbon`, a soft band along the row that marks the cursor's row and leaves its color showing."""
        key = (color, self._c, alpha, row, ribbon)
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
                if ribbon:
                    s.blit(self._ribbon(), (0, 0))
            self._sprites[key] = s
        return self._sprites[key]

    def _ribbon(self) -> pygame.Surface:
        """A soft light band across the middle of the top face and of the front, running along the row."""
        key = ("ribbon", self._c)
        if key not in self._sprites:
            dz, hy, sx, _ = self._metrics()
            c, lo, hi = self._c, 0.38, 0.62
            s = pygame.Surface((c + sx + 1, dz + hy + 1), pygame.SRCALPHA)
            for (ox, oy), (vx, vy) in (((0, dz), (sx, -dz)), ((0, dz), (0, hy))):
                band = [(ox + vx * lo, oy + vy * lo), (ox + vx * hi, oy + vy * hi)]
                pygame.draw.polygon(s, (*rgb(P.TEXT), 70), [band[0], (band[0][0] + c, band[0][1]), (band[1][0] + c, band[1][1]), band[1]])
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
        return scene_size(self._c, self._shape)

    def _floor_surface(self) -> pygame.Surface:
        """Checkerboard floor on a slab, built once per cell size."""
        if self._floor is None or self._floor.get_size() != self._scene_size():
            self._floor = self._build_floor(on_screen=True)
        return self._floor

    def _build_floor(self, on_screen) -> pygame.Surface:
        if on_screen:
            bg = art_room.CANVAS_BG  # a family theme can change it (canvas/theme.py)
            ground, tile, alt, slab_front, slab_side = P.SURFACE, bg, art_room.CANVAS_ALT, mix(bg, "#000000", 0.4), mix(bg, "#000000", 0.55)
        else:
            ground, tile, alt, slab_front, slab_side = paper.WHITE, "#f1f1f1", "#e4e4e4", "#c8c8c8", "#b4b4b4"
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
        """(floor with the cursor's row marked plus the blocks from that row back, the blocks in front of it)."""
        vx, row = self._view(self._x, self._z)
        if self._scene is None or self._scene.get_size() != self._scene_size() or row != self._scene_row:
            self._scene_row = row
            placed = self._placed()
            behind = self._stack(self._mark_row(self._floor_surface().copy(), row), [b for b in placed if b[1] > row])
            self._scene = self._stack(self._frame_row(behind, row), [b for b in placed if b[1] == row])
            self._front_blocks = [b for b in placed if b[1] < row]
            self._rects = {b: self._sprite_rect(*b[:3]) for b in self._front_blocks}
            self._front = self._solid_front = self._stack(pygame.Surface(self._scene_size(), pygame.SRCALPHA), self._front_blocks)
            self._faded, self._fade_key, self._fade_area = frozenset(), None, None
        key = (vx, self._cursor_y())
        if key != self._fade_key:
            self._fade_key = key
            faded = self._hiding(vx, row, key[1])
            if faded != self._faded:
                area = self._area(faded)
                self._redo = self._area(faded, [self._fade_area] if self._fade_area else [])
                self._faded, self._fade_area, self._front = faded, area, self._fade(faded, area)
        return self._scene, self._front

    def _area(self, blocks, rects=()) -> pygame.Rect | None:
        rects = [*rects, *(self._rects[b] for b in blocks)]
        return rects[0].unionall(rects[1:]) if rects else None

    def _scene_with_front(self, scene, front) -> pygame.Surface:
        """The scene with the front rows over it, as the cursor's layer
        would composite them, kept until either changes so a frame only blends near the cursor.
        A new fade redoes only the area it and the last one cover."""
        if self._composed is None or self._composed[0] is not scene:
            self._composed = [scene, front, scene.copy()]
            redo = scene.get_rect()
        elif self._composed[1] is not front:
            self._composed[1], redo = front, self._redo.clip(scene.get_rect())
        else:
            return self._composed[2]
        layer = pygame.Surface(redo.size, pygame.SRCALPHA)
        layer.blit(front, (0, 0), redo)
        out = self._composed[2]
        out.blit(scene, redo, redo)
        out.blit(layer, redo)
        return out

    def _hiding(self, vx, vz, y) -> frozenset:
        """Every block of each front tower that has a block whose picture overlaps the glass
        column or the landing block by a pixel or more. The block just laid stays solid while
        the cursor sits right behind it, and what it hides doesn't count."""
        polys = [*self._faces(*self._corner(vx, vz, HEIGHT), levels=HEIGHT - 1 - y), *self._faces(*self._corner(vx, vz, y + 1))]
        xs, ys = zip(*(p for poly in polys for p in poly))
        box = pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
        near = [b for b in self._front_blocks if self._rects[b].colliderect(box)]
        if not near:
            return frozenset()
        s = pygame.Surface(box.size, pygame.SRCALPHA)
        polys = [[(px - box.x, py - box.y) for px, py in poly] for poly in polys]
        for poly in polys:
            pygame.draw.polygon(s, (255, 255, 255), poly)
        for poly in polys:      # trimmed by a pixel: a block just in front shares an edge with them without hiding them
            pygame.draw.polygon(s, (0, 0, 0, 0), poly, 1)
        spot, block = pygame.mask.from_surface(s), self._block_mask()
        at = {b: self._rects[b].move(-box.x, -box.y).topleft for b in near}
        laid = self._last and (*self._view(*self._last[0][:2]), self._last[0][2])
        solid = next((b for b in near if b[:3] == laid and laid[:2] == (vx, vz - 1)), None)
        if solid:
            spot.erase(block, at[solid])
        towers = {b[:2] for b in near if b is not solid and spot.overlap(block, at[b])}
        return frozenset(b for b in self._front_blocks if b[:2] in towers and b is not solid)

    def _block_mask(self) -> pygame.mask.Mask:
        key = ("mask", self._c)
        if key not in self._sprites:
            self._sprites[key] = pygame.mask.from_surface(self._sprite(DEFAULT_BRUSH_COLOR))
        return self._sprites[key]

    def _fade(self, faded, area) -> pygame.Surface:
        """The front rows with `faded` see-through, multiplied by a picture of each
        block's alpha over `area` so a solid block nearer than a faded one stays solid."""
        if not faded:
            return self._solid_front
        alpha = pygame.Surface(area.size, pygame.SRCALPHA)
        alpha.fill((255, 255, 255, 255))

        def silhouette(*b):
            for poly in self._faces(*self._corner(b[0], b[1], b[2] + 1)):
                poly = [(x - area.x, y - area.y) for x, y in poly]
                for width in (0, 1):    # the outline too, as the sprite draws it
                    pygame.draw.polygon(alpha, (255, 255, 255, FRONT_ALPHA if b in faded else 255), poly, width)

        self._stack(alpha, [b for b in self._front_blocks if self._rects[b].colliderect(area)], block=silhouette, shadows=False)
        front = self._solid_front.copy()
        front.blit(alpha, area, special_flags=pygame.BLEND_RGBA_MULT)
        return front

    def _cursor_box(self, vx, vz) -> pygame.Rect:
        """Scene pixels the cursor can touch: its column and the ceiling cells
        around it, floor to ceiling, with room for the wire box and pointer."""
        rects = [self._sprite_rect(vx + dx, vz + dz, y) for dx in (-1, 1) for dz in (-1, 1) for y in (-1, HEIGHT)]
        return rects[0].unionall(rects[1:]).inflate(self._c, self._c).clip(pygame.Rect((0, 0), self._scene_size()))

    def _mark_row(self, s, row) -> pygame.Surface:
        stripe = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        for x in range(WIDTH):
            top, _, _ = self._faces(*self._corner(x, row, 0))
            pygame.draw.polygon(stripe, (*rgb(P.TEXT), 22), top)
        s.blit(stripe, (0, 0))
        return s

    def _frame_row(self, s, row) -> pygame.Surface:
        """An upright frame on the back of the cursor's row, floor to ceiling, wall to wall,
        so the row reads as one slice; the row's own blocks cover it."""
        frame = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        corners = [self._corner(x, row + 1, y) for x, y in ((0, 0), (WIDTH, 0), (WIDTH, HEIGHT), (0, HEIGHT))]
        pygame.draw.polygon(frame, (*rgb(P.TEXT), FRAME_ALPHA), corners, 2)
        s.blit(frame, (0, 0))
        return s

    def _stack(self, s, placed, haze: bool = True, block=None, shadows: bool = True) -> pygame.Surface:
        """Far rows first, left to right, bottom up, so nearer faces paint over
        farther ones. A floating block's shadow goes right after whatever it falls on."""
        block = block or (lambda vx, vz, y, color: s.blit(self._sprite(color, row=vz if haze else None, ribbon=haze and vz == self._scene_row),
                                                          self._sprite_rect(vx, vz, y)))
        occupied = {b[:3] for b in placed}
        items = []
        for b in placed:
            vx, vz, y, color = b
            items.append(((-vz, vx, y, 1), lambda b=b: block(*b)))
            if shadows and y and (vx, vz, y - 1) not in occupied:
                ground = max((h + 1 for h in range(y) if (vx, vz, h) in occupied), default=0)
                items.append(((-vz, vx, ground - 1, 2), lambda vx=vx, vz=vz, g=ground, y=y, c=color: self._shadow(s, vx, vz, g, y, c)))
        for _, paint in sorted(items, key=lambda i: i[0]):
            paint()
        return s

    def paper(self, g, size, on_screen=False):
        """The build for printing, on a pale floor (the screen's floor on screen), nothing see-through and no cursor."""
        if not self._blocks:
            return None
        screen = self._c, self._sprites, self._shape
        self._c, self._sprites, self._shape = fit(*size, REST), {}, REST
        try:
            floor = self._build_floor(on_screen)
            return self._stack(floor, self._placed(), haze=False)
        finally:
            self._c, self._sprites, self._shape = screen

    def draw(self, g, rect):
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = hint_row_h(g)
        foot_h = 0 if self.app.viewport_panel() is not None else chrome_h + gap
        area = pygame.Rect(inner.x, inner.y + chrome_h + gap, inner.w, inner.h - chrome_h - gap - foot_h)
        c = fit(area.w, area.h, self._shape)
        if c != self._c:
            self._c, self._sprites, self._scene = c, {}, None
        ox, oy = self._origin = centered(area, self._scene_size())
        camera = self._camera()
        if camera is None:
            scene, front = self._scene_surfaces()
            g.surface.blit(self._scene_with_front(scene, front), (ox, oy))
            self._draw_cursor(g, ox, oy, scene, front)
            self._draw_hold_badge(g, ox, oy, area)
        else:
            self._draw_moving(g, area, *camera)
        self.bar_row = draw_mode_switch(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h), tuple(pic for _, pic in SIDES),
                                        1 if self._back else 0, self._color, wheel=None if self.code_panel else wheel_chip(self))
        self.bar_foot = None
        if foot_h and self.app._panel is None:
            foot = self.bar_foot = pygame.Rect(inner.x, inner.bottom - chrome_h, inner.w, chrome_h)
            draw_key_hint(g, SHIFT_HINT if self.app._keyboard_state_machine.shift_active else HINT, g.vh(1.9), foot.x, foot.centery)
            color_recipe.draw_foot_right(g, foot, self.app._code_panel_enabled, color_recipe.hint_row(self._key, self._mixed))

    def _draw_hold_badge(self, g, ox, oy, area):
        if self._last and self.app._panel is None:
            bx, bz, by = self._last[0]
            x, y = self._corner(*self._view(bx, bz), by + 1)
            top = pygame.Rect(ox + x, oy + y - self._metrics()[0], self._c, self._metrics()[0])
            self._badge.draw(g, self.app, self._last[1], self._mix, self._color, top, area)

    def _draw_moving(self, g, area, half_turns, tilt):
        """One frame of the view moving: the world spun about the floor's center
        and drawn through the slanted projection tilted that far toward looking
        down, so both ends land exactly on the resting pictures, checkerboard,
        haze, shadows and all; only the cursor sits it out. Zooms out mid-turn
        so the long floor, end-on, still fits."""
        start = time.monotonic()
        shape = tuple(a + (b - a) * tilt for a, b in zip(REST, PEEK))
        row_depth, rise, skew = shape
        c = fit(area.w, area.h, shape)
        dz, hy, sx, slab = metrics(c, shape)
        base = DEPTH * dz + HEIGHT * hy
        ox, oy = centered(area, scene_size(c, shape))
        angle = math.pi * half_turns
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
        center = (ox + cx * c + cz * sx, oy + base - cz * dz)

        def at(x, y, z):
            return (center[0] + (x - cx) * ex[0] + (z - cz) * ez[0],
                    center[1] + (x - cx) * ex[1] + (z - cz) * ez[1] - y * hy)

        sides = []                                      # (normal, corner offsets, darkness) for the sides facing the viewer
        for nx, nz, quad in ((0, -1, ((0, 0), (1, 0))), (1, 0, ((1, 0), (1, 1))),
                             (0, 1, ((1, 1), (0, 1))), (-1, 0, ((0, 1), (0, 0)))):
            rnx, rnz = nx * cos - nz * sin, nx * sin + nz * cos
            if rnz - skew * rnx < 0:
                sides.append(((nx, nz), quad, round(0.32 * max(0.0, rnx), 2)))   # rounded so `tint` remembers few shades

        def solid(w, h, d):
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

        slab_bg, seam = mix(art_room.CANVAS_BG, "#000000", 0.4), rgb(P.LINE)
        box(0, -SLAB / rise, 0, solid(WIDTH, SLAB / rise, DEPTH), rgb(art_room.CANVAS_BG), lambda dark: tint(slab_bg, "#000000", dark))
        tiles = rgb(art_room.CANVAS_BG), rgb(art_room.CANVAS_ALT)
        grid = [[at(x, 0, z) for z in range(DEPTH + 1)] for x in range(WIDTH + 1)]
        for x in range(WIDTH):
            for z in range(1 - x % 2, DEPTH, 2):        # the slab's top already painted the other tiles
                pygame.draw.polygon(g.surface, tiles[1], [grid[x][z], grid[x + 1][z], grid[x + 1][z + 1], grid[x][z + 1]])

        def depth(x, z, y):
            dx, dz_ = x + 0.5 - cx, z + 0.5 - cz
            return (dx * sin + dz_ * cos) - skew * (dx * cos - dz_ * sin) - y * row_depth / rise

        def row(x, z):
            """The view row a world cell is passing through, for its haze."""
            return min(DEPTH - 1, max(0, round((x + 0.5 - cx) * sin + (z + 0.5 - cz) * cos + cz - 0.5)))

        def top(x, z, y):
            """Color of the surface at height y over (x, z): a block's top face or a floor tile."""
            below = self._blocks.get((x, z, y - 1))
            return tint(haze(below, row(x, z)), "#ffffff", 0.22) if below else tiles[(x + z) % 2]

        cube = solid(1, 1, 1)

        def block(x, z, y, color, shown):
            hazed = haze(color, row(x, z))
            box(x, y, z, cube, tint(hazed, "#ffffff", 0.22), lambda dark: tint(hazed, "#000000", dark), seam, shown)

        def shadow(x, z, y, ground, color):
            pygame.draw.polygon(g.surface, tint(top(x, z, ground), "#000000", SHADOW_ALPHA / 255),
                                [at(x, ground, z), at(x + 1, ground, z), at(x + 1, ground, z + 1), at(x, ground, z + 1)])
            line = tint(tint(haze(color, row(x, z)), "#000000", STEM_DARKEN), art_room.CANVAS_BG, 1 - STEM_ALPHA / 255)
            pygame.draw.line(g.surface, line, at(x + 0.5, ground, z + 0.5), at(x + 0.5, y, z + 0.5), 2)

        items = []
        for (x, z, y), color in self._blocks.items():
            shown = [n for n, _, _ in cube if (x + n[0], z + n[1], y + (n == (0, 0))) not in self._blocks]
            if shown:                                   # a face against a neighbor is hidden by it
                items.append((depth(x, z, y), block, (x, z, y, color, shown)))
        blocks = len(items)
        detailed = blocks <= self._turn_detail_limit
        if detailed:
            items += self._turning_shadows(depth, shadow)
        else:
            seam = None                                 # too many to draw in full every frame: plain shapes only
        for _, paint, args in sorted(items, key=lambda i: i[0], reverse=True):
            paint(*args)
        if detailed and time.monotonic() - start > TURN_FRAME_BUDGET_S:
            self._turn_detail_limit = blocks - 1        # a slow machine: from here on, builds this big turn plain

    def _turning_shadows(self, depth, shadow) -> list:
        items = []
        for (x, z, y), color in self._blocks.items():
            if y and (x, z, y - 1) not in self._blocks:
                ground = max((h + 1 for h in range(y) if (x, z, h) in self._blocks), default=0)
                items.append((depth(x, z, ground - 1) - 1e-6, shadow, (x, z, y, ground, color)))
        return items

    def _draw_cursor(self, g, ox, oy, scene, front):
        """A blinking glass column from the ceiling down onto the see-through
        landing block, with its shadow on whatever it would land on and a ring
        around each run of blocks in its column; then the rows in front, which
        hide those rings like any block; then a patch of ceiling fading out around
        the column, the column's edges faint through it, and a bold wire box around
        the landing block on top of everything. Only the patch around the column
        is redrawn; Gfx.blink swaps it bright and dim. guides/blocks-cursor.md"""
        vx, vz = self._view(self._x, self._z)
        y = self._cursor_y()
        box = self._cursor_box(vx, vz)
        at = box.move(ox, oy)
        if self._layer is None or self._layer.get_size() != scene.get_size():
            self._layer = pygame.Surface(scene.get_size(), pygame.SRCALPHA)
        layer = self._layer
        column = self._faces(*self._corner(vx, vz, HEIGHT), levels=HEIGHT - 1 - y)

        def draw(bright):
            fill, edge = (40, 150) if bright else (16, 70)
            g.surface.blit(scene, at, box)
            layer.fill((0, 0, 0, 0), box)
            self._outline(layer, column, edge, fill)
            self._shadow(layer, vx, vz, self._ground(y), y, self._color)
            layer.blit(self._sprite(self._color, 170 if bright else 100, vz), self._sprite_rect(vx, vz, y))
            for lo, hi in self._stacks():       # its blocks, ringed so they read as part of it among many columns
                for poly in self._faces(*self._corner(vx, vz, hi + 1), levels=hi + 1 - lo):
                    pygame.draw.polygon(layer, (*rgb(P.TEXT), 220 if bright else 120), poly, 2)
            layer.blit(front, box, box)
            g.surface.blit(layer, at, box)
            layer.fill((0, 0, 0, 0), box)       # draw calls replace pixels rather than blend, so the see-through top goes on fresh
            self._ceiling_patch(layer, vx, vz, 0.3 if y == HEIGHT - 1 else 1)   # faint when the box is up against it
            self._outline(layer, column, edge // 3)
            self._cage(layer, vx, vz, y)
            self._pointer(layer, vx, vz, y)
            g.surface.blit(layer, at, box)
        g.draw_caret(at, lambda: draw(True), lambda: draw(False))

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
        """Twelve wire edges a little outside the landing block: the three hidden ones
        thin and faint, the rest bold over a dark edge so they read against any block."""
        lo, hi = -CAGE_PAD, 1 + CAGE_PAD
        corners = [(a, b, h) for a in (lo, hi) for b in (lo, hi) for h in (lo, hi)]
        hidden = (lo, hi, lo)                           # back, left, bottom: behind the block
        edges = [[self._corner(vx + a, vz + b, y + h) for a, b, h in (p, q)] + [hidden in (p, q)]
                 for i, p in enumerate(corners) for q in corners[i + 1:] if sum(m != n for m, n in zip(p, q)) == 1]
        w = max(2, self._c // 10)
        for color, width, back in (((*rgb(art_room.CANVAS_BG), 220), w + 4, False), ((*rgb(P.TEXT), 90), 1, True),
                                   ((*rgb(P.TEXT), 240), w, False)):
            for start, end, behind in edges:
                if behind == back:
                    pygame.draw.line(layer, color, start, end, width)

    def _step(self) -> dict:
        axis, step = WRAP[self._dir][0]
        return {a: (step if a == axis else 0) for a in SIZE}

    def _pointer(self, layer, vx, vz, y):
        """An arrow out of the wire box's top (or bottom, going down) the way
        the next typed block goes, laid flat in the scene so depth foreshortens it."""
        d = self._step()
        across = {"x": 0, "z": 1} if d["x"] else {"x": 1, "z": 0}
        base = y - CAGE_PAD if self._dir == SINK else y + 1 + CAGE_PAD
        arrow = [self._corner(vx + 0.5 + u * d["x"] + v * across["x"], vz + 0.5 + u * d["z"] + v * across["z"], base + u * d["y"])
                 for u, v in POINTER]
        pygame.draw.polygon(layer, (*rgb(P.TEXT), 240), arrow)
        pygame.draw.polygon(layer, (*rgb(art_room.CANVAS_BG), 200), arrow, 1)
