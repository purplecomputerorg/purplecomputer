"""
Code Space: A per-room text editor widget.

Kids type code in a file-like interface below the viewport,
then run it with Tab+Space, Tab+Enter, or Shift+Space. Each room has its own buffer.

Uses render_line()/Strip/Segment for reliable rendering (same
pattern as ArtCanvas).
"""

from textual.widget import Widget
from textual.strip import Strip
from textual.message import Message
from rich.segment import Segment
from rich.style import Style

import re

from .keyboard import CharacterAction, NavigationAction, ControlAction

# Keywords to underline per room (recognized commands)
_ROOM_KEYWORDS = {
    "play": {"repeat", "end", "times", "plus", "minus"},
    "music": {"repeat", "end", "choose", "instrument", "fast", "slow",
              "letters", "on", "off"},
    "art": {"repeat", "end", "left", "right", "up", "down",
            "forward", "turn", "paint", "write", "on", "off"},
}


# Colors for the code editor
CODE_BG = "#d8c8e8"       # Soft purple background
CODE_FG = "#2a1845"       # Very dark purple text
CODE_CURSOR_BG = "#2a1845"  # Cursor: dark block
CODE_CURSOR_FG = "#d8c8e8"  # Cursor: light text
CODE_GHOST_FG = "#9b7bc4"  # Autocomplete ghost text color
CODE_GUTTER_BG = "#c8b8d8"  # Slightly darker purple gutter
CODE_SCROLLBAR_TRACK = "#c8b8d8"  # Scrollbar track (same as gutter)
CODE_SCROLLBAR_THUMB = "#9b7bc4"  # Scrollbar thumb (visible indicator)
CODE_HINT_FG = "#8a6bb4"          # Hint text in bottom gutter
CODE_TAB_LABEL_FG = "#b0a4be"      # Tab label when inactive (dim but visible)
CODE_TAB_DIMMED_FG = "#c0b4cc"     # Menu items when inactive (very dim)
CODE_TAB_ACTIVE_BG = "#8a6bb4"     # Tab label background when active
CODE_TAB_ACTIVE_FG = "#f0e8f4"     # Tab label text when active

# Gutter: 1-cell padding on all sides of the text area
GUTTER = 1


class RunCodeRequested(Message, bubble=True):
    """Posted when Shift+Space is pressed to run code."""
    def __init__(self, room: str, lines: list[str]):
        super().__init__()
        self.room = room
        self.lines = lines


class CloseCodeSpaceRequested(Message, bubble=True):
    """Posted when user closes code space from tab menu."""
    pass



