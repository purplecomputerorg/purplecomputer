"""Blocks room: a floor seen from above and in front, where every letter (or
Space, in the current color) drops a block of its sticker color into the
cursor's column, then moves on the way the cursor last went: along an arrow,
or up. Enter builds up: it drops a block in the current color on top of the
one just laid (or over the cursor, if it has moved since) and goes on up, so
holding it grows a tower, until the column is full. Shift with Up or Down moves
the cursor's height without building, onto blocks too (typing there mixes
into them), and typing then goes that way; that height stays put as
the arrows move, for building sideways. At the top, letters mix into the top
block.
Every block goes in the first free spot at or above the cursor's height, so
a line climbs over whatever is in its way and a stack passes floating
blocks; only the code line keeps the height it reached when it moves on.
Backspace takes blocks off the column top down from the cursor, then carries
on into the column to its left. Holding one letter while pressing another
mixes the two colors. Backslash
opens the color bar. A tap of Tab turns the build a little, and Tab held with
the arrows looks around it: Left and Right turn it a little at a time to any
angle, Up and Down tilt the view from the side to nearly straight down. The
arrows always go the way they point most on screen. The walls and the top
stop the cursor and typing: nothing wraps around. The code line opens from
the Esc menu."""

import asyncio
import math
import time
from functools import lru_cache

import pygame

from .. import palette as P
from ..keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ..palette import DEFAULT_BRUSH_COLOR
from .. import color_recipe
from ..color_wheel import chip as wheel_chip, open_on as open_color_wheel
from ..gfx import rgb
from ..panels import CodePanel, Echo
from ..ui import DOWN, LEFT, MOVE_HINT, PICK_HINT, RIGHT, UP, draw_key_hint, draw_mode_switch, hint_row_h
from .base import Room
from . import art_room
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, HOLD_ACCEL_MULTIPLIER, brush_for_key, onto_grid
from .blocks_code import WORDS, BlocksCodeRunner
from .blocks_view import DEPTH, HEIGHT, PAPER_FLOOR, REST_PITCH, WIDTH, Camera, Painter, bbox, hull, shape

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
REST_TILT = round(math.degrees(REST_PITCH))
# What Tab with an arrow does to the view, as (0 to turn or 1 to tilt, degrees). A quarter turn is
# five turns and none stops on a diagonal, where two arrows would point the same way.
LOOKS = {"left": (0, -18), "right": (0, 18), "up": (1, 15), "down": (1, -15)}
TILTS = (15, 75)             # degrees down the view looks, from the side to nearly straight down: the eye stays over every block and in front of every row
LOOK_PULL, LOOK_SPEED, LOOK_NEAR = 10.0, 240.0, 0.5   # the view closes this share of the way to its goal a second, at most this many degrees a second, and lands within this
TURN_DETAIL_BLOCKS = 600     # blocks; past this the moving view drops shadows and a new block lands at once
TURN_FRAME_BUDGET_S = 0.012  # a detailed moving frame, or one of a block falling, slower than this lowers that limit to its block count
HOVER = HEIGHT - 1            # the level the cursor's block waits on, over its column: the top one
CURSOR_INSET = 0.24           # in cells: the cursor's small block sits this far inside its cell
CURSOR_REACH = 2.0            # cells around the cursor's block that it repaints: its arrow reaches that far
DROP_S = 0.16                 # a new block falls into place this long
DASH = (0.25, 0.75)           # the part of each free cell the line from the cursor's block down to the landing spot crosses
CLEAR = (0, 0, 0, 0)
# The direction arrow as (along, across) points in cells, from the box center outward.
POINTER = ((0.1, -0.09), (0.75, -0.09), (0.75, -0.3), (1.2, 0), (0.75, 0.3), (0.75, 0.09), (0.1, 0.09))
STEPS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
RISE, SINK = "rise", "sink"
SIZE = {"x": WIDTH, "z": DEPTH, "y": HEIGHT}
# Where typing goes next, by way: one step along an axis, as far as the wall or the ceiling.
WAYS = {"right": ("x", 1), "left": ("x", -1), "up": ("z", 1), "down": ("z", -1), RISE: ("y", 1), SINK: ("y", -1)}
TURN_PIC = "hints/turn.png"
HINT = "Type to build!  {Enter} builds up {hints/up.png}"
ARROWS = f"{LEFT} {UP} {DOWN} {RIGHT}"
SHIFT_HINT = f"{PICK_HINT}   {UP} {DOWN} {{hints/up_down.png}}"
TAB_HINT = f"{ARROWS} {{{TURN_PIC}}}"


