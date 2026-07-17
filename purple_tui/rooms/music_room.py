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
import subprocess
import sys
import time
from ..keyboard import CharacterAction, ControlAction, NavigationAction, HoldOrTap
from ..music_constants import (
    GRID_KEYS, ALL_KEYS, COLORS, COLOR_KEYCAP,
    INSTRUMENTS, PERCUSSION_NAMES,
    FRIENDLY_KEYS, FRIENDLY_KEY_NAMES, DEFAULT_ROOT_INDEX,
    pitch_for, pitch_filename,
)
from .art_room import KEY_COLORS, text_color_for
from ..music_session import MODE_MUSIC, MODE_LETTERS
from ..loop_station import LoopStation, IDLE, RECORDING, LOOPING
from ..loop_panel import LoopPanel, LoopPanelToggleRequested
from ..constants import ICON_MUSIC, ICON_MUSIC_NOTE, ICON_TAB, HOLD_OR_TAP_THRESHOLD

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

# pygame.mixer.init() blocks in C code holding the GIL on broken audio hw
# (T2 Macs, some Surfaces/AMDs). A stuck call wedges the whole interpreter
# — Textual stops rendering, evdev grab stays held, only a power cycle
# recovers. So we probe in a subprocess first (subprocess wait releases the
# GIL; SIGKILL on timeout), and only init in-process after the probe passes.
# See guides/boot-hang-debugging.md.
pygame = None  # populated by warm_mixer() once pygame is safe to import
_MIXER_READY: bool | None = None  # None = untested, True/False = cached result
_PROBE_TIMED_OUT = False  # True = probe hung (hw is broken, don't retry)
_KNOWN_SILENT = False  # True = output codec opens fine but is inaudible (don't retry)

# Codecs that init cleanly but drive no speakers: the amp sits on an I2C
# side-channel the generic HDA driver never powers on, so ALSA accepts frames
# into a dead amp and mixer.init() "succeeds" while nothing is audible. No
# software probe (not even a test tone) can observe this, so we gate on codec
# identity. See guides/boot-hang-debugging.md.
_SILENT_HDA_CODECS = ("CS8409",)


def _has_usb_audio(sound_root: str = "/sys/class/sound") -> bool:
    """True if any ALSA card is a USB device (a real output Pulse can route to)."""
    for card in Path(sound_root).glob("card*"):
        try:
            if "usb" in os.path.realpath(card / "device").lower():
                return True
        except OSError:
            pass
    return False


def output_is_known_silent(sound_root: str = "/sys/class/sound") -> bool:
    """True when an HDA output codec is known to be inaudible and no USB audio
    adapter is present to provide a real output.

    A plugged-in USB device clears the veto: Pulse routes to it, so the silent
    internal codec no longer matters. The hotplug re-probe re-evaluates this,
    so plugging a speaker in flips audio back on without a restart.
    """
    if _has_usb_audio(sound_root):
        return False
    for chip in Path(sound_root).glob("hwC*D*/chip_name"):
        try:
            name = chip.read_text().strip()
        except OSError:
            continue
        if any(silent in name for silent in _SILENT_HDA_CODECS):
            return True
    return False

import threading as _threading
_MIXER_LOCK = _threading.Lock()


def _reap_orphan(proc) -> None:
    """Block until an abandoned probe child dies, so it doesn't linger as a
    zombie if the kernel eventually releases its D-state. Daemon-threaded."""
    try:
        proc.wait()
    except Exception:
        pass

_PROBE_SCRIPT = (
    "import os; os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'; "
    "import pygame.mixer; "
    "pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048); "
    "pygame.mixer.quit()"
)


def warm_mixer(timeout_seconds: float = 10.0) -> bool:
    """Probe mixer in a subprocess, then init in-process if it passed.

    Timeout must cover cold Python startup + pygame/numpy import + mixer
    init, so 10s gives margin for older hardware. True hangs (CS8409)
    block forever, so 10s cleanly separates working from broken.

    Called from both the post-boot warmup thread and MusicMode.on_mount.
    The lock serialises them so the probe runs at most once per process;
    a late caller waits for the early caller's result.
    """
    global pygame, _MIXER_READY, _PROBE_TIMED_OUT, _KNOWN_SILENT
    from ..tts import _dbg
    _dbg("warm_mixer: waiting for _MIXER_LOCK")
    with _MIXER_LOCK:
        _dbg(f"warm_mixer: got lock, ready={_MIXER_READY}")
        if _MIXER_READY is not None:
            return _MIXER_READY
        if output_is_known_silent():
            _KNOWN_SILENT = True
            _MIXER_READY = False
            return False
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", _PROBE_SCRIPT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            _MIXER_READY = False
            return False
        try:
            probe_ok = proc.wait(timeout=timeout_seconds) == 0
        except subprocess.TimeoutExpired:
            # A truly wedged codec (CS8409 on a T1/T2 Mac) leaves the child in
            # uninterruptible D-state: SIGKILL can't reap it, and a blocking
            # wait() would hang us forever, which is the "Audio: checking..."
            # that never resolves. Signal and abandon it: it's a separate
            # process so it can't wedge us, and a daemon reaper collects it if
            # the kernel ever lets go. wait(timeout) polls, so it always returns
            # at the deadline regardless of D-state.
            _PROBE_TIMED_OUT = True
            probe_ok = False
            try:
                proc.kill()
            except Exception:
                pass
            _threading.Thread(target=_reap_orphan, args=(proc,), daemon=True).start()
        except Exception:
            probe_ok = False
        if not probe_ok:
            _MIXER_READY = False
            return False
        _suppress_alsa_output()
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
        import pygame as _pg
        import pygame.mixer  # noqa: F401
        pygame = _pg
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.set_num_channels(16)
            _MIXER_READY = True
        except pygame.error:
            _MIXER_READY = False
        return _MIXER_READY


