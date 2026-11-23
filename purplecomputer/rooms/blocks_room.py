"""Blocks room: a floor seen from above and in front, where every letter (or
Space, in the current color) drops a block of its sticker color into the
cursor's column, on top of what is there: typing builds up. The arrows move
the cursor across the floor, Up away from the viewer and Down toward them, and
holding a letter while it moves lays a line. Shift with Up or Down moves its
height without building, onto blocks too (typing there mixes into them), and
that height stays put as the cursor moves, for building sideways.
Enter drops a block in the current color on top too, and held, grows a tower
until the column is full. At the top, letters mix into the top block.
Every block goes in the first free spot at or above the cursor's height, so
a line climbs over whatever is in its way and a stack passes floating
blocks; only the code line keeps the height it reached when it moves on.
Backspace takes blocks off the column top down from the cursor, then carries
on into the column to its left. Holding one letter while pressing another
mixes the two colors. Backslash
opens the color bar. A tap of Tab turns the build a quarter of the way around, clockwise,
and Tab held with the arrows looks around it: Left and Right turn it a little
at a time to any angle, Up and Down tilt the view from the side to nearly
straight down. The arrows always go the way they point most on screen. The walls stop the
cursor and nothing wraps around them; only a full tower sends the next letter on to the
column to its right, as typing wraps to a new line. The code line opens from the Esc menu."""

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
from ..gfx import mix, rgb
from ..panels import CodePanel, Echo
from ..ui import DOWN, LEFT, PICK_HINT, RIGHT, UP, draw_key_hint, draw_mode_switch, hint_row_h
from .base import Room
from . import art_room
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, HOLD_ACCEL_MULTIPLIER, brush_for_key, onto_grid
from .blocks_code import WORDS, BlocksCodeRunner
from .blocks_guide import MIN_W, Guide, columns
from .blocks_view import DEPTH, HEIGHT, PAPER_FLOOR, REST_PITCH, TOP, WIDTH, Camera, Painter, bbox, column_shape, joined, shape

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
REST_TILT = round(math.degrees(REST_PITCH))
# What Tab with an arrow does to the view, as (0 to turn or 1 to tilt, degrees). A quarter turn is
# five turns and none stops on a diagonal, where two arrows would point the same way.
LOOKS = {"left": (0, -18), "right": (0, 18), "up": (1, 15), "down": (1, -15)}
TILTS = (15, 75)             # degrees down the view looks, from the side to nearly straight down: the eye stays over every block and in front of every row
LOOK_PULL, LOOK_SPEED, LOOK_NEAR = 10.0, 240.0, 0.5   # the view closes this share of the way to its goal a second, at most this many degrees a second, and lands within this
LOOK_BOUNCE = 5.0            # degrees the view springs back off a tilt stop when an arrow pushes it past
TURN_DETAIL_BLOCKS = 600     # blocks; past this the moving view drops shadows
TURN_FRAME_BUDGET_S = 0.012  # a detailed moving frame slower than this lowers that limit to its block count
HOVER = HEIGHT                # the level the cursor's block waits on, over its column: one over the top, so it never shares a cell
BUBBLE = 0.62                 # in cells: the radius of the glass bubble the waiting block floats in
CURSOR_INSET = 0.24           # in cells: the cursor's small block sits this far inside its cell
CURSOR_REACH = 2.8            # cells around the cursor's block that it repaints: the arrows' keys reach that far
DROP_S = 0.16                 # a new block falls into place this long
GHOST_ALPHA = 90              # a block falling behind others shows through them this faintly
# The arrow down onto the landing spot, as (up the column from its tip, across) points: a head taller than
# it is wide on a stub of shaft, since a squat triangle alone reads as pointing sideways as easily as down.
HEAD = (0.36, 0.14)          # the line's arrowhead: how long in levels, and how wide each side in cells
FALL_SHADOW = 0.3            # how dark a falling block's shadow on its spot starts, of a landed float's
LINE_ALPHA = 170             # the line down the column: faint, so the waiting block and the spot lead
SPOT_SHADOW = 100            # the shadow the waiting block casts on the spot it lands in
SMOOTH = 3                    # the cursor's marks are painted this many times the size and scaled down: pygame's wide lines come out stepped
CLEAR = (0, 0, 0, 0)
STEPS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
ARROW_KEYS = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}
KEY_SPAN = (0.85, 1.85, 0.4, 0.1)
WALL_SPAN = (0.85, 1.05, 0.45, 0.1)    # the same for the flat stop bar lying where a key would, where the edge stops the cursor
BUMP, BUMP_S = 0.18, 0.18          # cells the waiting block knocks toward a wall an arrow pushes it into, and for how long   # cells: where each arrow's flat key starts and ends out from the column's middle, its half width, its thickness
RISE, SINK = "rise", "sink"
SIZE = {"x": WIDTH, "z": DEPTH, "y": HEIGHT}
OLD_FLOOR = (30, 12)          # the floor's width and depth before it was square: history saved then doesn't say
# Where typing goes next, by way: one step along an axis, as far as the wall or the ceiling.
WAYS = {"right": ("x", 1), "left": ("x", -1), "up": ("z", 1), "down": ("z", -1), RISE: ("y", 1), SINK: ("y", -1)}
TURN_PIC = "hints/turn.png"
LOOK_PIC = "hints/look.png"
HINT = "Type to build!"
SHIFT_HINT = f"{PICK_HINT}   {UP} {DOWN} {{hints/up_down.png}}"


