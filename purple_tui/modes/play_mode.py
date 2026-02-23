"""
Play Mode: Music and Art Grid

A rectangular grid mapped to QWERTY keyboard.
Press keys to play sounds and cycle colors.
Tab switches between Music and Letters sub-modes.
Space replays the current session.

Keyboard input is received via handle_keyboard_action() from the main app,
which reads directly from evdev.
"""

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from rich.segment import Segment
from rich.style import Style
from pathlib import Path
import asyncio
import os
import time

from ..keyboard import CharacterAction, ControlAction
from ..play_constants import GRID_KEYS, ALL_KEYS, COLORS
from ..play_session import PlaySession, SUBMODE_MUSIC, SUBMODE_LETTERS

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


# Default backgrounds (dark and light themes)
DEFAULT_BG_DARK = "#2a1845"
DEFAULT_BG_LIGHT = "#e8daf0"

# Light colors need dark text
LIGHT_COLORS = {"#da77f2", "#4dabf7", "#ff6b6b"}

# Letters that get spoken in Letters mode (A-Z only, not numbers or punctuation)
_LETTER_KEYS = {k for k in ALL_KEYS if k.isalpha()}

REPLAY_MAX_DURATION = 10.0  # hard cap on replay length (seconds)


class PlayModeHeader(Static):
    """Shows current sub-mode with both options visible, current highlighted.

    Follows the same pattern as DoodleMode's CanvasHeader.
    """

    DEFAULT_CSS = """
    PlayModeHeader {
        height: 1;
        dock: top;
        text-align: center;
        color: $text-muted;
        background: $surface;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._letters_mode = False
        self.add_class("caps-sensitive")

    def update_mode(self, letters_mode: bool) -> None:
        self._letters_mode = letters_mode
        self.refresh()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        music_label = caps("Music")
        letters_label = caps("Letters")

        if self._letters_mode:
            music_part = f"[dim]♪ {music_label}[/]"
            letters_part = f"[bold]{letters_label}[/]"
        else:
            music_part = f"[bold]♪ {music_label}[/]"
            letters_part = f"[dim]{letters_label}[/]"

        return f"{music_part}  [dim]{caps('Tab')}[/]  {letters_part}"


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
        self._sounds_loaded = False
        self._letter_sounds: dict[str, pygame.mixer.Sound] = {}
        self._letter_sounds_loaded = False

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
        """Play instrument sound for a key (respects app volume setting)."""
        # Check if volume is muted at app level
        if hasattr(self.app, 'volume_on') and not self.app.volume_on:
            return
        self._ensure_sounds_loaded()
        if key in self._sounds:
            self._sounds[key].play()

    def _ensure_letter_sounds_loaded(self) -> None:
        """Load letter sounds if not already loaded."""
        if self._letter_sounds_loaded or not _MIXER_READY:
            return
        self._load_letter_sounds()
        self._letter_sounds_loaded = True

    def _load_letter_sounds(self) -> None:
        """Load pregenerated letter name clips from the letters/ subdirectory."""
        sounds_path = self._get_sounds_path()
        letters_path = sounds_path / "letters"
        if not letters_path.exists():
            return
        for key in _LETTER_KEYS:
            path = letters_path / f"{key.lower()}.wav"
            if path.exists():
                try:
                    sound = pygame.mixer.Sound(str(path))
                    sound.set_volume(0.5)
                    self._letter_sounds[key] = sound
                except pygame.error:
                    pass

    def play_letter(self, key: str) -> None:
        """Play the letter name clip for a key (respects app volume setting)."""
        if hasattr(self.app, 'volume_on') and not self.app.volume_on:
            return
        self._ensure_letter_sounds_loaded()
        if key in self._letter_sounds:
            self._letter_sounds[key].play()

    def cleanup_sounds(self) -> None:
        """Stop all currently playing sounds and clear loaded sounds."""
        if _MIXER_READY:
            pygame.mixer.stop()
        self._sounds.clear()
        self._sounds_loaded = False
        self._letter_sounds.clear()
        self._letter_sounds_loaded = False

    def reset_colors(self) -> None:
        """Reset all key colors to default state."""
        self.color_state = {k: -1 for k in ALL_KEYS}
        self.refresh()

    def next_color(self, key: str) -> None:
        """Cycle color for a key."""
        self.color_state[key] = (self.color_state[key] + 1) % len(COLORS)
        self.refresh()

    def set_color_index(self, key: str, index: int) -> None:
        """Set a key's color to a specific index.

        Used by demo player for "flash" effects where keys light up
        momentarily then turn off.

        Args:
            key: The key to set (e.g., 'A', '5')
            index: Color index: 0=purple, 1=blue, 2=red, -1=off
        """
        if key in self.color_state:
            self.color_state[key] = index
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
                segments.append(Segment(key, text_style))
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Try pressing letters and numbers!")
        return f"[dim]{text}[/]"


class PlayMode(Container, can_focus=True):
    """Play Mode: press keys to make sounds and colors.

    Sub-modes (switched with Tab):
      Music: all keys play instrument sounds
      Letters: letter keys (A-Z) are spoken aloud, other keys play sounds
    """

    DEFAULT_CSS = """
    PlayMode {
        width: 100%;
        height: 100%;
    }

    PlayModeHeader {
        height: 1;
        dock: top;
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
        self._header: PlayModeHeader | None = None
        self.session = PlaySession()
        self._replay_task: asyncio.Task | None = None
        self._letters_mode = False

    def compose(self) -> ComposeResult:
        self._header = PlayModeHeader(id="play-header")
        yield self._header
        self.grid = PlayGrid()
        yield self.grid
        yield PlayExampleHint(id="example-hint")

    def on_mount(self) -> None:
        self.focus()

    def on_unmount(self) -> None:
        if self._replay_task and not self._replay_task.done():
            self._replay_task.cancel()
            self._replay_task = None
        if self.grid:
            self.grid.cleanup_sounds()

    def reset_state(self) -> None:
        """Reset play mode state (colors, session, replay). Called when leaving mode."""
        if self._replay_task and not self._replay_task.done():
            self._replay_task.cancel()
            self._replay_task = None
        self.session.clear()
        if self.grid:
            self.grid.reset_colors()

    def _current_submode(self) -> str:
        return SUBMODE_LETTERS if self._letters_mode else SUBMODE_MUSIC

    def _play_key(self, key: str, submode: str) -> None:
        """Play audio for a key in the given sub-mode.

        In music mode, all keys play instrument sounds.
        In letters mode, letter keys (A-Z) play their letter name clip,
        other keys (numbers, punctuation) still play instrument sounds.
        """
        if submode == SUBMODE_LETTERS and key in _LETTER_KEYS:
            self.grid.play_letter(key)
        else:
            self.grid.play_sound(key)

    async def handle_keyboard_action(self, action) -> None:
        """
        Handle keyboard actions from the main app's KeyboardStateMachine.

        Tab switches between Music and Letters sub-modes.
        Character keys cycle colors, play sounds or speak, and are recorded.
        Space triggers replay of the current session, then starts a new one.
        Keys pressed during replay are recorded in the new session.
        """
        if isinstance(action, ControlAction) and action.is_down:
            # Space: stop replay if playing, otherwise start replay
            if action.action == 'space':
                if self._replay_task and not self._replay_task.done():
                    self._replay_task.cancel()
                    self._replay_task = None
                else:
                    await self._start_replay()
                return

            # Tab switches sub-mode
            if action.action == 'tab':
                self._letters_mode = not self._letters_mode
                if self._header:
                    self._header.update_mode(self._letters_mode)
                return

        # Character keys cycle colors, play/speak, and record
        if isinstance(action, CharacterAction):
            char = action.char
            if not char:
                return

            lookup = char.upper() if char.isalpha() else char

            if lookup in ALL_KEYS:
                submode = self._current_submode()
                self.session.record(lookup, submode)
                self.grid.next_color(lookup)
                self._play_key(lookup, submode)
            return

    async def _start_replay(self) -> None:
        """Start replaying the current session."""
        replay_data = self.session.get_replay()
        if not replay_data:
            return

        # End current session and start fresh (new keys record to new session)
        self.session.clear()

        # Cancel any existing replay
        if self._replay_task and not self._replay_task.done():
            self._replay_task.cancel()

        self._replay_task = asyncio.create_task(self._do_replay(replay_data))

    async def _do_replay(self, replay_data: list[tuple[str, str, float]]) -> None:
        """Play back recorded key sequence with original timing and sub-modes.

        Stops silently after REPLAY_MAX_DURATION seconds.
        Can also be cancelled by pressing space.
        """
        try:
            start = time.monotonic()
            for key, submode, delay in replay_data:
                if delay > 0:
                    await asyncio.sleep(delay)
                if time.monotonic() - start >= REPLAY_MAX_DURATION:
                    break
                self.grid.next_color(key)
                self._play_key(key, submode)
        except asyncio.CancelledError:
            pass
