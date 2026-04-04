"""
Music Room: Music and Art Grid

A rectangular grid mapped to QWERTY keyboard.
Press keys to play sounds and cycle colors.
Tab switches between Music and Letters modes.
Space controls the loop station (record → loop → layer → double-tap stop).

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
from ..keyboard import CharacterAction, ControlAction, HoldOrTap
from ..music_constants import (
    GRID_KEYS, ALL_KEYS, COLORS, INSTRUMENTS, NOTE_NAMES, PERCUSSION_NAMES,
)
from ..music_session import MODE_MUSIC, MODE_LETTERS
from ..loop_station import LoopStation, IDLE, RECORDING, LOOPING
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


def reinit_mixer() -> None:
    """Quit and re-init the pygame mixer to recover from a dead audio backend.

    In VMs, PulseAudio/PipeWire can drop the connection and SDL2 won't reconnect
    on its own. This forces a fresh connection. All cached Sound objects become
    invalid after quit(), so callers must clear their sound caches.
    """
    global _MIXER_READY
    try:
        pygame.mixer.quit()
    except Exception:
        pass
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        pygame.mixer.set_num_channels(16)
        _MIXER_READY = True
    except pygame.error:
        _MIXER_READY = False
    # Reset TTS state so it picks up the fresh mixer
    from . import tts
    tts._mixer_initialized = False
    tts._current_channel = None


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
        self._code_mode = False
        self.add_class("caps-sensitive")

    def update_mode(self, letters_mode: bool) -> None:
        self._letters_mode = letters_mode
        self.refresh()

    def update_instrument(self, name: str) -> None:
        self._instrument_name = name
        self.refresh()

    def set_code_mode(self, code_mode: bool) -> None:
        self._code_mode = code_mode
        self.refresh()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        instrument_label = caps(self._instrument_name)

        if self._code_mode:
            return ""

        if getattr(self.app, '_littles_mode', None):
            return f"[bold]{ICON_MUSIC} {instrument_label}[/]"

        letters_label = caps("Letters")

        sel = "bold #1e1033 on #9b7bc4"
        unsel = "dim"

        if self._letters_mode:
            music_part = f"[{unsel}] {ICON_MUSIC} {instrument_label} [/]"
            letters_part = f"[{sel}] {letters_label} [/]"
        else:
            music_part = f"[{sel}] {ICON_MUSIC} {instrument_label} [/]"
            letters_part = f"[{unsel}] {letters_label} [/]"

        tab_label = caps("Tab")
        return f"{music_part}  [{unsel}]{tab_label}[/]  {letters_part}"


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
        # Suppress rendering until layout stabilizes (prevents flicker on mount).
        # Once ready, cache cell dimensions so reflows show the old layout
        # instead of a blank grid.
        self._layout_ready = False
        self._pending_ready_timer: asyncio.TimerHandle | None = None
        self._cached_layout: tuple[int, int, int, int, int, int] | None = None  # (cell_w, cell_h, margin_l, margin_t, grid_w, grid_h)

    def on_resize(self, event) -> None:
        """Mark layout ready after size stabilizes (debounced)."""
        if self._layout_ready:
            return
        # Cancel any pending ready signal, restart the debounce
        if self._pending_ready_timer is not None:
            self._pending_ready_timer.cancel()
        try:
            loop = asyncio.get_running_loop()
            self._pending_ready_timer = loop.call_later(0.05, self._mark_layout_ready)
        except RuntimeError:
            self._layout_ready = True

    def _mark_layout_ready(self) -> None:
        self._pending_ready_timer = None
        self._layout_ready = True
        self.refresh()

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
                    sound.set_volume(0.4)
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
                    sound.set_volume(0.4)
                    self._percussion_sounds[key] = sound
                except pygame.error:
                    pass
        self._percussion_loaded = True

    def play_sound(self, key: str) -> None:
        """Play instrument or percussion sound for a key."""
        if hasattr(self.app, 'volume_level') and self.app.volume_level == 0:
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

    def play_sound_with_instrument(self, key: str, instrument_index: int) -> None:
        """Play a sound using a specific instrument (for loop playback)."""
        if hasattr(self.app, 'volume_level') and self.app.volume_level == 0:
            return
        if key.isdigit():
            self._ensure_percussion_loaded()
            if key in self._percussion_sounds:
                self._percussion_sounds[key].play()
        else:
            inst_id = INSTRUMENTS[instrument_index][0]
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
                    sound.set_volume(0.4)
                    self._letter_sounds[key] = sound
                except pygame.error:
                    pass

    def play_letter(self, key: str) -> None:
        """Play the letter name clip for a key (respects app volume setting)."""
        if hasattr(self.app, 'volume_level') and self.app.volume_level == 0:
            return
        self._ensure_letter_sounds_loaded()
        if key in self._letter_sounds:
            self._letter_sounds[key].play()

    def cleanup_sounds(self) -> None:
        """Stop all currently playing sounds and clear loaded sounds."""
        if _MIXER_READY:
            try:
                pygame.mixer.stop()
            except pygame.error:
                pass
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

        # First mount: no cached layout yet, show blank until ready
        if not self._layout_ready and self._cached_layout is None:
            return Strip([Segment(" " * max(width, 0), Style(bgcolor=self._get_default_bg()))])

        if self._layout_ready and width >= 10 and height >= 4:
            # Calculate and cache cell dimensions
            cell_width = width // 10
            cell_height = height // 4
            grid_width = cell_width * 10
            grid_height = cell_height * 4
            margin_left = (width - grid_width) // 2
            margin_top = (height - grid_height) // 2
            self._cached_layout = (cell_width, cell_height, margin_left, margin_top, grid_width, grid_height)
        elif self._cached_layout is not None:
            # Reflow in progress: reuse last good layout
            cell_width, cell_height, margin_left, margin_top, grid_width, grid_height = self._cached_layout
        else:
            return Strip([Segment(" " * max(width, 0), Style(bgcolor=self._get_default_bg()))])

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

            letter_line = mid_line - 1
            note_line = mid_line + 1
            if line_in_cell == letter_line:
                # Center the key character
                display_key = caps(key)
                pad_left = (cell_width - 1) // 2
                pad_right = cell_width - pad_left - 1
                segments.append(Segment(" " * pad_left, cell_bg_style))
                segments.append(Segment(display_key, text_style))
                segments.append(Segment(" " * pad_right, cell_bg_style))
            elif line_in_cell == note_line and key in self._note_labels:
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


PROGRESS_BLOCKS = 20  # number of blocks in the recording progress bar


class MusicExampleHint(Static):
    """Shows context-sensitive hint for current loop station state.

    Stores raw markup and applies caps in render() so the caps-sensitive
    refresh pattern works (same as every other hint widget).
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("caps-sensitive")
        self._raw_markup: str = ""

    def set_hint(self, markup: str) -> None:
        """Set the hint markup (without caps). Caps applied at render time."""
        self._raw_markup = markup
        self.refresh()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        return caps(self._raw_markup)


