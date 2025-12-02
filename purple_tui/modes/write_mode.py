"""
Write Mode - Simple Text Editor for Kids

A blank screen with large font for typing:
- Letters, numbers, symbols only
- Sticky shift (toggle, don't hold)
- Caps lock works as expected
- Backspace works
- Enter creates new line
- Arrow keys and other modifiers do nothing
"""

from textual.widgets import Static, TextArea
from textual.containers import Container
from textual.app import ComposeResult
from textual import events

from ..constants import DOUBLE_TAP_TIME


class KidTextArea(TextArea):
    """
    Simple text area with kid-safe key handling.

    Only allows:
    - Letters, numbers, standard symbols
    - Backspace (delete)
    - Enter (new line)
    - Double-tap for shifted symbols (e.g., 88 fast = *)
    """

    # Map of unshifted -> shifted characters
    # NOTE: 0-9 excluded - numbers used for math and mode switching
    SHIFT_MAP = {
        '-': '_', '=': '+', '[': '{', ']': '}', '\\': '|',
        ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
        '`': '~',
    }

    DEFAULT_CSS = """
    KidTextArea {
        width: 100%;
        height: 100%;
        border: none;
        background: $surface;
    }

    KidTextArea:focus {
        border: none;
    }

    KidTextArea > .text-area--cursor-line {
        background: $surface;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_char = None
        self.last_char_time = 0
        self._recent_letters = []

    def _update_caps_mode(self, char: str) -> None:
        """Track caps mode based on recent letter keypresses"""
        if char and char.isalpha():
            self._recent_letters.append(char)
            self._recent_letters = self._recent_letters[-4:]
            if len(self._recent_letters) >= 4:
                new_caps = all(c.isupper() for c in self._recent_letters)
                if hasattr(self.app, 'caps_mode') and new_caps != self.app.caps_mode:
                    self.app.caps_mode = new_caps
                    if hasattr(self.app, '_refresh_caps_sensitive_widgets'):
                        self.app._refresh_caps_sensitive_widgets()

    def on_key(self, event: events.Key) -> None:
        """Filter keys for kid-safe editing"""
        import time

        key = event.key
        char = event.character

        # Track caps mode
        self._update_caps_mode(char)

        # Check for hold mode switching (0-4 keys)
        if hasattr(self.app, 'check_hold_mode_switch'):
            def delete_last_char():
                # Remove the digit that was typed on first press
                self.action_delete_left()
            if self.app.check_hold_mode_switch(key, delete_last_char):
                event.stop()
                event.prevent_default()
                return

        # Allow: backspace, enter
        if key in ("backspace", "enter"):
            self.last_char = None
            return  # Let default handling work

        # Block: arrows, ctrl combos, function keys, etc.
        blocked_keys = [
            "up", "down", "left", "right",
            "home", "end", "pageup", "pagedown",
            "insert", "delete", "escape", "tab",
        ]

        if key in blocked_keys:
            event.stop()
            event.prevent_default()
            return

        # Block non-printable keys (except allowed ones above)
        if not event.is_printable and key not in ("backspace", "enter"):
            event.stop()
            event.prevent_default()
            return

        # Check for double-tap to get shifted character
        if char and char in self.SHIFT_MAP:
            now = time.time()
            if self.last_char == char and (now - self.last_char_time) < DOUBLE_TAP_TIME:
                # Double-tap detected - replace last char with shifted version
                event.stop()
                event.prevent_default()
                # Delete the previous character and insert shifted
                self.action_delete_left()
                self.insert(self.SHIFT_MAP[char])
                self.last_char = None
                return
            else:
                # First tap - remember it
                self.last_char = char
                self.last_char_time = now
        else:
            self.last_char = None


class WriteHeader(Static):
    """Shows header with caps support"""

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Type anything you want!")
        return f"[dim]{text}[/]"


class WriteMode(Container):
    """
    Write Mode - Simple text editor for small kids.

    A blank screen where kids can type freely.
    No distractions, no complex features.
    """

    DEFAULT_CSS = """
    WriteMode {
        width: 100%;
        height: 100%;
        padding: 1;
        background: $surface;
    }

    #write-header {
        height: 1;
        dock: top;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
        background: $surface;
    }

    #write-area {
        width: 100%;
        height: 1fr;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        yield WriteHeader(id="write-header")
        yield KidTextArea(id="write-area")

    def on_mount(self) -> None:
        """Focus the text area when mode loads"""
        self.query_one("#write-area").focus()
