"""
REPL Panel: Overlay command input for Music and Art rooms.

Uses the same CodeInput/InputPrompt/AutocompleteHint widgets as the Play room.
Toggled via space-hold in music/art rooms.
"""

import re

from textual.containers import Vertical, Horizontal
from textual.message import Message

from .code_input import (
    WordHighlighter, CodeInput, InputPrompt,
    AutocompleteHint, RecallHint, ExampleHint,
)
from .content import get_content
from .keyboard import CharacterAction, NavigationAction, ControlAction

# Keywords per room for autocomplete and underlining
ROOM_KEYWORDS: dict[str, list[str]] = {
    'music': ['choose', 'instrument', 'fast', 'slow',
              'repeat', 'end', 'marimba', 'xylophone', 'ukulele', 'musicbox'],
    'art': ['left', 'right', 'up', 'down', 'forward', 'go', 'move', 'walk', 'step',
            'turn', 'color', 'lift', 'pen', 'penup', 'pendown',
            'repeat', 'end'],
}

ROOM_HINTS: dict[str, list[str]] = {
    'music': [
        "Try: abcdefg  \u2022  choose ukulele",
        "Try: fast qwertyuiop  \u2022  slow asdf",
        "Try: repeat 3 abcdefg  \u2022  choose musicbox",
        "Try: choose xylophone  \u2022  choose marimba",
    ],
    'art': [
        "Try: forward 10  \u2022  turn right",
        "Try: repeat 4 forward 20, turn right",
        "Try: repeat 36 forward 5, turn right",
        "Try: forward 20, turn left, forward 10",
        "Try: color red, go 10  \u2022  color blue, go 5",
        "Try: lift, go 5, lift, go 5",
        "Try: turn down  \u2022  turn around  \u2022  turn 90",
    ],
}


def _make_keyword_autocomplete(keywords: set[str], color_aware: bool = False):
    """Create an autocomplete function for a keyword set.

    When color_aware=True, suggests color names after 'color' prefix.
    """
    def autocomplete_fn(last_word: str, full_text: str = "") -> list[tuple[str, str, str]]:
        # After "color ", suggest color names instead of keywords
        if color_aware and re.match(r'.*\bcolor\s+\S*$', full_text, re.IGNORECASE):
            content = get_content()
            if content.get_color(last_word):
                return [(last_word, content.get_color(last_word), "")]
            results = content.search_words(last_word)
            # Filter to color-only results (no emoji-only entries)
            colors = [(w, c or "", "") for w, c, _e in results if c]
            return colors[:5]

        if last_word in keywords:
            return [(last_word, "", "")]
        matches = sorted(kw for kw in keywords if kw.startswith(last_word))
        return [(kw, "", "") for kw in matches[:5]]
    return autocomplete_fn


def _make_keyword_validator(keywords: set[str]):
    """Create a validator function for a keyword set."""
    def validator(word: str) -> bool:
        return word.lower() in keywords
    return validator


class ReplCommandSubmitted(Message, bubble=True):
    """Posted when a command is ready to execute."""
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


