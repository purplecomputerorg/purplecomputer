"""
REPL Panel: Overlay command input for Music and Art rooms.

Single-line input with scrolling history. Enter runs each command.
Supports `repeat N` ... `end` blocks that collect lines before executing.

Renders using render_line()/Strip/Segment (same pattern as ArtCanvas).
"""

import re

from textual.widget import Widget
from textual.strip import Strip
from textual.message import Message
from rich.segment import Segment
from rich.style import Style

from .keyboard import CharacterAction, NavigationAction, ControlAction

# Visual constants
BG = "#2a1845"
FG = "#d8c8e8"
PROMPT_COLOR = "#c4a0e8"
HISTORY_INPUT_COLOR = "#9b7bc4"
HISTORY_RESULT_COLOR = "#d8c8e8"
CURSOR_BG = "#d8c8e8"
CURSOR_FG = "#2a1845"
BLOCK_PROMPT_COLOR = "#9b7bc4"
SEPARATOR_COLOR = "#4a2870"

# Default height when not in a repeat block
DEFAULT_HEIGHT = 5
# Max height when collecting repeat block lines
MAX_HEIGHT = 10


class ReplCommandSubmitted(Message, bubble=True):
    """Posted when a command or block is ready to execute."""
    def __init__(self, room: str, lines: list[str]):
        super().__init__()
        self.room = room
        self.lines = lines


class ReplPanelClosed(Message, bubble=True):
    """Posted when the REPL panel wants to close."""
    pass


