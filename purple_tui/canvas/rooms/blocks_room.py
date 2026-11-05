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
from functools import lru_cache

import pygame

from ... import palette as P
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...palette import DEFAULT_BRUSH_COLOR
from .. import color_recipe
from ..color_wheel import chip as wheel_chip, open_on as open_color_wheel
from ..gfx import rgb
from ..panels import CodePanel, Echo
from ..ui import DOWN, MOVE_HINT, PICK_HINT, UP, HeldKey, draw_key_hint, draw_mode_switch, hint_row_h, hold_status
from .base import Room
from . import art_room
from .art_room import ARROW_HOLD_REPEAT_THRESHOLD, HOLD_ACCEL_MULTIPLIER, brush_for_key, onto_grid
from .blocks_code import WORDS, BlocksCodeRunner
from .blocks_view import DEPTH, HEIGHT, PAPER_FLOOR, PEEK_PITCH, REST_PITCH, WIDTH, Camera, Painter, bbox

ICON_CUBE = "\U000F01A7"     # nf-md-cube_outline
TURN_S, TILT_S = 0.5, 0.3
TURN_DETAIL_BLOCKS = 600     # blocks; past this the moving view drops seams and shadows
TURN_FRAME_BUDGET_S = 0.012  # a detailed moving frame slower than this lowers that limit to its block count
SIDES = (("Front", "modes/front.png"), ("Back", "modes/back.png"))  # the Tab switch's words and pictures
CEILING_ALPHA = {0: 70, 1: 30, 2: 12}   # by squared distance from the cursor's column
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


def ease(p: float) -> float:
    return p * p * (3 - 2 * p)


@lru_cache(maxsize=4)
def resting_camera(pitch: float, w: int, h: int) -> Camera:
    return Camera(0.0, pitch, w, h)


