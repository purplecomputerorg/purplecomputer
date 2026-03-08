"""
Music Room: Music and Art Grid

A rectangular grid mapped to QWERTY keyboard.
Press keys to play sounds and cycle colors.
Tab switches between Music and Letters modes.
Space replays recent session keys (loop feature).

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
from ..keyboard import CharacterAction, ControlAction
from ..music_constants import (
    GRID_KEYS, ALL_KEYS, COLORS, INSTRUMENTS, NOTE_NAMES, PERCUSSION_NAMES,
)
from ..music_session import MusicSession, MODE_MUSIC, MODE_LETTERS
from ..constants import ICON_MUSIC, ICON_MUSIC_NOTE

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

# Light colors need dark text (tinted palette is all dark, so none listed)
LIGHT_COLORS: set[str] = set()

# Keys that get spoken in Letters mode (A-Z and 0-9)
_SPEAKABLE_KEYS = {k for k in ALL_KEYS if k.isalpha() or k.isdigit()}

class MusicRoomHeader(Static):
    """Shows current mode with both options visible, current highlighted.

    Follows the same pattern as ArtMode's CanvasHeader.
    """

    DEFAULT_CSS = """
    MusicRoomHeader {
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
        self._instrument_name = INSTRUMENTS[0][1]
        self.add_class("caps-sensitive")

    def update_mode(self, letters_mode: bool) -> None:
        self._letters_mode = letters_mode
        self.refresh()

    def update_instrument(self, name: str) -> None:
        self._instrument_name = name
        self.refresh()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        instrument_label = caps(self._instrument_name)
        letters_label = caps("Letters")

        if self._letters_mode:
            music_part = f"[dim]{ICON_MUSIC} {instrument_label}[/]"
            letters_part = f"[bold]{letters_label}[/]"
        else:
            music_part = f"[bold]{ICON_MUSIC} {instrument_label}[/]"
            letters_part = f"[dim]{letters_label}[/]"

        return f"{music_part}  [dim]{caps('Tab')}[/]  {letters_part}"


class MusicGrid(Widget):
    """Single widget that renders the entire 10x4 grid manually."""

    DEFAULT_CSS = """
    MusicGrid {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        # Color state for each key: -1 = default, 0+ = index into COLORS
        self.color_state: dict[str, int] = {k: -1 for k in ALL_KEYS}
        self._instrument_index: int = 0
        # Per-instrument sound cache: instrument_id -> {key -> Sound}
        self._instrument_sounds: dict[str, dict[str, pygame.mixer.Sound]] = {}
        # Percussion sounds (shared across instruments)
        self._percussion_sounds: dict[str, pygame.mixer.Sound] = {}
        self._percussion_loaded = False
        self._letter_sounds: dict[str, pygame.mixer.Sound] = {}
        self._letter_sounds_loaded = False
        # Keys currently showing a note/percussion label (brief flash on press)
        self._note_labels: set[str] = set()
        self._note_timers: dict[str, asyncio.TimerHandle] = {}

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

    @staticmethod
    def _find_sound(base: Path, name: str) -> Path | None:
        """Find a sound file, preferring .ogg over .wav."""
        for ext in ('.ogg', '.wav'):
            p = base / f"{name}{ext}"
            if p.exists():
                return p
        return None

    def _ensure_instrument_loaded(self, instrument_id: str) -> None:
        """Load instrument sounds if not already cached."""
        if instrument_id in self._instrument_sounds or not _MIXER_READY:
            return
        sounds_path = self._get_sounds_path()
        inst_path = sounds_path / instrument_id
        names = {';': 'semicolon', ',': 'comma', '.': 'period', '/': 'slash'}
        cache: dict[str, pygame.mixer.Sound] = {}
        for key in ALL_KEYS:
            if key.isdigit():
                continue
            name = names.get(key, key.lower())
            # Try subdirectory first, fall back to flat files
            path = self._find_sound(inst_path, name) or self._find_sound(sounds_path, name)
            if path:
                try:
                    sound = pygame.mixer.Sound(str(path))
                    sound.set_volume(0.3)
                    cache[key] = sound
                except pygame.error:
                    pass
        self._instrument_sounds[instrument_id] = cache

    def _ensure_percussion_loaded(self) -> None:
        """Load percussion sounds (shared across all instruments)."""
        if self._percussion_loaded or not _MIXER_READY:
            return
        sounds_path = self._get_sounds_path()
        for key in ALL_KEYS:
            if not key.isdigit():
                continue
            path = self._find_sound(sounds_path, key)
            if path:
                try:
                    sound = pygame.mixer.Sound(str(path))
                    sound.set_volume(0.3)
                    self._percussion_sounds[key] = sound
                except pygame.error:
                    pass
        self._percussion_loaded = True

    def play_sound(self, key: str) -> None:
        """Play instrument or percussion sound for a key."""
        if hasattr(self.app, 'volume_on') and not self.app.volume_on:
            return
        if key.isdigit():
            self._ensure_percussion_loaded()
            if key in self._percussion_sounds:
                self._percussion_sounds[key].play()
        else:
            inst_id = INSTRUMENTS[self._instrument_index][0]
            self._ensure_instrument_loaded(inst_id)
            sounds = self._instrument_sounds.get(inst_id, {})
            if key in sounds:
                sounds[key].play()

    def set_instrument(self, index: int) -> None:
        """Set the current instrument index."""
        self._instrument_index = index

    def flash_note(self, key: str) -> None:
        """Briefly show the note/percussion name in a key's cell for ~1 second."""
        # Cancel existing timer for this key
        if key in self._note_timers:
            self._note_timers[key].cancel()
        self._note_labels.add(key)
        self.refresh()

        def _clear(k: str = key) -> None:
            self._note_labels.discard(k)
            self._note_timers.pop(k, None)
            self.refresh()

        try:
            loop = asyncio.get_running_loop()
            self._note_timers[key] = loop.call_later(1.0, _clear)
        except RuntimeError:
            pass

    def _ensure_letter_sounds_loaded(self) -> None:
        """Load letter sounds if not already loaded."""
        if self._letter_sounds_loaded or not _MIXER_READY:
            return
        self._load_letter_sounds()
        self._letter_sounds_loaded = True

    def _load_letter_sounds(self) -> None:
        """Load pregenerated letter and number name clips from the letters/ subdirectory."""
        sounds_path = self._get_sounds_path()
        letters_path = sounds_path / "letters"
        if not letters_path.exists():
            return
        for key in _SPEAKABLE_KEYS:
            path = self._find_sound(letters_path, key.lower())
            if path:
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
        self._instrument_sounds.clear()
        self._percussion_sounds.clear()
        self._percussion_loaded = False
        self._letter_sounds.clear()
        self._letter_sounds_loaded = False
        for timer in self._note_timers.values():
            timer.cancel()
        self._note_timers.clear()
        self._note_labels.clear()

    def reset_colors(self) -> None:
        """Reset all key colors to default state."""
        self.color_state = {k: -1 for k in ALL_KEYS}
        self.refresh()

    def next_color(self, key: str, refresh: bool = True) -> None:
        """Cycle color for a key."""
        self.color_state[key] = (self.color_state[key] + 1) % len(COLORS)
        if refresh:
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
        caps = getattr(self.app, 'caps_text', lambda x: x)

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
                display_key = caps(key)
                pad_left = (cell_width - 1) // 2
                pad_right = cell_width - pad_left - 1
                segments.append(Segment(" " * pad_left, cell_bg_style))
                segments.append(Segment(display_key, text_style))
                segments.append(Segment(" " * pad_right, cell_bg_style))
            elif line_in_cell == 1 and key in self._note_labels:
                # Flash note/percussion name, centered in cell
                if key.isdigit():
                    label = caps(PERCUSSION_NAMES.get(key, ""))
                else:
                    label = caps(NOTE_NAMES.get(key, ""))
                if label:
                    decorated = f"{ICON_MUSIC_NOTE} {label} {ICON_MUSIC_NOTE}"
                    decorated_width = len(decorated)
                    muted_color = "#6a5a7a" if bg_color in light_backgrounds else "#887799"
                    dim_style = Style(bgcolor=bg_color, color=muted_color)
                    pad_left = (cell_width - decorated_width) // 2
                    if pad_left < 0:
                        pad_left = 0
                    pad_right = cell_width - pad_left - decorated_width
                    if pad_right < 0:
                        pad_right = 0
                    segments.append(Segment(" " * pad_left, cell_bg_style))
                    segments.append(Segment(decorated[:cell_width], dim_style))
                    if pad_right > 0:
                        segments.append(Segment(" " * pad_right, cell_bg_style))
                else:
                    segments.append(Segment(" " * cell_width, cell_bg_style))
            else:
                segments.append(Segment(" " * cell_width, cell_bg_style))

        # Right margin
        margin_right = width - margin_left - grid_width
        if margin_right > 0:
            segments.append(Segment(" " * margin_right, bg_style))

        return Strip(segments)


class MusicExampleHint(Static):
    """Shows example hint with caps support"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        text = caps("Try pressing letters and numbers!")
        enter_hint = caps("Enter: change instrument")
        return f"[dim]{text}    {enter_hint}[/]"


class MusicMode(Container, can_focus=True):
    """Music Room: press keys to make sounds and colors.

    Sub-modes (switched with Tab):
      Music: all keys play instrument sounds
      Letters: letter keys (A-Z) are spoken aloud, other keys play sounds
    """

    DEFAULT_CSS = """
    MusicMode {
        width: 100%;
        height: 100%;
    }

    MusicRoomHeader {
        height: 1;
        dock: top;
    }

    MusicGrid {
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
        self.grid: MusicGrid | None = None
        self._header: MusicRoomHeader | None = None
        self.session = MusicSession()
        self._letters_mode = False
        self._instrument_index = 0
        self._session_replay_task: asyncio.Task | None = None

    @property
    def is_letters_mode(self) -> bool:
        """Whether Music room is in Letters mode (for DemoPlayer callback)."""
        return self._letters_mode

    def compose(self) -> ComposeResult:
        self._header = MusicRoomHeader(id="music-header")
        yield self._header
        self.grid = MusicGrid()
        yield self.grid
        yield MusicExampleHint(id="example-hint")

    def on_mount(self) -> None:
        self.focus()

    def on_unmount(self) -> None:
        if self.grid:
            self.grid.cleanup_sounds()

    def reset_state(self) -> None:
        """Reset music mode state (colors, session). Called when leaving mode."""
        self.session.clear()
        if self.grid:
            self.grid.reset_colors()

    def _start_session_replay(self) -> None:
        """Replay recent session keys with original timing."""
        if self._session_replay_task and not self._session_replay_task.done():
            self._session_replay_task.cancel()
        replay = self.session.get_recent_replay()
        if replay:
            self._session_replay_task = asyncio.create_task(
                self._do_session_replay(replay)
            )

    async def _do_session_replay(self, replay: list) -> None:
        """Play back a list of (key, submode, delay) triples."""
        try:
            for key, submode, delay in replay:
                if delay > 0:
                    await asyncio.sleep(delay)
                flash = submode == MODE_MUSIC
                self.grid.next_color(key, refresh=not flash)
                self._play_key(key, submode)
                if flash:
                    self.grid.flash_note(key)
        except asyncio.CancelledError:
            pass

    def _current_mode(self) -> str:
        return MODE_LETTERS if self._letters_mode else MODE_MUSIC

    def _play_key(self, key: str, mode: str) -> None:
        """Play audio for a key in the given mode.

        In music mode, all keys play instrument sounds.
        In letters mode, letter keys (A-Z) play their letter name clip
        layered with the instrument sound. Other keys just play sounds.
        """
        self.grid.play_sound(key)
        if mode == MODE_LETTERS and key in _SPEAKABLE_KEYS:
            self.grid.play_letter(key)

    async def handle_keyboard_action(self, action) -> None:
        """
        Handle keyboard actions from the main app's KeyboardStateMachine.

        Tab switches between Music and Letters modes.
        Character keys cycle colors, play sounds or speak, and are recorded.
        Space plays/stops the recording.
        """
        if isinstance(action, ControlAction) and action.is_down:
            # Space: replay recent session keys (loop feature)
            if action.action == 'space':
                if self.session.has_events():
                    self._start_session_replay()
                return

            # Tab switches mode
            if action.action == 'tab':
                self._letters_mode = not self._letters_mode
                if self._header:
                    self._header.update_mode(self._letters_mode)
                raw_label = "Letters" if self._letters_mode else INSTRUMENTS[self._instrument_index][1]
                label = self.app.caps_text(raw_label)
                self.app.clear_notifications()
                self.app.notify(f"{ICON_MUSIC} {label}" if not self._letters_mode else label, timeout=1.5)
                return

            # Enter cycles instruments
            if action.action == 'enter':
                self._instrument_index = (self._instrument_index + 1) % len(INSTRUMENTS)
                inst_id, inst_name = INSTRUMENTS[self._instrument_index]
                if self.grid:
                    self.grid.set_instrument(self._instrument_index)
                if self._header:
                    self._header.update_instrument(inst_name)
                self.app.clear_notifications()
                self.app.notify(f"{ICON_MUSIC} {self.app.caps_text(inst_name)}", timeout=1.5)
                return

        # Character keys cycle colors, play/speak, and record
        if isinstance(action, CharacterAction):
            char = action.char
            if not char:
                return

            lookup = char.upper() if char.isalpha() else char

            if lookup in ALL_KEYS:
                mode = self._current_mode()
                flash = mode == MODE_MUSIC
                self.session.record(lookup, mode)
                self.grid.next_color(lookup, refresh=not flash)
                self._play_key(lookup, mode)
                if flash:
                    self.grid.flash_note(lookup)
            return

