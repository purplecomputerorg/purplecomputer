"""Parent Menu: hold Esc. Install, Littles Mode, code and looping toggles,
ALL CAPS, sound lock, display, PIN, terminal, support, shut down."""

import asyncio
import json
import math
import os
import re
import select
import subprocess
import threading
import time
from pathlib import Path

import pygame

from .. import diagnostics
from .. import palette as P
from ..constants import SUPPORT_EMAIL, VOLUME_LEVELS, is_debug, is_live_boot, is_usb_cached, is_usb_present
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from ..ui import CANCELLED, TRACK, Dialog, Overlay, Picker, draw_bar, draw_scrim, draw_window, window_title_height
from .sleep_screen import FullScreen

DEFAULT_COMPUTER_NAME = "My Purple Computer"

# ---------------------------------------------------------------------------
# Display settings (xrandr brightness / gamma)
# ---------------------------------------------------------------------------
DISPLAY_SETTINGS_FILE = Path.home() / ".config" / "purple" / "display.json"
BRIGHTNESS_MIN, BRIGHTNESS_MAX, BRIGHTNESS_STEP, BRIGHTNESS_DEFAULT = 0.5, 1.0, 0.1, 1.0
CONTRAST_MIN, CONTRAST_MAX, CONTRAST_STEP, CONTRAST_DEFAULT = 0.7, 1.3, 0.1, 1.0


def load_display_settings() -> dict:
    try:
        if DISPLAY_SETTINGS_FILE.exists():
            data = json.loads(DISPLAY_SETTINGS_FILE.read_text())
            return {"brightness": float(data.get("brightness", BRIGHTNESS_DEFAULT)),
                    "contrast": float(data.get("contrast", CONTRAST_DEFAULT))}
    except Exception:
        pass
    return {"brightness": BRIGHTNESS_DEFAULT, "contrast": CONTRAST_DEFAULT}


def save_display_settings(settings: dict) -> bool:
    try:
        DISPLAY_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        DISPLAY_SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        return True
    except Exception:
        return False


_cached_xrandr_outputs = None


def _get_xrandr_outputs() -> list:
    global _cached_xrandr_outputs
    if _cached_xrandr_outputs is not None:
        return _cached_xrandr_outputs
    try:
        result = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return []
        _cached_xrandr_outputs = [line.split()[0] for line in result.stdout.splitlines() if " connected" in line]
        return _cached_xrandr_outputs
    except Exception:
        return []


def _check_xrandr_works() -> bool:
    outputs = _get_xrandr_outputs()
    if not outputs:
        return False
    try:
        result = subprocess.run(["xrandr", "--output", outputs[0], "--brightness", "1.0", "--gamma", "1.0:1.0:1.0"],
                                capture_output=True, text=True, timeout=5)
        out = result.stdout + result.stderr
        if "need crtc" in out or "not found" in out:
            return False
        return result.returncode == 0
    except Exception:
        return False


_display_control_available = None


def display_control_available() -> bool:
    global _display_control_available
    if _display_control_available is None:
        _display_control_available = _check_xrandr_works()
    return _display_control_available


def apply_display_settings(brightness: float, contrast: float) -> bool:
    if not display_control_available():
        return False
    brightness = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, brightness))
    contrast = max(CONTRAST_MIN, min(CONTRAST_MAX, contrast))
    outputs = _get_xrandr_outputs()
    if not outputs:
        return False
    gamma = 2.0 - contrast
    gamma_str = f"{gamma:.1f}:{gamma:.1f}:{gamma:.1f}"
    try:
        for output in outputs:
            subprocess.Popen(["xrandr", "--output", output, "--brightness", str(brightness), "--gamma", gamma_str],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def apply_saved_display_settings():
    s = load_display_settings()
    if s["brightness"] != BRIGHTNESS_DEFAULT or s["contrast"] != CONTRAST_DEFAULT:
        apply_display_settings(s["brightness"], s["contrast"])


class DisplaySettingsScreen(Dialog):
    title = "Display"
    hint = "← → adjust   ▲ ▼ switch   Esc done"
    width_pct = 50

    def __init__(self, app):
        super().__init__(app)
        s = load_display_settings()
        self._brightness, self._contrast = s["brightness"], s["contrast"]
        self._focus = 0

    def body_height(self, g):
        return g.vh(14)

    def draw_body(self, g, rect):
        rows = [("Brightness", self._brightness, BRIGHTNESS_MIN, BRIGHTNESS_MAX, BRIGHTNESS_STEP, BRIGHTNESS_MAX),
                ("Contrast", self._contrast, CONTRAST_MIN, CONTRAST_MAX, CONTRAST_STEP, 1.0)]
        px = g.vh(2.4)
        for i, (label, value, lo, hi, step, normal) in enumerate(rows):
            y = rect.y + i * g.vh(7) + g.vh(2)
            on = i == self._focus
            g.draw_text(f"{label}:", px, rect.x, y, "sans-bold", P.TEXT if on else P.MUTED, anchor="midleft")
            bx = rect.x + g.vw(11)
            bw = rect.w - g.vw(20)
            if on:
                g.draw_text("◀", px, bx - g.vw(1.2), y, "sans-bold", P.PRIMARY, anchor="midright")
                g.draw_text("▶", px, bx + bw + g.vw(1.2), y, "sans-bold", P.PRIMARY, anchor="midleft")
            draw_bar(g, bx, y - g.vh(0.7), bw, g.vh(1.4), (value - lo) / (hi - lo), P.PRIMARY if on else P.MUTED)
            offset = round((value - normal) / step)
            g.draw_text("Normal" if offset == 0 else f"{offset:+d}", px, rect.right, y, "sans-bold", P.MUTED, anchor="midright")

    def _save_and_apply(self):
        apply_display_settings(self._brightness, self._contrast)
        save_display_settings({"brightness": self._brightness, "contrast": self._contrast})

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            d = action.direction
            if d in ("up", "down"):
                self._focus = 0 if d == "up" else 1
            elif d in ("left", "right"):
                sign = 1 if d == "right" else -1
                if self._focus == 0:
                    self._brightness = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, self._brightness + sign * BRIGHTNESS_STEP))
                else:
                    self._contrast = max(CONTRAST_MIN, min(CONTRAST_MAX, self._contrast + sign * CONTRAST_STEP))
                self._save_and_apply()
            self.app.invalidate()
        elif isinstance(action, ControlAction) and action.is_down and action.action in ("enter", "escape"):
            self.close(True)


# ---------------------------------------------------------------------------
# Pickers
# ---------------------------------------------------------------------------


