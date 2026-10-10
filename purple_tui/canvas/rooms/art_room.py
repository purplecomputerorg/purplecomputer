"""Art room: a grid of square cells. Every letter paints its sticker color,
Backslash opens the color wheel, Space puts the pen down so arrows draw,
holding Backspace makes arrows erase, Tab switches to writing letters, and
hold Space opens the Logo-style code line."""

import time

import pygame

from ... import palette as P
from ...code_runner import ArtCodeRunner
from ...constants import ICON_PALETTE, ICON_ROBOT
from ...color_mixing import mix_colors_paint
from ..gfx import _Cache, rgb
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from .. import paper
from ...palette import DEFAULT_BRUSH_COLOR, GRAYSCALE, KEY_COLORS, UNMAPPED, get_key_color
from ..color_wheel import open_on as open_color_wheel
from ..panels import CodePanel, SpaceHold
from ..ui import draw_label, draw_mode_switch
from .base import Room

COLS, ROWS = 56, 24
BRUSH_CHAR = "█"
ARROW_HOLD_REPEAT_THRESHOLD = 8
HOLD_ACCEL_MULTIPLIER = 6
CANVAS_BG = "#221440"
CANVAS_ALT = "#281a4a"               # checkerboard partner of CANVAS_BG
TIP_EDGE = "#120a24"                # dark rim so the brush tip reads on any paint, even its own color
HEADING_TURNS = {"right": 0, "up": 90, "left": 180, "down": -90}
HINTS = {
    "littles": "Type to paint!",
    "pen": "Pen is down! Arrows paint a trail. Space lifts the pen.",
    "erase": "Erasing! Arrows clear a trail.",
    "paint": "Type to paint! Every letter is a color. Space puts the pen down.",
    "write": "Type to write! Arrow keys move. Enter for a new line.",
}


def _contrast_text_color(bg_hex: str) -> str:
    """Black on light paint, white on dark: the simple perceptual split the
    canvas has always used for letters over paint."""
    r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5 else "#FFFFFF"


def brush_for_key(char: str):
    """(key, color) for a key that has a sticker or gray color, else None."""
    k = char.lower()
    if k in GRAYSCALE:
        return k, GRAYSCALE[k]
    if (k.isalpha() or k in KEY_COLORS) and get_key_color(k) != UNMAPPED:
        return k, get_key_color(k)
    return None


def _brush_tip(c: int, color: str, tip, arrow: bool) -> pygame.Surface:
    """A 2c square centered on the cursor cell, drawn 4x and smoothed down:
    tip is "ring" (pen up), "dot" (pen down), "erase" (a hollow square over
    the cell) or None; arrow adds a chevron pointing right."""
    s = 4
    size, mid = 2 * c * s, c * s
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    r = round(c * s * (0.42 if tip == "dot" else 0.38))
    edge = max(s, round(c * s * 0.05))
    band = max(2 * s, round(c * s * 0.13))
    if tip == "ring":
        pygame.draw.circle(surf, rgb(TIP_EDGE), (mid, mid), r + edge, band + 2 * edge)
        pygame.draw.circle(surf, rgb(color), (mid, mid), r, band)
    elif tip == "dot":
        pygame.draw.circle(surf, rgb(TIP_EDGE), (mid, mid), r + edge)
        pygame.draw.circle(surf, rgb(P.TEXT), (mid, mid), r)
        pygame.draw.circle(surf, rgb(color), (mid, mid), r - max(s, round(c * s * 0.08)))
    elif tip == "erase":
        box = pygame.Rect(0, 0, c * s, c * s)
        box.center = (mid, mid)
        pygame.draw.rect(surf, rgb(TIP_EDGE), box.inflate(2 * edge, 2 * edge), band + 2 * edge)
        pygame.draw.rect(surf, rgb(P.TEXT), box, band)
    if arrow:
        x0, h = mid + max(r, round(c * s * 0.42)) + edge, round(c * s * 0.24)
        tri = [(x0, mid - h), (x0 + round(h * 1.3), mid), (x0, mid + h)]
        pygame.draw.polygon(surf, rgb(color), tri)
        pygame.draw.polygon(surf, rgb(TIP_EDGE), tri, edge)
    return pygame.transform.smoothscale(surf, (2 * c, 2 * c))


