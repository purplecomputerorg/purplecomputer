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

# Keywords per room for autocomplete and underlining
ROOM_KEYWORDS: dict[str, list[str]] = {
    'music': ['letters', 'on', 'off', 'choose', 'instrument', 'fast', 'slow',
              'repeat', 'end', 'marimba', 'xylophone', 'ukulele', 'musicbox'],
    'art': ['left', 'right', 'up', 'down', 'forward', 'turn', 'paint', 'write',
            'on', 'off', 'repeat', 'end'],
}

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
KEYWORD_COLOR = "#c4a0e8"
HINT_COLOR = "#7a6a9a"

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


class ReplPanelToggleRequested(Message, bubble=True):
    """Posted by rooms to request opening/closing the REPL panel."""
    def __init__(self, room: str):
        super().__init__()
        self.room = room


class ReplPanel(Widget):
    """REPL panel for music/art rooms.

    Hidden when closed. Expands when opened.
    """

    DEFAULT_CSS = """
    ReplPanel {
        dock: bottom;
        width: 100%;
        height: 5;
        display: none;
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
        self._autocomplete_matches: list[str] = []
        self._keywords = set(ROOM_KEYWORDS.get(room, []))

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True
        self.display = True
        self.styles.height = self._target_height
        self.refresh()

    def close(self) -> None:
        self._open = False
        self._repeat_stack.clear()
        self.display = False
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

    def _get_current_word(self) -> tuple[str, int, int]:
        """Get the word at/before cursor. Returns (word_lower, start, end)."""
        text = self._input_text
        pos = self._cursor_pos
        start = pos
        while start > 0 and text[start - 1] != ' ':
            start -= 1
        end = pos
        while end < len(text) and text[end] != ' ':
            end += 1
        return text[start:end].lower(), start, end

    def _check_autocomplete(self) -> None:
        """Update autocomplete matches based on current word at cursor."""
        word, _, _ = self._get_current_word()
        if not word or word in self._keywords:
            self._autocomplete_matches = []
            return
        matches = [kw for kw in sorted(self._keywords) if kw.startswith(word) and kw != word]
        self._autocomplete_matches = matches[:5]

    def _get_keyword_positions(self) -> set[int]:
        """Return character positions in _input_text that are part of recognized keywords."""
        if not self._keywords:
            return set()
        positions: set[int] = set()
        i = 0
        text_lower = self._input_text.lower()
        while i < len(self._input_text):
            if self._input_text[i] == ' ':
                i += 1
                continue
            j = i
            while j < len(self._input_text) and self._input_text[j] != ' ':
                j += 1
            if text_lower[i:j] in self._keywords:
                for k in range(i, j):
                    positions.add(k)
            i = j
        return positions

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        height = self.size.height
        if width == 0 or height == 0:
            return Strip.blank(width)

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
            return self._render_hint_line(width)
        elif y > separator_row and y < blank_row:
            # History area
            history_y = y - 1  # 0-indexed within history area
            return self._render_history_line(history_y, history_rows, width)
        else:
            return Strip([Segment(" " * width, Style(bgcolor=BG))])

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

        segments: list[Segment] = []
        prompt_style = Style(color=BLOCK_PROMPT_COLOR if self._repeat_stack else PROMPT_COLOR,
                            bgcolor=BG, bold=True)
        segments.append(Segment(prompt, prompt_style))

        # Render input text with cursor, underlining keywords
        text = self._input_text
        cursor = self._cursor_pos
        kw_pos = self._get_keyword_positions()

        if text:
            i = 0
            while i < len(text):
                is_cursor = (i == cursor)
                is_kw = (i in kw_pos)

                if is_cursor:
                    # Cursor char rendered individually
                    segments.append(Segment(text[i], Style(
                        color=CURSOR_FG, bgcolor=CURSOR_BG,
                        underline=is_kw)))
                    i += 1
                else:
                    # Batch consecutive chars with same style
                    j = i
                    while j < len(text) and j != cursor and (j in kw_pos) == is_kw:
                        j += 1
                    style = Style(color=KEYWORD_COLOR if is_kw else FG, bgcolor=BG,
                                  underline=is_kw)
                    segments.append(Segment(text[i:j], style))
                    i = j

            # Cursor at end of text
            if cursor >= len(text):
                segments.append(Segment(" ", Style(color=CURSOR_FG, bgcolor=CURSOR_BG)))
        else:
            segments.append(Segment(" ", Style(color=CURSOR_FG, bgcolor=CURSOR_BG)))

        # Fill remaining width
        used = len(prompt) + max(len(text), 1)
        remaining = width - used
        if remaining > 0:
            segments.append(Segment(" " * remaining, Style(bgcolor=BG)))

        return Strip(segments)

    def _render_hint_line(self, width: int) -> Strip:
        """Render autocomplete hint or blank line."""
        bg_style = Style(bgcolor=BG)
        if not self._autocomplete_matches:
            return Strip([Segment(" " * width, bg_style)])

        hint_style = Style(color=HINT_COLOR, bgcolor=BG)
        kw_style = Style(color=KEYWORD_COLOR, bgcolor=BG)

        segments: list[Segment] = []
        segments.append(Segment("  ", bg_style))
        used = 2

        for i, kw in enumerate(self._autocomplete_matches):
            if i > 0:
                segments.append(Segment("  ", bg_style))
                used += 2
            segments.append(Segment(kw, kw_style))
            used += len(kw)

        tab_hint = "  \u2192Tab"
        segments.append(Segment(tab_hint, hint_style))
        used += len(tab_hint)

        remaining = width - used
        if remaining > 0:
            segments.append(Segment(" " * remaining, bg_style))

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

    async def handle_keyboard_action(self, action):
        """Handle keyboard input. Returns "tab_fallthrough" if tab should be
        handled by the parent (no autocomplete match), None otherwise."""
        if isinstance(action, NavigationAction):
            if action.direction == 'left':
                if self._cursor_pos > 0:
                    self._cursor_pos -= 1
            elif action.direction == 'right':
                if self._cursor_pos < len(self._input_text):
                    self._cursor_pos += 1
            self._check_autocomplete()
            self.refresh()
            return

        if isinstance(action, ControlAction):
            if action.action == 'tab' and action.is_down:
                if self._autocomplete_matches:
                    word, start, end = self._get_current_word()
                    replacement = self._autocomplete_matches[0]
                    self._input_text = (self._input_text[:start] + replacement
                                       + self._input_text[end:])
                    self._cursor_pos = start + len(replacement)
                    self._check_autocomplete()
                    self.refresh()
                    return
                else:
                    return "tab_fallthrough"

            if action.action == 'enter' and action.is_down:
                self._autocomplete_matches = []
                self._handle_enter()
                return

            if action.action == 'backspace' and action.is_down:
                if self._cursor_pos > 0:
                    self._input_text = (self._input_text[:self._cursor_pos - 1]
                                       + self._input_text[self._cursor_pos:])
                    self._cursor_pos -= 1
                    self._check_autocomplete()
                    self.refresh()
                return

            if action.action == 'space' and action.is_down:
                self._input_text = (self._input_text[:self._cursor_pos] + " "
                                   + self._input_text[self._cursor_pos:])
                self._cursor_pos += 1
                self._autocomplete_matches = []
                self.refresh()
                return

            if action.action == 'escape' and action.is_down and not action.is_repeat:
                if self._repeat_stack:
                    # Cancel block
                    self._repeat_stack.clear()
                    self._input_text = ""
                    self._cursor_pos = 0
                    self._autocomplete_matches = []
                    self._update_height()
                elif self._input_text:
                    self._input_text = ""
                    self._cursor_pos = 0
                    self._autocomplete_matches = []
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
            self._check_autocomplete()
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