class BlocksRoom(Room):
    """Blocks live in a dict keyed by world (x, z, y), y up. Drawing and the
    arrows work in view coordinates, which are world (x, z) mirrored when the
    room shows its back. The floor and blocks paint (blocks_view) into two cached
    layers split at the cursor's row: the rows from the cursor's back, then the
    cursor, then the rows in front of it, with the towers in the way faded. A
    block's change repaints only around its column; the cursor changing rows, the
    room flipping or tilting repaints all."""

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
        self._stamps = color_recipe.ChordStamps(self._stamp_spot, self._unstamp, self._build)
        self._badge = color_recipe.HoldBadge()
        self._mixed = None                # (keycaps, color) of the last block that mixed
        self._last = None             # (pos, key) of the block just dropped
        self._next = None             # where a run up or down the column (or a code run) goes on from
        self._dir = "right"           # the way typing builds: a key of WRAP
        self._peek = False
        self._motion = None           # (start, seconds, (half turns, tilt) from, to) while the view moves
        self._motion_timer = None
        self._tab = HeldKey(app, lambda: self._tilt(True))
        self._turn_detail_limit = TURN_DETAIL_BLOCKS
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._origin = (0, 0)
        self._cam = self._painter = self._floor = None
        self._scene = self._front = self._composed = self._layer = None
        self._dirty: set = set()       # view columns whose blocks changed since the last paint
        self._faded, self._fade_key = frozenset(), None
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
        self._last = self._next = self._mixed = None
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
        self._changed(pos)
        return bool(old)

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
            self._changed((self._x, self._z))

    def _changed(self, cell=None):
        """A block changed in `cell`'s column (world), or with none, everything did."""
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
        if self._moving() is not None:
            return
        self._move_camera(TURN_S, lambda half, tilt: (half + 1, tilt))
        self._back = not self._back
        self.announce(*SIDES[self._back])

    def _tilt(self, peek: bool):
        """Held Tab eases the view up to look down from above; letting go eases it back."""
        if peek == self._peek:
            return
        self._move_camera(TILT_S, lambda half, tilt: (self._motion[3][0] if self._motion else half, float(peek)))
        self._peek = peek

    def _move_camera(self, seconds: float, to):
        """From wherever the view is now, even mid-move, to `to` of it."""
        start = self._moving() or (float(self._back), float(self._peek))
        self._motion = (time.monotonic(), seconds, start, to(*start))
        if self._motion_timer is None:
            self._motion_timer = self.app.timers.every(1 / 60, self._motion_tick)
        self._changed()

    def _motion_tick(self):
        if self._moving() is None:
            self._motion_timer.stop()
            self._motion_timer = None
        self.app.invalidate()

    def _moving(self):
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
        if not isinstance(action, CharacterAction):
            self._stamps.clear()
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
        """A tap of Tab turns around once it is let go; a hold looks down until then.
        A fresh press always starts from the resting view, so a release lost to an overlay can't leave it looking down."""
        if action.is_down and not action.is_repeat:
            self._tilt(False)
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
        self._stamps.press(chord and action.chord_meant)

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

    # ---------------------------------------------------------------- painting
    def _view_blocks(self) -> dict:
        return {(*self._view(x, z), y): color for (x, z, y), color in self._blocks.items()}

    def _layers(self, size):
        """Bring the cached layers up to date: everything for a new camera, the scene for a new
        cursor row, else only around the columns whose blocks changed; then the towers in the cursor's way."""
        cam = resting_camera(PEEK_PITCH if self._peek else REST_PITCH, *size)
        vx, row = self._view(self._x, self._z)
        fresh = self._scene is None or cam is not self._cam
        if fresh or self._dirty or row != self._painter.row:
            whole = fresh or row != self._painter.row
            moved_only = not fresh and not self._dirty
            self._painter = self._painter.on_row(row) if moved_only else Painter(cam, self._view_blocks(), row=row)
            if fresh:
                self._cam, self._faded = cam, frozenset()
                self._land, self._scene, self._composed = (pygame.Surface(size) for _ in range(3))
                self._front = pygame.Surface(size, pygame.SRCALPHA)
            rects = [cam.column_rect(x, z) for x, z in self._dirty] or [self._scene.get_rect()]
            dirty = self._scene.get_rect() if fresh else rects[0].unionall(rects[1:])
            if fresh or self._dirty:
                self._paint_ground(dirty)
            self._dirty, self._fade_key = set(), None
            self._repaint(self._scene.get_rect() if whole else dirty)
        key = (vx, self._cursor_y())
        if key != self._fade_key:
            self._fade_key = key
            faded = self._hiding(vx, row, key[1])
            if faded != self._faded:
                rects = [cam.block_rect(*b[:3]) for b in faded | self._faded]
                self._faded = faded
                self._repaint(rects[0].unionall(rects[1:]), scene=False)

    def _paint_ground(self, rect):
        """The floor and the sun's shadows on it: they change with blocks, never with the cursor."""
        g = self._land
        g.set_clip(rect)
        g.blit(self._painter.floor_picture(g.get_size()), rect, rect)
        self._painter.paint_sun(g, rect)
        g.set_clip(None)

    def _repaint(self, rect, scene: bool = True):
        """Repaint `rect` of the layers: the scene (ground, row stripe, the rows behind the cursor,
        the row's frame, the cursor's row) and the rows in front, then their composite."""
        p, rect = self._painter, rect.clip(self._composed.get_rect())
        if scene:
            s = self._scene
            s.set_clip(rect)
            s.blit(self._land, rect, rect)
            s.blit(*p.stripe())
            p.paint(s, p.behind, rect, stamp=True)
            p.frame_row(s)
            p.paint(s, p.on_row_items, rect, stamp=True)
            s.set_clip(None)
        f = self._front
        f.set_clip(rect)
        f.fill((0, 0, 0, 0), rect)
        p.paint(f, p.in_front, rect, frozenset(b[:2] for b in self._faded), stamp=True)
        f.set_clip(None)
        self._composed.blit(self._scene, rect, rect)
        self._composed.blit(f, rect, rect)

    def _hiding(self, vx, vz, y) -> frozenset:
        """Every block of each front tower that has a block whose picture overlaps the glass
        column or the landing block by a pixel or more. The block just laid stays solid while
        the cursor sits right behind it, and what it hides doesn't count."""
        cam, front = self._cam, self._painter.front_blocks
        polys = [poly for lo, hi in (((vx, y + 1, vz), (vx + 1, HEIGHT, vz + 1)), ((vx, y, vz), (vx + 1, y + 1, vz + 1)))
                 for _, poly in cam.box(lo, hi)]
        if not front or not polys:
            return frozenset()
        box = bbox([p for poly in polys for p in poly])
        near = [b for b in front if cam.block_rect(*b[:3]).colliderect(box)]
        if not near:
            return frozenset()
        s = pygame.Surface(box.size, pygame.SRCALPHA)
        polys = [[(px - box.x, py - box.y) for px, py in poly] for poly in polys]
        for poly in polys:
            pygame.draw.polygon(s, (255, 255, 255), poly)
        for poly in polys:      # trimmed by a pixel: a block just in front shares an edge with them without hiding them
            pygame.draw.polygon(s, (0, 0, 0, 0), poly, 1)
        spot = pygame.mask.from_surface(s)
        laid = self._last and (*self._view(*self._last[0][:2]), self._last[0][2])
        solid = next((b for b in near if b[:3] == laid and laid[:2] == (vx, vz - 1)), None)
        if solid:
            s.fill((0, 0, 0, 0))
            self._silhouette(s, solid, box)
            spot.erase(pygame.mask.from_surface(s), (0, 0))
        towers = set()
        for b in near:
            if b is not solid and b[:2] not in towers:
                s.fill((0, 0, 0, 0))
                self._silhouette(s, b, box)
                if spot.overlap(pygame.mask.from_surface(s), (0, 0)):
                    towers.add(b[:2])
        return frozenset(b for b in front if b[:2] in towers and b is not solid)

    def _silhouette(self, s, b, box):
        for _, poly in self._cam.box((b[0], b[2], b[1]), (b[0] + 1, b[2] + 1, b[1] + 1)):
            pygame.draw.polygon(s, (255, 255, 255), [(px - box.x, py - box.y) for px, py in poly])

    def paper(self, g, size, on_screen=False):
        """The build for printing, on a pale floor (the screen's floor on screen), nothing see-through and no cursor."""
        if not self._blocks:
            return None
        top = 1 + max(y for _, _, y in self._blocks)    # fit the build, not the empty air over it
        painter = Painter(Camera(0.0, REST_PITCH, *size, top=top), self._view_blocks(), hazy=False, floor=None if on_screen else PAPER_FLOOR)
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
            self._draw_cursor(g, area.topleft)
            self._draw_hold_badge(g, area)
        else:
            self._draw_moving(g, area, *moving)
        self.bar_row = draw_mode_switch(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h), tuple(pic for _, pic in SIDES),
                                        1 if self._back else 0, self._color, wheel=None if self.code_panel else wheel_chip(self))
        self.bar_foot = None
        if foot_h and self.app._panel is None:
            foot = self.bar_foot = pygame.Rect(inner.x, inner.bottom - chrome_h, inner.w, chrome_h)
            draw_key_hint(g, SHIFT_HINT if self.app._keyboard_state_machine.shift_active else HINT, g.vh(1.9), foot.x, foot.centery)
            color_recipe.draw_foot_right(g, foot, self.app._code_panel_enabled, color_recipe.hint_row(self._key, self._mixed))

    def _draw_hold_badge(self, g, area):
        if self._last and self.app._panel is None:
            (bx, bz, by), at = self._last[0], self._cam.at
            vx, vz = self._view(bx, bz)
            top = bbox([at(vx + a, by + 1, vz + b) for a in (0, 1) for b in (0, 1)]).move(area.topleft)
            self._badge.draw(g, self.app, self._last[1], self._mix, self._color, top, area)

    def _draw_moving(self, g, area, half_turns, tilt):
        """One frame of the view moving: the world through the same camera as the resting views, turned
        `half_turns` around and tipped `tilt` of the way down, so both ends land on those pictures; only
        the cursor sits it out. A frame over budget drops seams and shadows for builds this big from then on."""
        start = time.monotonic()
        cam = Camera(math.pi * half_turns, REST_PITCH + (PEEK_PITCH - REST_PITCH) * tilt, area.w, area.h, area.topleft)
        detailed = len(self._blocks) <= self._turn_detail_limit
        painter = Painter(cam, self._blocks, detail=detailed)
        painter.paint_floor(g.surface)
        if detailed:
            painter.paint_sun(g.surface, area)
        painter.paint(g.surface, painter.items)
        if detailed and time.monotonic() - start > TURN_FRAME_BUDGET_S:
            self._turn_detail_limit = len(self._blocks) - 1

    # ---------------------------------------------------------------- cursor
    def _cursor_box(self, vx, vz) -> pygame.Rect:
        """Layer pixels the cursor can touch: its column and the ceiling cells around it,
        below the floor to over the ceiling, with room for the wire box and pointer."""
        at = self._cam.at
        box = bbox([at(vx + dx, y, vz + dz) for dx in (-1, 2) for dz in (-1, 2) for y in (-2, HEIGHT + 2)])
        pad = math.ceil(self._cam.cell(vx, HEIGHT, vz))
        return box.inflate(pad, pad).clip(self._composed.get_rect())

    def _draw_cursor(self, g, origin):
        """A blinking glass column from the ceiling down onto the see-through
        landing block, with its shadow on whatever it would land on and a ring
        around each run of blocks in its column; then the rows in front, which
        hide those rings like any block; then a patch of ceiling fading out around
        the column, the column's edges faint through it, and a bold wire box around
        the landing block on top of everything. Only the patch around the column
        is redrawn; Gfx.blink swaps it bright and dim. guides/blocks-cursor.md"""
        cam, painter = self._cam, self._painter
        vx, vz = self._view(self._x, self._z)
        y = self._cursor_y()
        box = self._cursor_box(vx, vz)
        at = box.move(origin)
        if self._layer is None or self._layer.get_size() != self._composed.get_size():
            self._layer = pygame.Surface(self._composed.get_size(), pygame.SRCALPHA)
        layer = self._layer
        column = [poly for _, poly in cam.box((vx, y + 1, vz), (vx + 1, HEIGHT, vz + 1))]

        def draw(bright):
            fill, edge = (40, 150) if bright else (16, 70)
            g.surface.blit(self._scene, at, box)
            layer.fill((0, 0, 0, 0), box)
            self._outline(layer, column, edge, fill)
            painter.shadow(layer, vx, vz, self._ground(y), y, self._color, alpha=255)
            painter.block(layer, vx, vz, y, self._color, alpha=170 if bright else 100, solo=True)
            for lo, hi in self._stacks():       # its blocks, ringed so they read as part of it among many columns
                for _, poly in cam.box((vx, lo, vz), (vx + 1, hi + 1, vz + 1)):
                    pygame.draw.polygon(layer, (*rgb(P.TEXT), 220 if bright else 120), poly, 2)
            layer.blit(self._front, box, box)
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
        at = self._cam.at
        cells = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if 0 <= vx + dx < WIDTH and 0 <= vz + dz < DEPTH]
        for dx, dz in cells:
            x, z = vx + dx, vz + dz
            top = [at(x, HEIGHT, z), at(x + 1, HEIGHT, z), at(x + 1, HEIGHT, z + 1), at(x, HEIGHT, z + 1)]
            pygame.draw.polygon(layer, (*rgb(P.TEXT), round(CEILING_ALPHA[dx * dx + dz * dz] * strength)), top)

    def _cage(self, layer, vx, vz, y):
        """Twelve wire edges a little outside the landing block: the three hidden ones
        thin and faint, the rest bold over a dark edge so they read against any block."""
        cam = self._cam
        lo, hi = -CAGE_PAD, 1 + CAGE_PAD
        ex, _, ez = cam.eye
        hidden = (lo if ex > vx + 0.5 else hi, hi if ez < vz + 0.5 else lo, lo)   # (x, z, y): the corner away from the eye
        corners = [(a, b, h) for a in (lo, hi) for b in (lo, hi) for h in (lo, hi)]
        edges = [[cam.at(vx + a, y + h, vz + b) for a, b, h in (p, q)] + [hidden in (p, q)]
                 for i, p in enumerate(corners) for q in corners[i + 1:] if sum(m != n for m, n in zip(p, q)) == 1]
        w = max(2, round(cam.cell(vx, y, vz)) // 10)
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
        arrow = [self._cam.at(vx + 0.5 + u * d["x"] + v * across["x"], base + u * d["y"], vz + 0.5 + u * d["z"] + v * across["z"])
                 for u, v in POINTER]
        pygame.draw.polygon(layer, (*rgb(P.TEXT), 240), arrow)
        pygame.draw.polygon(layer, (*rgb(art_room.CANVAS_BG), 200), arrow, 1)