def turned(x: int, z: int, quarters: int) -> tuple:
    """Where cell (x, z) sits after the floor's quarter turns."""
    for _ in range(quarters % 4):
        x, z = WIDTH - 1 - z, x
    return x, z


@lru_cache(maxsize=4)
def resting_camera(yaw: float, tilt: float, w: int, h: int) -> Camera:
    """The camera for a view at rest, in degrees: `yaw` is how far the floor sits off its side's straight-on view."""
    return Camera(math.radians(yaw), math.radians(tilt), w, h, fit=math.radians(yaw))


class BlocksRoom(Room):
    """Blocks live in a dict keyed by world (x, z, y), y up. Drawing and the
    arrows work in view coordinates, which are world (x, z) turned to the
    side that faces the viewer most. The floor and blocks paint (blocks_view) into two cached
    layers split at the cursor's row: the rows from the cursor's back, then the
    cursor's marks, then the rows in front of it, which hide them like any block. A
    block's change repaints only around its column; the cursor changing rows, the
    room turning or tilting repaints all."""

    name, label, icon = "blocks", "Blocks", ICON_CUBE
    LANDSCAPE = True
    has_code_panel = True
    wheel_ready = True

    def __init__(self, app):
        super().__init__(app)
        self._blocks: dict = {}
        self._x, self._z = WIDTH // 2, DEPTH // 2
        self._hover = 0               # chosen cursor height; 0 = resting on the column
        self._color = DEFAULT_BRUSH_COLOR
        self._key = ""
        self._mix = color_recipe.NO_MIX   # (keycaps, color) of the last chord
        self._stamps = color_recipe.ChordStamps(self._stamp_spot, self._unstamp, self._build)
        self._badge = color_recipe.HoldBadge()
        self._mixed = None                # (keycaps, color) of the last block that mixed
        self._last = None             # (pos, key) of the block just dropped
        self._left = None             # (column, cursor) when typing moved on from the block it laid
        self._next = None             # where a run up or down the column (or a code run) goes on from
        self._dir = "right"           # the way typing builds: a key of WAYS
        # Where the view is headed, in degrees: how far the floor has turned, how far down the view looks,
        # and how far off straight on the floor it is sized to fit sits. Then where it is now.
        self._goal = [0.0, float(REST_TILT), 0.0]
        self._look = list(self._goal)
        self._look_timer = self._looked = None
        self._tab = None              # while Tab is down: whether an arrow has looked around with it
        self._turn_detail_limit = TURN_DETAIL_BLOCKS
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._origin = (0, 0)
        self._cam = self._painter = self._floor = None
        self._built = None             # the build's shape for a moving view, until a block changes
        self._scene = self._front = self._composed = None
        self._dirty: set = set()       # view columns whose blocks changed since the last paint
        self._falls: dict = {}         # blocks still falling into place: (when it was let go, from which level)
        self._fall_timer = None
        self.echo = Echo()
        self.code_panel = None
        self._space_pending = False

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        self.app.set_legend(self._color, visible=True)

    def on_leave(self):
        self.code_panel = None
        self._tab = None

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
        if self._cam is None:
            return None
        vx, vz = self._view(self._x, self._z)
        x, y = self._cam.at(vx + 0.5, 0, vz + 0.5)
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
        self._last = self._next = self._mixed = self._left = None
        self._falls.clear()
        self._stamps.clear()
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
        if not old:
            self._drop(pos)
        self._last = (pos, self._key)
        self._badge.dabbed()
        self._changed(pos)
        return bool(old)

    def _drop(self, pos):
        """A new block falls to its spot from as high as its column is clear, the cursor's block at most."""
        top = min((h for h in self._column() if h > pos[2]), default=HEIGHT) - 1
        if top > pos[2] and pos not in self._falls and len(self._blocks) <= self._turn_detail_limit:
            self._falls[pos] = (time.monotonic(), top)
            self._fall_timer = self._fall_timer or self.app.timers.every(1 / 60, self._fall_tick)

    def _fall_tick(self):
        now = time.monotonic()
        for pos, (since, _) in list(self._falls.items()):
            if now - since >= DROP_S:
                del self._falls[pos]
            self._changed(pos)
        if not self._falls:
            self._fall_timer.stop()
            self._fall_timer = None

    def _stamp_spot(self):
        pos = (self._x, self._z, self._cursor_y())
        return self._x, self._z, self._next, pos, self._blocks.get(pos)

    def _unstamp(self, undo):
        self._x, self._z, self._next, pos, old = undo
        if old is None:
            self._blocks.pop(pos, None)
        else:
            self._blocks[pos] = old
        self._changed(pos)

    def _build(self, keep_height: bool = False):
        """A typed block, then on to the next cell the way the cursor last went."""
        y, column = self._cursor_y(), (self._x, self._z)
        self._advance(y, keep_height, inside=self._place(y))
        self._left = column, (self._x, self._z)

    def _advance(self, y: int, keep_height: bool = False, inside: bool = False):
        """On from the cursor's column at height y the way it last went, as far as the wall or
        the ceiling: there it stays, and the next block goes on top. Typing into a new column
        starts again from the chosen height; code keeps the height it reached."""
        pos = self._spot(y)
        axis, step = WAYS[self._dir]
        pos[axis] = min(max(pos[axis] + step, 0), SIZE[axis] - 1)
        column = (self._x, self._z)
        self._x, self._z = self._world(pos["x"], pos["z"])
        keep = keep_height or column == (self._x, self._z)
        self._next = (self._x, self._z, pos["y"], inside) if keep else None

    def _spot(self, y=None) -> dict:
        """The cursor in view coordinates, at height y or its own."""
        vx, vz = self._view(self._x, self._z)
        return {"x": vx, "z": vz, "y": self._cursor_y() if y is None else y}

    def _face(self, way: str):
        """Typing goes the way the cursor walked, unless a wall is right there,
        since the kid walked to it on purpose: then along it, right, or left
        in the right-hand corner."""
        def room_ahead(w):
            axis, step = WAYS[w]
            return 0 <= self._spot()[axis] + step < SIZE[axis]
        self._dir = next((w for w in (way, "right", "left") if room_ahead(w)), way)

    # What code drives: the same moves as the keys, minus the echo.
    def set_way(self, way: str):
        """Turning straight back after a run starts on its last block, like Art's."""
        if self._next and self._last:
            pos = self._spot(self._next[2])
            axis, step = WAYS[way]
            pos[axis] += step
            back = (*self._world(pos["x"], pos["z"]), pos["y"])
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

    def _step_height(self, rise: int):
        """One level up or down, onto a block if one is there, as far as the floor or the top."""
        y = self._cursor_y() + rise
        if 0 <= y < HEIGHT:
            self._hover = y
            self._next = (self._x, self._z, y, True)

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
            self._changed((self._x, self._z))

    def _changed(self, cell=None):
        """A block changed in `cell`'s column (world), or with none, everything did."""
        self._built = None
        if cell is None:
            self._scene = None
        else:
            self._dirty.add(self._view(*cell[:2]))
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

    def _move(self, direction: str) -> bool:
        """One cell that way; the walls stop it."""
        dx, dz = STEPS[direction]
        vx, vz = self._view(self._x, self._z)
        spot = onto_grid(vx + dx, vz + dz, WIDTH, DEPTH, False)
        if not spot:
            return False
        self._x, self._z = self._world(*spot)
        self._next = None
        return True

    def _view(self, x: int, z: int) -> tuple:
        return turned(x, z, self._side)

    def _world(self, vx: int, vz: int) -> tuple:
        return turned(vx, vz, -self._side)

    # ---------------------------------------------------------------- looking around
    @property
    def _quarters(self) -> int:
        """The quarter turn nearest where the floor is headed: the side that faces the viewer."""
        return math.floor((self._goal[0] + 45) / 90)

    @property
    def _side(self) -> int:
        return self._quarters % 4

    def _off(self) -> float:
        """Degrees the floor is headed for off its side's straight-on view, -45 up to 45."""
        return self._goal[0] - 90 * self._quarters

    def face_front(self):
        """Back to the front and the resting tilt, the short way around."""
        self._aim(yaw=360.0 * round(self._goal[0] / 360), tilt=REST_TILT)

    def look_around(self, direction: str = "right", held: bool = False):
        """A tap of Tab, here or in Time Travel, or Tab with an arrow: one step around, the near edge
        going the arrow's way, or up or down. A held arrow keeps the view just moving."""
        axis, step = LOOKS[direction]
        if not (held and abs(self._goal[axis] - self._look[axis]) > abs(step) / 4):
            self._aim(**{"tilt" if axis else "yaw": self._goal[axis] + step})

    def _aim(self, yaw=None, tilt=None):
        """Set where the view is headed; it eases there from wherever it is now, even mid-move."""
        if yaw is not None:
            self._goal[0] = float(yaw)
            self._goal[2] = abs(self._off())
        if tilt is not None:
            self._goal[1] = float(min(max(tilt, TILTS[0]), TILTS[1]))
        if self._look != self._goal and self._look_timer is None:
            self._looked = time.monotonic()
            self._look_timer = self.app.timers.every(1 / 60, self._look_tick)
        self.app.invalidate()

    def _look_tick(self):
        now = time.monotonic()
        dt, self._looked = now - self._looked, now
        for axis, goal in enumerate(self._goal):
            gap = goal - self._look[axis]
            step = min(abs(gap) * min(1.0, LOOK_PULL * dt), LOOK_SPEED * dt)
            self._look[axis] = goal if abs(gap) - step < LOOK_NEAR else self._look[axis] + math.copysign(step, gap)
        if self._look == self._goal:
            self._look_timer.stop()
            self._look_timer = None
            turns = 360.0 * (self._goal[0] // 360)      # the same view, without the turns behind it
            self._goal[0] -= turns
            self._look[0] -= turns
        self.app.invalidate()

    def _moving(self):
        """(turn, tilt, fit) in degrees while the view is on its way to its goal, else None."""
        return None if self._look == self._goal else tuple(self._look)

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        if not isinstance(action, CharacterAction):
            self._stamps.clear()
        if self.code_panel is None and isinstance(action, ControlAction) and action.action == "space":
            return self._space(action)
        if self.code_panel is None and isinstance(action, ControlAction) and action.action == "tab":
            return self._tab_key(action)
        self._lay_pending()
        if self.code_panel is not None:
            result = await self.code_panel.handle(action)
            if result == "tab_fallthrough":
                self.look_around()
            elif result == "close":
                self.close_code_panel()
            return
        if isinstance(action, ControlAction):
            if action.is_down and (not action.is_repeat or action.action in ("backspace", "enter")):
                self._control(action.action)
        elif isinstance(action, NavigationAction):
            self._navigate(action)
        elif isinstance(action, CharacterAction):
            self._character(action)
        self.app.invalidate()

    def _space(self, action):
        """Space's block waits for release or the next key."""
        if action.is_down and not action.is_repeat:
            self._space_pending = True
        elif not action.is_down:
            self._lay_pending()

    def _tab_key(self, action):
        """Tab held with the arrows looks around; let go with no arrow pressed, it turns the build a little."""
        if action.is_down and not action.is_repeat:
            self._tab = False
        elif not action.is_down:
            if self._tab is False:
                self.look_around()
            self._tab = None
        self.app.invalidate()

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
        self._stamps.press(chord and action.chord_meant)

    def _lay(self, way: str):
        """A block in the brush color, written down as code too."""
        self.echo.color(self._color)
        self.echo.step(WORDS[way])

    def _control(self, name: str):
        if name == "space":
            self._lay(self._dir)
            self._build()
        elif name == "enter":
            self._stack()
        elif name == "backspace":
            self.echo.flush()
            self._erase()

    def _stack(self):
        """Enter: a block in the brush color in the first free spot over the one typing just laid, if
        the cursor is still where that left it, else over the cursor; then on up. A full column stops it."""
        if self._dir != RISE:
            self.echo.flush()
            if self._left and self._left[1] == (self._x, self._z):
                self._x, self._z = self._left[0]
            self._dir = RISE
        self._next = None
        if self._free(range(self._hover, HEIGHT)):
            self._lay(RISE)
            self._build()

    def _navigate(self, action):
        if self._tab is not None:
            self._tab = True
            self.echo.flush()
            self.look_around(action.direction, action.is_repeat)
            return
        if action.with_shift and LOOKS[action.direction][0]:
            self.echo.flush()
            self._step_height(STEPS[action.direction][1])
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
                if not self._move(direction):
                    break
                if laying:
                    self._lay(direction)
                    self._place()
        self._face(action.direction)

    # ---------------------------------------------------------------- painting
    def _view_blocks(self, falling: bool = True) -> dict:
        """The blocks in view coordinates; with `falling`, one still on its way down sits at the
        height it has reached, to a quarter of a cell, so the camera keeps remembering few points."""
        now, falls = time.monotonic(), self._falls if falling else {}

        def height(pos):
            if pos not in falls:
                return pos[2]
            since, top = falls[pos]
            left = max(0.0, 1 - ((now - since) / DROP_S) ** 2)
            return pos[2] + (round((top - pos[2]) * left * 4) / 4 or 0)
        return {(*self._view(x, z), height((x, z, y))): color for (x, z, y), color in self._blocks.items()}

    def _layers(self, size):
        """Bring the cached layers up to date: everything for a new camera, the scene for a new
        cursor row, else only around the columns whose blocks changed."""
        cam = resting_camera(self._off(), self._goal[1], *size)
        row = self._view(self._x, self._z)[1]
        fresh = self._scene is None or cam is not self._cam
        if not (fresh or self._dirty or row != self._painter.row):
            return
        start = time.monotonic()
        whole = fresh or row != self._painter.row
        moved_only = not fresh and not self._dirty
        self._painter = self._painter.on_row(row) if moved_only else Painter(cam, self._view_blocks(), row=row)
        if fresh:
            self._cam = cam
            self._land, self._scene, self._composed = (pygame.Surface(size) for _ in range(3))
            self._front = pygame.Surface(size, pygame.SRCALPHA)
        rects = [cam.column_rect(x, z) for x, z in self._dirty] or [self._scene.get_rect()]
        dirty = self._scene.get_rect() if fresh else rects[0].unionall(rects[1:])
        if fresh or self._dirty:
            self._paint_ground(dirty)
        self._dirty = set()
        self._repaint(self._scene.get_rect() if whole else dirty)
        if self._falls and not whole and time.monotonic() - start > TURN_FRAME_BUDGET_S:
            self._turn_detail_limit = len(self._blocks) - 1         # too slow here to watch blocks fall

    def _paint_ground(self, rect):
        """The floor and the sun's shadows on it: they change with blocks, never with the cursor."""
        g = self._land
        g.set_clip(rect)
        g.blit(self._painter.floor_picture(g.get_size()), rect, rect)
        self._painter.paint_sun(g, rect)
        g.set_clip(None)

    def _repaint(self, rect):
        """Repaint `rect` of the layers: the scene (the ground, the cursor's row and the rows behind
        it) and the rows in front, then their composite."""
        p, rect = self._painter, rect.clip(self._composed.get_rect())
        s, f = self._scene, self._front
        s.set_clip(rect)
        s.blit(self._land, rect, rect)
        p.paint(s, p.back, rect)
        s.set_clip(None)
        f.set_clip(rect)
        f.fill(CLEAR, rect)
        p.paint(f, p.in_front, rect)
        f.set_clip(None)
        self._composed.blit(s, rect, rect)
        self._composed.blit(f, rect, rect)

    def paper(self, g, size, on_screen=False):
        """The build for printing, on a pale floor (the screen's floor on screen), nothing see-through and no cursor."""
        if not self._blocks:
            return None
        top = 1 + max(y for _, _, y in self._blocks)    # fit the build, not the empty air over it
        painter = Painter(Camera(0.0, REST_PITCH, *size, top=top), self._view_blocks(falling=False), hazy=False,
                          floor=None if on_screen else PAPER_FLOOR)
        s = pygame.Surface(size)
        s.fill(rgb(painter.floor[0]))
        painter.paint_floor(s)
        painter.paint_sun(s)
        painter.paint(s, painter.items)
        return s

    def draw(self, g, rect):
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = hint_row_h(g)
        foot_h = 0 if self.app.viewport_panel() is not None else chrome_h + gap
        area = pygame.Rect(inner.x, inner.y + chrome_h + gap, inner.w, inner.h - chrome_h - gap - foot_h)
        self._origin = area.topleft
        moving = self._moving()
        if moving is None:
            self._layers(area.size)
            g.surface.blit(self._composed, area)
            self._draw_cursor(g, area)
            self._draw_hold_badge(g, area)
        else:
            g.surface.set_clip(area)      # a corner can swing a little past the fit on its way
            self._draw_moving(g, area, *moving)
            g.surface.set_clip(None)
        self.bar_row = draw_mode_switch(g, self.header_band(g, rect), (TURN_PIC,), 0 if self._tab is not None else 1,
                                        self._color, wheel=None if self.code_panel else wheel_chip(self),
                                        reserve=self.header_reserve(g))
        self.bar_foot = None
        if foot_h and self.app._panel is None:
            foot = self.bar_foot = pygame.Rect(inner.x, inner.bottom - chrome_h, inner.w, chrome_h)
            hint = SHIFT_HINT if self.app._keyboard_state_machine.shift_active else HINT if self._tab is None else TAB_HINT
            draw_key_hint(g, hint, g.vh(1.9), foot.x, foot.centery)
            color_recipe.draw_foot_right(g, foot, self.app._code_panel_enabled, color_recipe.hint_row(self._key, self._mixed))

    def _draw_hold_badge(self, g, area):
        if self._last and self.app._panel is None:
            (bx, bz, by), at = self._last[0], self._cam.at
            vx, vz = self._view(bx, bz)
            top = bbox([at(vx + a, by + 1, vz + b) for a in (0, 1) for b in (0, 1)]).move(area.topleft)
            self._badge.draw(g, self.app, self._last[1], self._mix, self._color, top, area)

    def _draw_moving(self, g, area, turn, tilt, fit):
        """One frame of the view moving: the world through the same camera as the resting views, turned
        `turn` degrees around, looking `tilt` degrees down and sized as from `fit` degrees off straight
        on, so both ends land on those pictures, the cursor's marks painted in their place among the
        blocks. A frame over budget drops shadows for builds this big from then on."""
        start = time.monotonic()
        cam = Camera(math.radians(turn), math.radians(tilt), area.w, area.h, area.topleft, fit=math.radians(fit))
        detailed = len(self._blocks) <= self._turn_detail_limit
        self._built = self._built or shape(self._blocks)
        painter = Painter(cam, self._blocks, detail=detailed, built=self._built)
        painter.paint_floor(g.surface)
        if detailed:
            painter.paint_sun(g.surface, g.surface.get_clip())
        x, z, items = self._x, self._z, painter.items
        behind = sum(1 for i in items if i[0][:2] <= cam.key(x, z, 0)[:2])     # sorted far to near: these come first
        painter.paint(g.surface, items[:behind])
        self._drop_marks(g.surface, painter, x, z, self._cursor_y())
        painter.paint(g.surface, items[behind:])
        self._hover_marks(g.surface, painter, x, z, self._way(world=True))
        if detailed and time.monotonic() - start > TURN_FRAME_BUDGET_S:
            self._turn_detail_limit = len(self._blocks) - 1

    # ---------------------------------------------------------------- cursor
    # The cursor is its column: a small block in the brush color waits in a bold edge on the top
    # level, over the column, and a dashed line runs down the column's free cells to the spot the
    # next block lands in. The block and its edge go over everything; the line and the landing spot
    # sit in the scene, so nearer blocks hide them. guides/blocks-cursor.md
    def _cursor_boxes(self, vx, vz) -> tuple:
        """Layer pixels the cursor can touch, and those its waiting block can."""
        cam, layer = self._cam, self._composed.get_rect()
        reach = round(CURSOR_REACH * cam.cell(vx, HOVER, vz))
        over = pygame.Rect(0, 0, 2 * reach, 2 * reach)
        over.center = tuple(map(round, cam.at(vx + 0.5, HOVER + 0.5, vz + 0.5)))
        return over.union(cam.column_rect(vx, vz)).clip(layer), over.clip(layer)

    def _draw_cursor(self, g, area):
        """The cursor at rest, drawn between the cached layers. Its waiting block blinks: Gfx.blink
        swaps the patch around it. Where rows in front hide the line's end, an arrowhead over them
        marks where it goes behind."""
        painter, sub = self._painter, g.surface.subsurface(area)
        vx, vz = self._view(self._x, self._z)
        y, way = self._cursor_y(), self._way()
        whole, over = self._cursor_boxes(vx, vz)

        def paint(clip, bright):
            sub.set_clip(clip)
            sub.blit(self._scene, clip, clip)
            self._drop_marks(sub, painter, vx, vz, y)
            sub.blit(self._front, clip, clip)
            self._mark_cut(sub, vx, vz, y)
            self._hover_marks(sub, painter, vx, vz, way, bright)
            sub.set_clip(None)
        g.draw_caret(over.move(area.topleft), lambda: paint(whole, True), lambda: paint(over, False))

    def _drop_marks(self, surf, painter, x, z, y):
        """The spot the next block lands in, thinly edged, with its shadow square if it floats, and
        the dashed line down to it, ending in an arrowhead."""
        if y >= HOVER:
            return
        cam = painter.cam
        if self._ground(y) < y:
            painter.shadow(surf, x, z, self._ground(y))
        self._stroke(surf, self._edge(cam, x, z, y), 1, 3)
        taken, width = set(self._column()), max(2, round(cam.cell(x, y, z)) // 14)
        dashes = [[cam.at(x + 0.5, h + end, z + 0.5) for end in DASH] for h in range(y + 1, HOVER) if h not in taken]
        for color, w in ((rgb(art_room.CANVAS_BG), width + 2), (rgb(P.TEXT), width)):
            for a, b in dashes:
                pygame.draw.line(surf, color, a, b, w)
        self._arrowhead(surf, cam.at(x + 0.5, y + 1, z + 0.5), cam.cell(x, y, z))

    def _mark_cut(self, surf, vx, vz, y):
        """An arrowhead at the lowest point of the line that the rows in front leave in view, if they hide its end."""
        at, front = self._cam.at, self._front
        (ax, ay), (bx, by) = at(vx + 0.5, y + 1, vz + 0.5), at(vx + 0.5, HOVER, vz + 0.5)

        def hidden(px, py):
            return front.get_rect().collidepoint(px, py) and front.get_at((int(px), int(py)))[3]
        steps = int(ay - by) // 2
        if y >= HOVER or steps < 1 or not hidden(ax, ay):
            return
        tip = next(((ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps) for i in range(steps)
                    if not hidden(ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps)), None)
        if tip:
            self._arrowhead(surf, tip, self._cam.cell(vx, y, vz))

    def _hover_marks(self, surf, painter, x, z, way, bright: bool = True):
        """The block waiting over the column, in its bold edge, and an arrow from its top the way typing goes across the floor."""
        cam = painter.cam
        if bright:
            painter.box(surf, x, z, HOVER, HOVER, self._color, inset=CURSOR_INSET)
        self._stroke(surf, self._edge(cam, x, z, HOVER), max(3, round(cam.cell(x, HOVER, z)) // 9), 4)
        if way:
            (dx, dz), ink = way, rgb(P.TEXT)
            arrow = [cam.at(x + 0.5 + u * dx - v * dz, HEIGHT, z + 0.5 + u * dz + v * dx) for u, v in POINTER]
            pygame.draw.polygon(surf, ink, arrow)
            pygame.draw.polygon(surf, rgb(art_room.CANVAS_BG), arrow, 1)

    def _edge(self, cam, x, z, y) -> list:
        return hull([p for _, poly in cam.box((x, y, z), (x + 1, y + 1, z + 1)) for p in poly])

    def _stroke(self, surf, edge, width, casing):
        """A closed light line with a dark one `casing` wider under it, so it reads on any color."""
        for color, w in ((rgb(art_room.CANVAS_BG), width + casing), (rgb(P.TEXT), width)):
            pygame.draw.polygon(surf, color, edge, w)
            for corner in edge:         # a wide line's corners come out notched
                pygame.draw.circle(surf, color, corner, w // 2)

    def _arrowhead(self, surf, tip, cell):
        (px, py), half = tip, max(4, round(cell * 0.2))
        head = [(px, py), (px - half, py - 1.5 * half), (px + half, py - 1.5 * half)]
        pygame.draw.polygon(surf, rgb(P.TEXT), head)
        pygame.draw.polygon(surf, rgb(art_room.CANVAS_BG), head, 1)

    def _ground(self, y: int) -> int:
        """The level the cursor's block would rest on below height y."""
        return max((h + 1 for h in self._column() if h < y), default=0)

    def _way(self, world: bool = False):
        """The (x, z) step typing takes across the floor, in view coordinates or the world's; None when it goes up or down."""
        axis, step = WAYS[self._dir]
        if axis == "y":
            return None
        dx, dz = (step, 0) if axis == "x" else (0, step)
        for _ in range(-self._side % 4 if world else 0):
            dx, dz = -dz, dx
        return dx, dz