class ReplPanel(Vertical):
    """REPL panel for music/art rooms.

    Hidden when closed (display: none). Uses same input widgets as Play room.
    """

    DEFAULT_CSS = """
    ReplPanel {
        dock: bottom;
        width: 100%;
        height: auto;
        display: none;
        padding: 1 1 0 1;
        background: $surface;
    }

    #repl-input-row {
        width: 100%;
        height: 1;
        layout: horizontal;
    }

    #repl-recall-hint {
        margin-left: 7;
    }

    #repl-autocomplete-hint {
        margin-left: 6;
    }
    """

    def __init__(self, room: str, **kwargs):
        super().__init__(**kwargs)
        self._room = room
        self._open = False
        self._last_input_text = ""
        keywords = set(ROOM_KEYWORDS.get(room, []))
        self._autocomplete_fn = _make_keyword_autocomplete(keywords, color_aware=(room == 'art'))
        self._validator = _make_keyword_validator(keywords)
        self._hints = ROOM_HINTS.get(room, ["Try: repeat 3 forward 10"])

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True
        self.display = True
        try:
            self.query_one("#repl-input", CodeInput).focus()
        except Exception:
            pass

    def close(self) -> None:
        self._open = False
        self.display = False

    def compose(self):
        with Horizontal(id="repl-input-row"):
            yield InputPrompt(label="Code", id="repl-prompt")
            yield CodeInput(
                highlighter=WordHighlighter(self._validator),
                autocomplete_fn=self._autocomplete_fn,
                id="repl-input",
            )
        yield RecallHint(id="repl-recall-hint")
        yield AutocompleteHint(id="repl-autocomplete-hint")
        yield ExampleHint(hints=self._hints, id="repl-example-hint")

    def on_input_changed(self, event) -> None:
        """Update autocomplete and recall hints when input changes."""
        try:
            code_input = self.query_one("#repl-input", CodeInput)
            hint = self.query_one("#repl-autocomplete-hint", AutocompleteHint)
            hint.update(code_input.autocomplete_hint)
            recall = self.query_one("#repl-recall-hint", RecallHint)
            recall.show_if_empty(not code_input.value)
        except Exception:
            pass

    async def handle_keyboard_action(self, action):
        """Handle keyboard input. Returns "tab_fallthrough" if tab should be
        handled by the parent (no autocomplete match), None otherwise."""
        try:
            code_input = self.query_one("#repl-input", CodeInput)
        except Exception:
            return

        if isinstance(action, NavigationAction):
            if action.direction == 'left':
                if code_input.cursor_position > 0:
                    code_input.cursor_position -= 1
            elif action.direction == 'right':
                if code_input.cursor_position < len(code_input.value):
                    code_input.cursor_position += 1
            return

        if isinstance(action, ControlAction):
            if action.action == 'tab' and action.is_down:
                if code_input.autocomplete_matches:
                    # Tab: accept autocomplete suggestion
                    selected = code_input.autocomplete_matches[code_input.autocomplete_index][0]
                    words = code_input.value.split()
                    if words:
                        words[-1] = selected
                        code_input.value = " ".join(words) + " "
                        code_input.cursor_position = len(code_input.value)
                    code_input.autocomplete_matches = []
                    code_input.autocomplete_index = 0
                    code_input.exact_match_display = ""
                else:
                    return "tab_fallthrough"
                return

            if action.action == 'enter' and action.is_down:
                line = code_input.value.strip()
                if line:
                    # "exit" closes the code panel
                    if line.lower() == 'exit':
                        code_input.value = ""
                        code_input.cursor_position = 0
                        self.post_message(ReplPanelClosed())
                        return
                    self._last_input_text = line
                    code_input.value = ""
                    code_input.cursor_position = 0
                    code_input.autocomplete_matches = []
                    code_input.exact_match_display = ""
                    try:
                        recall = self.query_one("#repl-recall-hint", RecallHint)
                        recall.set_last_command(line)
                    except Exception:
                        pass
                    self.post_message(ReplCommandSubmitted(self._room, [line]))
                elif self._last_input_text:
                    # Enter on empty: recall last command
                    code_input.value = self._last_input_text
                    code_input.cursor_position = len(code_input.value)
                try:
                    self.query_one("#repl-example-hint", ExampleHint).advance()
                except Exception:
                    pass
                return

            if action.action == 'backspace' and action.is_down:
                pos = code_input.cursor_position
                if pos > 0:
                    code_input.value = code_input.value[:pos - 1] + code_input.value[pos:]
                    code_input.cursor_position = pos - 1
                return

            if action.action == 'space' and action.is_down:
                pos = code_input.cursor_position
                code_input.value = code_input.value[:pos] + " " + code_input.value[pos:]
                code_input.cursor_position = pos + 1
                return

            if action.action == 'escape' and action.is_down and not action.is_repeat:
                # Escape clears input text, but does not close the panel
                if code_input.value:
                    code_input.value = ""
                    code_input.cursor_position = 0
                    code_input.autocomplete_matches = []
                    code_input.exact_match_display = ""
                return

            return

        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            char = action.char
            if not char:
                return
            pos = code_input.cursor_position
            code_input.value = code_input.value[:pos] + char + code_input.value[pos:]
            code_input.cursor_position = pos + 1
