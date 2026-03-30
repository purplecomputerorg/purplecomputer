"""
Shared code input widgets used by Play, Music, and Art rooms.

Provides: CodeInput (Input subclass with pluggable autocomplete),
WordHighlighter, InputPrompt, AutocompleteHint, RecallHint, ExampleHint.
"""

import re
from typing import Callable

from textual.widgets import Static, Input
from textual import events
from textual.message import Message
from rich.highlighter import Highlighter
from rich.text import Text


class WordHighlighter(Highlighter):
    """Underlines words that match a validator function."""

    def __init__(self, validator: Callable[[str], bool]):
        super().__init__()
        self._validator = validator

    def highlight(self, text: Text) -> None:
        plain = str(text).lower()
        for match in re.finditer(r'[a-z]+', plain):
            if self._validator(match.group()):
                text.stylize("underline", match.start(), match.end())


class CodeInput(Input):
    """Input widget with pluggable autocomplete.

    autocomplete_fn: given a partial word, returns list of (word, color_hex, emoji) tuples.
    If math_mode=True, auto-spaces and substitutes math operators.
    """

    DEFAULT_CSS = """
    CodeInput {
        width: 1fr;
        height: 1;
        border: none;
        background: $surface;
        padding: 0;
        margin: 0 0 0 1;
    }

    CodeInput:focus {
        border: none;
    }
    """

    class Submitted(Message, bubble=True):
        """Message sent when user presses Enter."""
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    # Math display substitutions (only used when math_mode=True)
    MATH_DISPLAY = {
        '*': '\u00d7',   # Multiplication sign
        '/': '\u00f7',   # Division sign
    }
    MATH_OPERATORS = {'+', '-', '*', '/'}

    def __init__(self, autocomplete_fn: Callable[[str], list[tuple[str, str, str]]] | None = None,
                 math_mode: bool = False, context_autocomplete: bool = False, **kwargs):
        super().__init__(placeholder="", **kwargs)
        self._autocomplete_fn = autocomplete_fn
        self._math_mode = math_mode
        self._context_autocomplete = context_autocomplete
        self.autocomplete_matches: list[tuple[str, str, str]] = []
        self.autocomplete_type: str = "emoji"
        self.autocomplete_index: int = 0
        self.exact_match_display: str = ""

    async def _on_key(self, event: events.Key) -> None:
        """Suppress terminal key events. All input comes via evdev."""
        event.stop()
        event.prevent_default()

    def _check_autocomplete(self) -> None:
        """Update autocomplete suggestions based on current input."""
        if not self._autocomplete_fn:
            self.autocomplete_matches = []
            self.exact_match_display = ""
            return

        text = self.value.lower().strip()
        match = re.search(r'([a-z]+)$', text)
        last_word = match.group(1) if match else ""

        # Common 2-letter words that shouldn't trigger autocomplete
        COMMON_2CHAR = {'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if',
                        'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so',
                        'to', 'up', 'us', 'we', 'hi', 'oh', 'ok'}

        if len(last_word) < 2 or last_word in COMMON_2CHAR:
            # Context-aware REPL panels (music/art) can handle short words
            # (e.g. "choose " showing instruments, "color " showing colors)
            if self._context_autocomplete and self._autocomplete_fn:
                results = self._autocomplete_fn(last_word, text)
            else:
                results = []
            if not results:
                self.autocomplete_matches = []
                self.autocomplete_type = "emoji"
                self.autocomplete_index = 0
                self.exact_match_display = ""
                return
        else:
            results = self._autocomplete_fn(last_word, text)

        # Separate exact matches from suggestions
        exact = [r for r in results if r[0] == last_word]
        suggestions = [r for r in results if r[0] != last_word]

        if exact:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            parts = []
            _, color_hex, emoji = exact[0]
            if emoji:
                parts.append(emoji)
            if color_hex:
                parts.append(f"[{color_hex}]\u2588\u2588[/]")
            self.exact_match_display = " ".join(parts)
            return

        self.exact_match_display = ""
        combined = suggestions[:5]

        if not combined:
            self.autocomplete_matches = []
            self.autocomplete_type = "emoji"
            self.autocomplete_index = 0
            return

        has_colors = any(c for _, c, _ in combined)
        has_emojis = any(e for _, _, e in combined)

        self.autocomplete_matches = combined
        self.autocomplete_type = "mixed" if (has_colors and has_emojis) else ("color" if has_colors else "emoji")
        self.autocomplete_index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._check_autocomplete()

    @property
    def autocomplete_hint(self) -> str:
        """Get the autocomplete hint markup to display."""
        if self.exact_match_display:
            return self.exact_match_display

        if not self.autocomplete_matches:
            return ""

        caps = getattr(self.app, 'caps_text', lambda x: x)
        shown = self.autocomplete_matches[:5]
        parts = []

        for word, color_hex, emoji in shown:
            display = f"[dim]{caps(word)}[/]"
            if emoji:
                display += f" {emoji}"
            if color_hex:
                display += f" [{color_hex}]\u2588\u2588[/]"
            parts.append(display)

        hint = "   ".join(parts)
        return caps(f"{hint}   [dim]\U000f0312 Tab[/]")