class CodeTextEditor(Widget, can_focus=True):
    """
    Multi-line text editor for Code Space.

    Per-room buffers, cursor blink, scrolling. Uses render_line()
    for direct Strip/Segment rendering.
    """

    DEFAULT_CSS = """
    CodeTextEditor {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Per-room state
        self._buffers: dict[str, list[str]] = {}
        self._cursors: dict[str, tuple[int, int]] = {}
        self._scroll_offsets: dict[str, int] = {}

        # Active room
        self._room = "play"

        # Cursor blink
        self._cursor_visible = True
        self._blink_timer = None

        # Autocomplete state
        self._autocomplete_suggestion: str | None = None

        # Inline tab menu state
        self._tab_menu_active = False

    # -- Buffer access helpers --

    def _get_lines(self) -> list[str]:
        if self._room not in self._buffers:
            self._buffers[self._room] = [""]
        return self._buffers[self._room]

    def _get_cursor(self) -> tuple[int, int]:
        if self._room not in self._cursors:
            self._cursors[self._room] = (0, 0)
        return self._cursors[self._room]

    def _set_cursor(self, row: int, col: int) -> None:
        self._cursors[self._room] = (row, col)

    def _get_scroll(self) -> int:
        return self._scroll_offsets.get(self._room, 0)

    def _set_scroll(self, offset: int) -> None:
        self._scroll_offsets[self._room] = max(0, offset)

    # -- Room switching --

    def set_room(self, room_name: str) -> None:
        self._room = room_name
        self._autocomplete_suggestion = None
        self._tab_menu_active = False
        self._ensure_scroll_visible()
        self.refresh()

    # -- Cursor blink --

    def on_mount(self) -> None:
        self._start_blink()

    def _start_blink(self) -> None:
        if self._blink_timer is not None:
            self._blink_timer.stop()
        self._cursor_visible = True
        self._blink_timer = self.set_interval(0.5, self._toggle_blink)

    def _restart_blink(self) -> None:
        """Reset blink to visible and restart timer."""
        self._cursor_visible = True
        if self._blink_timer is not None:
            self._blink_timer.reset()
        self.refresh()

    def _toggle_blink(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.refresh()

    # -- Scrolling --

    def _ensure_scroll_visible(self) -> None:
        """Make sure cursor row is visible (accounting for gutter)."""
        row, _ = self._get_cursor()
        scroll = self._get_scroll()
        visible_lines = self.size.height - GUTTER * 2

        if visible_lines <= 0:
            return

        if row < scroll:
            self._set_scroll(row)
        elif row >= scroll + visible_lines:
            self._set_scroll(row - visible_lines + 1)

    # -- Scrollbar --

    def _get_scrollbar_thumb(self) -> tuple[int, int] | None:
        """Return (thumb_start, thumb_end) in inner row coords, or None if no scrollbar needed."""
        lines = self._get_lines()
        inner_height = self.size.height - GUTTER * 2
        if inner_height <= 0 or len(lines) <= inner_height:
            return None
        total = len(lines)
        scroll = self._get_scroll()
        # Thumb size: at least 1 row
        thumb_size = max(1, round(inner_height * inner_height / total))
        # Thumb position
        max_scroll = total - inner_height
        if max_scroll > 0:
            thumb_start = round(scroll / max_scroll * (inner_height - thumb_size))
        else:
            thumb_start = 0
        return (thumb_start, thumb_start + thumb_size)

    # -- Rendering --

    def _get_keyword_positions(self, line: str) -> set[int]:
        """Return character indices that are part of a recognized keyword."""
        keywords = _ROOM_KEYWORDS.get(self._room, set())
        positions = set()
        for m in re.finditer(r'[a-zA-Z+]+', line):
            word = m.group().lower()
            if word in keywords:
                for i in range(m.start(), m.end()):
                    positions.add(i)
        return positions

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if width <= 0:
            return Strip([])

        gutter_style = Style(bgcolor=CODE_GUTTER_BG)
        bg_style = Style(bgcolor=CODE_BG, color=CODE_FG)
        kw_style = Style(bgcolor=CODE_BG, color=CODE_FG, underline=True)
        cursor_style = Style(bgcolor=CODE_CURSOR_BG, color=CODE_CURSOR_FG)
        cursor_kw_style = Style(bgcolor=CODE_CURSOR_BG, color=CODE_CURSOR_FG, underline=True)
        ghost_style = Style(bgcolor=CODE_BG, color=CODE_GHOST_FG)

        # Top and bottom gutter rows
        lines = self._get_lines()
        scroll = self._get_scroll()
        inner_height = self.size.height - GUTTER * 2
        inner_width = width - GUTTER * 2

        if y < GUTTER or inner_width <= 0:
            return Strip([Segment(" " * width, gutter_style)])

        # Bottom gutter: inline tab menu bar
        if y >= self.size.height - GUTTER:
            return self._render_tab_menu_bar(width)

        segments = []
        # Left gutter
        segments.append(Segment(" " * GUTTER, gutter_style))

        cursor_row, cursor_col = self._get_cursor()
        line_idx = (y - GUTTER) + scroll

        if line_idx < len(lines):
            line = lines[line_idx]
            is_cursor_line = (line_idx == cursor_row)
            kw_positions = self._get_keyword_positions(line)

            col = 0
            for i, ch in enumerate(line):
                if col >= inner_width:
                    break
                is_kw = i in kw_positions
                if is_cursor_line and i == cursor_col and self._cursor_visible:
                    segments.append(Segment(ch, cursor_kw_style if is_kw else cursor_style))
                else:
                    segments.append(Segment(ch, kw_style if is_kw else bg_style))
                col += 1

            # Cursor at end of line
            if is_cursor_line and cursor_col >= len(line) and self._cursor_visible:
                if col < inner_width:
                    segments.append(Segment(" ", cursor_style))
                    col += 1

            # Autocomplete ghost text
            if is_cursor_line and self._autocomplete_suggestion and cursor_col >= len(line):
                ghost = self._autocomplete_suggestion
                for ch in ghost:
                    if col >= inner_width:
                        break
                    segments.append(Segment(ch, ghost_style))
                    col += 1

            remaining = inner_width - col
            if remaining > 0:
                segments.append(Segment(" " * remaining, bg_style))
        else:
            segments.append(Segment(" " * inner_width, bg_style))

        # Right gutter (scrollbar when content overflows)
        thumb = self._get_scrollbar_thumb()
        if thumb is not None and GUTTER > 0:
            inner_y = y - GUTTER
            if 0 <= inner_y < self.size.height - GUTTER * 2 and thumb[0] <= inner_y < thumb[1]:
                segments.append(Segment(" " * GUTTER, Style(bgcolor=CODE_SCROLLBAR_THUMB)))
            else:
                segments.append(Segment(" " * GUTTER, Style(bgcolor=CODE_SCROLLBAR_TRACK)))
        else:
            segments.append(Segment(" " * GUTTER, gutter_style))

        return Strip(segments)

    def _render_tab_menu_bar(self, width: int) -> Strip:
        """Render the inline tab menu bar in the bottom gutter."""
        caps = getattr(self.app, 'caps_text', lambda x: x)
        gutter_style = Style(bgcolor=CODE_GUTTER_BG)

        if self._tab_menu_active:
            tab_style = Style(bgcolor=CODE_TAB_ACTIVE_BG, color=CODE_TAB_ACTIVE_FG, bold=True)
            item_style = Style(bgcolor=CODE_GUTTER_BG, color=CODE_HINT_FG)
            sep_style = Style(bgcolor=CODE_GUTTER_BG, color=CODE_TAB_DIMMED_FG)
        else:
            tab_style = Style(bgcolor=CODE_GUTTER_BG, color=CODE_TAB_LABEL_FG)
            item_style = Style(bgcolor=CODE_GUTTER_BG, color=CODE_TAB_DIMMED_FG)
            sep_style = Style(bgcolor=CODE_GUTTER_BG, color=CODE_TAB_DIMMED_FG)

        parts = [
            (caps(" Tab: Menu "), tab_style),
            (caps("  Space: Run"), item_style),
            (caps("  \u00b7  "), sep_style),
            (caps("C: Clear"), item_style),
            (caps("  \u00b7  "), sep_style),
            (caps("X: Exit Code"), item_style),
        ]

        total_len = sum(len(text) for text, _ in parts)
        pad_left = max(0, (width - total_len) // 2)
        pad_right = max(0, width - total_len - pad_left)

        segments = []
        if pad_left > 0:
            segments.append(Segment(" " * pad_left, gutter_style))
        for text, style in parts:
            segments.append(Segment(text, style))
        if pad_right > 0:
            segments.append(Segment(" " * pad_right, gutter_style))

        return Strip(segments)

    def _handle_tab_menu_key(self, action) -> bool:
        """Handle keyboard input while tab menu is active. Returns True if consumed."""
        # Consume key-up events without deactivating
        if isinstance(action, ControlAction) and not action.is_down:
            return True

        # Space or Enter: run code
        if isinstance(action, ControlAction) and action.is_down and action.action in ('space', 'enter'):
            self._tab_menu_active = False
            self.post_message(RunCodeRequested(
                room=self._room,
                lines=list(self._get_lines()),
            ))
            self.refresh()
            return True

        # Tab: toggle off (ignore repeats)
        if isinstance(action, ControlAction) and action.is_down and action.action == 'tab':
            if not action.is_repeat:
                self._tab_menu_active = False
                self.refresh()
            return True

        # Escape: deactivate
        if isinstance(action, ControlAction) and action.is_down and action.action == 'escape':
            self._tab_menu_active = False
            self.refresh()
            return True

        # Character shortcuts
        if isinstance(action, CharacterAction):
            ch = action.char.lower()
            if ch == 'c':
                self._tab_menu_active = False
                self.clear_buffer()
            elif ch == 'x':
                self._tab_menu_active = False
                self.post_message(CloseCodeSpaceRequested())
                self.refresh()
            else:
                # Any other character: just deactivate
                self._tab_menu_active = False
                self.refresh()
            return True

        # Any other action (navigation, etc.): deactivate
        self._tab_menu_active = False
        self.refresh()
        return True

    # -- Keyboard handling --

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard input. Returns True if consumed."""
        # Intercept keys when inline tab menu is active
        if self._tab_menu_active:
            if self._handle_tab_menu_key(action):
                return

        if isinstance(action, CharacterAction):
            # Backtick/tilde inserts repeat template
            if action.char in ('`', '~'):
                self._insert_repeat_template()
                self._restart_blink()
                return

            # Check autocomplete: if tab would accept, typing clears it
            self._autocomplete_suggestion = None

            self._insert_char(action.char)
            self._update_autocomplete()
            self._restart_blink()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                self._insert_newline()
                self._autocomplete_suggestion = None
                self._restart_blink()
                return

            if action.action == 'backspace':
                self._do_backspace()
                self._autocomplete_suggestion = None
                self._restart_blink()
                return

            if action.action == 'tab':
                # Tab: accept autocomplete or activate inline menu
                if self._autocomplete_suggestion:
                    self._accept_autocomplete()
                    self._restart_blink()
                elif not action.is_repeat:
                    self._tab_menu_active = True
                    self.refresh()
                return

            if action.action == 'space':
                # Check for Shift+Space: run code
                sm = self.app._keyboard_state_machine
                if sm._sticky_shift_active or sm._shift_held:
                    # Consume sticky shift
                    if sm._sticky_shift_active:
                        sm._sticky_shift_active = False
                        if sm._on_sticky_shift_change:
                            sm._on_sticky_shift_change(False)
                    # Post run request
                    self.post_message(RunCodeRequested(
                        room=self._room,
                        lines=list(self._get_lines()),
                    ))
                    return
                # Normal space: insert
                self._insert_char(' ')
                self._update_autocomplete()
                self._restart_blink()
                return

        if isinstance(action, NavigationAction):
            self._move_cursor(action.direction)
            self._autocomplete_suggestion = None
            self._restart_blink()
            return

    # -- Text editing operations --

    def _insert_char(self, ch: str) -> None:
        lines = self._get_lines()
        row, col = self._get_cursor()
        if row >= len(lines):
            lines.extend([""] * (row - len(lines) + 1))
        line = lines[row]
        lines[row] = line[:col] + ch + line[col:]
        self._set_cursor(row, col + 1)
        self._ensure_scroll_visible()
        self.refresh()

    def _insert_newline(self) -> None:
        lines = self._get_lines()
        row, col = self._get_cursor()
        line = lines[row]
        lines[row] = line[:col]
        lines.insert(row + 1, line[col:])
        self._set_cursor(row + 1, 0)
        self._ensure_scroll_visible()
        self.refresh()

    def _do_backspace(self) -> None:
        lines = self._get_lines()
        row, col = self._get_cursor()
        if col > 0:
            line = lines[row]
            lines[row] = line[:col - 1] + line[col:]
            self._set_cursor(row, col - 1)
        elif row > 0:
            # Join with previous line
            prev_len = len(lines[row - 1])
            lines[row - 1] += lines[row]
            lines.pop(row)
            self._set_cursor(row - 1, prev_len)
        self._ensure_scroll_visible()
        self.refresh()

    def _move_cursor(self, direction: str) -> None:
        lines = self._get_lines()
        row, col = self._get_cursor()

        if direction == 'left':
            if col > 0:
                col -= 1
            elif row > 0:
                row -= 1
                col = len(lines[row])
        elif direction == 'right':
            if row < len(lines) and col < len(lines[row]):
                col += 1
            elif row < len(lines) - 1:
                row += 1
                col = 0
        elif direction == 'up':
            if row > 0:
                row -= 1
                col = min(col, len(lines[row]))
        elif direction == 'down':
            if row < len(lines) - 1:
                row += 1
                col = min(col, len(lines[row]))

        self._set_cursor(row, col)
        self._ensure_scroll_visible()
        self.refresh()

    def _insert_repeat_template(self) -> None:
        """Insert `repeat 2\\n\\nend` template with cursor after 2."""
        lines = self._get_lines()
        row, col = self._get_cursor()
        line = lines[row]

        # Insert "repeat 2" on current line, then blank line, then "end"
        before = line[:col]
        after = line[col:]
        lines[row] = before + "repeat 2"
        lines.insert(row + 1, "")
        lines.insert(row + 2, "end" + after)
        # Cursor after the "2" in "repeat 2"
        self._set_cursor(row, len(before) + len("repeat 2"))
        self._ensure_scroll_visible()
        self.refresh()

    # -- Autocomplete --

    # Art mode commands for autocomplete
    _ART_COMMANDS = ["paint on", "paint off", "write on", "write off",
                     "left", "right", "up", "down",
                     "forward", "turn left", "turn right"]
    # Music mode commands for autocomplete
    _MUSIC_COMMANDS = ["choose", "instrument", "fast", "slow",
                       "letters on", "letters off"]
    _INSTRUMENT_NAMES = ["marimba", "xylophone", "ukulele", "musicbox"]

    def _update_autocomplete(self) -> None:
        """Check for autocomplete matches based on current word."""
        self._autocomplete_suggestion = None

        lines = self._get_lines()
        row, col = self._get_cursor()
        if row >= len(lines):
            return

        line = lines[row]
        # Find the word being typed (from start of line or after space)
        word_start = col
        while word_start > 0 and line[word_start - 1] != ' ':
            word_start -= 1
        prefix = line[word_start:col]

        if not prefix:
            return

        # "rep" -> "repeat "
        if "repeat".startswith(prefix) and prefix != "repeat":
            self._autocomplete_suggestion = "repeat "[len(prefix):]
            return

        # Room-specific autocomplete
        if self._room == "art":
            # Match against full line content (for multi-word like "paint on")
            line_so_far = line[:col].lstrip()
            for cmd in self._ART_COMMANDS:
                if cmd.startswith(line_so_far) and cmd != line_so_far and len(line_so_far) >= 1:
                    self._autocomplete_suggestion = cmd[len(line_so_far):]
                    return
            return

        if self._room == "music":
            # After "choose " or "instrument ", autocomplete instrument names
            line_so_far = line[:col].lstrip()
            m = re.match(r'^(?:choose|instrument)\s+(\S*)$', line_so_far, re.IGNORECASE)
            if m:
                inst_prefix = m.group(1).lower()
                if inst_prefix:
                    for name in self._INSTRUMENT_NAMES:
                        if name.startswith(inst_prefix) and name != inst_prefix:
                            self._autocomplete_suggestion = name[len(inst_prefix):]
                            return
                else:
                    # Just typed "choose ", suggest first instrument
                    self._autocomplete_suggestion = self._INSTRUMENT_NAMES[0]
                    return
                return
            # Match against full line for multi-word commands (e.g. "letters on")
            for cmd in self._MUSIC_COMMANDS:
                if ' ' in cmd:
                    if cmd.startswith(line_so_far) and cmd != line_so_far and len(line_so_far) >= 1:
                        self._autocomplete_suggestion = cmd[len(line_so_far):]
                        return
                elif cmd.startswith(prefix) and cmd != prefix and len(prefix) >= 1:
                    self._autocomplete_suggestion = cmd[len(prefix):] + " "
                    return
            return

        # Play room: emoji/color autocomplete
        if self._room == "play" and len(prefix) >= 2:
            try:
                from .content import get_content
                results = get_content().search_words(prefix)
                if results:
                    word = results[0][0]
                    if word != prefix and word.startswith(prefix):
                        self._autocomplete_suggestion = word[len(prefix):]
            except Exception:
                pass

    def _accept_autocomplete(self) -> None:
        """Accept the current autocomplete suggestion."""
        if not self._autocomplete_suggestion:
            return

        lines = self._get_lines()
        row, col = self._get_cursor()
        line = lines[row]
        lines[row] = line[:col] + self._autocomplete_suggestion + line[col:]
        self._set_cursor(row, col + len(self._autocomplete_suggestion))
        self._autocomplete_suggestion = None
        self._ensure_scroll_visible()
        self.refresh()

    # -- Public API --

    def get_lines(self, room: str | None = None) -> list[str]:
        """Get the lines for a room (or current room)."""
        r = room or self._room
        return list(self._buffers.get(r, [""]))

    def clear_buffer(self, room: str | None = None) -> None:
        """Clear the buffer for a room."""
        r = room or self._room
        self._buffers[r] = [""]
        self._cursors[r] = (0, 0)
        self._scroll_offsets[r] = 0
        self.refresh()