def _ensure_mixer() -> bool:
    """Backward-compatible alias for callers that don't pass a timeout."""
    return warm_mixer()


def _reset_mixer_state() -> bool:
    """Clear cached probe result so warm_mixer() retries on next call.

    Returns False if the probe timed out or the codec is known-silent
    (hardware can't produce sound, retrying won't help).
    """
    global _MIXER_READY
    if _PROBE_TIMED_OUT or _KNOWN_SILENT:
        return False
    _MIXER_READY = None
    return True


def reinit_mixer() -> None:
    """Quit and re-init the pygame mixer to recover from a dead audio backend.

    In VMs, PulseAudio/PipeWire can drop the connection and SDL2 won't reconnect
    on its own. This forces a fresh connection. All cached Sound objects become
    invalid after quit(), so callers must clear their sound caches.
    """
    global _MIXER_READY
    from ..tts import _dbg
    _dbg("reinit_mixer: start")
    if not _ensure_mixer():
        return
    try:
        _dbg("reinit_mixer: calling mixer.quit()")
        pygame.mixer.quit()
        _dbg("reinit_mixer: quit returned")
    except Exception:
        pass
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
        pygame.mixer.set_num_channels(16)
        _MIXER_READY = True
    except pygame.error:
        _MIXER_READY = False
    _dbg(f"reinit_mixer: done ready={_MIXER_READY}")
    from .. import tts
    tts._current_channel = None


def reinit_mixer_after_hotplug() -> bool:
    """Full re-probe after audio hardware changed (USB plug/unplug).

    Unlike reinit_mixer() (which assumes the mixer was working and just lost
    its connection), this resets the timeout flag too so a machine that
    failed at boot gets a fresh chance when a USB adapter is plugged in.
    Returns True iff the mixer is working after reinit.
    """
    global _MIXER_READY, _PROBE_TIMED_OUT, _KNOWN_SILENT
    from ..tts import _dbg
    _dbg("reinit_after_hotplug: waiting for _MIXER_LOCK")
    with _MIXER_LOCK:
        if pygame is not None:
            try:
                if pygame.mixer.get_init():
                    _dbg("reinit_after_hotplug: calling mixer.quit()")
                    pygame.mixer.quit()
                    _dbg("reinit_after_hotplug: quit returned")
            except Exception:
                pass
        _MIXER_READY = None
        _PROBE_TIMED_OUT = False
        _KNOWN_SILENT = False
    try:
        from .. import tts
        tts._current_channel = None
    except Exception:
        pass
    return warm_mixer()


# Default backgrounds (dark and light themes)
DEFAULT_BG_DARK = "#2a1845"
DEFAULT_BG_LIGHT = "#e8daf0"


# Keys that get spoken in Letters mode (A-Z and 0-9)
_SPEAKABLE_KEYS = {k for k in ALL_KEYS if k.isalpha() or k.isdigit()}

# Kid-math remap aliases: app-level remap turns '/'->'÷' and '*'->'×' before
# events reach the music room, but the grid is keyed by '/' and '*'. Reverse
# the remap on input. Cell labels use the same map to show the symbol that
# matches the physical sticker.
_KID_MATH_UNREMAP = {"÷": "/", "×": "*"}
_KID_MATH_DISPLAY = {"/": "÷", "*": "×"}

# Reverse lookup: melodic key -> (melodic_row, col) where melodic_row is
# 0 (Q-P), 1 (A-;), 2 (Z-/) — the index pitch_for(...) expects. GRID_KEYS
# row 0 is the digit row (percussion); melodic rows are GRID_KEYS rows 1..3,
# so melodic_row = grid_row - 1.
_KEY_TO_RC: dict[str, tuple[int, int]] = {
    GRID_KEYS[r][c]: (r - 1, c)
    for r in range(len(GRID_KEYS))
    for c in range(len(GRID_KEYS[r]))
    if not GRID_KEYS[r][c].isdigit()
}

