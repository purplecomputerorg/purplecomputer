"""
Write Mode - Simple Text Editor for Kids

A blank screen with large font for typing:
- Letters, numbers, symbols only
- Sticky shift (toggle, don't hold)
- Caps lock works as expected
- Backspace works
- Enter creates new line
- Up/Down arrows scroll the text
- Color mixing: keyboard rows (top=red, middle=blue, bottom=yellow) mix colors
"""

from collections import deque

from textual.widgets import Static, TextArea
from textual.containers import Container
from textual.app import ComposeResult
from textual.message import Message
from textual import events

from ..constants import DOUBLE_TAP_TIME
from ..keyboard import SHIFT_MAP
from ..color_mixing import mix_colors_paint
from ..scrolling import scroll_widget


# Keyboard row definitions for color mixing
# Top row: red, Middle row: blue, Bottom row: yellow
TOP_ROW = set("qwertyuiop[]\\")
MIDDLE_ROW = set("asdfghjkl;'")
BOTTOM_ROW = set("zxcvbnm,./")

# Colors for each row (true vibrant primaries)
ROW_COLORS = {
    "top": "#FF0000",      # red
    "middle": "#0066FF",   # blue (true blue, not purple-blue)
    "bottom": "#FFDD00",   # yellow
}

# Starting/neutral color (muted purple to match the app theme)
NEUTRAL_COLOR = "#2a1845"

# How many recent keystrokes to remember for color mixing
# 10-12 feels responsive but smooth - you can reach pure colors
# but transitions still feel gradual
COLOR_MEMORY_SIZE = 12


class ColorKeyPressed(Message):
    """Message sent when a color-row key is pressed (internal to WriteMode)"""
    def __init__(self, row: str) -> None:
        self.row = row  # "top", "middle", or "bottom"
        super().__init__()


class BorderColorChanged(Message, bubble=True):
    """Message sent to app to change viewport border color"""
    def __init__(self, color: str) -> None:
        self.color = color
        super().__init__()


class ColorMixer:
    """
    Tracks recent keystrokes and mixes colors.

    Uses a sliding window of recent keystrokes to determine color.
    Type enough keys from one row and you'll reach that pure color.
    """

    def __init__(self):
        self._color_memory: deque[str] = deque(maxlen=COLOR_MEMORY_SIZE)

    def add_key(self, row: str) -> str | None:
        """Add a new color key and return the new mixed color, or None if invalid."""
        if row not in ROW_COLORS:
            return None

        # Add to sliding window (automatically removes oldest if full)
        self._color_memory.append(row)

        # Mix all colors in the window using paint-like mixing
        if self._color_memory:
            colors = [ROW_COLORS[r] for r in self._color_memory]
            return mix_colors_paint(colors)
        return NEUTRAL_COLOR


def get_row_for_char(char: str) -> str | None:
    """Return which keyboard row a character belongs to, or None if not a row key."""
    char_lower = char.lower()
    if char_lower in TOP_ROW:
        return "top"
    elif char_lower in MIDDLE_ROW:
        return "middle"
    elif char_lower in BOTTOM_ROW:
        return "bottom"
    return None


class KidTextArea(TextArea):
    """
    Simple text area with kid-safe key handling.

    Only allows:
    - Letters, numbers, standard symbols
    - Backspace (delete)
    - Enter (new line)
    - Up/Down arrows (scroll by 5 lines)
    - Double-tap for shifted symbols (e.g., -- fast = _)
    """

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
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_char = None
        self.last_char_time = 0

    def on_key(self, event: events.Key) -> None:
        """Filter keys for kid-safe editing"""
        import time

        key = event.key
        char = event.character

        # Allow: backspace, enter
        if key in ("backspace", "enter"):
            self.last_char = None
            return  # Let default handling work

        # Up/Down arrows scroll the text
        if key == "up":
            event.stop()
            event.prevent_default()
            scroll_widget(self, -1)
            return

        if key == "down":
            event.stop()
            event.prevent_default()
            scroll_widget(self, 1)
            return

        # Block: left/right arrows, ctrl combos, function keys, etc.
        blocked_keys = [
            "left", "right",
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
        if char and char in SHIFT_MAP:
            now = time.time()
            if self.last_char == char and (now - self.last_char_time) < DOUBLE_TAP_TIME:
                # Double-tap detected - replace last char with shifted version
                event.stop()
                event.prevent_default()
                # Delete the previous character and insert shifted
                self.action_delete_left()
                self.insert(SHIFT_MAP[char])
                self.last_char = None
                return
            else:
                # First tap - remember it
                self.last_char = char
                self.last_char_time = now
        else:
            self.last_char = None

        # Notify parent about color key presses (for paint mixing)
        if char:
            row = get_row_for_char(char)
            if row:
                # Post a message to the parent WriteMode
                self.post_message(ColorKeyPressed(row))


class WriteHeader(Static):
    """Shows header with caps support"""

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Type anything you want!")
        return f"[dim]{text}[/]"


class WriteAreaContainer(Container):
    """Container that holds the text area."""

    DEFAULT_CSS = """
    WriteAreaContainer {
        width: 100%;
        height: 1fr;
    }

    WriteAreaContainer > KidTextArea {
        width: 100%;
        height: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield KidTextArea(id="write-area")


class WriteMode(Container):
    """
    Write Mode - Simple text editor for small kids.

    A blank screen where kids can type freely.
    Border color changes as you type based on keyboard row:
    - Top row (qwerty...): red
    - Middle row (asdf...): blue
    - Bottom row (zxcv...): yellow
    """

    DEFAULT_CSS = """
    WriteMode {
        width: 100%;
        height: 100%;
        padding: 0;
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

    #write-container {
        width: 100%;
        height: 1fr;
    }

    #write-area {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._color_mixer = ColorMixer()
        self._current_border_color: str | None = None

    def compose(self) -> ComposeResult:
        yield WriteHeader(id="write-header")
        yield WriteAreaContainer(id="write-container")

    def on_mount(self) -> None:
        """Focus the text area when mode loads."""
        self.query_one("#write-area").focus()

    def restore_border_color(self) -> None:
        """Restore the border color when re-entering write mode."""
        if self._current_border_color:
            self.post_message(BorderColorChanged(self._current_border_color))

    def on_color_key_pressed(self, event: ColorKeyPressed) -> None:
        """Handle color key presses by updating the viewport border color."""
        new_color = self._color_mixer.add_key(event.row)
        if new_color:
            self._current_border_color = new_color
            self.post_message(BorderColorChanged(new_color))