class LittlesExitScreen(Picker):
    title = "Exit Littles Mode?"
    OPTIONS = [("exit", "Yes, exit"), ("go_back", "No, go back"), ("switch", "Switch activity"), ("parent", "Parent Menu")]
    default_selected = 1
    escape_value = "go_back"


class LittlesModeScreen(Picker):
    title = "Littles Mode"
    DESCRIPTION = "One activity, no menus, no switching"
    OPTIONS = [(None, "Off", "All rooms, full experience"),
               ("music", "Music", "Every key plays a sound and shows a color"),
               ("music_noscreen", "No-Screen Music", "Sounds only, screen stays dark"),
               ("art", "Art", "Every key puts color on the canvas")]
    escape_value = CANCELLED

    def __init__(self, app):
        super().__init__(app)
        from ..settings import get_littles_mode
        current = get_littles_mode()
        self.selected = next((i for i, o in enumerate(self.OPTIONS) if o[0] == current), 0)

    def _on_confirm(self, value):
        from ..settings import set_littles_mode
        set_littles_mode(value)
        self.close(value)


class _YesNo(Picker):
    OPTIONS = [(True, "Yes"), (False, "No")]
    escape_value = CANCELLED
    getter = None

    def __init__(self, app):
        super().__init__(app)
        self.selected = 0 if self.getter() else 1


class CodePanelScreen(_YesNo):
    title = "Allow Code Space"
    DESCRIPTION = "Allow older kids to write code in Music and Art by holding the space button"

    @staticmethod
    def getter():
        from ..settings import get_code_panel
        return get_code_panel()


class MusicLoopingScreen(_YesNo):
    title = "Allow Music Looping"
    DESCRIPTION = "Allow recording loops in Music by holding the enter button"

    @staticmethod
    def getter():
        from ..settings import get_music_looping
        return get_music_looping()


class MusicKeySwitchingScreen(_YesNo):
    title = "Allow Music Key Switching"
    DESCRIPTION = "Allow changing the musical key in Music with the arrow keys"

    @staticmethod
    def getter():
        from ..settings import get_music_key_switching
        return get_music_key_switching()


class AllCapsScreen(_YesNo):
    title = "ALL CAPS"
    DESCRIPTION = "Show every letter as a capital letter"
    OPTIONS = [(True, "On"), (False, "Off")]

    @staticmethod
    def getter():
        from ..settings import get_all_caps
        return get_all_caps()


class KidLettersScreen(_YesNo):
    title = "Kid Voice Letters"
    DESCRIPTION = "Use the recorded kid-voice clips for A-Z in Say Letters mode"
    OPTIONS = [(True, "On"), (False, "Off")]

    @staticmethod
    def getter():
        from ..settings import get_kid_letters
        return get_kid_letters()

    def _on_confirm(self, value):
        from ..settings import set_kid_letters
        set_kid_letters(value)
        self.app.rooms["music"].reset_letter_sounds()
        self.close(value)


class SecretMenuScreen(Picker):
    title = "Secret Menu"
    DESCRIPTION = "Family only"
    OPTIONS = [("kid-letters", "Kid Voice Letters"), ("doodle", "Surprise Drawing"), ("photo", "Family Photo"), (None, "Close")]

    def _on_confirm(self, value):
        if value == "kid-letters":
            self.app.push(KidLettersScreen(self.app))
        else:
            self.close(value)


class PinActionScreen(Picker):
    title = "Parent PIN"
    OPTIONS = [("change", "Change PIN"), ("clear", "Turn Off")]


class InstallConfirmScreen(Picker):
    title = "Install Purple Computer"
    DESCRIPTION = ("This will set up Purple Computer\non this laptop.\n\n"
                   f"[bold {P.DANGER}]Everything on this computer\nwill be erased.[/]")
    OPTIONS = [(True, "Yes, install"), (False, "No, go back")]
    default_selected = 1
    escape_value = False

    async def handle(self, action):
        if isinstance(action, CharacterAction):
            return self.close(False)
        await super().handle(action)


# ---------------------------------------------------------------------------
# Sound: volume + lock + test tone
# ---------------------------------------------------------------------------
_VOLUME_LEVEL_LABELS = {0: "Silent Mode", 15: "Whisper", 35: "Quiet", 60: "Medium", 85: "Loud", 100: "Full"}


def _volume_menu_label(lock) -> str:
    if lock == 0:
        return "Sound: Silent Mode"
    return "Sound: Locked" if lock is not None else "Sound"