class MusicRoomHeader(Static):
    """Shows current mode with both options visible, current highlighted.

    Follows the same pattern as ArtMode's CanvasHeader.
    """

    DEFAULT_CSS = """
    MusicRoomHeader {
        height: 1;
        dock: top;
        color: $text-muted;
        background: $surface;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._letters_mode = False
        self._instrument_name = INSTRUMENTS[0][1]
        self._code_mode = False
        self._root_index = DEFAULT_ROOT_INDEX

    def update_pitch(self, root_index: int) -> None:
        self._root_index = root_index
        self.refresh()

    def update_mode(self, letters_mode: bool) -> None:
        self._letters_mode = letters_mode
        self.refresh()

    def update_instrument(self, name: str) -> None:
        self._instrument_name = name
        self.refresh()

    def set_code_mode(self, code_mode: bool) -> None:
        self._code_mode = code_mode
        self.refresh()

    def on_resize(self, event) -> None:
        self.refresh()

    def _pitch_tag(self) -> tuple[str, int]:
        """Return (markup, visible_width) for the current-key indicator."""
        if getattr(self.app, '_music_key_switching_enabled', True):
            root_name = FRIENDLY_KEY_NAMES[self._root_index]
            plain = f"← Key {root_name} →"
        else:
            root_name = FRIENDLY_KEY_NAMES[DEFAULT_ROOT_INDEX]
            plain = f"Key {root_name}"
        return f"[dim]{plain}[/]", len(plain)

    def render(self) -> str:
        instrument_label = self._instrument_name

        if self._code_mode:
            return ""

        if getattr(self.app, '_littles_mode', None):
            inner = f" {ICON_MUSIC} {instrument_label} "
            width = self.size.width or 134
            left_pad = max(0, (width - len(inner)) // 2)
            return f"{' ' * left_pad}[bold]{inner}[/]"

        letters_label = "Say Letters"

        sel = "bold #1e1033 on #9b7bc4"
        unsel = "dim"

        if self._letters_mode:
            music_part = f"[{unsel}] {ICON_MUSIC} {instrument_label} [/]"
            letters_part = f"[{sel}] {letters_label} [/]"
        else:
            music_part = f"[{sel}] {ICON_MUSIC} {instrument_label} [/]"
            letters_part = f"[{unsel}] {letters_label} [/]"

        music_inner = f" {ICON_MUSIC} {instrument_label} "
        letters_inner = f" {letters_label} "
        modes = f"{music_part}  {letters_part}"
        modes_w = len(music_inner) + 2 + len(letters_inner)
        hint = f"{ICON_TAB} Tab to {'stop saying' if self._letters_mode else 'say'} letters"
        hint_w = len(hint)
        pitch_markup, pitch_w = self._pitch_tag()
        width = self.size.width or 134
        left_pad = max(0, (width - modes_w) // 2)
        # Pitch tag lives at the very left, inside the left padding.
        pitch_lead = 2  # gutter from the screen edge
        if left_pad >= pitch_w + pitch_lead + 1:
            left_prefix = " " * pitch_lead + pitch_markup + " " * (left_pad - pitch_w - pitch_lead)
        else:
            left_prefix = " " * left_pad
        right_area = max(0, width - left_pad - modes_w)
        hint_left_pad = max(1, (right_area - hint_w) // 2)
        return f"{left_prefix}{modes}{' ' * hint_left_pad}[{unsel}]{hint}[/]"


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
        # Pitch state: which root note the grid is currently in.
        # Driven by Left/Right arrow keys (set via set_pitch_state).
        self._root_index: int = DEFAULT_ROOT_INDEX  # index into FRIENDLY_KEYS
        # Key-shift slide animation. None = idle. When set: dict with
        # start_time, direction (+1 right, -1 left), prev_root_index.
        self._pitch_transition: dict | None = None
        self._pitch_transition_timer = None
        # Show note names in every melodic cell (Up arrow on, Down off).
        self._show_labels: bool = False
        # Per-instrument sound cache: instrument_id -> {pitch_name -> Sound}.
        # Pitch names are the lowercase filename stems (e.g. 'g4', 'cs5').
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
        """Load instrument sounds if not already cached.

        Loads every pitch-named .ogg in the instrument directory (e.g.
        'c4.ogg', 'cs5.ogg') keyed by the filename stem. Lookup at play
        time uses pitch_for(...) to compute the right stem.
        """
        if instrument_id in self._instrument_sounds or not _MIXER_READY:
            return
        sounds_path = self._get_sounds_path()
        inst_path = sounds_path / instrument_id
        cache: dict[str, pygame.mixer.Sound] = {}
        if inst_path.exists():
            for path in inst_path.glob("*.ogg"):
                try:
                    sound = pygame.mixer.Sound(str(path))
                    sound.set_volume(0.4)
                    cache[path.stem] = sound
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

    def _pitch_stem_for_key(self, key: str) -> str | None:
        """Filename stem (e.g. 'g4') for a melodic key under current state."""
        rc = _KEY_TO_RC.get(key)
        if rc is None:
            return None
        row, col = rc
        root = FRIENDLY_KEYS[self._root_index]
        note, octave = pitch_for(row, col, root, 0)
        return pitch_filename(note, octave)

    def play_sound(self, key: str, volume_scale: float = 1.0) -> None:
        """Play instrument or percussion sound for a key."""
        self.play_sound_with_instrument(key, self._instrument_index, volume_scale)

    def play_sound_with_instrument(self, key: str, instrument_index: int,
                                   volume_scale: float = 1.0) -> None:
        """Play a sound using a specific instrument (for loop playback).

        volume_scale < 1.0 ducks the instrument so a layered sound (e.g. the
        spoken letter clip in letters mode) stays intelligible.
        """
        from ..audio import play_safe
        if hasattr(self.app, '_effective_volume') and self.app._effective_volume() == 0:
            return
        if key.isdigit():
            self._ensure_percussion_loaded()
            if key in self._percussion_sounds:
                ch = play_safe(self._percussion_sounds[key])
                if ch is not None and volume_scale != 1.0:
                    ch.set_volume(volume_scale)
            return
        stem = self._pitch_stem_for_key(key)
        if stem is None:
            return
        inst_id = INSTRUMENTS[instrument_index][0]
        self._ensure_instrument_loaded(inst_id)
        sounds = self._instrument_sounds.get(inst_id, {})
        if stem in sounds:
            ch = play_safe(sounds[stem])
            if ch is not None and volume_scale != 1.0:
                ch.set_volume(volume_scale)

    def set_instrument(self, index: int) -> None:
        """Set the current instrument index."""
        self._instrument_index = index

    # Pitch slide animation: ~250ms wave that crosses the grid in the arrow's
    # direction. Each column adopts the new key as the wave passes; cells at
    # the wave-front pulse for a single tick. Sound at the new key plays
    # immediately on press; the animation is purely visual scaffolding.
    PITCH_TRANSITION_DURATION = 0.25
    PITCH_TRANSITION_TICK = 0.03

    def shift_root(self, new_root_index: int, direction: int) -> None:
        """Shift the root and start the slide animation in the given direction."""
        prev = self._root_index
        self._root_index = new_root_index
        self._pitch_transition = {
            "start": time.monotonic(),
            "direction": direction,  # +1 = right (right arrow), -1 = left
            "prev_root_index": prev,
        }
        # Stop any in-flight tick interval and start a fresh one.
        if self._pitch_transition_timer is not None:
            self._pitch_transition_timer.stop()
        self._pitch_transition_timer = self.set_interval(
            self.PITCH_TRANSITION_TICK, self._on_pitch_transition_tick,
        )
        self.refresh()

    def _on_pitch_transition_tick(self) -> None:
        if self._pitch_transition is None:
            if self._pitch_transition_timer is not None:
                self._pitch_transition_timer.stop()
                self._pitch_transition_timer = None
            return
        elapsed = time.monotonic() - self._pitch_transition["start"]
        if elapsed >= self.PITCH_TRANSITION_DURATION:
            self._pitch_transition = None
            if self._pitch_transition_timer is not None:
                self._pitch_transition_timer.stop()
                self._pitch_transition_timer = None
        self.refresh()

    def _transition_state_for_col(self, col: int) -> tuple[int, bool]:
        """Return (effective_root_index, is_at_wavefront) for a given column.

        Wave travels in the arrow's direction across cols 0..9. Columns the
        wave has already passed show the new root; columns ahead of it show
        the previous root (until the wave reaches them). The cell currently
        at the wave-front pulses for one tick.
        """
        t = self._pitch_transition
        if t is None:
            return self._root_index, False
        elapsed = time.monotonic() - t["start"]
        progress = max(0.0, min(1.0, elapsed / self.PITCH_TRANSITION_DURATION))
        # Wave position in column space (0..10).
        wavefront = progress * 10.0
        if t["direction"] >= 0:
            passed = col < wavefront
            at_front = abs(col - wavefront) < 0.6
        else:
            passed = col > (9 - wavefront)
            at_front = abs((9 - col) - wavefront) < 0.6
        effective = self._root_index if passed else t["prev_root_index"]
        return effective, at_front

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
        """Load pregenerated letter and number name clips from the letters/ subdirectory.

        When the parent enables Kid Voice (VM-only), A-Z clips are sourced from
        letters-kid/ first, falling back to the standard letters/ clip for any
        key without a kid recording (e.g. the digits).
        """
        sounds_path = self._get_sounds_path()
        letters_path = sounds_path / "letters"
        if not letters_path.exists():
            return
        search_dirs = [letters_path]
        from ..settings import get_kid_letters
        if get_kid_letters():
            kid_path = sounds_path / "letters-kid"
            if kid_path.exists():
                search_dirs.insert(0, kid_path)
        for key in _SPEAKABLE_KEYS:
            path = next(
                (p for d in search_dirs if (p := self._find_sound(d, key.lower()))),
                None,
            )
            if path:
                try:
                    sound = pygame.mixer.Sound(str(path))
                    sound.set_volume(0.4)
                    self._letter_sounds[key] = sound
                except pygame.error:
                    pass

    def play_letter(self, key: str) -> None:
        """Play the letter name clip for a key (respects app volume setting)."""
        from ..audio import play_safe
        if hasattr(self.app, '_effective_volume') and self.app._effective_volume() == 0:
            return
        self._ensure_letter_sounds_loaded()
        if key in self._letter_sounds:
            play_safe(self._letter_sounds[key])

    def reset_letter_sounds(self) -> None:
        """Drop cached letter clips so the next play reloads from the active source."""
        self._letter_sounds.clear()
        self._letter_sounds_loaded = False

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
            index: Color index: 0=keycap, 1=purple, -1=off
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
        """Get current color for a key, resolving the keycap sentinel."""
        idx = self.color_state[key]
        if idx < 0:
            return self._get_default_bg()
        state = COLORS[idx]
        if state is None:
            return self._get_default_bg()
        if state == COLOR_KEYCAP:
            return KEY_COLORS.get(key.lower(), self._get_default_bg())
        return state

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
            cell_height = min(height // 4, 5)
            grid_width = cell_width * 10
            grid_height = cell_height * 4
            margin_left = (width - grid_width) // 2
            # Cap the top margin at the canonical value (25-high box → 2) so a
            # one-row-taller box (hint bar hidden or pinned mid-reflow on slow
            # hardware) pushes slack below the grid instead of nudging it down.
            margin_top = min((height - grid_height) // 2, 2)
            self._cached_layout = (cell_width, cell_height, margin_left, margin_top, grid_width, grid_height)
        elif self._cached_layout is not None:
            # Reflow in progress: reuse last good layout
            cell_width, cell_height, margin_left, margin_top, grid_width, grid_height = self._cached_layout
        else:
            return Strip([Segment(" " * max(width, 0), Style(bgcolor=self._get_default_bg()))])

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

        # Pre-compute melodic row state for home-note highlight + dynamic
        # note labels. row_idx 0 is the percussion (digit) row in GRID_KEYS;
        # rows 1..3 are the three melodic rows (Q-P, A-;, Z-/).
        is_melodic_row = row_idx >= 1
        melodic_row = row_idx - 1 if is_melodic_row else None

        # Grid cells. All equal width
        for col_idx in range(10):
            key = GRID_KEYS[row_idx][col_idx]
            bg_color = self.get_color(key)
            cell_note_name: str | None = None
            at_wavefront = False
            if is_melodic_row:
                effective_root_idx, at_wavefront = self._transition_state_for_col(col_idx)
                effective_root = FRIENDLY_KEYS[effective_root_idx]
                cell_note_name, _ = pitch_for(
                    melodic_row, col_idx, effective_root, 0,
                )
                # Wave-front pulse: brighten cells the slide is currently
                # passing through. Visual scaffolding for the key shift.
                if at_wavefront:
                    bg_color = "#5a3875"

            # Determine text color via WCAG black-or-white contrast against bg.
            text_color = text_color_for(bg_color)
            on_light_bg = text_color == "#000000"

            cell_bg_style = Style(bgcolor=bg_color)
            text_style = Style(bgcolor=bg_color, color=text_color, bold=True)

            letter_line = mid_line
            note_above = mid_line - 1
            note_below = mid_line + 1
            if line_in_cell == letter_line:
                # Center the key character
                display_key = _KID_MATH_DISPLAY.get(key, key)
                pad_left = (cell_width - 1) // 2
                pad_right = cell_width - pad_left - 1
                segments.append(Segment(" " * pad_left, cell_bg_style))
                segments.append(Segment(display_key, text_style))
                segments.append(Segment(" " * pad_right, cell_bg_style))
            elif line_in_cell in (note_above, note_below) and (
                key in self._note_labels
                or (is_melodic_row and self._pitch_transition is not None)
                or (is_melodic_row and self._show_labels)
            ):
                # Flash note/percussion name, centered in cell. During a key
                # shift, all melodic cells show their note name so the swap
                # is visible as the wave passes through.
                if key.isdigit():
                    label = PERCUSSION_NAMES.get(key, "")
                else:
                    label = cell_note_name or ""
                if label:
                    decorated = f"{ICON_MUSIC_NOTE} {label} {ICON_MUSIC_NOTE}"
                    decorated_width = len(decorated)
                    muted_color = "#6a5a7a" if on_light_bg else "#887799"
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

    Stores raw markup and renders it as-is; uppercasing happens at the
    Strip render-time chokepoint.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._raw_markup: str = ""

    def set_hint(self, markup: str) -> None:
        self._raw_markup = markup
        self.refresh()

    def render(self) -> str:
        return self._raw_markup


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

    # Letters mode debounce — two thresholds, picked from clip + finger-mash
    # characteristics. Letter clips average ~0.34s. Kids 4-7 don't type fast
    # unless they're mashing, so thresholds are tuned aggressively.
    #   Same key: 400ms so hammering "A" lets each clip finish with a beat.
    #   Different key: 200ms so multi-finger mashes and frantic alternation
    #   collapse, while deliberate A-B-C-D taps (≤~4/sec) still pass.
    LETTERS_SAME_KEY_DEBOUNCE_S = 0.40
    LETTERS_CROSS_KEY_DEBOUNCE_S = 0.20

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.grid: MusicGrid | None = None
        self._header: MusicRoomHeader | None = None
        self._loop = LoopStation()
        self._letters_mode = False
        self._last_letter_key: str | None = None
        self._last_letter_press_t: float = float("-inf")
        self._instrument_index = 0
        self._root_index = DEFAULT_ROOT_INDEX
        self._loop_task: asyncio.Task | None = None
        self._recording_timer = None
        self._loop_progress_timer = None
        # Space hold REPL toggle; Enter hold loop-state advance.
        self._space_hold = HoldOrTap(hold_seconds=HOLD_OR_TAP_THRESHOLD)
        self._enter_hold = HoldOrTap(hold_seconds=HOLD_OR_TAP_THRESHOLD)
        self._repl_panel = None
        self._loop_panel: LoopPanel | None = None
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
        self._loop_panel = LoopPanel(id="music-loop-panel")
        yield self._loop_panel
        self._repl_panel = ReplPanel(room="music", id="music-repl")
        yield self._repl_panel

    @property
    def _is_noscreen(self) -> bool:
        return getattr(self.app, '_littles_mode', None) == 'music_noscreen'

    def on_mount(self) -> None:
        warm_mixer()
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

    _NOSCREEN_TEXT = "[dim]No-screen music mode\nPress keys to play sounds\n\nHold Esc to exit[/]"

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

    def stop_sound(self) -> None:
        """Silence the room without clearing it: visuals persist across a room switch."""
        self._stop_loop()

    def reset_state(self) -> None:
        """Reset music mode to defaults (colors, loop, instrument, letters mode)."""
        self._stop_loop()
        self._instrument_index = 0
        self._letters_mode = False
        self._root_index = DEFAULT_ROOT_INDEX
        if self.grid:
            self.grid.reset_colors()
            self.grid.set_instrument(0)
            self.grid._root_index = self._root_index
            self.grid._pitch_transition = None
            self.grid._show_labels = False
            self.grid.refresh()
        if self._header:
            self._header.update_instrument(INSTRUMENTS[0][1])
            self._header.update_mode(False)
            self._header.set_code_mode(False)
            self._header.update_pitch(self._root_index)

    # -- Loop station controls -----------------------------------------------

    def _advance_loop_state(self) -> None:
        """Hold-Enter advances the loop state machine linearly:
        IDLE → RECORDING → LOOPING → IDLE. Same gesture every time.

        No toasts: the loop panel itself shows the current state.
        """
        state = self._loop.state
        if state == IDLE:
            self._loop.start_recording()
            self._start_recording_timer()
            self._update_hint()

        elif state == RECORDING:
            events, _duration = self._loop.finish_recording()
            self._stop_recording_timer()
            if events:
                self._start_loop_playback()
                self._start_loop_progress_timer()
                self._update_hint()
            else:
                self._loop.stop()
                self._update_hint()

        elif state == LOOPING:
            self._stop_loop()

    def _handle_escape(self) -> bool:
        """Escape stops loop from any non-idle state. Returns True if consumed."""
        if self._loop.state == IDLE:
            return False
        self._stop_loop()
        return True

    def _stop_loop(self) -> None:
        """Stop everything: loop, timers, playback task."""
        self._loop.stop()
        self._stop_recording_timer()
        self._stop_loop_progress_timer()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = None
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
                        self._noscreen_flash(self.grid.get_color(key))

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

    def refresh_hint(self) -> None:
        """Public entry point for refreshing the hint after a mode change."""
        self._update_hint()

    def _update_hint(self) -> None:
        """Update the bottom hint bar based on loop station state.

        Text is stored raw (without caps). MusicExampleHint.render()
        applies caps at render time so it responds to caps changes immediately.
        """
        # Idle hint: single-line affordance line under the grid.
        try:
            hint = self.query_one("#example-hint", MusicExampleHint)
        except Exception:
            hint = None
        if hint is not None:
            if getattr(self.app, '_littles_mode', None):
                hint.set_hint("[dim]Enter: instrument[/]")
            else:
                labels_shown = bool(self.grid and getattr(self.grid, '_show_labels', False))
                space_hint = "Space: hide notes" if labels_shown else "Space: show notes"
                enter_hint = "Enter: instrument"
                parts = [space_hint]
                if getattr(self.app, '_music_key_switching_enabled', True):
                    parts.append("Arrows: switch key")
                parts.append(enter_hint)
                if getattr(self.app, '_music_looping_enabled', True):
                    parts.append("Hold Enter: loop")
                hint.set_hint("[dim]" + "    ".join(parts) + "[/]")

        # Loop panel: opens when recording/looping, closes back to idle.
        # Mirrors the REPL open/close: hides the inline hint, pins the grid
        # so it doesn't reflow under the panel, and posts a toggle message
        # so the app grows / shrinks the viewport.
        state = self._loop.state
        if self._loop_panel is None:
            return
        was_open = self._loop_panel.is_open
        if state == IDLE:
            if was_open:
                self._close_loop_panel_layout()
        else:
            if not was_open:
                self._open_loop_panel_layout()
            if state == RECORDING:
                self._loop_panel.set_recording(
                    self._loop.recording_progress(),
                    int(self._loop.recording_remaining()),
                )
            elif state == LOOPING:
                self._loop_panel.set_looping(self._loop.loop_progress())

    def _open_loop_panel_layout(self) -> None:
        """Hide the inline hint, pin grid height, open the loop panel."""
        try:
            self.query_one("#example-hint", MusicExampleHint).display = False
        except Exception:
            pass
        grid = self.query_one(MusicGrid)
        grid.styles.height = grid.size.height
        self._loop_panel.open()
        self.post_message(LoopPanelToggleRequested(opened=True))

    def _close_loop_panel_layout(self) -> None:
        """Restore inline hint, unpin grid, close the loop panel."""
        self._loop_panel.close()
        self.post_message(LoopPanelToggleRequested(opened=False))
        try:
            self.query_one("#example-hint", MusicExampleHint).display = True
        except Exception:
            pass
        try:
            grid = self.query_one(MusicGrid)
            grid._layout_ready = False
            grid.styles.height = "1fr"
        except Exception:
            pass

    # -- Core key handling ---------------------------------------------------

    def _current_mode(self) -> str:
        return MODE_LETTERS if self._letters_mode else MODE_MUSIC

    def _letters_debounce_drop(self, lookup: str, now: float) -> bool:
        """Return True if this letters-mode press should be dropped.

        Same-letter repeats wait roughly a clip length; cross-letter
        presses use a tighter floor so deliberate fast drills still pass.
        Updates last-key/last-time state when the press is accepted.
        """
        threshold = (
            self.LETTERS_SAME_KEY_DEBOUNCE_S
            if lookup == self._last_letter_key
            else self.LETTERS_CROSS_KEY_DEBOUNCE_S
        )
        if now - self._last_letter_press_t < threshold:
            return True
        self._last_letter_key = lookup
        self._last_letter_press_t = now
        return False

    def _play_key(self, key: str, mode: str, instrument: int | None = None) -> None:
        """Play audio for a key in the given mode.

        In music mode, all keys play instrument sounds.
        In letters mode, letter keys (A-Z) play their letter name clip
        layered with the instrument sound. Other keys just play sounds.

        If instrument is provided, play with that instrument instead of the
        current one (used by loop playback to preserve each layer's sound).
        """
        # Duck the instrument under the spoken letter clip so the letter is
        # the foreground sound in letters mode.
        is_letters_layer = mode == MODE_LETTERS and key in _SPEAKABLE_KEYS
        volume_scale = 0.2 if is_letters_layer else 1.0
        if instrument is not None:
            self.grid.play_sound_with_instrument(key, instrument, volume_scale)
        else:
            self.grid.play_sound(key, volume_scale)
        if is_letters_layer:
            self.grid.play_letter(key)

    def _on_space_tap(self) -> None:
        """Space tap.

        While recording: finish recording and start looping playback (so
        the kid can "stop the loop and play it back" without hold-Enter
        which is reserved for closing the panel).

        Otherwise: toggle note name labels in every melodic cell.
        """
        if getattr(self.app, '_littles_mode', None):
            return
        if self._loop.state == RECORDING:
            self._advance_loop_state()  # recording → looping
            return
        if self._loop.state == LOOPING:
            # Restart the cycle from the top without changing the track length.
            self._loop.start_new_cycle()
            self._update_hint()
            return
        if self.grid is not None:
            self.grid._show_labels = not self.grid._show_labels
            self.grid.refresh()
            self._update_hint()

    def _on_enter_hold_fired(self) -> None:
        """Enter held long enough.

        From idle: start recording. From recording or looping: close the
        loop panel completely (full stop). Space (tap) is the gesture that
        advances recording into playback — Enter is reserved for "exit."

        While the code panel is open, Enter belongs to the REPL — ignore.
        """
        if getattr(self.app, '_littles_mode', None):
            return
        if self._repl_panel and self._repl_panel.is_open:
            return
        if self._loop.state == IDLE:
            if not getattr(self.app, '_music_looping_enabled', True):
                return
            self._advance_loop_state()  # idle → recording
        else:
            self._stop_loop()  # any non-idle → close panel

    def _on_space_hold_fired(self) -> None:
        """Space held long enough: toggle REPL.

        While the loop panel is open, Space belongs to the loop — ignore the
        hold-fire so the loop panel isn't yanked out from under the kid.
        """
        if not getattr(self.app, '_code_panel_enabled', True):
            return
        if self._loop_panel and self._loop_panel.is_open:
            return
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
                label = "Say Letters" if self._letters_mode else INSTRUMENTS[self._instrument_index][1]
                self.app.clear_notifications()
                self.app.notify(f"{ICON_MUSIC} {label}" if not self._letters_mode else label, timeout=1.5)
            return

        if isinstance(action, ControlAction):
            if action.action == 'space':
                # Space tap toggles note labels; space hold opens code panel.
                # After hold fired, suppress until release.
                if self._space_hold.fired:
                    if not action.is_down:
                        self._space_hold.on_up()
                    return
                if action.is_down and not action.is_repeat:
                    self._space_hold.on_down(self.set_timer, self._on_space_hold_fired)
                elif not action.is_down:
                    if self._space_hold.on_up():
                        self._on_space_tap()
                return

            if action.action == 'enter':
                # Tap cycles instrument; hold advances loop state. Littles mode
                # allows the tap but no-ops the hold (in _on_enter_hold_fired).
                if self._enter_hold.fired:
                    if not action.is_down:
                        self._enter_hold.on_up()
                    return
                if action.is_down and not action.is_repeat:
                    self._space_hold.on_other_key()
                    self._enter_hold.on_down(self.set_timer, self._on_enter_hold_fired)
                elif not action.is_down:
                    if self._enter_hold.on_up():
                        # Tap: cycle instrument
                        self._instrument_index = (self._instrument_index + 1) % len(INSTRUMENTS)
                        _inst_id, inst_name = INSTRUMENTS[self._instrument_index]
                        if self.grid:
                            self.grid.set_instrument(self._instrument_index)
                        if self._header:
                            self._header.update_instrument(inst_name)
                        self.app.clear_notifications()
                        self.app.notify(f"{ICON_MUSIC} {inst_name}", timeout=1.5)
                return

            if action.is_down:
                # Any other control key: cancel pending holds
                self._space_hold.on_other_key()
                self._enter_hold.on_other_key()

                # Escape: stop loop if active
                if action.action == 'escape':
                    if self._handle_escape():
                        self.app._escape_consumed_by_mode = True
                    return

                # Tab: stop loop if active, otherwise switch mode
                if action.action == 'tab':
                    if self._loop.state != IDLE:
                        self._stop_loop()
                        return
                    self._letters_mode = not self._letters_mode
                    if self._header:
                        self._header.update_mode(self._letters_mode)
                    label = "Say Letters" if self._letters_mode else INSTRUMENTS[self._instrument_index][1]
                    self.app.clear_notifications()
                    self.app.notify(f"{ICON_MUSIC} {label}" if not self._letters_mode else label, timeout=1.5)
                    return

        # Arrows: shift key (Left/Right). Up/Down unbound. Arrows DO NOT
        # close the loop panel — the kid can shift key while looping. Tab
        # and Esc remain the easy-outs.
        if isinstance(action, NavigationAction):
            if action.is_repeat:
                return
            if getattr(self.app, '_littles_mode', None):
                return
            if not getattr(self.app, '_music_key_switching_enabled', True):
                return
            self._space_hold.on_other_key()
            self._enter_hold.on_other_key()
            d = action.direction
            if d in ('left', 'right'):
                step = 1 if d == 'right' else -1
                self._root_index = (self._root_index + step) % len(FRIENDLY_KEYS)
                if self.grid:
                    self.grid.shift_root(self._root_index, step)
                if self._header:
                    self._header.update_pitch(self._root_index)
                root_name = FRIENDLY_KEY_NAMES[self._root_index]
                self.app.clear_notifications()
                self.app.notify(f"{ICON_MUSIC} Key {root_name}", timeout=1.5)
            return

        # Character keys: play sound, cycle color, record into loop if active.
        # Piano semantics: a held key plays one note, not a stream of repeats.
        # Tapping fast still produces overlapping notes because each fresh
        # press is is_repeat=False.
        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            # Any key press: cancel space hold
            self._space_hold.on_other_key()

            char = action.char
            if not char:
                return

            lookup = char.upper() if char.isalpha() else _KID_MATH_UNREMAP.get(char, char)

            # Letters mode debounce: keep spoken clips from stacking, whether
            # the kid is hammering one key or mashing many. Music mode stays
            # un-debounced (piano semantics).
            if self._letters_mode and lookup in ALL_KEYS:
                if self._letters_debounce_drop(lookup, time.monotonic()):
                    return

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
                    self._noscreen_flash(self.grid.get_color(lookup))
            return