class MusicMode(Container, can_focus=True):
    """Music Room: press keys to make sounds and colors.

    Sub-modes (switched with Tab):
      Music: all keys play instrument sounds
      Letters: letter keys (A-Z) are spoken aloud, other keys play sounds

    Loop station (Space):
      Press Space to start recording, Space again to loop,
      play on top to layer, Space to merge layer, Escape to stop.
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

    #noscreen-label {
        width: 100%;
        height: 100%;
        text-align: center;
        content-align: center middle;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.grid: MusicGrid | None = None
        self._header: MusicRoomHeader | None = None
        self._loop = LoopStation()
        self._letters_mode = False
        self._instrument_index = 0
        self._loop_task: asyncio.Task | None = None
        self._recording_timer = None
        self._loop_progress_timer = None
        self._last_loop_space_time: float = 0.0
        # Space hold REPL toggle
        self._space_hold = HoldOrTap(hold_seconds=0.5)
        self._repl_panel = None
        self._noscreen_dot_timer = None

    @property
    def is_letters_mode(self) -> bool:
        """Whether Music room is in Letters mode (for DemoPlayer callback)."""
        return self._letters_mode

    def compose(self) -> ComposeResult:
        from ..repl_panel import ReplPanel
        self._header = MusicRoomHeader(id="music-header")
        yield self._header
        self.grid = MusicGrid()
        yield self.grid
        yield MusicExampleHint(id="example-hint")
        self._repl_panel = ReplPanel(room="music", id="music-repl")
        yield self._repl_panel

    @property
    def _is_noscreen(self) -> bool:
        return getattr(self.app, '_littles_mode', None) == 'music_noscreen'

    def on_mount(self) -> None:
        self.focus()
        self._update_hint()
        if self._is_noscreen:
            self._apply_noscreen()

    def _apply_noscreen(self) -> None:
        """Hide visual elements for no-screen music mode."""
        if self._header:
            self._header.display = False
        if self.grid:
            self.grid.display = False
        try:
            self.query_one("#example-hint").display = False
        except Exception:
            pass
        try:
            self.query_one("#music-repl").display = False
        except Exception:
            pass
        # Show minimal centered message (if not already mounted)
        try:
            self.query_one("#noscreen-label")
        except Exception:
            self.mount(Static(
                f"\n\n{self._NOSCREEN_TEXT}",
                id="noscreen-label",
            ))

    def _restore_screen(self) -> None:
        """Restore visual elements after leaving no-screen mode."""
        if self._header:
            self._header.display = True
        if self.grid:
            self.grid.display = True
        try:
            self.query_one("#example-hint").display = True
        except Exception:
            pass
        try:
            self.query_one("#noscreen-label").remove()
        except Exception:
            pass

    _NOSCREEN_TEXT = "[dim]No-screen music mode\nPress keys to play sounds\n\nHold ` or Esc: parent menu[/]"

    def _noscreen_flash(self, color: str) -> None:
        """Show a colored circle briefly in no-screen mode."""
        try:
            label = self.query_one("#noscreen-label", Static)
        except Exception:
            return
        label.update(f"[{color}]●[/]\n\n{self._NOSCREEN_TEXT}")
        if self._noscreen_dot_timer is not None:
            self._noscreen_dot_timer.cancel()
        try:
            loop = asyncio.get_running_loop()
            def _clear():
                self._noscreen_dot_timer = None
                try:
                    label.update(f"\n\n{self._NOSCREEN_TEXT}")
                except Exception:
                    pass
            self._noscreen_dot_timer = loop.call_later(0.4, _clear)
        except RuntimeError:
            pass

    def on_unmount(self) -> None:
        self._stop_loop()
        if self.grid:
            self.grid.cleanup_sounds()

    def reset_state(self) -> None:
        """Reset music mode to defaults (colors, loop, instrument, letters mode)."""
        self._stop_loop()
        self._instrument_index = 0
        self._letters_mode = False
        if self.grid:
            self.grid.reset_colors()
            self.grid.set_instrument(0)
        if self._header:
            self._header.update_instrument(INSTRUMENTS[0][1])
            self._header.update_mode(False)
            self._header.set_code_mode(False)

    # -- Loop station controls -----------------------------------------------

    def _handle_space(self) -> None:
        """Space key state machine: idle → recording → looping/stop."""
        state = self._loop.state
        if state == IDLE:
            self._loop.start_recording()
            self._start_recording_timer()
            self._update_hint()
            self.app.clear_notifications()
            self.app.notify(self.app.caps_text("Recording!"), timeout=1.5)

        elif state == RECORDING:
            events, duration = self._loop.finish_recording()
            self._stop_recording_timer()
            if events:
                self._start_loop_playback()
                self._start_loop_progress_timer()
                self._update_hint()
                self.app.clear_notifications()
                self.app.notify(self.app.caps_text("Looping! Play on top!"), timeout=2.0)
            else:
                # No notes recorded, go back to idle
                self._loop.stop()
                self._update_hint()

        elif state == LOOPING:
            now = time.monotonic()
            if now - self._last_loop_space_time < 2.0:
                # Double-tap space: stop the loop
                self._stop_loop()
                self.app.clear_notifications()
                self.app.notify(self.app.caps_text("Loop stopped"), timeout=1.0)
                self._last_loop_space_time = 0.0
            else:
                # First tap: ignore but remember the time
                self._last_loop_space_time = now

    def _handle_escape(self) -> bool:
        """Escape stops loop from any non-idle state. Returns True if consumed."""
        if self._loop.state == IDLE:
            return False
        self._stop_loop()
        self.app.clear_notifications()
        self.app.notify(self.app.caps_text("Loop stopped"), timeout=1.0)
        return True

    def _stop_loop(self) -> None:
        """Stop everything: loop, timers, playback task."""
        self._loop.stop()
        self._stop_recording_timer()
        self._stop_loop_progress_timer()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = None
        self._last_loop_space_time = 0.0
        self._update_hint()

    def _start_loop_playback(self) -> None:
        """Start the async loop playback task."""
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = asyncio.create_task(self._loop_playback())

    async def _loop_playback(self) -> None:
        """Continuously play the loop until stopped."""
        try:
            while self._loop.state == LOOPING:
                events = self._loop.loop_events
                duration = self._loop.loop_duration
                if not events or duration <= 0:
                    break

                cycle_start = asyncio.get_event_loop().time()
                self._loop.start_new_cycle()

                sorted_events = sorted(events, key=lambda e: e[2])
                for key, mode, offset, instrument in sorted_events:
                    if self._loop.state != LOOPING:
                        return
                    now = asyncio.get_event_loop().time()
                    wait = offset - (now - cycle_start)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    if self._loop.state != LOOPING:
                        return

                    flash = mode == MODE_MUSIC
                    self.grid.next_color(key, refresh=not flash)
                    self._play_key(key, mode, instrument=instrument)
                    if flash:
                        self.grid.flash_note(key)
                    if self._is_noscreen:
                        self._noscreen_flash(COLORS[self.grid.color_state[key]])

                # Wait for remaining loop duration
                elapsed = asyncio.get_event_loop().time() - cycle_start
                remaining = duration - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            pass

    # -- Recording timer (for progress bar and auto-stop) --------------------

    def _start_recording_timer(self) -> None:
        self._recording_timer = self.set_interval(0.5, self._on_recording_tick)

    def _stop_recording_timer(self) -> None:
        if self._recording_timer:
            self._recording_timer.stop()
            self._recording_timer = None

    async def _on_recording_tick(self) -> None:
        """Update hint bar progress, auto-start loop at max duration."""
        if self._loop.state != RECORDING:
            self._stop_recording_timer()
            return
        if self._loop.is_at_max_duration():
            events, duration = self._loop.finish_recording()
            self._stop_recording_timer()
            if events:
                self._start_loop_playback()
                self.app.clear_notifications()
                self.app.notify(self.app.caps_text("Loop full! Playing..."), timeout=2.0)
            else:
                self._loop.stop()
            self._update_hint()
        else:
            self._update_hint()

    # -- Loop progress timer (for cycling position indicator) -----------------

    def _start_loop_progress_timer(self) -> None:
        self._loop_progress_timer = self.set_interval(0.15, self._on_loop_progress_tick)

    def _stop_loop_progress_timer(self) -> None:
        if self._loop_progress_timer:
            self._loop_progress_timer.stop()
            self._loop_progress_timer = None

    def _on_loop_progress_tick(self) -> None:
        """Update hint bar with current loop position."""
        if self._loop.state != LOOPING:
            self._stop_loop_progress_timer()
            return
        self._update_hint()

    # -- Hint bar ------------------------------------------------------------

    def _update_hint(self) -> None:
        """Update the bottom hint bar based on loop station state.

        Text is stored raw (without caps). MusicExampleHint.render()
        applies caps at render time so it responds to caps changes immediately.
        """
        try:
            hint = self.query_one("#example-hint", MusicExampleHint)
        except Exception:
            return
        state = self._loop.state

        if state == IDLE:
            text = "Try pressing letters and numbers!"
            if getattr(self.app, '_littles_mode', None):
                hint.set_hint(f"[dim]{text}[/]")
                return
            space_hint = "Space: record a loop"
            enter_hint = "Enter: change instrument"
            hint.set_hint(f"[dim]{text}    {space_hint}    {enter_hint}[/]")

        elif state == RECORDING:
            progress = self._loop.recording_progress()
            remaining = self._loop.recording_remaining()
            filled = int(progress * PROGRESS_BLOCKS)
            empty = PROGRESS_BLOCKS - filled
            bar = "█" * filled + "░" * empty
            secs = int(remaining)
            if remaining <= 5:
                label = f"Recording  {secs}s left"
                action = "Almost full!"
                hint.set_hint(f"[bold dark_orange]● {label}[/]  {bar}  [dim]{action}[/]")
            else:
                label = f"Recording  {secs}s left"
                action = "Space: loop it!"
                hint.set_hint(f"[bold red]● {label}[/]  {bar}  [dim]{action}[/]")

        elif state == LOOPING:
            progress = self._loop.loop_progress()
            pos = int(progress * PROGRESS_BLOCKS)
            bar_chars = list("░" * PROGRESS_BLOCKS)
            if pos < PROGRESS_BLOCKS:
                bar_chars[pos] = "█"
            bar = "".join(bar_chars)
            label = "Looping and recording"
            play = "Play on top"
            stop = "Esc: stop"
            hint.set_hint(f"[bold red]● {label}[/]  {bar}  [dim]{play}    {stop}[/]")

    # -- Core key handling ---------------------------------------------------

    def _current_mode(self) -> str:
        return MODE_LETTERS if self._letters_mode else MODE_MUSIC

    def _play_key(self, key: str, mode: str, instrument: int | None = None) -> None:
        """Play audio for a key in the given mode.

        In music mode, all keys play instrument sounds.
        In letters mode, letter keys (A-Z) play their letter name clip
        layered with the instrument sound. Other keys just play sounds.

        If instrument is provided, play with that instrument instead of the
        current one (used by loop playback to preserve each layer's sound).
        """
        if instrument is not None:
            self.grid.play_sound_with_instrument(key, instrument)
        else:
            self.grid.play_sound(key)
        if mode == MODE_LETTERS and key in _SPEAKABLE_KEYS:
            self.grid.play_letter(key)

    def _on_space_hold_fired(self) -> None:
        """Space held long enough: toggle REPL."""
        if not getattr(self.app, '_code_panel_enabled', True):
            return
        # Stop any active loop/playback so toggling code panel silences everything
        self._stop_loop()
        self.grid.cleanup_sounds()
        if self._repl_panel and not self._repl_panel.is_open:
            # Hide hint bar (REPL has its own hints) and pin grid height
            try:
                self.query_one("#example-hint", MusicExampleHint).display = False
            except Exception:
                pass
            grid = self.query_one(MusicGrid)
            grid.styles.height = grid.size.height
            # Sync instrument state (grid is authoritative for sound playback)
            grid.set_instrument(self._instrument_index)
            self._repl_panel.open()
            from ..repl_panel import ReplPanelToggleRequested
            self.post_message(ReplPanelToggleRequested("music"))
        elif self._repl_panel and self._repl_panel.is_open:
            self._repl_panel.close()
            # Sync instrument state back from grid
            self._instrument_index = self.grid._instrument_index
            if self._header:
                self._header.update_instrument(INSTRUMENTS[self._instrument_index][1])
            # Restore hint bar and flex sizing; suppress rendering during reflow
            try:
                self.query_one("#example-hint", MusicExampleHint).display = True
            except Exception:
                pass
            grid = self.query_one(MusicGrid)
            grid._layout_ready = False
            grid.styles.height = "1fr"
            from ..repl_panel import ReplPanelToggleRequested
            self.post_message(ReplPanelToggleRequested("music"))

    async def _flush_space_tap_to_repl(self) -> None:
        """Insert a space character into the REPL panel."""
        from ..keyboard import ControlAction as CA
        await self._repl_panel.handle_keyboard_action(
            CA(action='space', is_down=True, is_repeat=False))

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard actions from the main app's KeyboardStateMachine.

        Tab switches between Music and Letters modes.
        Character keys cycle colors, play sounds or speak.
        Space controls the loop station.
        Escape stops the loop (if active).
        Space hold (~0.5s, no other keys): toggles REPL panel.
        """
        # When REPL panel is open, route everything there
        if self._repl_panel and self._repl_panel.is_open:
            # Space hold to close REPL, short press inserts space
            if isinstance(action, ControlAction) and action.action == 'space':
                if action.is_down and not action.is_repeat:
                    self._space_hold.on_down(self.set_timer, self._on_space_hold_fired)
                elif not action.is_down:
                    if self._space_hold.on_up():
                        await self._flush_space_tap_to_repl()
                return
            # Another key while space pending: flush space first
            if self._space_hold.on_other_key():
                await self._flush_space_tap_to_repl()
            result = await self._repl_panel.handle_keyboard_action(action)
            if result == "tab_fallthrough":
                # Tab with no autocomplete: switch music/letters mode
                self._letters_mode = not self._letters_mode
                if self._header:
                    self._header.update_mode(self._letters_mode)
                raw_label = "Letters" if self._letters_mode else INSTRUMENTS[self._instrument_index][1]
                label = self.app.caps_text(raw_label)
                self.app.clear_notifications()
                self.app.notify(f"{ICON_MUSIC} {label}" if not self._letters_mode else label, timeout=1.5)
            return

        if isinstance(action, ControlAction):
            if action.action == 'space':
                # After hold fired (panel just opened/closed), suppress until release
                if self._space_hold.fired:
                    if not action.is_down:
                        self._space_hold.on_up()
                    return
                if action.is_down and not action.is_repeat:
                    self._space_hold.on_down(self.set_timer, self._on_space_hold_fired)
                elif not action.is_down:
                    if self._space_hold.on_up():
                        if not getattr(self.app, '_littles_mode', None):
                            self._handle_space()
                return

            if action.is_down:
                # Any other control key: cancel space hold
                self._space_hold.on_other_key()

                # Escape: stop loop if active
                if action.action == 'escape':
                    if self._handle_escape():
                        self.app._escape_consumed_by_mode = True
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

        # Character keys: play sound, cycle color, record into loop if active
        if isinstance(action, CharacterAction):
            # Any key press: cancel space hold
            self._space_hold.on_other_key()

            char = action.char
            if not char:
                return

            lookup = char.upper() if char.isalpha() else char

            if lookup in ALL_KEYS:
                mode = self._current_mode()
                flash = mode == MODE_MUSIC

                # Record into loop station (no-op if idle)
                self._loop.record_event(lookup, mode, instrument=self._instrument_index)

                self.grid.next_color(lookup, refresh=not flash)
                self._play_key(lookup, mode)
                if flash:
                    self.grid.flash_note(lookup)
                if self._is_noscreen:
                    self._noscreen_flash(COLORS[self.grid.color_state[lookup]])
            return

