"""
Play Mode - Music and Art Grid

A rectangular grid mapped to QWERTY keyboard.
Press keys to play sounds and cycle colors.
"""

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from textual import events
from rich.segment import Segment
from rich.style import Style
from pathlib import Path
import os

# Suppress ALSA error/log messages before pygame imports ALSA.
# These corrupt Textual's stderr-based UI. Install null handlers for both paths.
def _suppress_alsa_output():
    try:
        import ctypes
        import ctypes.util

        # Find libasound
        path = ctypes.util.find_library('asound')
        if not path:
            for p in ('libasound.so.2', 'libasound.so'):
                try:
                    path = p
                    ctypes.CDLL(p)
                    break
                except OSError:
                    path = None
        if not path:
            return

        asound = ctypes.CDLL(path)

        # Handler types: error has int err, log has uint level
        HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                   ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
        LOG_HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                       ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p)

        noop = lambda *_: None
        err_h, log_h = HANDLER(noop), LOG_HANDLER(noop)
        _suppress_alsa_output._refs = (err_h, log_h)  # prevent GC

        asound.snd_lib_error_set_handler(err_h)
        try:
            asound.snd_lib_log_set_handler(log_h)
        except AttributeError:
            pass
    except Exception:
        pass

_suppress_alsa_output()

# Suppress pygame welcome message (must be set before import)
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame.mixer

from ..constants import TOGGLE_DEBOUNCE, ICON_ERASER, ICON_PALETTE


# 10x4 grid matching keyboard layout
GRID_KEYS = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';'],
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/'],
]

# All keys in a flat list for indexing
ALL_KEYS = [key for row in GRID_KEYS for key in row]

# Rainbow colors + None (back to default)
COLORS = ["#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#4dabf7", "#da77f2", None]

# Default backgrounds (dark and light themes)
DEFAULT_BG_DARK = "#2a1845"
DEFAULT_BG_LIGHT = "#e8daf0"

# Light colors need dark text
LIGHT_COLORS = {"#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#4dabf7", "#da77f2"}


class PlayGrid(Widget):
    """Single widget that renders the entire 10x4 grid manually."""

    DEFAULT_CSS = """
    PlayGrid {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        # Color state for each key: -1 = default, 0+ = index into COLORS
        self.color_state: dict[str, int] = {k: -1 for k in ALL_KEYS}
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._mixer_initialized = False
        # Flash keys for visual feedback in clear mode
        self._flash_keys: set[str] = set()

    def _init_audio(self) -> None:
        """Initialize pygame mixer and load sounds."""
        if self._mixer_initialized:
            return
        try:
            # Larger buffer (2048) prevents ALSA underrun errors on slower hardware
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.set_num_channels(16)
            self._mixer_initialized = True
            self._load_sounds()
        except pygame.error:
            pass

    def _get_sounds_path(self) -> Path:
        """Find the sounds directory."""
        paths = [
            Path(__file__).parent.parent.parent / "packs" / "core-sounds" / "content",
            Path.home() / ".purple" / "packs" / "core-sounds" / "content",
        ]
        for p in paths:
            if p.exists():
                return p
        return paths[0]

    def _load_sounds(self) -> None:
        """Load all sounds into memory."""
        sounds_path = self._get_sounds_path()
        names = {';': 'semicolon', ',': 'comma', '.': 'period', '/': 'slash'}
        for key in ALL_KEYS:
            name = names.get(key, key.lower())
            path = sounds_path / f"{name}.wav"
            if path.exists():
                try:
                    sound = pygame.mixer.Sound(str(path))
                    sound.set_volume(0.4)  # Prevent clipping when multiple sounds play
                    self._sounds[key] = sound
                except pygame.error:
                    pass

    def play_sound(self, key: str) -> None:
        """Play sound for a key."""
        if not self._mixer_initialized:
            self._init_audio()
        if key in self._sounds:
            self._sounds[key].play()

    def cleanup_sounds(self) -> None:
        """Stop all sounds and quit mixer."""
        if self._mixer_initialized:
            pygame.mixer.stop()
            pygame.mixer.quit()
            self._mixer_initialized = False
        self._sounds.clear()

    def next_color(self, key: str) -> None:
        """Cycle color for a key."""
        self.color_state[key] = (self.color_state[key] + 1) % len(COLORS)
        self.refresh()

    def prev_color(self, key: str) -> None:
        """Undo color cycle for a key (go back one step)."""
        current = self.color_state[key]
        if current == 0:
            # Was at first color, go back to no color
            self.color_state[key] = -1
        elif current == -1:
            # Was at no color, wrap to last color
            self.color_state[key] = len(COLORS) - 1
        else:
            self.color_state[key] = current - 1
        self.refresh()

    def clear_color(self, key: str) -> None:
        """Reset a key to default color."""
        self.color_state[key] = -1
        self._flash_keys.add(key)
        self.refresh()

    def clear_flash(self, key: str) -> None:
        """Clear the flash indicator for a specific key."""
        self._flash_keys.discard(key)
        self.refresh()

    def _get_default_bg(self) -> str:
        """Get default background based on current theme."""
        try:
            is_dark = "dark" in self.app.theme
            return DEFAULT_BG_DARK if is_dark else DEFAULT_BG_LIGHT
        except Exception:
            return DEFAULT_BG_DARK

    def get_color(self, key: str) -> str:
        """Get current color for a key."""
        idx = self.color_state[key]
        if idx < 0 or COLORS[idx] is None:
            return self._get_default_bg()
        return COLORS[idx]

    def render_line(self, y: int) -> Strip:
        """Render a single line of the grid."""
        width = self.size.width
        height = self.size.height

        # Calculate cell dimensions - all cells equal size
        cell_width = width // 10
        cell_height = height // 4

        # Calculate grid dimensions and margins to center it
        grid_width = cell_width * 10
        grid_height = cell_height * 4
        margin_left = (width - grid_width) // 2
        margin_top = (height - grid_height) // 2

        default_bg = self._get_default_bg()
        bg_style = Style(bgcolor=default_bg)

        # Above or below the grid?
        if y < margin_top or y >= margin_top + grid_height:
            return Strip([Segment(" " * width, bg_style)])

        # Which row of the grid?
        grid_y = y - margin_top
        row_idx = grid_y // cell_height if cell_height > 0 else 0
        if row_idx >= 4:
            return Strip([Segment(" " * width, bg_style)])

        # Which line within the cell?
        line_in_cell = grid_y % cell_height if cell_height > 0 else 0
        mid_line = cell_height // 2

        segments = []

        # Left margin
        if margin_left > 0:
            segments.append(Segment(" " * margin_left, bg_style))

        # Grid cells - all equal width
        for col_idx in range(10):
            key = GRID_KEYS[row_idx][col_idx]
            bg_color = self.get_color(key)

            # Flash effect: contrasting color when key is flashed
            is_flashed = key in self._flash_keys
            if is_flashed:
                try:
                    is_dark = "dark" in self.app.theme
                    bg_color = "#4a3866" if is_dark else "#c4b5fd"
                except Exception:
                    bg_color = "#4a3866"

            # Determine text color based on background brightness
            light_backgrounds = LIGHT_COLORS | {DEFAULT_BG_LIGHT, "#c4b5fd"}  # Include light mode default and flash
            text_color = "#1e1033" if bg_color in light_backgrounds else "white"

            cell_bg_style = Style(bgcolor=bg_color)
            text_style = Style(bgcolor=bg_color, color=text_color, bold=True)

            if line_in_cell == mid_line:
                # Center the key character
                pad_left = (cell_width - 1) // 2
                pad_right = cell_width - pad_left - 1
                segments.append(Segment(" " * pad_left, cell_bg_style))
                segments.append(Segment(key, text_style))
                segments.append(Segment(" " * pad_right, cell_bg_style))
            else:
                segments.append(Segment(" " * cell_width, cell_bg_style))

        # Right margin
        margin_right = width - margin_left - grid_width
        if margin_right > 0:
            segments.append(Segment(" " * margin_right, bg_style))

        return Strip(segments)


class EraserModeIndicator(Static):
    """Shows whether eraser mode is on/off - Tab to toggle"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.eraser_on = False
        self._state_before_toggle = False  # Track state before rapid toggles

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        if self.eraser_on:
            return f"[bold #ff6b6b]{ICON_ERASER}  {caps('Tab: eraser ON')}[/]"
        else:
            return f"[dim]{ICON_PALETTE}  {caps('Tab: eraser off')}[/]"

    def _speak_if_changed(self) -> None:
        """Speak current state only if it differs from state before toggle sequence"""
        from ..tts import speak, stop
        stop()  # Cancel any previous
        if self.eraser_on != self._state_before_toggle:
            speak("eraser on" if self.eraser_on else "eraser off")
        # Reset for next toggle sequence
        self._state_before_toggle = self.eraser_on

    def toggle(self) -> bool:
        # On first toggle in a sequence, remember the starting state
        if self.eraser_on == self._state_before_toggle:
            self._state_before_toggle = self.eraser_on

        self.eraser_on = not self.eraser_on

        # Update UI immediately
        self.refresh()

        # Debounce: only speak after delay if state actually changed
        self.set_timer(TOGGLE_DEBOUNCE, self._speak_if_changed)

        return self.eraser_on


