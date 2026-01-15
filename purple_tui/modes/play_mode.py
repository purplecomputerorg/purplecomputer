"""
Play Mode: Music and Art Grid

A rectangular grid mapped to QWERTY keyboard.
Press keys to play sounds and cycle colors.

Keyboard input is received via handle_keyboard_action() from the main app,
which reads directly from evdev.
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

from ..keyboard import CharacterAction

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

# Initialize mixer at module load time (before UI shows) to avoid click later
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
    pygame.mixer.set_num_channels(16)
    _MIXER_READY = True
except pygame.error:
    _MIXER_READY = False


# 10x4 grid matching keyboard layout
GRID_KEYS = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';'],
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/'],
]

# All keys in a flat list for indexing
ALL_KEYS = [key for row in GRID_KEYS for key in row]

# Simple color cycle: purple → blue → red → default
COLORS = ["#da77f2", "#4dabf7", "#ff6b6b", None]

# Default backgrounds (dark and light themes)
DEFAULT_BG_DARK = "#2a1845"
DEFAULT_BG_LIGHT = "#e8daf0"

# Light colors need dark text
LIGHT_COLORS = {"#da77f2", "#4dabf7", "#ff6b6b"}


class PlayGrid(Widget):
    """Single widget that renders the entire 10x4 grid manually."""

    DEFAULT_CSS = """
    PlayGrid {
        width: 100%;
        height: 100%;
    }
    """

    CLASSES = "caps-sensitive"

    def __init__(self) -> None:
        super().__init__()
        # Color state for each key: -1 = default, 0+ = index into COLORS
        self.color_state: dict[str, int] = {k: -1 for k in ALL_KEYS}
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._sounds_loaded = False

    def _caps_key(self, key: str) -> str:
        """Transform key label based on caps mode."""
        if key.isalpha():
            if hasattr(self.app, 'caps_mode') and self.app.caps_mode:
                return key.upper()
            return key.lower()
        return key

    def _ensure_sounds_loaded(self) -> None:
        """Load sounds if not already loaded."""
        if self._sounds_loaded or not _MIXER_READY:
            return
        self._load_sounds()
        self._sounds_loaded = True

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
                    sound.set_volume(0.3)  # Lower volume prevents clipping with many simultaneous sounds
                    self._sounds[key] = sound
                except pygame.error:
                    pass

    def play_sound(self, key: str) -> None:
        """Play sound for a key (respects app volume setting)."""
        # Check if volume is muted at app level
        if hasattr(self.app, 'volume_on') and not self.app.volume_on:
            return
        self._ensure_sounds_loaded()
        if key in self._sounds:
            self._sounds[key].play()

    def cleanup_sounds(self) -> None:
        """Stop all currently playing sounds and clear loaded sounds."""
        if _MIXER_READY:
            pygame.mixer.stop()
        self._sounds.clear()
        self._sounds_loaded = False

    def reset_colors(self) -> None:
        """Reset all key colors to default state."""
        self.color_state = {k: -1 for k in ALL_KEYS}
        self.refresh()

    def next_color(self, key: str) -> None:
        """Cycle color for a key."""
        self.color_state[key] = (self.color_state[key] + 1) % len(COLORS)
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

        # Calculate cell dimensions. All cells equal size
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

        # Grid cells. All equal width
        for col_idx in range(10):
            key = GRID_KEYS[row_idx][col_idx]
            bg_color = self.get_color(key)

            # Determine text color based on background brightness
            light_backgrounds = LIGHT_COLORS | {DEFAULT_BG_LIGHT}
            text_color = "#1e1033" if bg_color in light_backgrounds else "white"

            cell_bg_style = Style(bgcolor=bg_color)
            text_style = Style(bgcolor=bg_color, color=text_color, bold=True)

            if line_in_cell == mid_line:
                # Center the key character
                pad_left = (cell_width - 1) // 2
                pad_right = cell_width - pad_left - 1
                segments.append(Segment(" " * pad_left, cell_bg_style))
                segments.append(Segment(self._caps_key(key), text_style))
                segments.append(Segment(" " * pad_right, cell_bg_style))
            else:
                segments.append(Segment(" " * cell_width, cell_bg_style))

        # Right margin
        margin_right = width - margin_left - grid_width
        if margin_right > 0:
            segments.append(Segment(" " * margin_right, bg_style))

        return Strip(segments)


class PlayExampleHint(Static):
    """Shows example hint with caps support"""

    CLASSES = "caps-sensitive"

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Try pressing letters and numbers!")
        return f"[dim]{text}[/]"


class PlayMode(Container, can_focus=True):
    """Play Mode: press keys to make sounds and colors."""

    DEFAULT_CSS = """
    PlayMode {
        width: 100%;
        height: 100%;
    }

    PlayGrid {
        width: 100%;
        height: 1fr;
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

    def compose(self) -> ComposeResult:
        self.grid = PlayGrid()
        yield self.grid
        yield PlayExampleHint(id="example-hint")

    def on_mount(self) -> None:
        self.focus()

    def on_unmount(self) -> None:
        if self.grid:
            self.grid.cleanup_sounds()

    def reset_state(self) -> None:
        """Reset play mode state (colors). Called when leaving mode."""
        if self.grid:
            self.grid.reset_colors()

    async def handle_keyboard_action(self, action) -> None:
        """
        Handle keyboard actions from the main app's KeyboardStateMachine.

        Play mode is simple: character keys cycle colors and play sounds.
        """
        # Character keys cycle colors and play sounds
        if isinstance(action, CharacterAction):
            char = action.char
            if not char:
                return

            lookup = char.upper() if char.isalpha() else char

            if lookup in ALL_KEYS:
                self.grid.next_color(lookup)
                self.grid.play_sound(lookup)
            return
