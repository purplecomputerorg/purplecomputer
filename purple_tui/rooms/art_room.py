"""Art room: a grid of square cells. Every letter paints its sticker color,
Space puts the pen down so arrows draw, Tab switches to writing letters, and
hold Space opens the Logo-style code line."""

import time

import pygame

from .. import palette as P
from ..code_runner import ArtCodeRunner
from ..color_mixing import mix_colors_paint
from ..gfx import contrast_text, luminance, mix, rgb
from ..keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ..palette import DEFAULT_BRUSH_COLOR, GRAYSCALE, KEY_COLORS, UNMAPPED, get_key_color
from ..panels import CodePanel, SpaceHold

COLS, ROWS = 64, 36
LETTER_ROWS = 2                      # written letters stand two cells tall
BRUSH_CHAR = "█"
ARROW_HOLD_REPEAT_THRESHOLD = 8
HOLD_ACCEL_MULTIPLIER = 6
CANVAS_BG = "#221440"
HEADING_ARROWS = {"right": "▶", "left": "◀", "up": "▲", "down": "▼"}
HINTS = {
    "littles": "Type to paint!",
    "pen": "Pen is down! Arrows paint a trail. Space lifts the pen.",
    "paint": "Type to paint! Every letter is a color. Space puts the pen down.",
    "write": "Type to write! Arrow keys move. Enter for a new line.",
}


def _contrast_text_color(bg_hex: str) -> str:
    """Black on light paint, white on dark: the simple perceptual split the
    canvas has always used for letters over paint."""
    r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5 else "#FFFFFF"


def _visible_arrow_color(fg_hex: str, bg_hex: str) -> str:
    return fg_hex if abs(luminance(fg_hex) - luminance(bg_hex)) >= 0.25 else contrast_text(bg_hex)


