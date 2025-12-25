"""
Write Mode: Simple Text Editor for Kids

A blank screen with large font for typing:
- Letters, numbers, symbols only
- Sticky shift (toggle, don't hold)
- Caps lock works as expected
- Backspace works
- Enter creates new line
- Up/Down arrows scroll the text
- Color mixing: keyboard rows (top=red, middle=blue, bottom=yellow) mix colors
- Storage bins: F5 to save, F6 to load (5 slots)
- F10: Clear all text (with confirmation)
"""

from collections import deque
from enum import Enum
from pathlib import Path
import json

from textual.widgets import Static, TextArea
from textual.containers import Container, Vertical
from textual.app import ComposeResult
from textual.message import Message
from textual import events

from ..constants import DOUBLE_TAP_TIME
from ..keyboard import SHIFT_MAP
from ..color_mixing import mix_colors_paint
from ..scrolling import scroll_widget


# Number of storage slots
NUM_SLOTS = 5

# Slot mode states
class SlotMode(Enum):
    IDLE = "idle"
    SAVING = "saving"
    LOADING = "loading"
    CONFIRM_CLEAR = "confirm_clear"


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
# 10-12 feels responsive but smooth. You can reach pure colors
# but transitions still feel gradual
COLOR_MEMORY_SIZE = 12


class ColorKeyPressed(Message):
    """Message sent when a color-row key is pressed (internal to WriteMode)"""
    def __init__(self, row: str) -> None:
        self.row = row  # "top", "middle", or "bottom"
        super().__init__()