class ArtRoom(Room):
    """Cells are (char, fg, bg); a painted cell holds BRUSH_CHAR with both
    colors equal, a written letter holds the letter over whatever bg it had."""

    name, label, icon = "art", "Art", ICON_PALETTE
    arrow_hint = "Arrows move  ← ↑ ↓ →"
    LANDSCAPE = True
    has_code_panel = True
    canvas_width = COLS
    canvas_height = ROWS
    _TURN_RIGHT = {'right': 'down', 'down': 'left', 'left': 'up', 'up': 'right'}
    _TURN_LEFT = {'right': 'up', 'up': 'left', 'left': 'down', 'down': 'right'}

    def __init__(self, app):
        super().__init__(app)
        self._grid: dict = {}
        self._painted_positions: set = set()
        self._last_paint_pos = None
        self._cursor_x = self._cursor_y = 0
        self._paint_mode = True
        self._last_key_color = DEFAULT_BRUSH_COLOR
        self._last_key_char = ""
        self._pen_down = False
        self._code_mode = False
        self._heading = "right"
        self._use_heading_cursor = False
        self._post_stamp_x = None
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._backspace_repeat_count = 0
        self._erasing = False         # Backspace held: arrows clear a trail
        self._blink_on = True
        self._blink_stamp = time.monotonic()
        self._blink_timer = None
        self._tips = _Cache()
        self.space = SpaceHold(app, self._space_tap, self._space_hold_fired)
        self.code_panel = None
        self._cell = 10
        self._origin = (0, 0)
        self._surf = None            # cached canvas: cells are repainted only when they change
        self._dirty = None           # None = repaint everything, else a set of (x, y)

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        self._post_paint_mode_changed()
        if self._blink_timer is None:
            self._blink_timer = self.app.timers.every(0.4, self._blink)

    def on_leave(self):
        self.code_panel = None
        self._erasing = False
        if self._blink_timer:
            self._blink_timer.stop()
            self._blink_timer = None

    def _blink(self):
        """Only the write caret blinks; the brush tip holds still."""
        if self._paint_mode or self.code_panel is not None:
            return
        self._blink_on = not self._blink_on
        self.app.invalidate()

    def _restart_blink(self):
        self._blink_on = True
        if self._blink_timer:
            self._blink_timer.reset()

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
        return self._last_key_color

    def set_brush_color(self, color: str, key: str = ""):
        self._last_key_char, self._last_key_color = key, color
        self._post_paint_mode_changed()

    def _post_paint_mode_changed(self):
        self.app.set_legend(self._last_key_color if self._paint_mode else None, visible=True)
        self.app.invalidate()

    def hold_progress(self):
        p = self.space.progress()
        return (p, "Code") if p is not None else None

    def cursor_fraction(self, vp):
        return ((self._origin[0] + self._cursor_x * self._cell - vp.x) / vp.w,
                (self._origin[1] + self._cursor_y * self._cell - vp.y) / vp.h)

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        state = {f"c:{x},{y}": [ch, fg, bg, 1 if (x, y) in self._painted_positions else 0]
                 for (x, y), (ch, fg, bg) in self._grid.items()}
        state.update(cursor=[self._cursor_x, self._cursor_y], paint=self._paint_mode, color=self._last_key_color)
        return state

    def restore_timeline_state(self, state: dict):
        self._grid.clear()
        self._painted_positions.clear()
        self._last_paint_pos = None
        for key, val in state.items():
            if key.startswith("c:"):
                x, y = (int(n) for n in key[2:].split(","))
                self._grid[(x, y)] = (val[0], val[1], val[2])
                if val[3]:
                    self._painted_positions.add((x, y))
        self._repaint_all()
        self._cursor_x, self._cursor_y = state.get("cursor", [0, 0])
        self._paint_mode = bool(state.get("paint", True))
        self._set_pen(False)
        self._last_key_color = state.get("color", DEFAULT_BRUSH_COLOR)
        self._post_paint_mode_changed()

    def clear(self):
        self._grid.clear()
        self._repaint_all()
        self._painted_positions.clear()
        self._last_paint_pos = None
        self._cursor_x = self._cursor_y = 0
        self._paint_mode = True
        self._set_pen(False)
        self._code_mode = False
        self._heading = "right"
        self._use_heading_cursor = False
        self._last_key_color = DEFAULT_BRUSH_COLOR
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

    def _touch(self, pos):
        if self._dirty is not None:
            self._dirty.add(pos)

    def _repaint_all(self):
        self._dirty = None

    def _paint_at_cursor(self):
        pos = (self._cursor_x, self._cursor_y)
        cell = self._grid.get(pos)
        color = mix_colors_paint([self._get_cell_bg(pos), self._last_key_color]) if pos in self._painted_positions else self._last_key_color
        self._painted_positions.add(pos)
        self._last_paint_pos = pos
        if cell and cell[0] not in ("", " ", BRUSH_CHAR):
            self._set_cell(pos, cell[0], _contrast_text_color(color), color)
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
        self._restart_blink()
        self._post_paint_mode_changed()

    def set_code_mode(self, on: bool):
        self._code_mode = on
        self._use_heading_cursor = on
        if on:
            self._heading = "right"
        self.app.invalidate()

    def _move_in_direction(self, direction: str) -> bool:
        dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}.get(direction, (0, 0))
        nx, ny = self._cursor_x + dx, self._cursor_y + dy
        if not (0 <= nx < COLS and 0 <= ny < ROWS):
            return False
        self._cursor_x, self._cursor_y = nx, ny
        return True

    def _carriage_return(self):
        self._cursor_x = 0
        self._cursor_y = (self._cursor_y + 1) % ROWS

    def _advance_after_stamp(self, direction: str):
        stamp_x = self._cursor_x
        if direction == "right" and self._cursor_x >= COLS - 1:
            self._carriage_return()
        else:
            self._move_in_direction(direction)
        self._post_stamp_x = stamp_x

    def execute_logo_command(self, action: str, direction: str, distance: int):
        for _ in range(distance):
            if action == "paint":
                self._paint_at_cursor()
            if not self._move_in_direction(direction):
                break
        self._restart_blink()
        self.refresh()

    def turn(self, direction: str):
        if direction in ("left", "right", "up", "down"):
            self._heading = direction
        elif direction in ("spin", "rotate"):
            self._heading = self._TURN_RIGHT[self._heading]
        elif direction in ("back", "backward", "around"):
            self._heading = self._TURN_RIGHT[self._TURN_RIGHT[self._heading]]
        self._use_heading_cursor = True
        self._restart_blink()
        self.refresh()

    def paint_char(self, char: str, direction: str = "right"):
        self._last_key_char = char.lower()
        self._last_key_color = get_key_color(char)
        self._paint_at_cursor()
        self._advance_after_stamp(direction)

    def _letter_px(self, c: int) -> int:
        return max(6, round(c * 0.8))

    def _new_line(self):
        self._cursor_x = 0
        self._cursor_y = min(ROWS - 1, self._cursor_y + 1)

    def type_char(self, char: str, direction: str = "right"):
        pos = (self._cursor_x, self._cursor_y)
        self._last_key_char = char
        self._last_key_color = get_key_color(char)
        bg = self._get_cell_bg(pos)
        self._set_cell(pos, char, _contrast_text_color(bg) if pos in self._painted_positions else P.TEXT, bg)
        self._post_stamp_x = self._cursor_x
        if direction == "right" and self._cursor_x >= COLS - 1:
            self._new_line()
        else:
            self._move_in_direction(direction)
        self._restart_blink()
        self.app.invalidate()

    def _backspace(self):
        if self._cursor_x > 0:
            self._cursor_x -= 1
        elif self._cursor_y > 0:
            self._cursor_y -= 1
            self._cursor_x = COLS - 1
        self._erase_at_cursor()

    def _erase_at_cursor(self):
        pos = (self._cursor_x, self._cursor_y)
        if pos in self._grid:
            self._del_cell(pos)
            self._painted_positions.discard(pos)
            if pos == self._last_paint_pos:
                self._last_paint_pos = None
        self.app.invalidate()

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

    def _select_brush(self, char: str) -> bool:
        """Set the brush from a key; False when the key has no color."""
        brush = brush_for_key(char)
        if brush:
            self.set_brush_color(brush[1], brush[0])
        return bool(brush)

    # ---------------------------------------------------------------- code panel
    def open_code_panel(self):
        if self.code_panel is None and self.app._code_panel_enabled:
            self._set_pen(False)
            self.code_panel = CodePanel(self.app, "art")
            self.set_code_mode(True)
            self.app.set_panel(self.code_panel)

    def close_code_panel(self):
        if self.code_panel is not None:
            self.code_panel = None
            self.set_code_mode(False)
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
            self._space(arrow_held=None)

    async def run_code(self, lines: list):
        try:
            runner = ArtCodeRunner(self)
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
        else:
            self.type_char(" ")
        self.app.invalidate()

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.action == "space" and self.space.route(action):
            return
        if self.code_panel is not None:
            self.space.other_key()
            result = await self.code_panel.handle(action)
            if result == "tab_fallthrough":
                self._toggle_paint_mode()
            elif result == "close":
                self.close_code_panel()
            return
        self.space.other_key()
        prior_post_stamp_x = self._post_stamp_x
        self._post_stamp_x = None
        if isinstance(action, ControlAction):
            if not action.is_down:
                if action.action == "backspace":
                    self._backspace_repeat_count = 0
                    self._erasing = False
                    self.app.invalidate()
                return
            a = action.action
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
                self._erasing = True
                self._backspace_repeat_count = self._backspace_repeat_count + 1 if action.is_repeat else 0
                for _ in range(HOLD_ACCEL_MULTIPLIER if self._backspace_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD else 1):
                    self._backspace()
            return
        if isinstance(action, NavigationAction):
            self._navigate(action, prior_post_stamp_x)
            return
        if isinstance(action, CharacterAction):
            self._backspace_repeat_count = 0
            char = action.char
            direction = action.arrow_held or "right"
            if not self._paint_mode:
                self.type_char(char)
                return
            if action.shift_held and char in UNSHIFT_MAP:
                char = UNSHIFT_MAP[char]
            if open_color_wheel(self, char):
                return
            if self._select_brush(char) and not action.shift_held:
                self._paint_at_cursor()
                self._advance_after_stamp(direction)
            self._restart_blink()
            self.app.invalidate()

    def _navigate(self, action, prior_post_stamp_x):
        if action.is_repeat and action.direction == self._arrow_repeat_dir:
            self._arrow_repeat_count += 1
        else:
            self._arrow_repeat_dir = action.direction
            self._arrow_repeat_count = 1 if action.is_repeat else 0
        if self._paint_mode and action.char_held and not self._erasing:
            self._select_brush(action.char_held)
            if self._arrow_repeat_count == 0 or (self._cursor_x, self._cursor_y) != self._last_paint_pos:
                self._paint_at_cursor()
        if action.direction in ("up", "down") and prior_post_stamp_x is not None and not action.char_held:
            self._cursor_x = prior_post_stamp_x
        paint_each_step = self._paint_mode and not self._erasing and (self._pen_down or bool(action.char_held))
        trail = self._erase_at_cursor if self._erasing else self._paint_at_cursor if paint_each_step else None
        steps = HOLD_ACCEL_MULTIPLIER if (not trail and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD) else 1
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(steps):
                if not self._move_in_direction(direction):
                    break
                if trail:
                    trail()
        self._restart_blink()
        self.app.invalidate()

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        """The mode switch hugs the top edge and the hint the bottom, a touch in
        from the border; the grid fills what is left. A bottom panel takes the
        hint row instead."""
        pad, gap = g.em(0.7), g.em(0.5)
        inner = rect.inflate(-2 * pad, -2 * pad)
        chrome_h = 0 if self.app._panel is not None else g.line_height(g.vh(1.9), "mono") + g.em(0.4)
        area = inner.inflate(0, -2 * (chrome_h + gap))
        c = self._cell = max(3, min(area.w // COLS, area.h // ROWS))
        ox = area.x + (area.w - c * COLS) // 2
        oy = area.y + (area.h - c * ROWS) // 2
        self._origin = (ox, oy)
        if chrome_h:
            self._draw_header(g, pygame.Rect(inner.x, inner.y, inner.w, chrome_h))
        g.surface.blit(self._canvas_surface(g, c), (ox, oy))
        self._draw_letters(g, ox, oy, c)
        self._draw_cursor(g, ox, oy, c)
        if chrome_h:
            foot = pygame.Rect(inner.x, inner.bottom - chrome_h, inner.w, chrome_h)
            key = "littles" if self.app._littles_mode else self._hint_key()
            g.draw_text(HINTS[key], g.vh(1.9), foot.x, foot.centery, "mono", P.DIM, anchor="midleft")
            if self.app._code_panel_enabled and not self.app._littles_mode:
                g.draw_text(f"{ICON_ROBOT} Hold Space: write code", g.vh(1.9), foot.right, foot.centery, "mono", P.DIM, anchor="midright")

    def _hint_key(self) -> str:
        if self._erasing:
            return "erase"
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
            self._surf.fill(rgb(cell[2] if self._painted(cell) else self._ground(x, y)), (x * c, y * c, c, c))
        self._dirty = set()
        return self._surf

    @staticmethod
    def _painted(cell) -> bool:
        return bool(cell) and (cell[2] != CANVAS_BG or cell[0] == BRUSH_CHAR)

    def paper(self, g, size):
        """The picture for printing: paint and letters, unpainted cells left white."""
        if not self.has_content():
            return None
        c = min(size[0] // COLS, size[1] // ROWS)
        s = paper.blank((c * COLS, c * ROWS))
        for (x, y), cell in self._grid.items():
            if 0 <= x < COLS and 0 <= y < ROWS and self._painted(cell):
                s.fill(rgb(cell[2]), (x * c, y * c, c, c))
        with g.drawing_on(s):
            self._draw_letters(g, 0, 0, c, on_paper=True)
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
                g.draw_text(ch, px, ox + x * c + c // 2, oy + y * c + c // 2, "block", fg, anchor="center")

    def _draw_cursor(self, g, ox, oy, c):
        x, y = ox + self._cursor_x * c, oy + self._cursor_y * c
        if not self._paint_mode and self._blink_on:  # underline caret: the next letter lands in this cell
            bar = max(2, c // 4)
            g.rect(P.ACCENT, (x, y + c - bar, c, bar))
        tip = "erase" if self._erasing else ("dot" if self._pen_down else "ring") if self._paint_mode else None
        heading = self._heading if self._use_heading_cursor else None
        if tip or heading:
            color = self._last_key_color if self._paint_mode else P.TEXT
            key = (c, color, tip, heading)
            sprite = self._tips.get_or(key, lambda: pygame.transform.rotate(_brush_tip(c, color, tip, bool(heading)), HEADING_TURNS.get(heading, 0)))
            g.surface.blit(sprite, sprite.get_rect(center=(x + c // 2, y + c // 2)))

    def _draw_header(self, g, r):
        """PAINT / ABC mode switch (active one in inverse video) with the brush
        color as a swatch beside it, and the Tab keycap on the right."""
        if self.app._littles_mode:
            draw_label(g, "Paint" if self._paint_mode else "Write", g.vh(1.9), r.centerx, r.centery, P.TEXT, anchor="center")
            return
        draw_mode_switch(g, r, ("Paint", "ABC"), 0 if self._paint_mode else 1, self._last_key_color,
                         "to write" if self._paint_mode else "to paint")