class ArtRoom:
    """Cells are (char, fg, bg); a painted cell holds BRUSH_CHAR with both
    colors equal, a written letter holds the letter over whatever bg it had."""

    name = "art"
    canvas_width = COLS
    canvas_height = ROWS
    _TURN_RIGHT = {'right': 'down', 'down': 'left', 'left': 'up', 'up': 'right'}
    _TURN_LEFT = {'right': 'up', 'up': 'left', 'left': 'down', 'down': 'right'}

    def __init__(self, app):
        self.app = app
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
        self._line_start = 0          # write mode: where Enter returns to
        self._arrow_repeat_dir = None
        self._arrow_repeat_count = 0
        self._backspace_repeat_count = 0
        self._blink_on = True
        self._blink_stamp = time.monotonic()
        self._blink_timer = None
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
        if self._blink_timer:
            self._blink_timer.stop()
            self._blink_timer = None

    def stop_sound(self):
        pass

    def _blink(self):
        if self._pen_down or self.code_panel is not None:
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

    def _post_paint_mode_changed(self):
        self.app.set_legend(self._last_key_color if self._paint_mode else None, visible=True)
        self.app.invalidate()

    def hold_progress(self):
        p = self.space.progress()
        return (p, "code") if p is not None else None

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
        if not self._paint_mode:
            self._line_start = self._cursor_x

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
        return max(8, int(c * LETTER_ROWS * 0.95))

    def _advance_for(self, char: str) -> int:
        """Cells a written letter takes: its measured width, at least one."""
        if char == " ":
            return 1
        w = self.app.g.measure(char, self._letter_px(self._cell), "sans-heavy")[0]
        return max(1, round(w / self._cell + 0.15))

    def type_char(self, char: str, direction: str = "right"):
        adv = self._advance_for(char)
        if direction == "right" and self._cursor_x > COLS - adv:
            self._cursor_x = self._line_start
            self._cursor_y = min(ROWS - LETTER_ROWS, self._cursor_y + LETTER_ROWS)
        pos = (self._cursor_x, self._cursor_y)
        self._last_key_char = char
        self._last_key_color = get_key_color(char)
        bg = self._get_cell_bg(pos)
        self._set_cell(pos, char, _contrast_text_color(bg) if pos in self._painted_positions else P.TEXT, bg)
        self._post_stamp_x = self._cursor_x
        if direction == "right":
            self._cursor_x += adv
            if self._cursor_x >= COLS:
                self._cursor_x = self._line_start
                self._cursor_y = min(ROWS - LETTER_ROWS, self._cursor_y + LETTER_ROWS)
        else:
            self._move_in_direction(direction)
        self._restart_blink()
        self.app.invalidate()

    def _backspace_letter(self):
        """Walk back to the previous written letter on this row and erase it."""
        y = self._cursor_y
        for d in range(1, 4):
            x = self._cursor_x - d
            if x < 0:
                break
            cell = self._grid.get((x, y))
            if cell and cell[0] not in ("", " ", BRUSH_CHAR):
                self._cursor_x = x
                self._del_cell((x, y))
                self._painted_positions.discard((x, y))
                self.app.invalidate()
                return
        self._backspace()

    def _backspace(self):
        if self._cursor_x > 0:
            self._cursor_x -= 1
        elif self._cursor_y > 0:
            self._cursor_y -= 1
            self._cursor_x = COLS - 1
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
        if k.startswith("#"):
            self._last_key_color = k
        elif k in GRAYSCALE:
            self._last_key_char, self._last_key_color = k, GRAYSCALE[k]
        elif (k.isalpha() or k in KEY_COLORS) and get_key_color(k) != UNMAPPED:
            self._last_key_char, self._last_key_color = k, get_key_color(k)
        self._paint_at_cursor()

    def _select_brush(self, char: str) -> bool:
        """Set the brush from a key; False when the key has no color."""
        if char in GRAYSCALE:
            self._last_key_char, self._last_key_color = char, GRAYSCALE[char]
        elif (char.isalpha() or char in KEY_COLORS) and get_key_color(char) != UNMAPPED:
            self._last_key_char, self._last_key_color = char.lower(), get_key_color(char)
        else:
            return False
        self._post_paint_mode_changed()
        return True

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
                    self._cursor_x = self._line_start
                    self._cursor_y = min(ROWS - LETTER_ROWS, self._cursor_y + LETTER_ROWS)
                    self.app.invalidate()
            elif a == "backspace":
                self._backspace_repeat_count = self._backspace_repeat_count + 1 if action.is_repeat else 0
                for _ in range(HOLD_ACCEL_MULTIPLIER if self._backspace_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD else 1):
                    self._backspace_letter() if not self._paint_mode else self._backspace()
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
        if self._paint_mode and action.char_held:
            self._select_brush(action.char_held)
            if self._arrow_repeat_count == 0 or (self._cursor_x, self._cursor_y) != self._last_paint_pos:
                self._paint_at_cursor()
        if action.direction in ("up", "down") and prior_post_stamp_x is not None and not action.char_held:
            self._cursor_x = prior_post_stamp_x
        paint_each_step = self._paint_mode and (self._pen_down or bool(action.char_held))
        steps = HOLD_ACCEL_MULTIPLIER if (not paint_each_step and self._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD) else 1
        for direction in [action.direction] + list(action.other_arrows_held or ()):
            for _ in range(steps):
                if not self._move_in_direction(direction):
                    break
                if paint_each_step:
                    self._paint_at_cursor()
        self._restart_blink()
        self.app.invalidate()

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        head_h, hint_h = g.vh(5.5), g.vh(4.5)
        self._draw_header(g, pygame.Rect(rect.x, rect.y, rect.w, head_h))
        area = pygame.Rect(rect.x + g.vw(1), rect.y + head_h, rect.w - g.vw(2), rect.h - head_h - hint_h)
        self._cell = max(3, min(area.w // COLS, area.h // ROWS))
        ox = area.x + (area.w - self._cell * COLS) // 2
        oy = area.y + (area.h - self._cell * ROWS) // 2
        self._origin = (ox, oy)
        c = self._cell
        g.surface.blit(self._canvas_surface(g, c), (ox, oy))
        self._draw_grid_halo(g, ox, oy, c)
        self._draw_letters(g, ox, oy, c)
        self._draw_cursor(g, ox, oy, c)
        if self.app._panel is None:
            key = "littles" if self.app._littles_mode else ("pen" if self._paint_mode and self._pen_down else "paint" if self._paint_mode else "write")
            g.draw_text(HINTS[key], g.vh(2.1), rect.centerx, rect.bottom - hint_h // 2, "sans-bold", P.DIM, anchor="center")
            if self.app._code_panel_enabled and not self.app._littles_mode:
                g.draw_text("🤖 Hold Space: write code!", g.vh(2.0), rect.right - g.vw(1.5), rect.bottom - hint_h // 2, "sans-bold", P.DIM, anchor="midright")

    def _canvas_surface(self, g, c):
        """The cells as one surface; only cells that changed since the last
        frame are repainted, so a keystroke costs a cell, not a canvas."""
        if self._surf is None or self._surf.get_width() != c * COLS or self._surf.get_height() != c * ROWS:
            self._surf = pygame.Surface((c * COLS, c * ROWS))
            self._dirty = None
        cells = self._grid.keys() if self._dirty is None else self._dirty
        if self._dirty is None:
            self._surf.fill(rgb(CANVAS_BG))
        for x, y in list(cells):
            if not (0 <= x < COLS and 0 <= y < ROWS):
                continue
            cell = self._grid.get((x, y))
            rect = (x * c, y * c, c, c)
            self._surf.fill(rgb(cell[2] if cell and (cell[2] != CANVAS_BG or cell[0] == BRUSH_CHAR) else CANVAS_BG), rect)
        self._dirty = set()
        return self._surf

    def _draw_letters(self, g, ox, oy, c):
        px = self._letter_px(c)
        for (x, y), (ch, fg, _bg) in self._grid.items():
            if ch not in ("", " ", BRUSH_CHAR) and 0 <= x < COLS and 0 <= y < ROWS:
                g.draw_text(ch, px, ox + x * c + int(c * 0.08), oy + y * c + c, "sans-heavy", fg, anchor="midleft")

    def _draw_grid_halo(self, g, ox, oy, c):
        """Faint grid only near the cursor, so the canvas reads as paper."""
        R = 4
        cx, cy = self._cursor_x, self._cursor_y
        x0, x1 = max(0, cx - R), min(COLS, cx + R + 1)
        y0, y1 = max(0, cy - R), min(ROWS, cy + R + 1)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1):
                d = max(abs(x - cx), abs(y - cy))
                pygame.draw.line(g.surface, mix(CANVAS_BG, P.PRIMARY, 0.18 * (1 - d / (R + 1))), (ox + x * c, oy + y * c), (ox + x * c, oy + (y + 1) * c))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1):
                d = max(abs(x - cx), abs(y - cy))
                pygame.draw.line(g.surface, mix(CANVAS_BG, P.PRIMARY, 0.18 * (1 - d / (R + 1))), (ox + x * c, oy + y * c), (ox + (x + 1) * c, oy + y * c))

    def _draw_cursor(self, g, ox, oy, c):
        x, y = ox + self._cursor_x * c, oy + self._cursor_y * c
        visible = self._blink_on or self._pen_down
        if self._paint_mode:
            ring = pygame.Rect(x - c, y - c, 3 * c, 3 * c)
            thick = max(3, c // 3) if self._pen_down else 2
            if visible:
                g.rect(self._last_key_color, ring, width=thick, radius=2)
                corner = P.TEXT
                for cx, cy in ((ring.x, ring.y), (ring.right - thick, ring.y), (ring.x, ring.bottom - thick), (ring.right - thick, ring.bottom - thick)):
                    g.rect(corner, (cx, cy, thick, thick))
        elif visible:
            g.rect("#6633AA", (x, y, max(2, c // 3), c * LETTER_ROWS))
        if self._use_heading_cursor and visible:
            dx, dy = {"right": (1, 0), "left": (-1, 0), "up": (0, -1), "down": (0, 1)}[self._heading]
            color = _visible_arrow_color(self._last_key_color if self._paint_mode else "#FFFFFF", CANVAS_BG)
            g.draw_text(HEADING_ARROWS[self._heading], max(8, int(c * 0.9)), x + c // 2 + dx * c, y + c // 2 + dy * c, "sans-heavy", color, anchor="center")

    def _draw_header(self, g, r):
        px = g.vh(2.4)
        cy = r.centery
        if self.app._littles_mode:
            label = "■■■  Paint" if self._paint_mode else "ABC  Write"
            g.draw_text(label, px, r.centerx, cy, "sans-heavy", P.TEXT, anchor="center")
            return
        tabs = [("paint", self._paint_mode), ("ABC", not self._paint_mode)]
        widths = [g.vw(7), g.measure("ABC", px, "sans-bold")[0] + g.vw(2)]
        x = r.centerx - (sum(widths) + g.vw(1)) // 2
        for (label, on), w in zip(tabs, widths):
            box = pygame.Rect(x, cy - g.vh(1.9), w, g.vh(3.8))
            if on:
                g.rect(self._last_key_color if label == "paint" else P.PRIMARY, box, radius=g.vh(0.3))
            if label == "paint":
                sw = g.vh(1.6)
                for i, color in enumerate(("#DF7070", "#DFC070", "#7090DF")):
                    g.rect(color, (box.centerx - sw * 1.5 + i * sw, cy - sw // 2, sw, sw))
            else:
                g.draw_text("ABC", px, box.centerx, cy, "sans-bold", P.BG if on else P.MUTED, anchor="center")
            x += w + g.vw(1)
        g.draw_text("⇥ Tab to paint" if not self._paint_mode else "⇥ Tab to write", px, r.right - g.vw(1.5), cy, "sans-bold", P.MUTED, anchor="midright")
