"""Art room: a grid of square cells. Every letter paints its sticker color,
Backslash opens the color wheel (for the brush, or in ABC for the letters),
Space puts the brush down so arrows draw (or only while held),
holding Backspace takes squares, then whole lines, and Tab switches to writing letters.
The Logo-style code line opens from the Esc menu."""

import math
import time

import pygame

from ... import palette as P
from ...code_runner import ArtCodeRunner
from ...constants import ART_COLS, ART_ROWS, ICON_PALETTE
from ...color_mixing import mix_colors_paint
from ..gfx import _Cache, hexcolor, mix, rgb
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from .. import color_recipe, paper
from ...palette import DEFAULT_BRUSH_COLOR, GRAYSCALE, KEY_COLORS, UNMAPPED, get_key_color
from ..color_wheel import chip as wheel_chip, open_on as open_color_wheel
from ..panels import CodePanel, Echo
from ..ui import (AUTO, MOVE_HINT, PICK_HINT, auto_ink, draw_key_hint, draw_label, draw_mode_switch, draw_status_row, hint_row_h,
                  status_row_h, status_row_px, swatch_dot)
from .base import Room

COLS, ROWS = ART_COLS, ART_ROWS
BRUSH_CHAR = "█"
ARROW_HOLD_REPEAT_THRESHOLD = 8
HOLD_ACCEL_MULTIPLIER = 6
LINES_AFTER = 1.0                   # seconds of holding Backspace before it takes whole lines
LINE_FADE_S = 0.5                   # each line fades out this long first; letting go brings it back
CANVAS_BG = "#221440"
CANVAS_ALT = "#281a4a"               # checkerboard partner of CANVAS_BG
TIP_EDGE = "#120a24"                # dark rim so the brush tip reads on any paint, even its own color
BRUSH_LEAN = (0.5, -0.866)          # handle up and to the right, the way a right hand holds it
BRUSH_FLOAT = 0.35                  # cells the lifted brush hovers above its ring
BRUSH_HEAD = 0.55                   # of the brush's height from the tip: bristles and ferrule, no handle
SPRITE_HALF = 3.5                   # cells from the cursor cell's center to the sprite's edge
LIFT_FRAME, LIFT_STEP = 0.03, 0.34  # Space drops or lifts the brush over three quick frames
HEADING_TURNS = {"right": 0, "up": 90, "left": 180, "down": -90}
HINTS = {
    "littles": "Type to paint!",
    "pen": "Brush down! Arrows paint. {Space} lifts it.",
    "paint": "Type to paint! {Space} puts the brush down.",
    "write": "Type to write! Arrow keys move. {Enter} for a new line.",
    "pick": PICK_HINT,
}


def brush_for_key(char: str):
    """(key, color) for a key that has a sticker or gray color, else None."""
    k = char.lower()
    if k in GRAYSCALE:
        return k, GRAYSCALE[k]
    if (k.isalpha() or k in KEY_COLORS) and get_key_color(k) != UNMAPPED:
        return k, get_key_color(k)
    return None


def onto_grid(x: int, y: int, w: int, h: int, wrap: bool):
    """(x, y) if it's on a w by h grid, else around to the far side with `wrap`, else None.
    Moves wrap on a fresh press but a held key stops at the edge, so a fast run sticks there."""
    if 0 <= x < w and 0 <= y < h:
        return x, y
    return (x % w, y % h) if wrap else None


def _brush_shape(at, u: float, press: float) -> tuple:
    """Bristles, sheen, ferrule and handle as polygons, tip first along the lean.
    Pressing splays the bristles and bends their tip off sideways, the way a
    brush flattens against paper."""
    n, belly = 20, 0.42
    length, half, bend = u * (1.15 - 0.2 * press), u * (0.4 + 0.12 * press), u * 0.6 * press
    tip_r, neck = u * (0.01 + 0.08 * press), u * 0.21
    width = lambda t: (tip_r + (half - tip_r) * math.sin(math.pi / 2 * t / belly) if t < belly
                       else half - (half - neck) * ((t - belly) / (1 - belly)) ** 2)
    dx, dy = BRUSH_LEAN
    paper = at(0, 0)[1] + u * (0.5 - 0.45 * press)

    def side(t, k):
        x, y = at(length * t, 0)
        tx_, ty_ = dx * length + 2 * bend * (1 - t), dy * length
        m = math.hypot(tx_, ty_)
        w = width(t) * k
        return x - bend * (1 - t) ** 2 - ty_ / m * w, min(paper, y + tx_ / m * w)

    ts = [i / n for i in range(n + 1)]
    bristles = [side(t, 1) for t in ts] + [side(t, -1) for t in reversed(ts)]
    sheen = [side(t, -0.45) for t in ts[4:15]]
    f0, f1, h1 = length, length + 0.32 * u, length + 1.6 * u
    ferrule = [at(f0, neck * 1.15), at(f1, neck * 0.95), at(f1, -neck * 0.95), at(f0, -neck * 1.15)]
    stations = ((f1, 0.12), (f1 + 0.35 * u, 0.16), (h1, 0.07))
    handle = [at(a, w * u) for a, w in stations] + [at(a, -w * u) for a, w in reversed(stations)]
    return bristles, sheen, ferrule, handle, at(h1, 0)