class InputPrompt(Static):
    """Shows 'Ask \u2192' or custom prompt label."""

    DEFAULT_CSS = """
    InputPrompt {
        width: auto;
        height: 1;
        color: $primary;
    }
    """

    def __init__(self, label: str = "Ask", **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")
        self._label = label
        self._block_depth = 0

    def set_block_depth(self, depth: int) -> None:
        self._block_depth = depth
        self.refresh()

    def render(self) -> str:
        if self._block_depth > 0:
            dots = "\u00b7" * self._block_depth
            return f"[bold #9b7bc4]{dots}\u00b7\u00b7[/]"
        text = self.app.caps_text(self._label) if hasattr(self.app, 'caps_text') else self._label
        return f"[bold #c4a0e8]{text} \u2192[/]"


class AutocompleteHint(Static):
    """Shows autocomplete suggestion and help hints."""

    DEFAULT_CSS = """
    AutocompleteHint {
        height: 1;
        color: $text-muted;
        margin-left: 5;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")


class RecallHint(Static):
    """Shows 'Enter to try again' hint when input is empty and there's a previous command."""

    DEFAULT_CSS = """
    RecallHint {
        height: 1;
        color: $text-muted;
        margin-left: 6;
    }
    """

    MAX_RECALL_LEN = 40

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")
        self._last_command: str = ""
        self._visible = False

    def set_last_command(self, command: str) -> None:
        self._last_command = command

    def show_if_empty(self, input_empty: bool) -> None:
        self._visible = input_empty and bool(self._last_command)
        self.refresh()

    def render(self) -> str:
        if not self._visible or not self._last_command:
            return ""
        caps = getattr(self.app, 'caps_text', lambda x: x)
        display = self._last_command
        if len(display) > self.MAX_RECALL_LEN:
            display = display[:self.MAX_RECALL_LEN - 1] + "\u2026"
        return f"[dim]{caps(f'Enter to try again: {display}')}[/]"


class ExampleHint(Static):
    """Shows cycling 'Try' hints."""

    DEFAULT_CSS = """
    ExampleHint {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    DEFAULT_HINTS = [
        "Try: cat  \u2022  5 + 3  \u2022  red + blue",
    ]

    CYCLE_SECONDS = 60

    def __init__(self, hints: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")
        self.HINTS = hints or self.DEFAULT_HINTS
        self._hint_index = 0

    def on_mount(self) -> None:
        self.set_interval(self.CYCLE_SECONDS, self._next_hint)

    def _next_hint(self) -> None:
        self._hint_index = (self._hint_index + 1) % len(self.HINTS)
        self.refresh()

    def advance(self) -> None:
        """Manually advance to next hint (called on Enter)."""
        self._next_hint()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        hint = self.HINTS[self._hint_index]
        return f"[dim]{caps(hint)}[/]"