def turned(x: int, z: int, quarters: int) -> tuple:
    """Where cell (x, z) sits after the floor's quarter turns."""
    for _ in range(quarters % 4):
        x, z = WIDTH - 1 - z, x
    return x, z


@lru_cache(maxsize=4)
def resting_camera(yaw: float, tilt: float, w: int, h: int) -> Camera:
    """The camera for a view at rest, in degrees: `yaw` is how far the floor sits off its side's straight-on view."""
    return Camera(math.radians(yaw), math.radians(tilt), w, h, top=HOVER + 1, fit=math.radians(yaw))


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
        self._next = None             # where a run up or down the column (or a code run) goes on from
        self._dir = RISE              # the way the last block went on, a key of WAYS: up, as code starts out too
        self._code_dir = RISE         # the way code builds until it says another: up, as typing does
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
        self._seen, self._cols = {}, {}
        self._guide, self._guide_lit = Guide(), None   # the guide beside the floor, and its row lit when the layers were painted  # the landed blocks in view coordinates, and each view column's shape
        self._bump = self._bump_timer = None   # (dx, dz, dy, when) while the waiting block knocks against a wall or the ceiling
        self._fell: list = []          # where the falling blocks were drawn last, in the layers' pixels
        self._falls: dict = {}         # blocks still falling into place, kept out of the layers: (when it was let go, from which level)
        self._hide: dict = {}          # for each of those, (the painter's items, the ones that can stand in front of it on its way)
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
        return ""       # the guide beside the floor shows the arrows

    def cursor_fraction(self, vp):
        if self._cam is None:
            return None
        vx, vz = self._view(self._x, self._z)
        x, y = self._cam.at(vx + 0.5, 0, vz + 0.5)
        return (self._origin[0] + x - vp.x) / vp.w, (self._origin[1] + y - vp.y) / vp.h

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        state = {f"b:{x},{z},{y}": color for (x, z, y), color in self._blocks.items()}
        state.update(cursor=[self._x, self._z], color=self._color, hover=self._hover, floor=[WIDTH, DEPTH])   # the view isn't the build's
        return state

    def restore_timeline_state(self, state: dict):
        # A step saved on another floor size keeps its middle on the floor's middle; what falls past today's walls goes.
        fw, fd = state.get("floor", OLD_FLOOR)
        ox, oz = (WIDTH - fw) // 2, (DEPTH - fd) // 2
        blocks = {(x + ox, z + oz, y): v for k, v in state.items() if k.startswith("b:") for x, z, y in [map(int, k[2:].split(","))]}
        self._blocks = {p: c for p, c in blocks.items() if all(0 <= n < SIZE[a] for n, a in zip(p, "xzy"))}
        x, z = (state["cursor"][0] + ox, state["cursor"][1] + oz) if "cursor" in state else (WIDTH // 2, DEPTH // 2)
        self._x, self._z = min(max(x, 0), WIDTH - 1), min(max(z, 0), DEPTH - 1)
        self._color = state.get("color", DEFAULT_BRUSH_COLOR)
        self._hover = state.get("hover", 0)
        self._last = self._next = self._mixed = None
        self._falls.clear()
        self._hide.clear()
        self._stamps.clear()
        self._dir = self._code_dir = RISE
        self.echo.reset()
        self._changed()

    def clear(self):
        self.restore_timeline_state({})
        self.face_front()

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
        self._last = (pos, self._key)
        self._badge.dabbed()
        self._changed(pos, landed=bool(old) or not self._drop(pos))
        return bool(old)

    def _drop(self, pos) -> bool:
        """A new block falls to its spot from as high as its column is clear, the cursor's block at most."""
        top = min((h for h in self._column() if h > pos[2]), default=HOVER + 1) - 1
        under = max((p for p in self._falls if p[:2] == pos[:2] and p[2] < pos[2]), default=None)
        if under:       # typed while the one under it still falls: it joins that fall, one stack, one drop
            since, low = self._falls[under]
            self._falls[pos] = (since, low + pos[2] - under[2])
        elif top > pos[2] and pos not in self._falls:
            self._falls[pos] = (time.monotonic(), top)
            self._fall_timer = self._fall_timer or self.app.timers.every(1 / 60, self._fall_tick)
        return pos in self._falls

    def _fall_tick(self):
        now = time.monotonic()
        landed = [pos for pos, (since, _) in self._falls.items() if now - since >= DROP_S]
        for pos in landed:
            del self._falls[pos]
            self._hide.pop(pos, None)
            self._changed(pos)
        if not landed:
            self.app.repaint(self._fall_patch)
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

    def _build(self, way=RISE, keep_height: bool = False):
        """A block, then on to the next cell `way`: up, for everything but code."""
        self._dir = way
        y = self._cursor_y()
        onto = bool(self._next) and self._next[:2] == (self._x, self._z) and self._next[3]     # put on that block on purpose
        if way == RISE and y == HEIGHT - 1 and (self._x, self._z, y) in self._blocks and not onto and self._move("right"):
            y = self._cursor_y()        # a full tower: on to the next column, as typing wraps to a new line
        self._advance(y, keep_height, inside=self._place(y))

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
        self._dir = self._code_dir = way

    def build(self):
        self._build(self._code_dir, keep_height=True)

    def build_letter(self, ch: str) -> bool:
        if not self._set_color(ch):
            return False
        self.build()
        return True

    def skip(self):
        self._dir = self._code_dir
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

    def _step_height(self, rise: int) -> bool:
        """One level up or down, onto a block if one is there, as far as the floor or the top."""
        y = self._cursor_y() + rise
        if not 0 <= y < HEIGHT:
            self._knock(0, 0, rise)
            return False
        self._hover = y
        self._next = (self._x, self._z, y, True)
        return True

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

    def _changed(self, cell=None, landed: bool = True):
        """A block changed in `cell`'s column (world), or with none, everything did. One not yet
        `landed` is drawn over the layers as it falls, and joins them when it lands."""
        self._built = None
        if cell is None:
            self._scene = None
        elif landed:
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
            self._knock(dx, dz)
            return False
        self._x, self._z = self._world(*spot)
        self._next = None
        return True

    def _knock(self, dx, dz, dy=0):
        """The waiting block knocks against the wall (dx, dz) in view coordinates, or with dy the ceiling
        or the floor, and springs back."""
        if self._bump is None:
            self._bump = (dx, dz, dy, time.monotonic())
            self._bump_timer = self.app.timers.every(1 / 60, self._bump_tick)

    def _bump_tick(self):
        if time.monotonic() - self._bump[3] >= BUMP_S:
            self._bump = None
            self._bump_timer.stop()
        self.app.invalidate()

    def _nudge(self) -> tuple:
        """(x, z, height) the waiting block is off its spot as it knocks against a wall, in view coordinates."""
        if self._bump is None or self._moving() is not None:
            return 0.0, 0.0, 0.0
        dx, dz, dy, since = self._bump
        reach = BUMP * math.sin(math.pi * min(1.0, (time.monotonic() - since) / BUMP_S))
        return dx * reach, dz * reach, dy * reach

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

    def turn(self):
        """A tap of Tab, here or in Time Travel: on to the floor's next side, straight on and at the
        resting tilt, so a tap always lands on a standard view however far the view was looked around."""
        self._aim(yaw=90.0 * (self._quarters - 1), tilt=REST_TILT)      # clockwise, seen from above

    def look_around(self, direction: str, held: bool = False):
        """Tab with an arrow: one step around, the near edge going the arrow's way, or up or down.
        A held arrow keeps the view just moving."""
        axis, step = LOOKS[direction]
        if axis and self._goal[1] in TILTS and not TILTS[0] < self._goal[1] + step < TILTS[1]:
            if not held and self._look == self._goal:       # at a stop: it springs back off it, the way that still goes
                self._look[1] -= math.copysign(LOOK_BOUNCE, step)
                self._aim()
        elif not (held and abs(self._goal[axis] - self._look[axis]) > abs(step) / 4):
            self._aim(**{"tilt" if axis else "yaw": self._goal[axis] + step})

    def _tab_hint(self) -> str:
        """The arrows that look around while Tab is down: at a tilt stop, without the one that has nowhere left to go."""
        stuck = {TILTS[0]: DOWN, TILTS[1]: UP}.get(self._goal[1])
        return " ".join(a for a in (LEFT, UP, DOWN, RIGHT) if a != stuck) + f" {{{LOOK_PIC}}}"

    def _aim(self, yaw=None, tilt=None):
        """Set where the view is headed; it eases there from wherever it is now, even mid-move."""
        if yaw is not None:
            side = self._side
            self._goal[0] = float(yaw)
            self._goal[2] = abs(self._off())
            if self._side != side:
                self._scene = None      # a side seen straight on shares its camera with the others: the layers are the old side's
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
        if isinstance(action, ControlAction) and action.action == "tab":
            return await self._tab_key(action)
        self._lay_pending()
        if self.code_panel is not None and not (self._tab is not None and isinstance(action, NavigationAction)):
            result = await self.code_panel.handle(action)
            if result == "tab_fallthrough":
                self.turn()
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

    async def _tab_key(self, action):
        """Tab held with the arrows looks around, in the code line too; let go with no arrow pressed, it's a
        tap: the code line takes the word it suggests, if it has one, else the build turns a quarter."""
        if action.is_down and not action.is_repeat:
            self._tab = False
        elif not action.is_down:
            if self._tab is False and (self.code_panel is None or
                                       await self.code_panel.handle(ControlAction(action="tab")) == "tab_fallthrough"):
                self.turn()
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
            self.echo.letter(WORDS[RISE], char)
        else:
            self.echo.flush()       # a digit would read as a count
        self._stamps.press(chord and action.chord_meant)

    def _lay(self, way: str):
        """A block in the brush color, written down as code too."""
        self.echo.color(self._color)
        self.echo.step(WORDS[way])

    def _control(self, name: str):
        if name == "space":
            self._lay(RISE)
            self._build()
        elif name == "enter":
            self._stack()
        elif name == "backspace":
            self.echo.flush()
            self._erase()

    def _stack(self):
        """Enter: a block in the brush color in the first free spot at or over the cursor's height.
        Unlike Space it never mixes into a block, so held, it grows a tower and a full column stops it."""
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
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        across = not (action.with_shift and LOOKS[action.direction][0])
        laying = across and ((bool(action.char_held) and self._set_color(action.char_held, hold=True)) or action.space_held)
        if not laying:
            self.echo.flush()
        fast = across and not laying and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(HOLD_ACCEL_MULTIPLIER if fast else 1):
                if not self._go(direction, action.with_shift):
                    break
                if laying:
                    self._lay(direction)
                    self._place()

    def _go(self, direction: str, shift: bool) -> bool:
        """One step across the floor, or with Shift and Up or Down, in height."""
        if LOOKS[direction][0] and shift:
            return self._step_height(STEPS[direction][1])
        return self._move(direction)

    # ---------------------------------------------------------------- painting
    def _view_blocks(self, falling: bool = False) -> dict:
        """The blocks in view coordinates: those that have landed, or with `falling`, all of them where they will land."""
        return {(*self._view(x, z), y): color for (x, z, y), color in self._blocks.items()
                if falling or (x, z, y) not in self._falls}

    def _shaped(self, fresh: bool) -> tuple:
        """The landed blocks in view coordinates and their shape: all of it when `fresh`, else only the
        columns that changed and those beside them, whose faces they hide or show."""
        if fresh:
            self._seen, self._cols = self._view_blocks(), {}
            redo = {k[:2] for k in self._seen}
        else:
            for vx, vz in self._dirty:
                x, z = self._world(vx, vz)
                for y in range(HEIGHT):
                    if (x, z, y) in self._blocks and (x, z, y) not in self._falls:
                        self._seen[(vx, vz, y)] = self._blocks[(x, z, y)]
                    else:
                        self._seen.pop((vx, vz, y), None)
            redo = {(vx + dx, vz + dz) for vx, vz in self._dirty for dx, dz in ((0, 0), *STEPS.values())}
        for col in redo:
            self._cols[col] = column_shape(self._seen, *col)
        return self._seen, joined(self._cols[col] for col in sorted(self._cols))

    def _layers(self, size):
        """Bring the cached layers up to date: everything for a new camera, else only around the columns
        whose blocks changed and what crossed the cursor's row as it moved."""
        cam = resting_camera(self._off(), self._goal[1], *size)
        row, was = self._view(self._x, self._z)[1], self._painter and self._painter.row
        fresh = self._scene is None or cam is not self._cam
        lit, self._guide_lit = self._lit_row(), self._lit_row() if fresh else self._guide_lit
        if not (fresh or self._dirty or row != was or lit != self._guide_lit):
            return
        if fresh or self._dirty:
            blocks, built = self._shaped(fresh)
            self._painter = Painter(cam, blocks, row=row, quarters=self._side, built=built)
        else:
            self._painter = self._painter.on_row(row)
        if fresh:
            self._cam = cam
            self._land, self._scene, self._composed = (pygame.Surface(size) for _ in range(3))
            self._front = pygame.Surface(size, pygame.SRCALPHA)
            rects = [self._scene.get_rect()]
        else:
            rects = [cam.column_rect(x, z) for x, z in self._dirty] + (list(self._guide_spots().values()) if lit != self._guide_lit else [])
        self._guide_lit = lit
        if rects:
            self._paint_ground(rects[0].unionall(rects[1:]))
        if not fresh and was is not None and row != was:
            rects += self._painter.crossed(was, row)
        self._dirty = set()
        if rects:
            self._repaint(rects[0].unionall(rects[1:]))

    def _paint_ground(self, rect):
        """The floor and the sun's shadows on it: they change with blocks, never with the cursor."""
        g = self._land
        g.set_clip(rect)
        g.blit(self._painter.floor_picture(g.get_size()), rect, rect)
        self._guide.paint(self.app.g, g, self._guide_spots(), self._guide_lit, rect)
        self._painter.paint_sun(g, rect)
        g.set_clip(None)

    def _guide_spots(self) -> dict:
        return columns(self._composed.get_size(), self.code_panel is not None, self.app.g.vw(MIN_W), HOVER + 1, TILTS)

    def _lit_row(self):
        """The guide's row for the key held now, if any."""
        return "height" if self.app._keyboard_state_machine.shift_active else "look" if self._tab is not None else None

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
        painter = Painter(Camera(0.0, REST_PITCH, *size, top=top), self._view_blocks(falling=True), hazy=False,
                          floor=None if on_screen else PAPER_FLOOR, quarters=self._side)
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
            self._draw_falls(g.surface.subsurface(area))
            self._draw_hold_badge(g, area)
        else:
            g.surface.set_clip(area)      # a corner can swing a little past the fit on its way
            self._draw_moving(g, area, *moving)
            g.surface.set_clip(None)
        shift = self.app._keyboard_state_machine.shift_active
        self.bar_row = draw_mode_switch(g, self.header_band(g, rect), (TURN_PIC,), 0 if self._tab is False else 1,
                                        self._color, wheel=None if self.code_panel else wheel_chip(self),
                                        reserve=self.header_reserve(g))
        self.bar_foot = None
        if foot_h and self.app._panel is None:
            foot = self.bar_foot = pygame.Rect(inner.x, inner.bottom - chrome_h, inner.w, chrome_h)
            hint = SHIFT_HINT if shift else HINT if self._tab is None else self._tab_hint()
            draw_key_hint(g, hint, g.vh(1.9), foot.x, foot.centery)
            color_recipe.draw_foot_right(g, foot, self.app._code_panel_enabled, color_recipe.hint_row(self._key, self._mixed))

    def _draw_hold_badge(self, g, area):
        if self._last and self.app._panel is None:
            (bx, bz, by), at = self._last[0], self._cam.at
            vx, vz = self._view(bx, bz)
            top = bbox([at(vx + a, by + 1, vz + b) for a in (0, 1) for b in (0, 1)]).move(area.topleft)
            self._badge.draw(g, self.app, self._last[1], self._mix, self._color, top, area)

    def _falling(self) -> list:
        """(x, z, height now, level it lands on, level it fell from, color) of each block on its way
        down, in view coordinates, far to near. Heights go by quarter cells, so the camera remembers few points."""
        now, cam, out = time.monotonic(), self._cam, []
        for (x, z, y), (since, top) in self._falls.items():
            if (x, z, y) in self._blocks:
                left = max(0.0, 1 - ((now - since) / DROP_S) ** 2)
                out.append((*self._view(x, z), y + round((top - y) * left * 4) / 4, y, top, self._blocks[(x, z, y)]))
        return sorted(out, key=lambda f: cam.key(*f[:3]))

    def _fall_patch(self):
        """A frame of the falls alone, for app.repaint: the layers again where the blocks were and are now,
        the cursor over them if they touch it, then the blocks. Returns the screen rect it painted."""
        if self._moving() is not None or self._scene is None or self._dirty:
            return self.app.invalidate()
        g, area = self.app.g, pygame.Rect(self._origin, self._composed.get_size())
        sub = g.surface.subsurface(area)
        rects = self._fell + [self._cam.run_rect(vx, vz, y, h) for vx, vz, h, y, *_ in self._falling()]
        if not rects:
            return None
        spot = rects[0].unionall(rects[1:]).clip(sub.get_rect())
        sub.blit(self._composed, spot, spot)
        whole = self._cursor_boxes(*self._view(self._x, self._z))[0]
        if spot.colliderect(whole):
            self._draw_cursor(g, area)
            spot = spot.union(whole)
        self._draw_falls(sub)
        g.surface.set_clip(spot.move(area.topleft))
        self._draw_hold_badge(g, area)
        g.surface.set_clip(None)
        return spot.move(area.topleft)

    def _draw_falls(self, sub):
        """The falling blocks over the layers, each behind what the layers hold in front of it: that
        is found once a fall, and again when the blocks change, so a frame costs the same in any build."""
        cam, painter = self._cam, self._painter
        self._fell = []
        for vx, vz, h, y, top, color in self._falling():
            pos = (*self._world(vx, vz), y)
            kept = self._hide.get(pos)
            if not kept or kept[0] is not painter.items:
                kept = self._hide[pos] = painter.items, painter.after(vx, vz, y, cam.run_rect(vx, vz, y, top))
            rect = cam.run_rect(vx, vz, y, h)       # down to its spot, where its shadow darkens as it comes
            self._fell.append(rect)
            sub.set_clip(rect)
            painter.shadow(sub, vx, vz, y, dark=FALL_SHADOW + (1 - FALL_SHADOW) * (1 - (h - y) / max(1, top - y)))
            painter.box(sub, vx, vz, h, h, color)
            if kept[1]:
                painter.paint(sub, kept[1], rect)
                ghost = pygame.Surface(rect.size, pygame.SRCALPHA)
                painter.on(cam.zoomed(1, rect.topleft)).box(ghost, vx, vz, h, h, color)
                ghost.set_alpha(GHOST_ALPHA)
                sub.blit(ghost, rect)
        sub.set_clip(None)

    def _draw_moving(self, g, area, turn, tilt, fit):
        """One frame of the view moving: the world through the same camera as the resting views, turned
        `turn` degrees around, looking `tilt` degrees down and sized as from `fit` degrees off straight
        on, so both ends land on those pictures, the cursor's marks painted in their place among the
        blocks. A frame over budget drops shadows for builds this big from then on."""
        start = time.monotonic()
        cam = Camera(math.radians(turn), math.radians(tilt), area.w, area.h, area.topleft, top=HOVER + 1, fit=math.radians(fit))
        detailed = len(self._blocks) <= self._turn_detail_limit
        self._built = self._built or shape(self._blocks)
        painter = Painter(cam, self._blocks, detail=detailed, built=self._built)
        if self._composed is not None:
            self._guide.paint(g, g.surface.subsurface(area), self._guide_spots(), self._lit_row())
        painter.paint_floor(g.surface)
        if detailed:
            painter.paint_sun(g.surface, g.surface.get_clip())
        x, z, items = self._x, self._z, painter.items
        behind = sum(1 for i in items if i[0][:2] <= cam.key(x, z, 0)[:2])     # sorted far to near: these come first
        painter.paint(g.surface, items[:behind])
        self._drop_marks(g.surface, painter, x, z, self._cursor_y())
        painter.paint(g.surface, items[behind:])
        self._hover_marks(g.surface, painter, x, z)
        self._draw_arrow_keys(g, g.surface, painter, x, z, world=True)
        if detailed and time.monotonic() - start > TURN_FRAME_BUDGET_S:
            self._turn_detail_limit = len(self._blocks) - 1

    # ---------------------------------------------------------------- cursor
    # The cursor is its column: a small block in the brush color waits in a wire box on the top
    # level, over the column, and a line runs down the column's free cells to the spot the
    # next block lands in. The block and its box go over everything; the rest sits in the scene,
    # so nearer blocks hide it. guides/blocks-cursor.md
    def _cursor_boxes(self, vx, vz) -> tuple:
        """Layer pixels the cursor can touch, and those its waiting block can."""
        cam, layer = self._cam, self._composed.get_rect()
        over = self._square(cam, vx, vz, HOVER + 0.5, round(CURSOR_REACH * cam.cell(vx, HOVER, vz)))
        return over.union(cam.column_rect(vx, vz)).clip(layer), over.clip(layer)

    def _square(self, cam, x, z, h, reach: int) -> pygame.Rect:
        """The screen square reaching `reach` pixels each way from the column's middle at height h."""
        px, py = cam.at(x + 0.5, h, z + 0.5)
        return pygame.Rect(round(px) - reach, round(py) - reach, 2 * reach, 2 * reach)

    def _draw_cursor(self, g, area):
        """The cursor at rest, drawn between the cached layers. Its waiting block blinks: Gfx.blink
        swaps the patch around it. Where rows in front hide the line's end, an arrowhead over them
        marks where it goes behind."""
        painter, sub = self._painter, g.surface.subsurface(area)
        vx, vz = self._view(self._x, self._z)
        y = self._cursor_y()
        whole, over = self._cursor_boxes(vx, vz)
        cut = self._cut(vx, vz, y)

        def paint(clip, bright):
            sub.set_clip(clip)
            sub.blit(self._scene, clip, clip)
            self._drop_marks(sub, painter, vx, vz, y)
            sub.blit(self._front, clip, clip)
            if cut:
                self._smooth(sub, painter, self._square(painter.cam, vx, vz, cut, round(painter.cam.cell(vx, cut, vz) * 1.3)),
                             lambda layer, big: self._arrowhead(layer, big.cam, vx, vz, cut))
            self._hover_marks(sub, painter, vx, vz, bright)
            sub.set_clip(None)
            self._draw_arrow_keys(g, sub, painter, vx, vz, origin=area.topleft)
        g.draw_caret(over.move(area.topleft), lambda: paint(whole, True), lambda: paint(over, False))

    def _smooth(self, surf, painter, rect, draw):
        """Paint with `draw(layer, painter)` SMOOTH times the size and scale it down onto `rect` of `surf`."""
        rect = rect.clip(surf.get_clip())
        if rect.w and rect.h:
            layer = pygame.Surface((rect.w * SMOOTH, rect.h * SMOOTH), pygame.SRCALPHA)
            draw(layer, painter.on(painter.cam.zoomed(SMOOTH, rect.topleft)))
            surf.blit(pygame.transform.smoothscale(layer, rect.size), rect)

    def _drop_marks(self, surf, painter, x, z, y):
        """The spot the next block lands in as a wire box with the waiting block's shadow in it (and its own
        square on the ground if it floats), and a faint line down to it through the column's free cells,
        ending in a small arrowhead."""
        if y >= HOVER:
            return
        ground, taken = self._ground(y), set(self._column())

        def draw(layer, big):
            cam, unit = big.cam, big.cam.zoom
            if ground < y:
                big.shadow(layer, x, z, ground)
            big.shadow(layer, x, z, y, alpha=SPOT_SHADOW)
            self._wire(layer, cam, x, z, y, 2 * unit, 2 * unit)
            width = max(unit, round(cam.cell(x, y, z)) // 22)
            for h in range(y + 1, HOVER):
                if h not in taken:
                    pygame.draw.line(layer, (*rgb(P.TEXT), LINE_ALPHA), cam.at(x + 0.5, h, z + 0.5), cam.at(x + 0.5, h + 1, z + 0.5), width)
            self._arrowhead(layer, cam, x, z, y + 1)
        pad = round(painter.cam.cell(x, y, z) * 0.5) + 6
        self._smooth(surf, painter, painter.cam.run_rect(x, z, ground, HOVER).inflate(2 * pad, 2 * pad), draw)

    def _cut(self, vx, vz, y):
        """The height of the lowest point of the line that the rows in front leave in view, if they hide its end."""
        at, front = self._cam.at, self._front

        def hidden(h):
            px, py = at(vx + 0.5, h, vz + 0.5)
            return front.get_rect().collidepoint(px, py) and front.get_at((int(px), int(py)))[3]
        if y < HOVER and hidden(y + 1):
            return next((h for h in (y + 1 + i / 16 for i in range(1, 16 * (HOVER - y - 1))) if not hidden(h)), None)

    def _hover_marks(self, surf, painter, x, z, bright: bool = True):
        """The small block waiting over the column in a glass bubble, so it never reads as a block already laid.
        Its blink shows the bubble empty."""
        ox, oz, oy = self._nudge()

        def draw(layer, big):
            cam = big.cam
            center = cam.at(x + ox + 0.5, HOVER + oy + 0.5, z + oz + 0.5)
            r, unit = BUBBLE * cam.cell(x, HOVER, z), cam.zoom
            pygame.draw.circle(layer, (*rgb(P.TEXT), 34), center, r)
            if bright:
                big.box(layer, x + ox, z + oz, HOVER + oy, HOVER + oy, self._color, inset=CURSOR_INSET)
            pygame.draw.circle(layer, (*rgb(art_room.CANVAS_BG), 140), center, r, 4 * unit)
            pygame.draw.circle(layer, (*rgb(P.TEXT), 200), center, r - unit, 2 * unit)
            glint = pygame.Rect(0, 0, 1.3 * r, 1.3 * r)
            glint.center = center
            pygame.draw.arc(layer, (255, 255, 255, 150), glint, 1.9, 2.7, 2 * unit)
        reach = 16 + round(painter.cam.cell(x, HOVER, z) * BUMP)
        self._smooth(surf, painter, painter.cam.run_rect(x, z, HOVER, HOVER).inflate(2 * reach, 2 * reach), draw)

    def _arrow_keys(self, cam, x, z, world: bool = False) -> list:
        """(glyph, lo, hi) of each arrow's key, far to near: a thin slab lying flat out from the waiting block
        the way that arrow moves the cursor. One going away sits level with the box's top and one coming
        toward with its bottom, the rest in between, so the box hides none of them. Where the edge stops
        the cursor, a short bright bar lies flat in the key's place instead, with no glyph: a stop line."""
        keys = []
        for way, (dx, dz) in STEPS.items():
            for _ in range(-self._side % 4 if world else 0):
                dx, dz = -dz, dx
            wall = not (0 <= x + dx < WIDTH and 0 <= z + dz < DEPTH)
            near, far, half, thick = WALL_SPAN if wall else KEY_SPAN
            h = HOVER + 0.5 + 0.5 * cam.away(dx, dz)
            xs = sorted((x + 0.5 + dx * near - dz * half, x + 0.5 + dx * far + dz * half))
            zs = sorted((z + 0.5 + dz * near + dx * half, z + 0.5 + dz * far - dx * half))
            keys.append((None if wall else ARROW_KEYS[way], (xs[0], h - thick, zs[0]), (xs[1], h, zs[1])))
        return sorted(keys, key=lambda k: cam.key(k[1][0], k[1][2], 0))

    def _draw_arrow_keys(self, g, surf, painter, x, z, world: bool = False, origin=(0, 0)):
        """Each arrow's key lying flat beside the waiting block in faint glass, its arrow upright on it as
        printed on the real key. `origin` is where `surf` sits on the screen."""
        cam = painter.cam
        keys, cell = self._arrow_keys(cam, x, z, world), cam.cell(x, HOVER, z)

        def draw(layer, big):
            c, edge = big.cam, (*rgb(P.TEXT), 150)
            for glyph, lo, hi in keys:
                top, side = ((*rgb(P.TEXT), 64), (*mix(P.TEXT, art_room.CANVAS_BG, 0.45), 200)) if glyph else \
                    ((*rgb(P.TEXT), 210), (*mix(P.TEXT, art_room.CANVAS_BG, 0.3), 240))
                for n, poly in c.box(lo, hi):
                    pygame.draw.polygon(layer, top if n is TOP else side, poly)
                face = [c.at(px, hi[1], pz) for px, pz in ((lo[0], lo[2]), (hi[0], lo[2]), (hi[0], hi[2]), (lo[0], hi[2]))]
                pygame.draw.polygon(layer, edge, face, c.zoom)
        self._smooth(surf, painter, self._square(cam, x, z, HOVER + 0.5, round(cell * (KEY_SPAN[1] + 0.9))), draw)
        px = max(g.vh(1.3), round(cell * 0.34))
        for glyph, lo, hi in (k for k in keys if k[0]):
            kx, ky = cam.at((lo[0] + hi[0]) / 2, hi[1], (lo[2] + hi[2]) / 2)
            for color, d in ((art_room.CANVAS_BG, 1), (P.TEXT, 0)):     # a soft shadow, so it reads on any color
                g.draw_text(glyph, px, round(kx) + origin[0] + d, round(ky) + origin[1] + d, "mono-bold", color, anchor="center")

    def _wire(self, surf, cam, x, z, y, width, casing):
        """The cell as a wire box: the edges of the faces the eye sees, each a light line with a
        dark one `casing` wider under it, so it reads on any color."""
        faces = [poly for _, poly in cam.box((x, y, z), (x + 1, y + 1, z + 1))]
        for color, w in ((rgb(art_room.CANVAS_BG), width + casing), (rgb(P.TEXT), width)):
            for poly in faces:
                pygame.draw.polygon(surf, color, poly, w)
                for corner in poly:         # a wide line's corners come out notched
                    pygame.draw.circle(surf, color, corner, w // 2)

    def _arrowhead(self, surf, cam, x, z, h):
        """A small arrowhead on the column's middle line, its tip at height h, pointing down it."""
        (px, py), (qx, qy) = cam.at(x + 0.5, h, z + 0.5), cam.at(x + 0.5, h + HEAD[0], z + 0.5)
        level, wide = math.hypot(qx - px, qy - py) or 1.0, HEAD[1] * cam.cell(x, h, z)
        ux, uy = (qx - px) / level, (qy - py) / level
        head = [(px, py), (qx - uy * wide, qy + ux * wide), (qx + uy * wide, qy - ux * wide)]
        pygame.draw.polygon(surf, rgb(art_room.CANVAS_BG), head, 2 * cam.zoom)
        pygame.draw.polygon(surf, rgb(P.TEXT), head)

    def _ground(self, y: int) -> int:
        """The level the cursor's block would rest on below height y."""
        return max((h + 1 for h in self._column() if h < y), default=0)