def _dash_outline(surf, mid: int, u: float, edge: int, color: str, alpha: int):
    """Thin dashes around the cursor cell, the square the brush will paint."""
    lo, hi, n = mid - u / 2, mid + u / 2, 3
    seg, w = u / (2 * n - 1), max(2, round(u * 0.035))
    for (x0, y0), (x1, y1) in (((lo, lo), (hi, lo)), ((hi, lo), (hi, hi)), ((hi, hi), (lo, hi)), ((lo, hi), (lo, lo))):
        dx, dy = (x1 - x0) / u, (y1 - y0) / u
        for i in range(n):
            a, b = 2 * i * seg, (2 * i + 1) * seg
            line = ((x0 + dx * a, y0 + dy * a), (x0 + dx * b, y0 + dy * b))
            pygame.draw.line(surf, (*rgb(TIP_EDGE), alpha), *line, w + edge)
            pygame.draw.line(surf, (*rgb(color), alpha), *line, w)


def _brush_tip(c: int, color: str, tip, arrow_turn, lift: float = 1.0, ground="cell") -> pygame.Surface:
    """A 7c square centered on the cursor cell, drawn 4x and smoothed down.
    tip "brush" is a paintbrush in the brush color: lift 1 floats it above a
    ring on the cell (pen up), lift 0 presses its splayed bristles into the
    cell (pen down); ground "ring" leaves off the dashed cell, None the ring too.
    arrow_turn, when not None, adds a chevron turned that many degrees from pointing right."""
    s = 4
    u = c * s
    mid = round(SPRITE_HALF * u)
    surf = pygame.Surface((2 * mid, 2 * mid), pygame.SRCALPHA)
    edge = max(s, round(u * 0.06))
    if tip == "brush":
        press = 1 - lift
        if lift and ground:
            ring, band, alpha = pygame.Rect(0, 0, round(u * 0.9), round(u * 0.42)), max(2 * s, round(u * 0.09)), round(255 * lift)
            ring.center = (mid, mid + round(u * 0.3))
            if ground == "cell":
                _dash_outline(surf, mid, u, edge, color, alpha)
            pygame.draw.ellipse(surf, (*rgb(TIP_EDGE), alpha), ring.inflate(2 * edge, 2 * edge), band + 2 * edge)
            pygame.draw.ellipse(surf, (*rgb(color), alpha), ring, band)
        tx, ty = mid + u * 0.3 * press, mid + u * (0.3 - BRUSH_FLOAT * lift)
        (dx, dy), (px, py) = BRUSH_LEAN, (-BRUSH_LEAN[1], BRUSH_LEAN[0])
        at = lambda a, b: (tx + dx * a + px * b, ty + dy * a + py * b)
        bristles, sheen, ferrule, handle, end = _brush_shape(at, u, press)
        r_end = round(u * 0.08)
        pygame.draw.circle(surf, rgb(TIP_EDGE), end, r_end + edge)
        parts = ((handle, P.ACCENT), (ferrule, P.TEXT), (bristles, color))
        for poly, _ in parts:
            pygame.draw.polygon(surf, rgb(TIP_EDGE), poly, 2 * edge)
        for poly, fill in parts:
            pygame.draw.polygon(surf, rgb(fill), poly)
        pygame.draw.circle(surf, rgb(P.ACCENT), end, r_end)
        pygame.draw.lines(surf, rgb(mix_colors_paint([color, "#FFFFFF"])), False, sheen, 2 * edge)
    if arrow_turn is not None:
        x0, h = round(u * 0.65), round(u * 0.32)
        a = math.radians(arrow_turn)
        turn = lambda x, y: (mid + x * math.cos(a) + y * math.sin(a), mid - x * math.sin(a) + y * math.cos(a))
        tri = [turn(x0, -h), turn(x0 + h * 1.3, 0), turn(x0, h)]
        fill = color if tip else P.TEXT
        pygame.draw.polygon(surf, rgb(fill), tri)
        pygame.draw.polygon(surf, rgb(TIP_EDGE), tri, edge)
    return pygame.transform.smoothscale(surf, (2 * mid // s, 2 * mid // s))


def _brush_icon(h: int, color: str, lift: float) -> pygame.Surface:
    """The cursor brush's bristles and ferrule over its ring, no handle, cropped to their ink."""
    c = max(3, round(h / 1.4))
    ink = _brush_tip(c, color, "brush", None, lift, ground=None).get_bounding_rect()
    surf = _brush_tip(c, color, "brush", None, lift, ground="ring")
    full = surf.get_bounding_rect()
    top = ink.bottom - round(ink.h * BRUSH_HEAD)
    head = surf.subsurface(pygame.Rect(full.x, top, full.w, full.bottom - top))
    return head.subsurface(head.get_bounding_rect()).copy()


class _RoomBrushRunner(ArtCodeRunner):
    """The brush lives on the room, so `brush up` holds across lines and shows on
    the cursor; `_paint_on` is Paint (not ABC) with that brush down."""

    @property
    def _paint_on(self) -> bool:
        return self._painting and self.canvas._code_brush_down

    @_paint_on.setter
    def _paint_on(self, on: bool):
        self._painting = on

    async def _do_lift(self, m) -> bool:
        self.canvas.set_code_brush(not self.canvas._code_brush_down)
        return True

    async def _do_pen_up(self, m) -> bool:
        self.canvas.set_code_brush(False)
        return True

    async def _do_pen_down(self, m) -> bool:
        self.canvas.set_code_brush(True)
        return True


class ArtRoom(Room):
    """Cells are (char, fg, bg); a painted cell holds BRUSH_CHAR with both
    colors equal, a written letter holds the letter over whatever bg it had."""

    name, label, icon = "art", "Art", ICON_PALETTE
    LANDSCAPE = True
    has_code_panel = True
    wheel_ready = True
    canvas_width = COLS
    canvas_height = ROWS
    _TURN_RIGHT = {'right': 'down', 'down': 'left', 'left': 'up', 'up': 'right'}
    _TURN_LEFT = {'right': 'up', 'up': 'left', 'left': 'down', 'down': 'right'}

    def __init__(self, app):
        super().__init__(app)
        self._run_end = None            # (way, cursor) after a code run, to turn straight back from
        self._grid: dict = {}
        self._painted_positions: set = set()
        self._last_paint_pos = None
        self._cursor_x = self._cursor_y = 0
        self._paint_mode = True
        self._last_key_color = DEFAULT_BRUSH_COLOR
        self._last_key_char = ""
        self._mix = color_recipe.NO_MIX   # (keycaps, color) of the last chord
        self._mixed = None                # (keycaps, color) of the last dab that mixed
        self._ink = None              # ABC letters' color from the wheel; None: light, or black/white over paint
        self._wheel_spots = {}        # per mode
        self._pen_down = False
        self._lift = 1.0              # the brush's height: 1 up, 0 pressed down; eases on Space
        self._lift_timer = None
        self._pen_at_press = self._dragged = False   # holding Space while moving lowers the brush until release
        self._code_mode = False
        self._code_brush_down = True  # code's brush, apart from Space's pen
        self._heading = "right"
        self._use_heading_cursor = False
        self._post_stamp_x = None
        self._wrap_at = None            # a right-edge cell just stamped: the next stamp starts the next line
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._backspace_since = None    # when a held Backspace went down
        self._fade = None               # {"cells", "row", "since"}: the line a held Backspace is taking
        self._fade_timer = None
        self._tips = _Cache()
        self.echo = Echo()
        self.code_panel = None
        self._cell = 10
        self._origin = (0, 0)
        self._surf = None            # cached canvas: cells are repainted only when they change
        self._dirty = None           # None = repaint everything, else a set of (x, y)

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        self._post_paint_mode_changed()

    def on_leave(self):
        self.code_panel = None
        self._stop_fade()

    @property
    def paint_mode(self) -> bool:
        return self._paint_mode

    @property
    def is_painting(self) -> bool:
        return self._paint_mode

    def set_pen(self, down: bool):
        self._set_pen(down)

    def refresh(self):
        self.app.invalidate()

    def _mark_cursor_dirty(self):
        pass

    @property
    def brush_color(self) -> str:
        """In ABC the wheel's 'brush' is the letters' ink."""
        return self._last_key_color if self._paint_mode else self._ink or AUTO

    def set_brush_color(self, color: str, key: str = ""):
        if self._paint_mode:
            self._last_key_char, self._last_key_color = key, color
        else:
            self._ink = None if color == AUTO else color
        self._post_paint_mode_changed()

    @property
    def wheel_auto(self) -> bool:
        return not self._paint_mode

    @property
    def wheel_spot(self):
        return self._wheel_spots.get(self._paint_mode)

    @wheel_spot.setter
    def wheel_spot(self, spot):
        self._wheel_spots[self._paint_mode] = spot

    def _post_paint_mode_changed(self):
        self.app.set_legend(self._last_key_color if self._paint_mode else None, visible=True)
        self.app.invalidate()

    def arrow_hint(self) -> str:
        return MOVE_HINT

    def cursor_fraction(self, vp):
        return ((self._origin[0] + self._cursor_x * self._cell - vp.x) / vp.w,
                (self._origin[1] + self._cursor_y * self._cell - vp.y) / vp.h)

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        state = {f"c:{x},{y}": [ch, fg, bg, 1 if (x, y) in self._painted_positions else 0]
                 for (x, y), (ch, fg, bg) in self._grid.items()}
        state.update(cursor=[self._cursor_x, self._cursor_y], paint=self._paint_mode, color=self._last_key_color,
                     ink=self._ink)
        return state

    def restore_timeline_state(self, state: dict):
        self._stop_fade()
        self._grid.clear()
        self._painted_positions.clear()
        self._last_paint_pos = self._mixed = None
        for key, val in state.items():
            if key.startswith("c:"):
                x, y = (int(n) for n in key[2:].split(","))
                self._grid[(x, y)] = (val[0], val[1], val[2])
                if val[3]:
                    self._painted_positions.add((x, y))
        self._repaint_all()
        self._cursor_x, self._cursor_y = state.get("cursor", [0, 0])
        self._wrap_at = None
        self._paint_mode = bool(state.get("paint", True))
        self._set_pen(False)
        self._last_key_color = state.get("color", DEFAULT_BRUSH_COLOR)
        self._ink = state.get("ink")
        self.echo.reset()
        self._post_paint_mode_changed()

    def clear(self):
        self._stop_fade()
        self._grid.clear()
        self._repaint_all()
        self._painted_positions.clear()
        self._last_paint_pos = self._mixed = None
        self._cursor_x = self._cursor_y = 0
        self._paint_mode = True
        self._set_pen(False)
        self._code_mode = False
        self._heading = "right"
        self._use_heading_cursor = False
        self._last_key_color = DEFAULT_BRUSH_COLOR
        self._ink = None
        self.echo.reset()
        self._post_paint_mode_changed()

    def has_content(self) -> bool:
        return bool(self._grid)

    # ---------------------------------------------------------------- cell ops
    def _get_cell_bg(self, pos) -> str:
        cell = self._grid.get(pos)
        return cell[2] if cell else CANVAS_BG

    def _set_cell(self, pos, char, fg, bg):
        self._grid[pos] = (char, fg, bg)
        self._touch(pos)

    def _del_cell(self, pos):
        if self._grid.pop(pos, None) is not None:
            self._touch(pos)

    def _erase(self, pos):
        self._del_cell(pos)
        self._painted_positions.discard(pos)
        if pos == self._last_paint_pos:
            self._last_paint_pos = None

    def _touch(self, pos):
        if self._dirty is not None:
            self._dirty.add(pos)

    def _repaint_all(self):
        self._dirty = None

    def _paint_at_cursor(self):
        self._paint_at((self._cursor_x, self._cursor_y))

    def _paint_at(self, pos):
        cell = self._grid.get(pos)
        under = self._get_cell_bg(pos) if pos in self._painted_positions else None
        self._mixed = color_recipe.dab(under, self._mix, (self._last_key_char, self._last_key_color))
        color = self._mixed[1] if self._mixed else self._last_key_color
        self._painted_positions.add(pos)
        self._last_paint_pos = pos
        if cell and cell[0] not in ("", " ", BRUSH_CHAR):
            self._set_cell(pos, cell[0], auto_ink(color), color)
        else:
            self._set_cell(pos, BRUSH_CHAR, color, color)
        self.app.invalidate()

    def _set_paint_mode(self, painting: bool):
        if self._paint_mode == painting:
            return
        self._paint_mode = painting
        self._set_pen(False)
        self._post_paint_mode_changed()

    def _toggle_paint_mode(self):
        self._set_paint_mode(not self._paint_mode)

    def _set_pen(self, down: bool):
        if self._pen_down == down:
            return
        self._pen_down = down
        if down:
            self._paint_at_cursor()
        self._ease_lift()
        self._post_paint_mode_changed()

    def set_code_brush(self, down: bool):
        self._code_brush_down = down
        self._ease_lift()

    def _ease_lift(self):
        if self._lift_timer is None:
            self._lift_timer = self.app.timers.every(LIFT_FRAME, self._step_lift)

    def _step_lift(self):
        target = 0.0 if (self._code_brush_down if self._code_mode else self._pen_down) else 1.0
        self._lift = target if abs(target - self._lift) <= LIFT_STEP else self._lift + math.copysign(LIFT_STEP, target - self._lift)
        if self._lift == target:
            self._lift_timer.stop()
            self._lift_timer = None
        self.app.invalidate()

    def set_code_mode(self, on: bool):
        self._code_mode = on
        self._use_heading_cursor = on
        if on:
            self._heading = "right"
            self._code_brush_down = True
        self._ease_lift()
        self.app.invalidate()

    def _move_in_direction(self, direction: str, wrap: bool = False) -> bool:
        dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}.get(direction, (0, 0))
        spot = onto_grid(self._cursor_x + dx, self._cursor_y + dy, COLS, ROWS, wrap)
        if spot:
            self._cursor_x, self._cursor_y = spot
        return bool(spot)

    def _advance_after_stamp(self, direction: str):
        """On past a typed or stamped cell. At the right edge the brush stays in view
        until the next stamp, which wraps like lines of text."""
        self._post_stamp_x = self._cursor_x
        if direction == "right" and self._cursor_x >= COLS - 1:
            self._wrap_at = (self._cursor_x, self._cursor_y)
        else:
            self._move_in_direction(direction, wrap=True)

    def execute_logo_command(self, action: str, direction: str, distance: int):
        back = self._TURN_RIGHT[self._TURN_RIGHT[direction]]
        if distance and self._run_end == (back, self._cursor_x, self._cursor_y):
            self._move_in_direction(direction, wrap=True)    # turning straight back starts on the run's last cell
        self._run_end = None
        for _ in range(distance):
            if action == "paint":
                self._paint_at_cursor()
            self._move_in_direction(direction, wrap=True)    # as tapped arrows do, so echoed strokes replay whole
        if action == "paint" and distance:
            self._run_end = (direction, self._cursor_x, self._cursor_y)
        self.refresh()

    def turn(self, direction: str):
        if direction in ("left", "right", "up", "down"):
            self._heading = direction
        elif direction in ("spin", "rotate"):
            self._heading = self._TURN_RIGHT[self._heading]
        elif direction in ("back", "backward", "around"):
            self._heading = self._TURN_RIGHT[self._TURN_RIGHT[self._heading]]
        self._use_heading_cursor = True
        self.refresh()

    def _to_stamp_spot(self):
        if self._wrap_at == (self._cursor_x, self._cursor_y):
            self._new_line()

    def paint_char(self, char: str, direction: str = "right"):
        self._to_stamp_spot()
        self._last_key_char = char.lower()
        self._last_key_color = get_key_color(char)
        self._paint_at_cursor()
        self._advance_after_stamp(direction)

    def _letter_px(self, c: int) -> int:
        return max(6, round(c * 0.85))

    def _new_line(self):
        self._cursor_x = 0
        self._cursor_y = (self._cursor_y + 1) % ROWS

    def type_char(self, char: str, direction: str = "right"):
        self._to_stamp_spot()
        pos = (self._cursor_x, self._cursor_y)
        self._last_key_char = char
        self._last_key_color = get_key_color(char)
        bg = self._get_cell_bg(pos)
        self._set_cell(pos, char, self._ink or (auto_ink(bg) if pos in self._painted_positions else P.TEXT), bg)
        self._advance_after_stamp(direction)
        self.app.invalidate()

    def _backspace(self, just_stamped: bool = False):
        """Erase the square under the brush, like a spreadsheet cell. Right after typing or stamping,
        or on an empty square, first back one cell, or up to the last thing on the line above."""
        waiting, self._wrap_at = self._wrap_at == (self._cursor_x, self._cursor_y), None
        if (just_stamped and not waiting) or (self._cursor_x, self._cursor_y) not in self._grid:
            if self._cursor_x > 0:
                self._cursor_x -= 1
            elif self._cursor_y > 0:
                self._cursor_y -= 1
                self._cursor_x = max((x for x, y in self._grid if y == self._cursor_y), default=0)
        self._erase((self._cursor_x, self._cursor_y))
        self.app.invalidate()

    def _hold_backspace(self, repeat: bool, just_stamped: bool):
        """Squares one at a time, then after LINES_AFTER whole lines, the way Write takes letters then words."""
        now = time.monotonic()
        if not repeat or self._backspace_since is None:
            self._backspace_since = now
            self._backspace(just_stamped)
        elif now - self._backspace_since < LINES_AFTER:
            self._backspace()
        elif self._fade is None:
            self._fade_next_line()

    def _fade_next_line(self):
        """Start fading what's left of the cursor's line up to it, else the nearest line above with anything on it."""
        x0, y0 = self._cursor_x, self._cursor_y
        ahead = [(x, y) for x, y in self._grid if y < y0 or (y == y0 and x <= x0)]
        if not ahead:
            return
        row = max(y for _, y in ahead)
        self._fade = {"cells": {p for p in ahead if p[1] == row}, "row": row, "since": time.monotonic(),
                      "right": x0 + 1 if row == y0 else COLS}
        if self._fade_timer is None:
            self._fade_timer = self.app.timers.every(1 / 30, self._step_fade)

    def _step_fade(self):
        fade = self._fade
        if fade is None:
            return self._stop_fade()
        for pos in fade["cells"]:
            self._touch(pos)
        if time.monotonic() - fade["since"] >= LINE_FADE_S:
            for pos in fade["cells"]:
                self._erase(pos)
            self._cursor_x, self._cursor_y = 0, fade["row"]
            self._fade = None
            self._fade_next_line()      # still held: on to the next line straight away
            if self._fade is None:
                self._stop_fade()
        self.app.invalidate()

    def _stop_fade(self):
        """Letting go mid-fade brings the line back."""
        if self._fade is not None:
            for pos in self._fade["cells"]:
                self._touch(pos)
        self._fade = None
        if self._fade_timer is not None:
            self._fade_timer.stop()
            self._fade_timer = None
        self.app.invalidate()

    def _faded(self, pos) -> float:
        fade = self._fade
        return min(1.0, (time.monotonic() - fade["since"]) / LINE_FADE_S) if fade and pos in fade["cells"] else 0.0

    def _paint_stroke(self, direction: str):
        """One cell of an arrow trail, written down as code too."""
        self._paint_at_cursor()
        self.echo.color(self._last_key_color)
        self.echo.step(direction)

    def set_cursor_position(self, x: int, y: int):
        self._cursor_x = max(0, min(x, COLS - 1))
        self._cursor_y = max(0, min(y, ROWS - 1))
        self.app.invalidate()

    def paint_at(self, x: int, y: int, color_key: str):
        """Paint one cell by key char or '#rrggbb' (Secret Menu pictures)."""
        self._cursor_x, self._cursor_y = max(0, min(x, COLS - 1)), max(0, min(y, ROWS - 1))
        k = color_key.lower()
        brush = brush_for_key(k)
        if k.startswith("#"):
            self._last_key_color = k
        elif brush:
            self._last_key_char, self._last_key_color = brush
        self._paint_at_cursor()

    def write_at(self, x: int, y: int, char: str, ink: str):
        """Write one letter in that ink over whatever is painted there (pack pictures)."""
        pos = (x, y)
        self._set_cell(pos, char, ink, self._get_cell_bg(pos))

    def picture(self) -> tuple[list, list]:
        """The canvas as a pack picture: its painted cells' colors, and its letters in their inks."""
        cells = sorted(self._grid.items())
        return ([[x, y, bg] for (x, y), (_, _, bg) in cells if (x, y) in self._painted_positions],
                [[x, y, ch, fg] for (x, y), (ch, fg, _) in cells if ch not in ("", " ", BRUSH_CHAR)])

    def _chord_brush(self, held_key: str, char: str) -> bool:
        """A key pressed while another color key is down: the brush becomes the
        held brush mixed with this key's color. Holding on, each next key mixes in too."""
        brush = brush_for_key(char)
        if not brush or not self._select_brush(held_key, hold=True):
            return False
        self._mix = color_recipe.chord(self._mix, (self._last_key_char, self._last_key_color), brush)
        self.set_brush_color(self._mix[1], brush[0])
        return True

    def _select_brush(self, char: str, hold: bool = False) -> bool:
        """Set the brush from a key; False when the key has no color. With
        `hold`, a key still down keeps its brush, so a chord's mix keeps going."""
        brush = brush_for_key(char)
        if brush and not (hold and brush[0] == self._last_key_char):
            self.set_brush_color(brush[1], brush[0])
        return bool(brush)

    # ---------------------------------------------------------------- code panel
    def open_code_panel(self):
        if self.code_panel is None and self.app._code_panel_enabled:
            self._set_pen(False)
            self.code_panel = CodePanel(self.app, "art", self.echo.take())
            self.set_code_mode(True)
            self.app.set_panel(self.code_panel)

    def close_code_panel(self):
        if self.code_panel is not None:
            self.code_panel = None
            self.set_code_mode(False)
            self.app.set_panel(None)

    async def run_code(self, lines: list):
        try:
            runner = _RoomBrushRunner(self)
            await runner.run(lines, paint=self._paint_mode)
            self._post_paint_mode_changed()
            if runner.corrections and self.code_panel:
                self.code_panel.set_correction(*runner.corrections[-1])
        except Exception as exc:
            if isinstance(exc, __import__("asyncio").CancelledError):
                raise
        self.app.invalidate()

    # ---------------------------------------------------------------- input
    def _space(self, arrow_held):
        if self._paint_mode:
            self._set_pen(not self._pen_down)
            if self._pen_down and arrow_held:
                self._advance_after_stamp(arrow_held)
            elif not self._pen_down:
                self.echo.flush()
        else:
            self.type_char(" ")
            self.echo.letter("write", " ")
        self.app.invalidate()

    def _space_press(self, down: bool):
        if down:
            self._pen_at_press, self._dragged = self._pen_down, False
        elif self._dragged and not self._pen_at_press:
            self._set_pen(False)
            self.echo.flush()

    async def handle(self, action):
        if self._fade and not (isinstance(action, ControlAction) and action.action == "backspace"):
            self._stop_fade()
        if isinstance(action, ControlAction) and action.action == "space":
            if not action.is_repeat:
                self._space_press(action.is_down)
        if self.code_panel is not None:
            result = await self.code_panel.handle(action)
            if result == "tab_fallthrough":
                self._toggle_paint_mode()
            elif result == "close":
                self.close_code_panel()
            return
        prior_post_stamp_x = self._post_stamp_x
        self._post_stamp_x = None
        if isinstance(action, ControlAction):
            if not action.is_down:
                if action.action == "backspace":
                    self._backspace_since = None
                    self._stop_fade()
                return
            a = action.action
            if a in ("tab", "backspace") or (a == "enter" and not self._paint_mode):
                self.echo.flush()
            if a == "space":
                if not (self._paint_mode and action.is_repeat):
                    self._space(action.arrow_held)
            elif a == "tab":
                self._toggle_paint_mode()
            elif a == "enter":
                if self._paint_mode:
                    self._post_stamp_x = prior_post_stamp_x
                    await self.handle(NavigationAction(direction="down", is_repeat=action.is_repeat))
                elif not action.is_repeat:
                    self._new_line()
                    self.app.invalidate()
            elif a == "backspace":
                self._hold_backspace(action.is_repeat, prior_post_stamp_x is not None)
            return
        if isinstance(action, NavigationAction):
            self._navigate(action, prior_post_stamp_x)
            return
        if isinstance(action, CharacterAction):
            char = action.char
            direction = action.arrow_held or "right"
            if self._paint_mode and action.with_shift and char in UNSHIFT_MAP:
                char = UNSHIFT_MAP[char]
            if open_color_wheel(self, char):
                return
            if not self._paint_mode:
                self.type_char(char)
                self.echo.letter("write", char)
                return
            chord = bool(action.char_held) and not action.with_shift and self._chord_brush(action.char_held, char)
            if (chord or self._select_brush(char, hold=action.is_repeat)) and not action.with_shift:
                self._to_stamp_spot()
                self._paint_at_cursor()
                self._advance_after_stamp(direction)
                if char.isalpha():
                    self.echo.letter(direction, char)
                else:
                    self.echo.flush()   # a digit would read as a distance
            self.app.invalidate()

    def _navigate(self, action, prior_post_stamp_x):
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        if self._paint_mode and action.char_held:
            self._select_brush(action.char_held, hold=True)
            if self._arrow_repeat_count == 0 or (self._cursor_x, self._cursor_y) != self._last_paint_pos:
                self._paint_at_cursor()
        if action.direction in ("up", "down") and prior_post_stamp_x is not None and not action.char_held:
            self._cursor_x = prior_post_stamp_x
        if self._paint_mode and action.space_held:
            self._dragged = True
            self._set_pen(True)
        trail = self._paint_mode and (self._pen_down or bool(action.char_held))
        if not trail:
            self.echo.flush()
        steps = HOLD_ACCEL_MULTIPLIER if (not trail and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD) else 1
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(steps):
                if not self._move_in_direction(direction, wrap=not action.is_repeat):
                    break
                if trail:
                    self._paint_stroke(direction)
        self.app.invalidate()

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        """The mode switch hugs the top edge and the hint the bottom, a touch in
        from the border; the grid fills what is left. A bottom panel takes the
        hint row instead."""
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = 0 if self.app._panel is not None else hint_row_h(g)
        status_h = status_row_h(g) if self.code_panel is not None else 0
        area = inner.inflate(0, -2 * (chrome_h + gap))
        if status_h:
            area.y, area.h = area.y + status_h, area.h - status_h
            draw_status_row(g, pygame.Rect(inner.x, inner.y, inner.w, status_h), self._code_status(g))
        c = self._cell = max(3, min(area.w // COLS, area.h // ROWS))
        ox = area.x + (area.w - c * COLS) // 2
        oy = area.y + (area.h - c * ROWS) // 2
        self._origin = (ox, oy)
        if chrome_h:
            self._draw_header(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h))
        g.surface.blit(self._canvas_surface(g, c), (ox, oy))
        self._draw_letters(g, ox, oy, c)
        self._draw_fade_wash(g, ox, oy, c)
        self._draw_cursor(g, ox, oy, c)
        held = chrome_h and self._paint_mode and self._last_paint_pos and color_recipe.held_key(self.app, self._last_key_char)
        if held:
            x, y = self._last_paint_pos
            cell = pygame.Rect(ox + x * c, oy + y * c, c, c)
            color_recipe.draw_hold_badge(g, held, g.vh(1.9), cell, pygame.Rect(ox, oy, c * COLS, c * ROWS))
        if chrome_h:
            foot = pygame.Rect(inner.x, inner.bottom - chrome_h, inner.w, chrome_h)
            key = "littles" if self.app._littles_mode else self._hint_key()
            draw_key_hint(g, HINTS[key], g.vh(1.9), foot.x, foot.centery)
            if not self.app._littles_mode:
                color_recipe.draw_foot_right(g, foot, self.app._code_panel_enabled,
                                           self._paint_mode and color_recipe.hint_row(self._last_key_char, self._mixed))

    def _hint_key(self) -> str:
        if self._paint_mode and self.app._keyboard_state_machine.sticky_shift:
            return "pick"
        if self._paint_mode:
            return "pen" if self._pen_down else "paint"
        return "write"

    def _canvas_surface(self, g, c):
        """The cells as one surface; only cells that changed since the last
        frame are repainted, so a keystroke costs a cell, not a canvas."""
        if self._surf is None or self._surf.get_width() != c * COLS or self._surf.get_height() != c * ROWS:
            self._surf = pygame.Surface((c * COLS, c * ROWS))
            self._dirty = None
        cells = [(x, y) for x in range(COLS) for y in range(ROWS)] if self._dirty is None else self._dirty
        for x, y in list(cells):
            if not (0 <= x < COLS and 0 <= y < ROWS):
                continue
            cell = self._grid.get((x, y))
            ground = self._ground(x, y)
            self._surf.fill(mix(cell[2] if self._painted(cell) else ground, ground, self._faded((x, y))), (x * c, y * c, c, c))
        self._dirty = set()
        return self._surf

    @staticmethod
    def _painted(cell) -> bool:
        return bool(cell) and (cell[2] != CANVAS_BG or cell[0] == BRUSH_CHAR)

    def paper(self, g, size, on_screen=False):
        """The picture for printing: paint and letters, unpainted cells left white (or the checkerboard on screen)."""
        if not self.has_content():
            return None
        c = min(size[0] // COLS, size[1] // ROWS)
        s = paper.blank((c * COLS, c * ROWS))
        for x in range(COLS):
            for y in range(ROWS):
                cell = self._grid.get((x, y))
                if self._painted(cell) or on_screen:
                    s.fill(rgb(cell[2] if self._painted(cell) else self._ground(x, y)), (x * c, y * c, c, c))
        with g.drawing_on(s):
            self._draw_letters(g, 0, 0, c, on_paper=not on_screen)
        return s

    @staticmethod
    def _ground(x: int, y: int) -> str:
        """Unpainted cells alternate two near-identical purples: a checkerboard
        shows the grid without lines."""
        return CANVAS_ALT if (x + y) % 2 else CANVAS_BG

    def _draw_letters(self, g, ox, oy, c, on_paper=False):
        """On paper a pale letter on an unpainted cell would vanish into the white, so it prints in ink."""
        px = self._letter_px(c)
        for (x, y), (ch, fg, _bg) in self._grid.items():
            if ch not in ("", " ", BRUSH_CHAR) and 0 <= x < COLS and 0 <= y < ROWS:
                if on_paper and not self._painted(self._grid[(x, y)]) and P.luminance(fg) > 0.5:
                    fg = paper.INK
                elif not on_paper and self._faded((x, y)):
                    fg = hexcolor(mix(fg, self._ground(x, y), self._faded((x, y))))
                g.draw_text(ch, px, ox + x * c + c // 2, oy + y * c + c // 2, "block", fg, anchor="center")

    def _draw_fade_wash(self, g, ox, oy, c):
        """A flash over the whole line being taken that fades with it, so a line with one square still shows."""
        if self._fade is None:
            return
        t = min(1.0, (time.monotonic() - self._fade["since"]) / LINE_FADE_S)
        band = pygame.Surface((self._fade["right"] * c, c))
        band.fill(rgb(P.TEXT))
        band.set_alpha(round(170 * (1 - t) ** 2))
        g.surface.blit(band, (ox, oy + self._fade["row"] * c))

    def _draw_cursor(self, g, ox, oy, c):
        x, y = ox + self._cursor_x * c, oy + self._cursor_y * c
        if not self._paint_mode:  # underline caret: the next letter lands in this cell
            bar = (x, y + c - max(2, c // 4), c, max(2, c // 4))
            g.draw_caret(bar, lambda: g.rect(P.ACCENT, bar))
        tip = "brush" if self._paint_mode else None
        turn = HEADING_TURNS[self._heading] if self._use_heading_cursor else None
        if tip or turn is not None:
            key = (c, self._last_key_color, tip, turn, round(self._lift, 2))
            sprite = self._tips.get_or(key, lambda: _brush_tip(*key))
            g.surface.blit(sprite, sprite.get_rect(center=(x + c // 2, y + c // 2)))

    def _code_status(self, g) -> tuple:
        """What code can change, in its own words: paint, write, color, brush."""
        dot = swatch_dot(self.brush_color, status_row_px(g))
        if not self._paint_mode:
            return ((dot, "Write"),)
        return (dot, "Paint"), (None, "Brush down" if self._code_brush_down else "Brush up")

    def _draw_header(self, g, r):
        """The Tab switch between Paint and ABC, with the brush beside it."""
        if self.app._littles_mode:
            draw_label(g, "Paint" if self._paint_mode else "Write", g.vh(1.9), r.centerx, r.centery, P.TEXT, anchor="center")
            return
        icon = self._tips.get_or(("icon", r.h, self._last_key_color, self._lift), lambda: _brush_icon(r.h, self._last_key_color, self._lift)) if self._paint_mode else None
        draw_mode_switch(g, r, ("Paint", "ABC"), 0 if self._paint_mode else 1, self.brush_color,
                         icon, wheel_chip(self))