class PlayExampleHint(Static):
    """Shows example hint with caps support"""

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Try pressing letters and numbers!")
        return f"[dim]{text}[/]"


class PlayMode(Container, can_focus=True):
    """Play Mode - press keys to make sounds and colors."""

    DEFAULT_CSS = """
    PlayMode {
        width: 100%;
        height: 100%;
    }

    PlayGrid {
        width: 100%;
        height: 1fr;
    }

    #eraser-indicator {
        dock: top;
        height: 1;
        text-align: right;
        padding: 0 1;
    }

    #example-hint {
        dock: bottom;
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.grid: PlayGrid | None = None
        self.eraser_mode = False

    # Block all mouse events
    def on_click(self, event) -> None:
        event.stop()

    def on_mouse_down(self, event) -> None:
        event.stop()

    def on_mouse_up(self, event) -> None:
        event.stop()

    def on_mouse_scroll_down(self, event) -> None:
        event.stop()

    def on_mouse_scroll_up(self, event) -> None:
        event.stop()

    def compose(self) -> ComposeResult:
        yield EraserModeIndicator(id="eraser-indicator")
        self.grid = PlayGrid()
        yield self.grid
        yield PlayExampleHint(id="example-hint")

    def on_mount(self) -> None:
        self.focus()

    def on_unmount(self) -> None:
        if self.grid:
            self.grid.cleanup_sounds()

    def on_key(self, event: events.Key) -> None:
        """Handle key press."""
        key = event.key
        char = event.character or key

        # Tab toggles sticky eraser mode
        if event.key == "tab":
            indicator = self.query_one("#eraser-indicator", EraserModeIndicator)
            self.eraser_mode = indicator.toggle()
            event.stop()
            return

        if not char:
            return

        lookup = char.upper() if char.isalpha() else char

        if lookup in ALL_KEYS:
            event.stop()
            if self.eraser_mode:
                self.grid.clear_color(lookup)
                # Clear flash after brief delay (capture key in lambda)
                self.set_timer(0.3, lambda k=lookup: self.grid.clear_flash(k))
            else:
                self.grid.next_color(lookup)
            self.grid.play_sound(lookup)