class SlotKeyPressed(Message):
    """Message sent when a slot-related key is pressed during slot mode"""
    def __init__(self, key: str) -> None:
        self.key = key  # "1"-"5", "escape", or "f10"
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
        self.slot_mode_active = False  # Set by WriteMode when in save/load/clear mode

    def on_key(self, event: events.Key) -> None:
        """Filter keys for kid-safe editing"""
        import time

        key = event.key
        char = event.character

        # When in slot mode, capture 1-5, escape, f10 and send to WriteMode
        if self.slot_mode_active:
            if key in ("1", "2", "3", "4", "5", "escape", "f10"):
                event.stop()
                event.prevent_default()
                self.post_message(SlotKeyPressed(key))
                return

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

        # Let F5/F6/F10/F11 bubble up to WriteMode/App for slot/volume handling
        if key in ("f5", "f6", "f10", "f11"):
            return  # Don't stop, let it bubble

        # Block non-printable keys (except allowed ones above)
        if not event.is_printable and key not in ("backspace", "enter"):
            event.stop()
            event.prevent_default()
            return

        # Check for double-tap to get shifted character
        if char and char in SHIFT_MAP:
            now = time.time()
            if self.last_char == char and (now - self.last_char_time) < DOUBLE_TAP_TIME:
                # Double-tap detected. Replace last char with shifted version
                event.stop()
                event.prevent_default()
                # Delete the previous character and insert shifted
                self.action_delete_left()
                self.insert(SHIFT_MAP[char])
                self.last_char = None
                return
            else:
                # First tap. Remember it
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
    """Shows header with caps support, also shows slot mode prompts"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._slot_mode = SlotMode.IDLE
        self._slot_previews: list[str] = [""] * NUM_SLOTS

    def set_slot_mode(self, mode: SlotMode, previews: list[str] | None = None) -> None:
        self._slot_mode = mode
        if previews:
            self._slot_previews = previews
        self.refresh()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)

        if self._slot_mode == SlotMode.SAVING:
            return f"[bold yellow]{caps('Save to which slot?')}[/] [dim](1-5 or Esc)[/]"
        elif self._slot_mode == SlotMode.LOADING:
            return f"[bold cyan]{caps('Load from which slot?')}[/] [dim](1-5 or Esc)[/]"
        elif self._slot_mode == SlotMode.CONFIRM_CLEAR:
            return f"[bold red]{caps('Erase everything?')}[/] [dim](F10 yes, Esc no)[/]"
        else:
            text = caps("Type anything you want!")
            return f"[dim]{text}[/]"


class SlotIndicator(Static):
    """A single storage slot indicator"""

    DEFAULT_CSS = """
    SlotIndicator {
        width: 3;
        height: 3;
        content-align: center middle;
        border: round $primary-darken-2;
        margin-bottom: 1;
    }

    SlotIndicator.filled {
        border: round $accent;
    }

    SlotIndicator.highlighted {
        border: round $warning;
        background: $warning 20%;
    }
    """

    def __init__(self, slot_num: int, **kwargs):
        super().__init__(**kwargs)
        self.slot_num = slot_num
        self._filled = False
        self._highlighted = False

    def set_filled(self, filled: bool) -> None:
        self._filled = filled
        self.remove_class("filled")
        if filled:
            self.add_class("filled")
        self.refresh()

    def set_highlighted(self, highlighted: bool) -> None:
        self._highlighted = highlighted
        self.remove_class("highlighted")
        if highlighted:
            self.add_class("highlighted")
        self.refresh()

    def render(self) -> str:
        num = str(self.slot_num)
        if self._filled:
            # Show filled indicator
            return f"[bold]{num}[/]\n[bold $accent]●[/]"
        else:
            return f"{num}\n[dim]○[/]"


class SlotStrip(Vertical):
    """Vertical strip of storage slot indicators"""

    DEFAULT_CSS = """
    SlotStrip {
        width: 5;
        height: 100%;
        dock: right;
        padding: 1 1;
        background: $surface;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._slots: list[SlotIndicator] = []

    def compose(self) -> ComposeResult:
        for i in range(1, NUM_SLOTS + 1):
            indicator = SlotIndicator(i, id=f"slot-{i}")
            self._slots.append(indicator)
            yield indicator

    def update_slot(self, slot_num: int, filled: bool) -> None:
        """Update whether a slot is filled"""
        if 1 <= slot_num <= NUM_SLOTS:
            try:
                indicator = self.query_one(f"#slot-{slot_num}", SlotIndicator)
                indicator.set_filled(filled)
            except Exception:
                pass

    def highlight_all(self, highlight: bool) -> None:
        """Highlight all slots (for save/load mode)"""
        for i in range(1, NUM_SLOTS + 1):
            try:
                indicator = self.query_one(f"#slot-{i}", SlotIndicator)
                indicator.set_highlighted(highlight)
            except Exception:
                pass


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


def get_slots_file() -> Path:
    """Get path to slots storage file"""
    purple_dir = Path.home() / ".purple"
    purple_dir.mkdir(exist_ok=True)
    return purple_dir / "write_slots.json"


def load_slots() -> dict[int, str]:
    """Load slots from disk"""
    slots_file = get_slots_file()
    if slots_file.exists():
        try:
            with open(slots_file) as f:
                data = json.load(f)
                # Convert string keys back to int
                return {int(k): v for k, v in data.items()}
        except Exception:
            pass
    return {}


def save_slots(slots: dict[int, str]) -> None:
    """Save slots to disk"""
    slots_file = get_slots_file()
    try:
        with open(slots_file, "w") as f:
            json.dump(slots, f)
    except Exception:
        pass


class WriteMode(Container):
    """
    Write Mode: Simple text editor for small kids.

    A blank screen where kids can type freely.
    Border color changes as you type based on keyboard row:
    - Top row (qwerty...): red
    - Middle row (asdf...): blue
    - Bottom row (zxcv...): yellow

    Storage bins (F5/F6):
    - F5: Enter save mode, then press 1-5 to save
    - F6: Enter load mode, then press 1-5 to load
    - F10: Clear all text (with confirmation)
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

    #write-main {
        width: 100%;
        height: 1fr;
        layout: horizontal;
    }

    #write-container {
        width: 1fr;
        height: 100%;
    }

    #write-area {
        width: 100%;
        height: 100%;
    }

    #slot-strip {
        width: 5;
        height: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._color_mixer = ColorMixer()
        self._current_border_color: str | None = None
        self._slot_mode = SlotMode.IDLE
        self._slots: dict[int, str] = load_slots()

    def compose(self) -> ComposeResult:
        yield WriteHeader(id="write-header")
        with Container(id="write-main"):
            yield WriteAreaContainer(id="write-container")
            yield SlotStrip(id="slot-strip")

    def on_mount(self) -> None:
        """Focus the text area when mode loads."""
        self.query_one("#write-area").focus()
        # Update slot indicators based on loaded data
        self._update_slot_indicators()

    def _update_slot_indicators(self) -> None:
        """Update all slot indicators based on current slot data"""
        try:
            strip = self.query_one("#slot-strip", SlotStrip)
            for i in range(1, NUM_SLOTS + 1):
                strip.update_slot(i, bool(self._slots.get(i)))
        except Exception:
            pass

    def _set_slot_mode(self, mode: SlotMode) -> None:
        """Set the current slot mode and update UI"""
        self._slot_mode = mode
        try:
            # Tell KidTextArea to pass through slot keys when in slot mode
            text_area = self.query_one("#write-area", KidTextArea)
            text_area.slot_mode_active = mode != SlotMode.IDLE
        except Exception:
            pass
        try:
            header = self.query_one("#write-header", WriteHeader)
            header.set_slot_mode(mode)
            strip = self.query_one("#slot-strip", SlotStrip)
            strip.highlight_all(mode in (SlotMode.SAVING, SlotMode.LOADING))
        except Exception:
            pass

    def _save_to_slot(self, slot_num: int) -> None:
        """Save current text to a slot"""
        try:
            text_area = self.query_one("#write-area", KidTextArea)
            text = text_area.text
            if text:  # Only save if there's content
                self._slots[slot_num] = text
                save_slots(self._slots)
                self._update_slot_indicators()
        except Exception:
            pass
        self._set_slot_mode(SlotMode.IDLE)
        # Re-focus text area
        try:
            self.query_one("#write-area").focus()
        except Exception:
            pass

    def _load_from_slot(self, slot_num: int) -> None:
        """Load text from a slot"""
        try:
            text = self._slots.get(slot_num, "")
            if text:
                text_area = self.query_one("#write-area", KidTextArea)
                text_area.clear()
                text_area.insert(text)
        except Exception:
            pass
        self._set_slot_mode(SlotMode.IDLE)
        # Re-focus text area
        try:
            self.query_one("#write-area").focus()
        except Exception:
            pass

    def _clear_all_text(self) -> None:
        """Clear all text in the editor"""
        try:
            text_area = self.query_one("#write-area", KidTextArea)
            text_area.clear()
        except Exception:
            pass
        self._set_slot_mode(SlotMode.IDLE)
        # Re-focus text area
        try:
            self.query_one("#write-area").focus()
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle F5/F6/F10 and slot number keys"""
        key = event.key

        # Handle slot mode keys
        if self._slot_mode == SlotMode.SAVING:
            if key in ("1", "2", "3", "4", "5"):
                event.stop()
                event.prevent_default()
                self._save_to_slot(int(key))
                return
            elif key == "escape":
                event.stop()
                event.prevent_default()
                self._set_slot_mode(SlotMode.IDLE)
                self.query_one("#write-area").focus()
                return

        elif self._slot_mode == SlotMode.LOADING:
            if key in ("1", "2", "3", "4", "5"):
                event.stop()
                event.prevent_default()
                self._load_from_slot(int(key))
                return
            elif key == "escape":
                event.stop()
                event.prevent_default()
                self._set_slot_mode(SlotMode.IDLE)
                self.query_one("#write-area").focus()
                return

        elif self._slot_mode == SlotMode.CONFIRM_CLEAR:
            if key == "f10":
                event.stop()
                event.prevent_default()
                self._clear_all_text()
                return
            elif key == "escape":
                event.stop()
                event.prevent_default()
                self._set_slot_mode(SlotMode.IDLE)
                self.query_one("#write-area").focus()
                return

        # F5 = Save mode
        if key == "f5":
            event.stop()
            event.prevent_default()
            self._set_slot_mode(SlotMode.SAVING)
            return

        # F6 = Load mode
        if key == "f6":
            event.stop()
            event.prevent_default()
            self._set_slot_mode(SlotMode.LOADING)
            return

        # F10 = Clear all (first press shows confirmation)
        if key == "f10":
            event.stop()
            event.prevent_default()
            self._set_slot_mode(SlotMode.CONFIRM_CLEAR)
            return

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

    def on_slot_key_pressed(self, event: SlotKeyPressed) -> None:
        """Handle slot key presses from KidTextArea."""
        key = event.key

        if self._slot_mode == SlotMode.SAVING:
            if key in ("1", "2", "3", "4", "5"):
                self._save_to_slot(int(key))
            elif key == "escape":
                self._set_slot_mode(SlotMode.IDLE)
                self.query_one("#write-area").focus()

        elif self._slot_mode == SlotMode.LOADING:
            if key in ("1", "2", "3", "4", "5"):
                self._load_from_slot(int(key))
            elif key == "escape":
                self._set_slot_mode(SlotMode.IDLE)
                self.query_one("#write-area").focus()

        elif self._slot_mode == SlotMode.CONFIRM_CLEAR:
            if key == "f10":
                self._clear_all_text()
            elif key == "escape":
                self._set_slot_mode(SlotMode.IDLE)
                self.query_one("#write-area").focus()