class ReplPanel(Widget):
    """REPL panel for music/art rooms.

    Always visible as a 1-row stub when closed. Expands when opened.
    """

    DEFAULT_CSS = """
    ReplPanel {
        dock: bottom;
        width: 100%;
        height: 1;
    }
    """

    def __init__(self, room: str, **kwargs):
        super().__init__(**kwargs)
        self._room = room
        self._open = False
        self._input_text = ""
        self._cursor_pos = 0
        self._history: list[tuple[str, str]] = []  # (type, text): type is "input" or "result"
        self._history_scroll = 0  # how far scrolled up from bottom
        self._repeat_stack: list[dict] = []
        self._target_height = DEFAULT_HEIGHT

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True
        self.styles.height = self._target_height
        self.refresh()

    def close(self) -> None:
        self._open = False
        self._repeat_stack.clear()
        self.styles.height = 1
        self.refresh()

    def _update_height(self) -> None:
        """Adjust height based on repeat block depth."""
        if self._repeat_stack:
            # Count collected lines across all stack levels
            total_lines = sum(len(s['lines']) for s in self._repeat_stack)
            self._target_height = min(DEFAULT_HEIGHT + total_lines, MAX_HEIGHT)
        else:
            self._target_height = DEFAULT_HEIGHT
        self.styles.height = self._target_height
        self.refresh()

    def add_result(self, text: str) -> None:
        """Add a result line to history (called by the app after execution)."""
        self._history.append(("result", text))
        self._history_scroll = 0
        self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        height = self.size.height
        if width == 0 or height == 0:
            return Strip.blank(width)

        # Stub mode: single row with hint
        if not self._open:
            return self._render_stub(width)

        # Layout: separator (1 row), history (height-3 rows), blank (1 row), input (1 row)
        separator_row = 0
        input_row = height - 1
        blank_row = height - 2
        history_rows = height - 3

        if y == separator_row:
            return self._render_separator(width)
        elif y == input_row:
            return self._render_input_line(width)
        elif y == blank_row:
            return Strip([Segment(" " * width, Style(bgcolor=BG))])
        elif y > separator_row and y < blank_row:
            # History area
            history_y = y - 1  # 0-indexed within history area
            return self._render_history_line(history_y, history_rows, width)
        else:
            return Strip([Segment(" " * width, Style(bgcolor=BG))])

    def _render_stub(self, width: int) -> Strip:
        """Render the 1-row closed state."""
        hint = "Hold Space: type commands"
        pad_left = max(0, (width - len(hint)) // 2)
        pad_right = max(0, width - len(hint) - pad_left)
        style = Style(color=SEPARATOR_COLOR, bgcolor=BG)
        return Strip([
            Segment(" " * pad_left, Style(bgcolor=BG)),
            Segment(hint, style),
            Segment(" " * pad_right, Style(bgcolor=BG)),
        ])

    def _render_separator(self, width: int) -> Strip:
        line = "─" * width
        return Strip([Segment(line, Style(color=SEPARATOR_COLOR, bgcolor=BG))])

    def _render_input_line(self, width: int) -> Strip:
        # Build prompt
        if self._repeat_stack:
            depth = len(self._repeat_stack)
            prompt = "·" * (depth + 1) + " "
        else:
            prompt = "> "

        segments = []
        prompt_style = Style(color=BLOCK_PROMPT_COLOR if self._repeat_stack else PROMPT_COLOR,
                            bgcolor=BG, bold=True)
        segments.append(Segment(prompt, prompt_style))

        # Render input text with cursor
        text = self._input_text
        cursor = self._cursor_pos
        text_style = Style(color=FG, bgcolor=BG)
        cursor_style = Style(color=CURSOR_FG, bgcolor=CURSOR_BG)

        if text:
            before = text[:cursor]
            cursor_char = text[cursor] if cursor < len(text) else " "
            after = text[cursor + 1:] if cursor < len(text) else ""

            if before:
                segments.append(Segment(before, text_style))
            segments.append(Segment(cursor_char, cursor_style))
            if after:
                segments.append(Segment(after, text_style))
        else:
            segments.append(Segment(" ", cursor_style))

        # Fill remaining width
        used = len(prompt) + max(len(text), 1)
        remaining = width - used
        if remaining > 0:
            segments.append(Segment(" " * remaining, Style(bgcolor=BG)))

        return Strip(segments)

    def _render_history_line(self, y: int, total_rows: int, width: int) -> Strip:
        """Render a line from the history, bottom-aligned."""
        empty = Strip([Segment(" " * width, Style(bgcolor=BG))])

        if not self._history:
            return empty

        # Bottom-align: the last history item is at the bottom row
        # y=0 is top of history area, y=total_rows-1 is bottom
        idx = len(self._history) - total_rows + y - self._history_scroll
        if idx < 0 or idx >= len(self._history):
            return empty

        line_type, text = self._history[idx]
        if line_type == "input":
            style = Style(color=HISTORY_INPUT_COLOR, bgcolor=BG)
            display = f"  {text}"
        else:
            style = Style(color=HISTORY_RESULT_COLOR, bgcolor=BG)
            display = f"  {text}"

        # Truncate to width
        display = display[:width]
        remaining = width - len(display)
        segments = [Segment(display, style)]
        if remaining > 0:
            segments.append(Segment(" " * remaining, Style(bgcolor=BG)))
        return Strip(segments)

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction == 'left':
                if self._cursor_pos > 0:
                    self._cursor_pos -= 1
            elif action.direction == 'right':
                if self._cursor_pos < len(self._input_text):
                    self._cursor_pos += 1
            self.refresh()
            return

        if isinstance(action, ControlAction):
            if action.action == 'enter' and action.is_down:
                self._handle_enter()
                return

            if action.action == 'backspace' and action.is_down:
                if self._cursor_pos > 0:
                    self._input_text = (self._input_text[:self._cursor_pos - 1]
                                       + self._input_text[self._cursor_pos:])
                    self._cursor_pos -= 1
                    self.refresh()
                return

            if action.action == 'space' and action.is_down:
                self._input_text = (self._input_text[:self._cursor_pos] + " "
                                   + self._input_text[self._cursor_pos:])
                self._cursor_pos += 1
                self.refresh()
                return

            if action.action == 'escape' and action.is_down and not action.is_repeat:
                if self._repeat_stack:
                    # Cancel block
                    self._repeat_stack.clear()
                    self._input_text = ""
                    self._cursor_pos = 0
                    self._update_height()
                elif self._input_text:
                    self._input_text = ""
                    self._cursor_pos = 0
                    self.refresh()
                else:
                    # Empty input, no block: close panel
                    self.post_message(ReplPanelClosed())
                return

            return

        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            char = action.char
            if not char:
                return
            self._input_text = (self._input_text[:self._cursor_pos] + char
                               + self._input_text[self._cursor_pos:])
            self._cursor_pos += 1
            self.refresh()

    def _handle_enter(self) -> None:
        line = self._input_text.strip()
        if not line:
            self.refresh()
            return

        self._input_text = ""
        self._cursor_pos = 0

        # Check for repeat block start
        m = re.match(r'^repeat\s+(\d+)\s*$', line, re.IGNORECASE)
        if m:
            count = max(1, min(int(m.group(1)), 100))
            self._repeat_stack.append({'count': count, 'lines': [line]})
            self._history.append(("input", line))
            self._update_height()
            return

        # Check for end
        if re.match(r'^end\s*$', line, re.IGNORECASE) and self._repeat_stack:
            self._repeat_stack[-1]['lines'].append(line)
            self._history.append(("input", line))
            if len(self._repeat_stack) == 1:
                # Outermost end: execute block
                all_lines = self._repeat_stack[0]['lines']
                self._repeat_stack.clear()
                self._update_height()
                self.post_message(ReplCommandSubmitted(self._room, all_lines))
            else:
                # Nested end: merge into parent
                inner = self._repeat_stack.pop()
                self._repeat_stack[-1]['lines'].extend(inner['lines'])
                self._update_height()
            return

        # Inside a block: collect line
        if self._repeat_stack:
            self._repeat_stack[-1]['lines'].append(line)
            self._history.append(("input", line))
            self._update_height()
            return

        # Normal single line: execute immediately
        self._history.append(("input", line))
        self._history_scroll = 0
        self.refresh()
        self.post_message(ReplCommandSubmitted(self._room, [line]))