class ParentVolumeModal(Dialog):
    title = "Volume"
    width_pct = 50

    def __init__(self, app):
        super().__init__(app)
        self._focus = "volume"

    @property
    def hint(self):
        row = "← → change    ▲ ▼ switch" if self._focus == "volume" else "Enter on/off    ▲ ▼ switch"
        return f"{row}\nSpace plays sound    Esc done"

    def body_height(self, g):
        return g.vh(14)

    def draw_body(self, g, rect):
        px = g.vh(2.4)
        level = self.app.volume_level
        y = rect.y + g.vh(2)
        on = self._focus == "volume"
        g.draw_text("Volume:", px, rect.x, y, "sans-bold", P.TEXT if on else P.MUTED, anchor="midleft")
        bx, bw = rect.x + g.vw(9), rect.w - g.vw(24)
        if on:
            g.draw_text("◀", px, bx - g.vw(1.2), y, "sans-bold", P.PRIMARY, anchor="midright")
            g.draw_text("▶", px, bx + bw + g.vw(1.2), y, "sans-bold", P.PRIMARY, anchor="midleft")
        draw_bar(g, bx, y - g.vh(0.7), bw, g.vh(1.4), level / 100, P.PRIMARY if on else P.MUTED)
        g.draw_text(_VOLUME_LEVEL_LABELS.get(level, str(level)), px, rect.right, y, "sans-bold", P.MUTED, anchor="midright")
        y += g.vh(7)
        on = self._focus == "lock"
        g.draw_text("Lock:", px, rect.x, y, "sans-bold", P.TEXT if on else P.MUTED, anchor="midleft")
        state = "On" if self.app._volume_lock is not None else "Off"
        g.draw_text(("▶ " if on else "") + state, px, bx, y, "sans-bold", P.PRIMARY if on else P.MUTED, anchor="midleft")

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            d = action.direction
            if d == "down":
                self._focus = "lock"
            elif d == "up":
                self._focus = "volume"
            elif d in ("left", "right") and self._focus == "volume":
                self._adjust(d == "right")
            self.app.invalidate()
            return
        if isinstance(action, ControlAction) and action.is_down and not action.is_repeat:
            if action.action == "space":
                self._play_test_sound()
            elif action.action == "enter" and self._focus == "lock":
                self._toggle_lock()
            elif action.action in ("enter", "escape"):
                self.app._apply_volume_system()
                self.close(None)

    def _adjust(self, up: bool):
        cur = self.app.volume_level
        new = next((v for v in VOLUME_LEVELS if v > cur), cur) if up else next((v for v in reversed(VOLUME_LEVELS) if v < cur), cur)
        if new == cur:
            return
        self.app.volume_level = new
        if self.app._volume_lock is not None:
            self._write_lock(new)
        self.app._apply_volume()

    def _toggle_lock(self):
        self._write_lock(None if self.app._volume_lock is not None else self.app.volume_level)
        self.app._apply_volume()

    def _write_lock(self, level):
        from ..settings import set_volume_lock
        set_volume_lock(level)
        self.app._volume_lock = level

    def _play_test_sound(self):
        level = self.app.volume_level
        if level == 0:
            return
        try:
            from ..constants import SYSTEM_VOLUME_MAX
            subprocess.run(["amixer", "sset", "Master", f"{round(level * SYSTEM_VOLUME_MAX / 100)}%"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        except Exception:
            pass
        try:
            from ..audio import play_safe
            from ..mixer import warm_mixer
            if not warm_mixer():
                return
            path = Path(__file__).parent.parent.parent / "packs" / "core-sounds" / "content" / "glockenspiel" / "c5.ogg"
            if path.exists():
                sound = pygame.mixer.Sound(str(path))
                sound.set_volume(level / 100)
                play_safe(sound)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# PIN and name entry
# ---------------------------------------------------------------------------


class _Entry(Dialog):
    """A dialog with a description, a one-line field, and an error slot."""

    hint = "Enter  Esc"
    width_pct = 46

    def __init__(self, app, title, description):
        super().__init__(app)
        self.title = title
        self._description = description
        self._error = ""
        self._blink_on = True

    def on_open(self):
        self._timer = self.app.timers.every(0.5, self._blink)

    def on_close(self):
        self._timer.stop()

    def _blink(self):
        self._blink_on = not self._blink_on
        self.app.invalidate()

    def body_height(self, g):
        return g.vh(14)

    def field_text(self) -> str:
        return ""

    def draw_body(self, g, rect):
        desc = self._error or self._description
        g.draw_markup(desc, g.vh(2.2), rect.x, rect.y, "sans", P.DANGER if self._error else P.MUTED, rect.w, "center", P.SURFACE, g.vh(0.4))
        g.draw_markup(self.field_text(), g.vh(3.4), rect.x, rect.y + g.vh(8), "mono-bold", P.TEXT, rect.w, "center", P.SURFACE)


class PinEntry(_Entry):
    _LEN = 4

    def __init__(self, app, title="Enter PIN", description="Type 4 digits.\nForgot it? Reinstall from USB to reset.",
                 verify=None, error_message="Wrong PIN, try again."):
        super().__init__(app, title, description)
        self._verify = verify
        self._error_message = error_message
        self._pin = ""
        self._ignore_keys = {"escape"}   # the parent may still be holding Esc from opening this

    def field_text(self):
        filled = "● " * len(self._pin)
        empty = "_ " * (self._LEN - len(self._pin))
        if self._blink_on and len(self._pin) < self._LEN:
            empty = "█ " + "_ " * max(0, self._LEN - len(self._pin) - 1)
        return (filled + empty).rstrip()

    def _submit(self):
        if len(self._pin) != self._LEN:
            self._error = "Type 4 digits."
        elif self._verify is not None and not self._verify(self._pin):
            self._pin, self._error = "", self._error_message
        else:
            return self.close(self._pin)
        self.app.invalidate()

    async def handle(self, action):
        if isinstance(action, ControlAction):
            key = action.action
            if not action.is_down:
                self._ignore_keys.discard(key)
                return
            if key in self._ignore_keys:
                return
            if key == "escape":
                self.close(None)
            elif key == "enter":
                self._submit()
            elif key == "backspace" and self._pin:
                self._pin, self._error = self._pin[:-1], ""
                self.app.invalidate()
        elif isinstance(action, CharacterAction) and not action.is_repeat:
            ch = action.char
            if ch and ch.isdigit() and len(self._pin) < self._LEN:
                self._pin += ch
                self._error = ""
                self.app.invalidate()
                if len(self._pin) == self._LEN:
                    self._submit()


_NAME_MAX = 24


class ComputerNameScreen(_Entry):
    """Returns the trimmed name (maybe empty) or CANCELLED."""

    _MIN_LEN = 3

    def __init__(self, app, title="Name this computer", description="Optional. Leave blank to skip.", initial=""):
        super().__init__(app, title, description)
        self._name = initial

    def field_text(self):
        cursor = "█" if self._blink_on else " "
        return self._name + cursor if self._name else f"{cursor} [dim]{DEFAULT_COMPUTER_NAME}[/]"

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.is_down:
            key = action.action
            if key == "escape":
                return self.close(CANCELLED)
            if key == "enter":
                trimmed = self._name.strip()
                if not self._name:
                    return self.close("")
                if len(trimmed) < self._MIN_LEN:
                    self._error = f"Use {self._MIN_LEN}+ letters or leave blank."
                else:
                    return self.close(trimmed[:_NAME_MAX])
            elif key == "backspace" and self._name:
                self._name, self._error = self._name[:-1], ""
            elif key == "space" and len(self._name) < _NAME_MAX:
                self._name, self._error = self._name + " ", ""
            self.app.invalidate()
        elif isinstance(action, CharacterAction) and not action.is_repeat and action.char and len(self._name) < _NAME_MAX:
            self._name, self._error = self._name + action.char, ""
            self.app.invalidate()


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
_NOMINAL_WRITE_SECS = 420.0
_INSTALL_STAGES = [
    ("Detecting internal disk",       5,  "Getting started...",            4,   False),
    ("Found internal disk",           8,  "Getting started...",            3,   False),
    ("Writing Purple Computer",       10, "Setting up Purple Computer...", _NOMINAL_WRITE_SECS, True),
    ("Reloading partition table",     70, "Double-checking everything...", 8,   False),
    ("Verifying disk write",          72, "Double-checking everything...", 180, True),
    ("Disk verification passed",      85, "Double-checking everything...", 3,   False),
    ("Rebuilding partition table",    86, "Almost ready...",               8,   False),
    ("Waiting for partition devices", 88, "Almost ready...",               10,  False),
    ("Checking root filesystem",      90, "Almost ready...",               25,  False),
    ("Growing root filesystem",       92, "Almost ready...",               25,  False),
    ("Setting up boot",               94, "Almost ready...",               50,  False),
    ("Boot setup complete",           98, "Almost ready...",               5,   False),
]


def _build_eta_curve():
    pts = [(_INSTALL_STAGES[0][1], 0.0)]
    cum = 0.0
    for i, (_, pct, _disp, nominal, _pv) in enumerate(_INSTALL_STAGES):
        cum += nominal
        nxt = _INSTALL_STAGES[i + 1][1] if i + 1 < len(_INSTALL_STAGES) else 100
        pts.append((nxt, cum))
    return pts, cum


_ETA_CURVE, _ETA_TOTAL_SECS = _build_eta_curve()
_REBOOT_BIN = '/run/purple-reboot-mount/purple-reboot'
_SENTINEL = Path('/run/purple-install-complete')


class InstallProgressScreen(FullScreen):
    """Runs install.sh on a thread, streams its [PURPLE] lines into a progress
    bar with a speed-calibrated ETA, then hands off to the reboot screen or
    shows the failure page with a scrollable diagnostics report."""

    _SCROLL_DELAY = 0.25
    _SCROLL_VISIBLE = 25

    def __init__(self, app, computer_name: str = ""):
        super().__init__(app)
        self._progress = 0
        self._status = "Starting..."
        self._phase = "installing"
        self._log_lines: list = []
        self._corrupt_key = False
        self._diag_lines: list = []
        self._diag_scroll_pos = 0
        self._scroll_timer = None
        self._scrolling = False
        self._computer_name = computer_name
        self._start_time = None
        self._creep_timer = None
        self._creep_t0 = 0.0
        self._creep_lo = self._creep_hi = 0
        self._creep_tau = 1.0
        self._write_t0 = None
        self._k = 1.0

    def on_open(self):
        self.app.inhibit_idle("install")
        self._start_time = time.monotonic()
        self._creep_timer = self.app.timers.every(0.5, self._creep_tick)
        threading.Thread(target=self._run_install_thread, daemon=True).start()

    def on_close(self):
        self.app.uninhibit_idle("install")
        if self._creep_timer:
            self._creep_timer.stop()
        self._stop_diag_scroll()

    # --- ETA (unchanged math) ---
    def _time_fraction(self, pct: int) -> float:
        if pct <= _ETA_CURVE[0][0]:
            return 0.0
        prev_p, prev_c = _ETA_CURVE[0]
        for p, c in _ETA_CURVE[1:]:
            if pct <= p:
                return (prev_c + (c - prev_c) * (pct - prev_p) / (p - prev_p)) / _ETA_TOTAL_SECS
            prev_p, prev_c = p, c
        return 1.0

    def _nominal_remaining_secs(self) -> float:
        total = 0.0
        n = len(_INSTALL_STAGES)
        for i, (_, pct, _disp, nominal, _pv) in enumerate(_INSTALL_STAGES):
            hi = _INSTALL_STAGES[i + 1][1] if i + 1 < n else 100
            if self._progress >= hi:
                continue
            total += nominal if self._progress <= pct else nominal * (hi - self._progress) / (hi - pct)
        return total * self._k

    def _eta_hint(self) -> str:
        if self._progress < 20 or self._start_time is None:
            return "This usually takes 10 to 15 minutes"
        f = self._time_fraction(self._progress)
        if f <= 0:
            return "This usually takes 10 to 15 minutes"
        elapsed = time.monotonic() - self._start_time
        remaining = max(elapsed * (1 - f) / f, self._nominal_remaining_secs())
        if self._progress >= 96 or remaining < 45:
            return "Almost done"
        minutes = max(1, math.ceil(remaining / 60))
        return f"About {minutes} {'minute' if minutes == 1 else 'minutes'} left"

    def _set_progress(self, pct: int, status: str):
        if pct > self._progress:
            self._progress, self._status = pct, status
            self.app.invalidate()

    def _start_creep_band(self, lo: int, hi: int, nominal_secs: float, pv_driven: bool):
        self._creep_t0 = time.monotonic()
        self._creep_lo = max(lo, self._progress)
        self._creep_hi = self._creep_lo if pv_driven else hi
        self._creep_tau = max(0.5, nominal_secs * self._k / 3.0)

    def _creep_tick(self):
        if self._phase != "installing" or self._creep_hi <= self._creep_lo:
            return
        t = time.monotonic() - self._creep_t0
        pct = self._creep_lo + int((self._creep_hi - self._creep_lo) * (1.0 - math.exp(-t / self._creep_tau)))
        if pct < self._creep_hi:
            self._set_progress(pct, self._status)
        self.app.invalidate()

    # --- install subprocess (thread; UI updates hop back to the loop) ---
    def _run_install_thread(self):
        proc = subprocess.Popen(
            ["sudo", "-E", "bash", "/cdrom/purple/install.sh"], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
            env={**os.environ, "PURPLE_PAYLOAD_DIR": "/cdrom/purple", "PURPLE_COMPUTER_NAME": self._computer_name,
                 "PURPLE_LIVE_AUDIO_OK": "1" if self.app.audio_ok is True else "0"})
        buf = b""

        def emit(line: bytes):
            self.app.call_from_thread(self._handle_line, line.decode("utf-8", errors="replace"))
        while proc.poll() is None and not _SENTINEL.exists():
            if select.select([proc.stderr], [], [], 0.1)[0]:
                chunk = proc.stderr.read(256)
                if chunk:
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        emit(line)
        try:
            buf += proc.stderr.read() or b""
        except Exception:
            pass
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            emit(line)
        if buf.strip():
            emit(buf)
        self.app.call_from_thread(self._on_install_complete, _SENTINEL.exists() or proc.poll() == 0)

    def _on_install_complete(self, success: bool):
        if success and os.path.isfile(_REBOOT_BIN):
            self._phase = "done"
            self.app.push(InstallDoneScreen(self.app))
            return
        self._phase = "error"
        self.app.invalidate()

    def _handle_line(self, text: str):
        clean = _ANSI_ESCAPE.sub("", text).strip()
        if clean:
            self._log_lines.append(clean)
        for tag, lo, span in (("[PURPLE-PV]", 10, 60), ("[PURPLE-PV2]", 72, 13)):
            if clean.startswith(tag):
                try:
                    pv = max(0, min(100, int(clean[len(tag):].strip())))
                except ValueError:
                    return
                return self._set_progress(lo + int(pv * span / 100), self._status)
        if clean.startswith("[PURPLE-RETRY]"):
            self._status = "Double-checking with a backup copy..."
            return self.app.invalidate()
        if clean.startswith("[PURPLE-MERGING]"):
            self._status = "Still double-checking, this adds a few extra minutes..."
            return self.app.invalidate()
        if clean.startswith("[PURPLE-CORRUPT-KEY]"):
            self._corrupt_key = True
            return
        if not clean.startswith("[PURPLE]"):
            return
        msg = clean[8:].strip()
        for i, (keyword, pct, display, nominal, pv_driven) in enumerate(_INSTALL_STAGES):
            if keyword in msg and pct > self._progress:
                if keyword == "Writing Purple Computer":
                    self._write_t0 = time.monotonic()
                elif self._write_t0 is not None and pct >= 70:
                    self._k = min(6.0, max(0.25, (time.monotonic() - self._write_t0) / _NOMINAL_WRITE_SECS))
                    self._write_t0 = None
                self._set_progress(pct, display)
                hi = _INSTALL_STAGES[i + 1][1] if i + 1 < len(_INSTALL_STAGES) else 100
                self._start_creep_band(pct, hi, nominal, pv_driven)
                return

    def _get_error_summary(self) -> str:
        for tags, prefixes in ((("[ERROR]", "[PURPLE ERROR]"), ("[PURPLE ERROR] ", "[ERROR] ")),
                               (("[WARN]", "[PURPLE WARN]"), ("[PURPLE WARN] ", "[WARN] "))):
            for line in reversed(self._log_lines):
                if any(t in line for t in tags):
                    for prefix in prefixes:
                        if prefix in line:
                            return f"(Technical: {line.split(prefix, 1)[-1]})"
                    return f"(Technical: {line})"
        return ""

    def _collect_diagnostics(self) -> list:
        lines: list = []

        def section(title):
            lines.extend(["", f"=== {title} ==="])

        def cmd(label, command, max_lines=20):
            try:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=5)
                output = (result.stdout + result.stderr).strip()
                lines.extend(f"  {ln}" for ln in output.splitlines()[:max_lines]) if output else lines.append(f"  ({label}: no output)")
            except Exception:
                lines.append(f"  ({label}: failed)")

        def file_info(label, path):
            try:
                p = Path(path)
                if p.is_file():
                    lines.append(f"  {label}: {path} ({p.stat().st_size} bytes)")
                elif p.is_dir():
                    lines.append(f"  {label}: {path} (directory)")
                else:
                    lines.append(f"  {label}: {path} NOT FOUND")
            except Exception:
                lines.append(f"  {label}: {path} (check failed)")
        section("Install log (last 40 lines)")
        lines.extend(f"  {ln}" for ln in self._log_lines[-40:]) if self._log_lines else lines.append("  (no log output captured)")
        section("Device")
        try:
            lines.extend(f"  {ln}" for ln in diagnostics.device_summary_lines())
        except Exception:
            lines.append("  (device info failed)")
        section("USB / source media")
        file_info("Golden image", "/cdrom/purple/purple-os.img.zst")
        file_info("Install script", "/cdrom/purple/install.sh")
        file_info("/cdrom mount", "/cdrom")
        cmd("cdrom contents", "ls /cdrom/purple/ 2>&1", 10)
        cmd("USB device", "blkid -L PURPLE_INSTALLER 2>&1", 3)
        section("Memory")
        cmd("meminfo", "free -h 2>&1", 5)
        section("Block devices")
        cmd("lsblk", "lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT 2>&1")
        section("Partition IDs")
        cmd("blkid", "blkid 2>&1")
        section("/proc/partitions")
        cmd("partitions", "cat /proc/partitions 2>&1")
        section("Device-mapper")
        cmd("dmsetup", "dmsetup ls 2>&1")
        section("Mounts (non-virtual)")
        cmd("mounts", ("mount | grep -v -e 'type proc' -e 'type sys' -e 'type devpts' -e 'type tmpfs' -e 'type cgroup'"
                       " -e 'type securityfs' -e 'type debugfs' -e 'type pstore' -e 'type fusectl' -e 'type configfs'"
                       " -e 'type bpf' -e 'type efivarfs' -e 'type hugetlbfs' -e 'type mqueue' -e 'type tracefs' 2>&1"))
        section("EFI boot entries")
        cmd("efibootmgr", "efibootmgr -v 2>&1", 15)
        section("EFI partition contents")
        cmd("efi-ls", ("for d in /mnt/efi /boot/efi; do  [ -d \"$d/EFI\" ] && find \"$d/EFI\" -type f 2>&1 && break;"
                       "done || echo '  (EFI partition not mounted)'"), 15)
        section("Kernel")
        cmd("uname", "uname -r 2>&1", 3)
        cmd("cmdline", "cat /proc/cmdline 2>&1", 5)
        section("Input devices")
        cmd("evdev-diag", "cat /tmp/evdev-diag.log 2>&1", 10)
        section("Kernel messages (errors)")
        cmd("dmesg-errors", "dmesg | grep -iE 'error|fail|oom|kill|nvme|usb.*disconnect|I/O|blk|reset' | tail -25 2>&1", 25)
        try:
            Path("/tmp/purple-install-diag.txt").write_text("\n".join(lines) + "\n")
        except Exception:
            pass
        return lines

    def _start_diag_scroll(self):
        self._stop_diag_scroll()
        self._diag_lines = self._collect_diagnostics()
        self._diag_scroll_pos = 0
        self._scrolling = True
        self._scroll_timer = self.app.timers.every(self._SCROLL_DELAY, self._scroll_tick)
        self.app.invalidate()

    def _scroll_tick(self):
        self._diag_scroll_pos += 1
        if self._diag_scroll_pos > len(self._diag_lines):
            self._stop_diag_scroll()
        self.app.invalidate()

    def _stop_diag_scroll(self):
        if self._scroll_timer is not None:
            self._scroll_timer.stop()
            self._scroll_timer = None
        self._scrolling = False

    async def handle(self, action):
        if self._phase != "error" or not isinstance(action, ControlAction) or not action.is_down:
            return
        if self._scrolling:
            self._stop_diag_scroll()
        elif action.action == "enter":
            self._start_diag_scroll()
        elif action.action == "escape":
            if self._diag_lines:
                self._diag_lines = []
            else:
                self.close()
        self.app.invalidate()

    def draw(self, g):
        g.fill(P.BG)
        if self._phase == "error" and (self._scrolling or self._diag_lines):
            g.draw_markup(f"Please record this with your phone and send to {SUPPORT_EMAIL}\nEsc: go back   Enter: replay",
                          g.vh(2.4), g.vw(4), g.vh(3), "sans-bold", P.PRIMARY, g.vw(92), "left", P.BG)
            end = self._diag_scroll_pos if self._scrolling else len(self._diag_lines)
            visible = self._diag_lines[max(0, end - self._SCROLL_VISIBLE):end]
            y = g.vh(11)
            for line in visible:
                g.draw_text(line or " ", g.vh(2.4), g.vw(4), y, "mono", P.TEXT)
                y += g.vh(3.2)
            return
        cx = g.w // 2
        if self._phase == "error":
            g.draw_text("Setup did not finish.", g.vh(4), cx, g.vh(22), "sans-heavy", P.PRIMARY, anchor="center")
            if self._corrupt_key:
                summary = ("It looks like the installation data on\nthis Purple Key got damaged. This computer\n"
                           "is fine, and Purple still works from the\nUSB without installing.\n\n"
                           f"Email us for a replacement Key:\n{SUPPORT_EMAIL}")
            else:
                summary = f"{self._get_error_summary()}\n\nIf this keeps happening,\ncontact us: {SUPPORT_EMAIL}"
            g.draw_markup(summary, g.vh(2.6), g.vw(10), g.vh(30), "sans", P.TEXT, g.vw(80), "center", P.BG, g.vh(0.6))
            g.draw_markup("Press Enter for technical details.\nEsc to go back. Power button to turn off.", g.vh(2.2),
                          g.vw(10), g.vh(78), "sans-bold", P.MUTED, g.vw(80), "center", P.BG)
            return
        g.draw_text("Installing Purple Computer", g.vh(4), cx, g.vh(30), "sans-heavy", P.PRIMARY, anchor="center")
        g.draw_text(self._status, g.vh(2.8), cx, g.vh(42), "sans-bold", P.TEXT, anchor="center")
        bw = g.vw(50)
        draw_bar(g, cx - bw // 2, g.vh(50), bw, g.vh(2.4), self._progress / 100)
        g.draw_text(f"{self._progress:>3d}%", g.vh(2.6), cx + bw // 2 + g.vw(2), g.vh(51.2), "mono-bold", P.TEXT, anchor="midleft")
        g.draw_text(self._eta_hint(), g.vh(2.4), cx, g.vh(60), "sans", P.MUTED, anchor="center")


class InstallDoneScreen(FullScreen):
    """The install finished; the USB can come out. Enter restarts through the
    static purple-reboot binary, which lives on tmpfs so it survives removal."""

    message = "All done!\n\nYou can remove the USB drive now."
    hint = "Press Enter to restart"

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.action == "enter" and action.is_down:
            self.hint = "Restarting..."
            self.app.invalidate()
            if self.app._evdev_reader:
                self.app._evdev_reader.release_grab()
            os.execv(_REBOOT_BIN, [_REBOOT_BIN])


# ---------------------------------------------------------------------------
# Terminal (an xterm on the same screen; VT switch stays as last-resort escape)
# ---------------------------------------------------------------------------

_TERM_RC = "/opt/purple/parent-shell-rc.sh"


def _xterm_cmd() -> list:
    return [
        "xterm",
        "-fa", "IBM Plex Mono", "-fs", "14",
        "-bg", P.BG, "-fg", "#ffffff", "-b", "24",
        "-title", "Purple Terminal",
        "-e", "bash", "--rcfile", _TERM_RC,
    ]


class TerminalScreen(FullScreen):
    message = "Terminal"
    hint = "Type exit and press Enter to go back to Purple."

    def on_open(self):
        self._proc = None
        self._running = False
        self.status = _boot_mode_hint()
        if is_debug():
            self.status += ("\n\nDisplay checkerboard? Run:\n/opt/purple/scripts/debug-display.sh   (state + verdict)\n"
                            "/opt/purple/scripts/debug-display.sh repro   (reproduce it)\n"
                            "/opt/purple/scripts/debug-display.sh compositor off|on   (A/B the fix)")
        reader = self.app._evdev_reader
        if reader is not None and not self.app.demo_running:
            self._running = True
            asyncio.ensure_future(self._run_terminal(reader))

    async def _run_terminal(self, reader):
        try:
            self._proc = subprocess.Popen(_xterm_cmd())
        except OSError as e:
            self.message = "Terminal unavailable"
            self.hint = f"Could not open a terminal.\nPress Enter to go back.\n(Technical: {e})"
            self._running = False
            self.app.invalidate()
            return
        # If the terminal never takes focus, Ctrl+Alt+F1 closes it (rescue), so
        # a parent can't get stuck. Normal exit is typing exit in the shell.
        reader.suspend_for_x_terminal(on_rescue=self._proc.terminate)
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._proc.wait)
        finally:
            reader.resume_from_x_terminal()
            self._running = False
            self.close()
            self.app.invalidate()

    async def handle(self, action):
        if self._running:
            return
        if isinstance(action, ControlAction) and action.is_down and action.action in ("escape", "enter"):
            self.close()


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
_USB_LABELS = ("PURPLE_INSTALLER", "PURPLE_DEBUG")
_PAYLOAD_PATH = Path("/cdrom/purple/install.sh")


def _boot_mode_hint() -> str:
    if not is_live_boot():
        return "Installed on this computer."
    if is_usb_cached() and not is_usb_present():
        return "Running from USB. Not yet installed.\nReinsert after restart.\nInstall to keep it without the USB."
    if is_usb_cached():
        return "Running from USB. Not yet installed.\nOK to remove USB. Reinsert after restart.\nInstall to keep it without the USB."
    return "Running from USB. Not yet installed.\n\nInstall to keep it without the USB."


def _find_usb_device():
    for label in _USB_LABELS:
        link = Path(f"/dev/disk/by-label/{label}")
        if link.exists():
            try:
                return str(link.resolve())
            except OSError:
                pass
    return None


def _try_remount_usb(dev: str) -> bool:
    try:
        subprocess.run(["sudo", "umount", "-l", "/cdrom"], capture_output=True, timeout=5)
        subprocess.run(["sudo", "mount", "-o", "ro", dev, "/cdrom"], capture_output=True, timeout=5)
        return _PAYLOAD_PATH.exists()
    except (subprocess.TimeoutExpired, OSError):
        return False


def _is_usb_payload_available() -> bool:
    if os.environ.get("PURPLE_FAKE_USB", "") in ("caching", "cached"):
        return True
    dev = _find_usb_device()
    if dev is None:
        return False
    return _PAYLOAD_PATH.exists() or _try_remount_usb(dev)


def _is_dev_environment() -> bool:
    return bool(os.environ.get("PURPLE_TEST_BATTERY")) or (Path(__file__).parent.parent.parent / ".git").is_dir()


def _get_menu_items(app) -> list:
    """(id, label) rows; ids starting with sec- are section headers."""
    from ..settings import (get_all_caps, get_code_panel, get_littles_mode, get_music_key_switching, get_music_looping,
                            get_parent_pin, get_secret_unlocked, get_volume_lock)
    items = [("menu-help", "Help & Videos")]
    if is_live_boot():
        items.append(("menu-install", "Install on this Computer" if _is_usb_payload_available() else "Install (Reinsert USB)"))
    else:
        items.append(("menu-rename", "Rename this Computer" if app.computer_name() != DEFAULT_COMPUTER_NAME else "Name this Computer"))
    items.append(("sec-kid", "Activities"))
    littles = get_littles_mode()
    names = {"music": "Music", "music_noscreen": "No-Screen Music", "art": "Art"}
    items.append(("menu-littles", f"Littles Mode: {names.get(littles, littles.title())}" if littles else "Littles Mode: Off"))
    if not littles:
        items.append(("menu-code-panel", "Allow Code Space: Yes" if get_code_panel() else "Allow Code Space: No"))
        items.append(("menu-music-looping", "Allow Music Looping: Yes" if get_music_looping() else "Allow Music Looping: No"))
        items.append(("menu-music-key-switching", "Allow Music Key Switching: Yes" if get_music_key_switching() else "Allow Music Key Switching: No"))
    items.append(("menu-all-caps", "ALL CAPS: On" if get_all_caps() else "ALL CAPS: Off"))
    items.append(("sec-av", "Sound & Display"))
    items.append(("menu-volume", _volume_menu_label(get_volume_lock())))
    if display_control_available():
        items.append(("menu-display", "Display"))
    items.append(("sec-advanced", "Advanced"))
    if get_secret_unlocked():
        items.append(("menu-secret", "Secret Menu"))
    items.append(("menu-parent-pin", "Parent PIN: On" if get_parent_pin() else "Parent PIN: Off"))
    items.append(("menu-shell", "Open Terminal"))
    items.append(("menu-support", "Support Info"))
    if _is_dev_environment():
        items.append(("menu-demo", "Start Demo"))
        items.append(("menu-bash", "Exit to Bash"))
    if is_debug():
        items.append(("menu-system", "Exit to System"))
    items.append(("menu-shutdown", "Shut Down"))
    items.append(("menu-exit", "Exit Parent Menu"))
    return items


class ParentMenu(Overlay):
    def __init__(self, app):
        super().__init__(app)
        self.items = _get_menu_items(app)
        self.selected = self._next_selectable(-1, 1)
        self._ignore_until_released = {"escape"}
        self._usb_remount_attempted = False
        self._timer = None

    def on_open(self):
        if is_live_boot():
            self._timer = self.app.timers.every(0.5, self._refresh_install_item)

    def on_close(self):
        if self._timer:
            self._timer.stop()

    def _is_section(self, idx) -> bool:
        return self.items[idx][0].startswith("sec-")

    def _next_selectable(self, start, direction) -> int:
        n = len(self.items)
        idx = start
        for _ in range(n):
            idx = (idx + direction) % n
            if not self._is_section(idx):
                return idx
        return 0

    def _disabled(self, item_id) -> bool:
        if item_id == "menu-install":
            return self.items[[i for i, _ in self.items].index(item_id)][1] != "Install on this Computer"
        return item_id == "menu-volume" and self.app.audio_ok is False

    def _refresh_install_item(self):
        dev = _find_usb_device()
        if dev is None:
            available, self._usb_remount_attempted = False, False
        elif _PAYLOAD_PATH.exists():
            available, self._usb_remount_attempted = True, False
        elif not self._usb_remount_attempted:
            self._usb_remount_attempted = True
            available = _try_remount_usb(dev)
        else:
            available = False
        if os.environ.get("PURPLE_FAKE_USB", "") in ("caching", "cached"):
            available = True
        label = "Install on this Computer" if available else "Install (Reinsert USB)"
        for i, (item_id, old) in enumerate(self.items):
            if item_id == "menu-install" and old != label:
                self.items[i] = (item_id, label)
                self.app.invalidate()

    def _relabel(self, item_id, label):
        for i, (iid, _) in enumerate(self.items):
            if iid == item_id:
                self.items[i] = (iid, label)
        self.app.invalidate()

    def selected_item_label(self):
        return self.items[self.selected][1]

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            if action.direction == "up":
                self.selected = self._next_selectable(self.selected, -1)
            elif action.direction == "down":
                self.selected = self._next_selectable(self.selected, 1)
            self.app.invalidate()
        elif isinstance(action, ControlAction):
            key = action.action
            if not action.is_down:
                self._ignore_until_released.discard(key)
                return
            if key in self._ignore_until_released:
                return
            if key == "enter":
                self._activate()
            elif key == "escape":
                self.close()

    def _activate(self):
        item_id = self.items[self.selected][0]
        if self._disabled(item_id):
            return
        handler = {
            "menu-littles": self._open_littles_mode, "menu-code-panel": self._open_code_panel,
            "menu-music-looping": self._open_music_looping, "menu-music-key-switching": self._open_music_key_switching,
            "menu-all-caps": self._open_all_caps, "menu-secret": self._open_secret_menu,
            "menu-parent-pin": self._open_parent_pin, "menu-display": lambda: self.app.push(DisplaySettingsScreen(self.app)),
            "menu-volume": self._open_volume, "menu-install": self._install_to_disk, "menu-rename": self._rename_computer,
            "menu-shell": lambda: (self.close(), self.app.push(TerminalScreen(self.app))),
            "menu-demo": lambda: (self.close(), self.app.start_demo()),
            "menu-bash": lambda: (self.close(), self.app.exit()), "menu-system": lambda: (self.close(), self.app.exit()),
            "menu-help": lambda: self.app.push(__import__("purple_tui.rooms.help_videos", fromlist=["HelpVideosScreen"]).HelpVideosScreen(self.app)),
            "menu-support": lambda: self.app.push(__import__("purple_tui.rooms.support_info", fromlist=["SupportInfoScreen"]).SupportInfoScreen(self.app)),
            "menu-shutdown": lambda: (self.close(), self.app._show_bye_screen()),
            "menu-exit": self.close,
        }.get(item_id)
        if handler:
            handler()

    # --- item handlers ---
    def _open_littles_mode(self):
        self.app.push(LittlesModeScreen(self.app), on_close=lambda r: r is not CANCELLED and self.close({"littles_mode": r}))

    def _open_code_panel(self):
        def apply(v):
            if v is CANCELLED:
                return
            from ..settings import set_code_panel
            set_code_panel(v)
            self.app._code_panel_enabled = v
            if not v:
                self.app.room.close_code_panel()
            self._relabel("menu-code-panel", "Allow Code Space: Yes" if v else "Allow Code Space: No")
        self.app.push(CodePanelScreen(self.app), on_close=apply)

    def _open_music_looping(self):
        def apply(v):
            if v is CANCELLED:
                return
            from ..settings import set_music_looping
            set_music_looping(v)
            self.app._music_looping_enabled = v
            if not v:
                self.app.rooms["music"].stop_sound()
            self._relabel("menu-music-looping", "Allow Music Looping: Yes" if v else "Allow Music Looping: No")
        self.app.push(MusicLoopingScreen(self.app), on_close=apply)

    def _open_music_key_switching(self):
        def apply(v):
            if v is CANCELLED:
                return
            from ..music_constants import DEFAULT_ROOT_INDEX
            from ..settings import set_music_key_switching
            set_music_key_switching(v)
            self.app._music_key_switching_enabled = v
            if not v:
                self.app.rooms["music"].root_index = DEFAULT_ROOT_INDEX
            self._relabel("menu-music-key-switching", "Allow Music Key Switching: Yes" if v else "Allow Music Key Switching: No")
        self.app.push(MusicKeySwitchingScreen(self.app), on_close=apply)

    def _open_all_caps(self):
        def apply(v):
            if v is CANCELLED:
                return
            from ..settings import set_all_caps
            set_all_caps(v)
            self.app.g.all_caps = v
            self._relabel("menu-all-caps", "ALL CAPS: On" if v else "ALL CAPS: Off")
        self.app.push(AllCapsScreen(self.app), on_close=apply)

    def _open_secret_menu(self):
        def done(result):
            if result in ("doodle", "photo"):
                from ..secret_doodle import paint_doodle, paint_photo
                self.close()
                (paint_doodle if result == "doodle" else paint_photo)(self.app)
        self.app.push(SecretMenuScreen(self.app), on_close=done)

    def _open_parent_pin(self):
        from ..settings import get_parent_pin
        if get_parent_pin() is None:
            return self._start_set_pin_flow()

        def on_action(result):
            if result == "change":
                self._start_set_pin_flow()
            elif result == "clear":
                self._save_pin(None)
        self.app.push(PinActionScreen(self.app), on_close=on_action)

    def _start_set_pin_flow(self):
        def on_first(first):
            if first is None:
                return
            self.app.push(PinEntry(self.app, "Confirm New PIN", verify=lambda p: p == first, error_message="Didn't match, try again."),
                          on_close=lambda second: second is not None and self._save_pin(first))
        self.app.push(PinEntry(self.app, "Enter New PIN"), on_close=on_first)

    def _save_pin(self, pin):
        from ..settings import set_parent_pin
        set_parent_pin(pin)
        self._relabel("menu-parent-pin", "Parent PIN: On" if pin else "Parent PIN: Off")

    def _open_volume(self):
        self.app.push(ParentVolumeModal(self.app), on_close=lambda _: self._relabel("menu-volume", _volume_menu_label(self.app._volume_lock)))

    def _install_to_disk(self):
        def on_name(name):
            if name is CANCELLED:
                return

            def on_confirm(ok):
                if ok:
                    self.close()
                    self.app.push(InstallProgressScreen(self.app, computer_name=name or ""))
            self.app.push(InstallConfirmScreen(self.app), on_close=on_confirm)
        self.app.push(ComputerNameScreen(self.app), on_close=on_name)

    def _rename_computer(self):
        current = self.app.computer_name()
        current = "" if current == DEFAULT_COMPUTER_NAME else current
        title = "Rename this computer" if current else "Name this computer"
        desc = "Leave blank to remove the name." if current else "Optional. Leave blank to skip."

        def on_name(name):
            if name is not CANCELLED:
                write_computer_name(name or "")
                self.app.set_computer_name(name or DEFAULT_COMPUTER_NAME)
                self._relabel("menu-rename", "Rename this Computer" if name else "Name this Computer")
        self.app.push(ComputerNameScreen(self.app, title=title, description=desc, initial=current), on_close=on_name)

    # --- drawing ---
    def draw(self, g):
        draw_scrim(g, 235)
        live_h = g.vh(9) if is_live_boot() else 0
        fixed = window_title_height(g, "x") + g.vh(1.5) + live_h + g.vh(12)
        n_rows = sum(1 for i in range(len(self.items)) if not self._is_section(i))
        n_secs = len(self.items) - n_rows
        row_h = min(g.vh(4.6), int((g.h - g.vh(2) - fixed) / (n_rows + n_secs * 0.85)))
        sec_h = int(row_h * 0.85)
        rows_h = n_rows * row_h + n_secs * sec_h
        box = pygame.Rect(0, 0, g.vw(56), fixed + rows_h)
        box.center = (g.w // 2, g.h // 2)
        y = draw_window(g, box, "Parent Menu") + g.vh(1.5)
        version = diagnostics.get_version_label()
        if version:
            g.draw_text(version, g.vh(1.8), box.right - g.vw(1.5), box.bottom - g.vh(1.2), "mono", P.DIM, anchor="bottomright")
        if live_h:
            g.draw_markup(_boot_mode_hint(), g.vh(1.9), box.x + g.vw(2), y, "sans", P.MUTED, box.w - g.vw(4), "center", P.SURFACE)
            y += live_h
        px = min(g.vh(2.4), int(row_h * 0.55))
        for i, (item_id, label) in enumerate(self.items):
            if self._is_section(i):
                g.draw_text(label.upper(), g.vh(1.6), box.x + g.vw(3), y + sec_h - g.vh(1.4), "mono-bold", P.DIM, anchor="bottomleft", track=TRACK)
                y += sec_h
                continue
            if item_id in ("menu-support", "menu-volume") and self.app.audio_ok is False:
                label = f"{label}   (audio not working)"
            on = i == self.selected
            r = pygame.Rect(box.x + g.vw(2.5), y, box.w - g.vw(5), row_h - g.vh(0.6))
            if on:
                g.rect(P.PRIMARY, r)
            fg = P.BG if on else (P.DIM if self._disabled(item_id) else P.TEXT)
            g.draw_text(label, px, r.x + g.vw(1.5), r.centery, "sans-bold", fg, anchor="midleft")
            y += row_h
        g.draw_text("▲ ▼   Enter   Esc", g.vh(2.0), box.centerx, y + g.vh(1.5), "mono", P.MUTED, anchor="midtop")
        g.draw_markup("Purple is keyboard only, on purpose!\nKids explore by typing.", g.vh(1.9), box.x, y + g.vh(5),
                      "sans", P.DIM, box.w, "center", P.SURFACE)


def write_computer_name(name: str):
    path = Path.home() / ".purple" / "computer_name.txt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if name:
            path.write_text(name)
        elif path.exists():
            path.unlink()
    except OSError:
        pass
