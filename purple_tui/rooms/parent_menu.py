"""
Parent Menu: Admin menu for parents/guardians

Accessed by holding Escape for ~1 second.
Provides access to system settings, bash shell, etc.

Navigation is handled explicitly via on_key (no focus system).
Up/Down arrows move selection, Enter activates, Escape exits.
"""

from textual.widgets import Static
from textual.containers import Vertical, Horizontal
from textual.app import ComposeResult
from ..modal import PurpleModal, PickerModal
from textual import events
import subprocess
import os
import sys
import select
import threading
import termios
import time
import json
from pathlib import Path

import re

from ..keyboard import NavigationAction, ControlAction, CharacterAction
from ..constants import is_debug, is_live_boot, is_usb_cached, is_usb_present, SUPPORT_EMAIL


# =============================================================================
# Display Settings
# =============================================================================
#
# Uses xrandr for software-level display adjustment. This works consistently
# across all X11 systems regardless of laptop hardware (ThinkPad, Dell, HP,
# Surface, MacBook, etc.) because it adjusts gamma at the GPU level, not the
# actual backlight.
#
# Brightness: xrandr --brightness (multiplier, 0.5-1.0)
# Contrast: xrandr --gamma (gamma curve, 0.7-1.3 applied uniformly to R:G:B)

DISPLAY_SETTINGS_FILE = Path.home() / ".config" / "purple" / "display.json"

# Brightness: how bright the screen appears (software gamma multiplier)
BRIGHTNESS_MIN = 0.5
BRIGHTNESS_MAX = 1.0
BRIGHTNESS_STEP = 0.1
BRIGHTNESS_DEFAULT = 1.0

# Contrast: gamma curve adjustment (lower = washed out, higher = punchy)
# 1.0 is default, <1.0 increases perceived contrast, >1.0 decreases it
# We invert the scale for UX: user sees "higher = more contrast"
CONTRAST_MIN = 0.7
CONTRAST_MAX = 1.3
CONTRAST_STEP = 0.1
CONTRAST_DEFAULT = 1.0


def load_display_settings() -> dict:
    """Load display settings from disk."""
    try:
        if DISPLAY_SETTINGS_FILE.exists():
            data = json.loads(DISPLAY_SETTINGS_FILE.read_text())
            return {
                "brightness": float(data.get("brightness", BRIGHTNESS_DEFAULT)),
                "contrast": float(data.get("contrast", CONTRAST_DEFAULT)),
            }
    except Exception:
        pass
    return {"brightness": BRIGHTNESS_DEFAULT, "contrast": CONTRAST_DEFAULT}


def save_display_settings(settings: dict) -> bool:
    """Save display settings to disk."""
    try:
        DISPLAY_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        DISPLAY_SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        return True
    except Exception:
        return False


_cached_xrandr_outputs: list | None = None

def _get_xrandr_outputs() -> list:
    """Get list of connected display outputs. Cached after first call."""
    global _cached_xrandr_outputs
    if _cached_xrandr_outputs is not None:
        return _cached_xrandr_outputs
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return []

        outputs = []
        for line in result.stdout.splitlines():
            if " connected" in line:
                output_name = line.split()[0]
                outputs.append(output_name)
        _cached_xrandr_outputs = outputs
        return outputs
    except Exception:
        return []


def _check_xrandr_works() -> bool:
    """Test whether xrandr can actually control the display.

    Some hardware (e.g. Surface Laptop 2) reports outputs via xrandr but
    can't set brightness/gamma on them (no CRTC). We test by applying a
    no-op setting and checking for errors.
    """
    outputs = _get_xrandr_outputs()
    if not outputs:
        return False

    try:
        result = subprocess.run(
            ["xrandr", "--output", outputs[0],
             "--brightness", "1.0",
             "--gamma", "1.0:1.0:1.0"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # xrandr prints warnings like "need crtc to set gamma on" to stdout
        if "need crtc" in result.stdout or "not found" in result.stdout:
            return False
        if "need crtc" in result.stderr or "not found" in result.stderr:
            return False
        return result.returncode == 0
    except Exception:
        return False


# Cache the result so we only probe once per session
_display_control_available: bool | None = None


def display_control_available() -> bool:
    """Check whether display brightness/contrast controls work on this hardware."""
    global _display_control_available
    if _display_control_available is None:
        _display_control_available = _check_xrandr_works()
    return _display_control_available


def apply_display_settings(brightness: float, contrast: float) -> bool:
    """
    Apply brightness and contrast using xrandr.

    brightness: 0.5-1.0 (software gamma multiplier)
    contrast: 0.7-1.3 (gamma curve, inverted for UX)

    Returns True on success.
    """
    if not display_control_available():
        return False

    brightness = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, brightness))
    contrast = max(CONTRAST_MIN, min(CONTRAST_MAX, contrast))

    outputs = _get_xrandr_outputs()
    if not outputs:
        return False

    # Contrast uses gamma: we invert so higher value = more contrast
    # gamma < 1.0 = more contrast (darker darks, brighter brights)
    # gamma > 1.0 = less contrast (washed out)
    # User slider: 0.7 (low) to 1.3 (high contrast)
    # We map: user 0.7 -> gamma 1.3, user 1.3 -> gamma 0.7
    gamma = 2.0 - contrast  # Invert: 0.7->1.3, 1.0->1.0, 1.3->0.7
    gamma_str = f"{gamma:.1f}:{gamma:.1f}:{gamma:.1f}"

    try:
        for output in outputs:
            subprocess.Popen(
                ["xrandr", "--output", output,
                 "--brightness", str(brightness),
                 "--gamma", gamma_str],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return True
    except Exception:
        return False


def apply_saved_display_settings() -> None:
    """Apply saved display settings. Call on app startup."""
    settings = load_display_settings()
    apply_display_settings(settings["brightness"], settings["contrast"])


class DisplaySettingsScreen(PurpleModal):
    """
    Modal for adjusting display brightness and contrast.

    Simple +/- interface with visual bars for each setting.
    Parent-friendly design.
    """

    CSS = """
    #modal-dialog {
        width: 50;
        padding: 1 2;
    }

    #modal-title {
        color: $primary;
    }

    .setting-row {
        width: 100%;
        height: 1;
        margin: 1 0;
    }

    .setting-label {
        width: 12;
        text-align: right;
        padding-right: 1;
    }

    .setting-bar {
        width: 20;
    }

    .setting-value {
        width: 8;
        text-align: left;
        padding-left: 1;
    }
    """

    FOCUS_AREAS = ["brightness", "contrast"]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        settings = load_display_settings()
        self._brightness = settings["brightness"]
        self._contrast = settings["contrast"]
        self._focus_index = 0  # Index into FOCUS_AREAS

    @property
    def _focus_area(self) -> str:
        return self.FOCUS_AREAS[self._focus_index]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static("Adjust Display", id="modal-title")
            with Horizontal(classes="setting-row"):
                yield Static("Brightness:", classes="setting-label")
                yield Static("", id="brightness-bar", classes="setting-bar")
                yield Static("", id="brightness-value", classes="setting-value")
            with Horizontal(classes="setting-row"):
                yield Static("Contrast:", classes="setting-label")
                yield Static("", id="contrast-bar", classes="setting-bar")
                yield Static("", id="contrast-value", classes="setting-value")
            yield Static("\u2190 \u2192 adjust   \u25b2 \u25bc switch   Esc done", id="modal-hint")

    def on_mount(self) -> None:
        self._update_display()

    def _render_bar(self, value: float, min_val: float, max_val: float, focused: bool) -> str:
        """Render a setting bar with optional focus highlight."""
        segments = 7
        filled = round((value - min_val) / (max_val - min_val) * segments)
        bar = "█" * filled + "░" * (segments - filled)
        if focused:
            return f"[bold cyan]◀ {bar} ▶[/]"
        return f"  {bar}  "

    def _update_display(self) -> None:
        """Update all display elements."""
        # Brightness bar
        bright_bar = self.query_one("#brightness-bar", Static)
        bright_val = self.query_one("#brightness-value", Static)
        bright_bar.update(self._render_bar(
            self._brightness, BRIGHTNESS_MIN, BRIGHTNESS_MAX,
            self._focus_area == "brightness"
        ))
        bright_val.update(f"{int(self._brightness * 100)}%")

        # Contrast bar
        contrast_bar = self.query_one("#contrast-bar", Static)
        contrast_val = self.query_one("#contrast-value", Static)
        contrast_bar.update(self._render_bar(
            self._contrast, CONTRAST_MIN, CONTRAST_MAX,
            self._focus_area == "contrast"
        ))
        # Show contrast as a relative scale: 1.0 = "Normal"
        if abs(self._contrast - 1.0) < 0.05:
            contrast_text = "Normal"
        elif self._contrast < 1.0:
            contrast_text = "Low"
        else:
            contrast_text = "High"
        contrast_val.update(contrast_text)

    def _save_and_apply(self) -> None:
        """Apply current settings to display and save to disk."""
        apply_display_settings(self._brightness, self._contrast)
        save_display_settings({
            "brightness": self._brightness,
            "contrast": self._contrast,
        })

    def on_key(self, event: events.Key) -> None:
        """Suppress terminal key events."""
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard input."""
        if isinstance(action, NavigationAction):
            if self._focus_area == "brightness":
                if action.direction == 'left':
                    self._brightness = max(BRIGHTNESS_MIN, self._brightness - BRIGHTNESS_STEP)
                    self._save_and_apply()
                elif action.direction == 'right':
                    self._brightness = min(BRIGHTNESS_MAX, self._brightness + BRIGHTNESS_STEP)
                    self._save_and_apply()
                elif action.direction == 'down':
                    self._focus_index = 1
                self._update_display()

            elif self._focus_area == "contrast":
                if action.direction == 'left':
                    self._contrast = max(CONTRAST_MIN, self._contrast - CONTRAST_STEP)
                    self._save_and_apply()
                elif action.direction == 'right':
                    self._contrast = min(CONTRAST_MAX, self._contrast + CONTRAST_STEP)
                    self._save_and_apply()
                elif action.direction == 'up':
                    self._focus_index = 0
                self._update_display()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action in ('enter', 'escape'):
                self.dismiss(True)


_LITTLES_CANCELLED = object()  # Sentinel: user pressed Escape without choosing

# LittlesExitScreen dismiss values
_LITTLES_EXIT = "exit"        # Exit littles mode
_LITTLES_GO_BACK = "go_back"  # Return to littles mode
_LITTLES_SWITCH = "switch"    # Open the littles mode picker to switch activity
_LITTLES_PARENT = "parent"    # Open the full parent menu (keep littles on)

# CodePanelScreen dismiss value
_CODE_PANEL_CANCELLED = object()

# MusicLoopingScreen dismiss value
_MUSIC_LOOPING_CANCELLED = object()

# MusicKeySwitchingScreen dismiss value
_MUSIC_KEY_SWITCHING_CANCELLED = object()

# AllCapsScreen dismiss value
_ALL_CAPS_CANCELLED = object()

# SilentModeScreen dismiss value
_SILENT_MODE_CANCELLED = object()

# VolumeLockScreen dismiss value
_VOLUME_LOCK_CANCELLED = object()

# PinEntryScreen dismiss value (Esc / cancel)
_PIN_CANCELLED = object()

# PinActionScreen dismiss values
_PIN_ACTION_CANCELLED = object()
_PIN_ACTION_CHANGE = "change"
_PIN_ACTION_CLEAR = "clear"


class LittlesExitScreen(PickerModal):
    """Shown when parent long-holds Escape while in Littles Mode."""

    TITLE = "Exit Littles Mode?"
    OPTIONS = [
        (_LITTLES_EXIT, "Yes, exit"),
        (_LITTLES_GO_BACK, "No, go back"),
        (_LITTLES_SWITCH, "Switch activity"),
        (_LITTLES_PARENT, "Parent Menu"),
    ]
    default_selected = 1
    escape_value = _LITTLES_GO_BACK


class LittlesModeScreen(PickerModal):
    """Pick a Littles Mode: lock the app into a single activity for young kids."""

    TITLE = "Littles Mode"
    DESCRIPTION = "One activity, no menus, no switching"
    OPTIONS = [
        (None, "Off", "All rooms, full experience"),
        ("music", "Music", "Every key plays a sound and shows a color"),
        ("music_noscreen", "No-Screen Music", "Sounds only, screen stays dark"),
        ("art", "Art", "Every key puts color on the canvas"),
    ]
    escape_value = _LITTLES_CANCELLED

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ..settings import get_littles_mode
        current = get_littles_mode()
        for i, (value, *_) in enumerate(self.OPTIONS):
            if value == current:
                self._selected = i
                break

    def _on_confirm(self, value):
        from ..settings import set_littles_mode
        set_littles_mode(value)
        self.dismiss(value)


class CodePanelScreen(PickerModal):
    """Toggle the code panel setting."""

    TITLE = "Allow Code Space"
    DESCRIPTION = "Allow older kids to write code in Music and Art by holding the space button"
    OPTIONS = [
        (True, "Yes"),
        (False, "No"),
    ]
    escape_value = _CODE_PANEL_CANCELLED

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ..settings import get_code_panel
        self._selected = 0 if get_code_panel() else 1


class AllCapsScreen(PickerModal):
    """Toggle the all-caps display setting."""

    TITLE = "ALL CAPS"
    DESCRIPTION = "Show every letter as a capital letter"
    OPTIONS = [
        (True, "On"),
        (False, "Off"),
    ]
    escape_value = _ALL_CAPS_CANCELLED

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ..settings import get_all_caps
        self._selected = 0 if get_all_caps() else 1


class SilentModeScreen(PickerModal):
    """Toggle the parent silence lock."""

    TITLE = "Silent Mode"
    DESCRIPTION = "Turn off all sound. The volume buttons stay off until you turn this back on."
    OPTIONS = [
        (True, "On"),
        (False, "Off"),
    ]
    escape_value = _SILENT_MODE_CANCELLED

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ..settings import get_silent_mode
        self._selected = 0 if get_silent_mode() else 1


# Picker bar art for each lockable volume level (single source of truth).
_VOLUME_LOCK_BARS = {
    15:  "██░░░░░░░░",
    35:  "████░░░░░░",
    60:  "██████░░░░",
    85:  "████████░░",
    100: "██████████",
}


def _volume_lock_menu_label(level) -> str:
    if level is None:
        return "Volume Lock: Off"
    return f"Volume Lock: {_VOLUME_LOCK_BARS.get(level, '')}"


class VolumeLockScreen(PickerModal):
    """Lock playback at a fixed volume so the kid can't change it."""

    TITLE = "Volume Lock"
    DESCRIPTION = "Pin the volume at one level. The volume keys won't change it until you remove the lock."
    OPTIONS = [(None, "No Lock")] + [(v, _VOLUME_LOCK_BARS[v]) for v in (15, 35, 60, 85, 100)]
    HINT = "▲ ▼ choose   Space test   Enter confirm   Esc cancel"
    escape_value = _VOLUME_LOCK_CANCELLED

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ..settings import get_volume_lock
        current = get_volume_lock()
        for i, (value, *_) in enumerate(self.OPTIONS):
            if value == current:
                self._selected = i
                break
        self._test_sound = None

    async def handle_keyboard_action(self, action) -> None:
        if (isinstance(action, ControlAction) and action.action == 'space'
                and action.is_down and not action.is_repeat):
            self._play_test_sound()
            return
        await super().handle_keyboard_action(action)

    def _play_test_sound(self) -> None:
        value = self.OPTIONS[self._selected][0]
        if value is None:
            return
        # Preview the speaker level: amixer to the lock value, ignoring
        # current silent mode so the parent can hear the test. Use
        # subprocess.run so the mixer change lands before sound.play() —
        # otherwise the audio buffer can leave the device at the old level.
        try:
            from ..constants import SYSTEM_VOLUME_MAX
            system_vol = round(value * SYSTEM_VOLUME_MAX / 100)
            subprocess.run(
                ["amixer", "sset", "Master", f"{system_vol}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=2,
            )
        except Exception:
            pass
        try:
            from ..audio import play_safe
            from .music_room import warm_mixer
            if not warm_mixer():
                return
            import pygame.mixer
            if self._test_sound is None:
                sounds_path = (Path(__file__).parent.parent.parent
                               / "packs" / "core-sounds" / "content")
                test_path = sounds_path / "glockenspiel" / "c5.ogg"
                if test_path.exists():
                    self._test_sound = pygame.mixer.Sound(str(test_path))
            # Scale per-sound volume too, so even on a system where amixer
            # doesn't drive the perceived output the lower options stay
            # quieter than the higher ones.
            if self._test_sound is not None:
                self._test_sound.set_volume(value / 100)
                play_safe(self._test_sound)
        except Exception:
            pass


class PinActionScreen(PickerModal):
    """Choose what to do with an existing PIN: change it or turn it off."""

    TITLE = "Parent PIN"
    OPTIONS = [
        (_PIN_ACTION_CHANGE, "Change PIN"),
        (_PIN_ACTION_CLEAR, "Turn Off"),
    ]
    escape_value = _PIN_ACTION_CANCELLED


class PinEntryScreen(PurpleModal):
    """Enter a 4-digit PIN. Returns the digit string or _PIN_CANCELLED."""

    CSS = """
    #modal-dialog {
        width: 50;
        padding: 1 2;
        max-height: 14;
    }

    #modal-title {
        color: $primary;
    }

    #pin-desc {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin: 1 0;
    }

    #pin-desc.error {
        color: $error;
    }

    #pin-field {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-align: center;
        padding: 0 1;
        border: heavy $accent;
        margin: 1 0;
    }
    """

    _LEN = 4

    def __init__(self, title: str = "Enter PIN",
                 description: str = "Type 4 digits.\nForgot it? Reinstall from USB to reset.",
                 verify=None, error_message: str = "Wrong PIN, try again.",
                 ignore_held_escape: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._description = description
        self._verify = verify
        self._error_message = error_message
        self._pin = ""
        self._blink_on = True
        self._error = ""
        self._ignore_keys = {'escape'} if ignore_held_escape else set()

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        with Vertical(id="modal-dialog"):
            yield Static(caps(self._title), id="modal-title")
            yield Static(self._description, id="pin-desc")
            yield Static("", id="pin-field")
            yield Static(caps("Enter  Esc"), id="modal-hint")

    def on_mount(self) -> None:
        self._update_ui()
        self.set_interval(0.5, self._toggle_blink)

    def _toggle_blink(self) -> None:
        self._blink_on = not self._blink_on
        self._update_ui()

    def _update_ui(self) -> None:
        try:
            field = self.query_one("#pin-field", Static)
            desc = self.query_one("#pin-desc", Static)
        except Exception:
            return
        filled = "● " * len(self._pin)
        empty = "_ " * (self._LEN - len(self._pin))
        cursor_on = self._blink_on and len(self._pin) < self._LEN
        if cursor_on:
            empty = "█ " + "_ " * max(0, self._LEN - len(self._pin) - 1)
        field.update((filled + empty).rstrip())
        if self._error:
            desc.update(self._error)
            desc.add_class("error")
        else:
            desc.update(self._description)
            desc.remove_class("error")

    def _submit(self) -> None:
        if len(self._pin) != self._LEN:
            self._error = "Type 4 digits."
            self._update_ui()
            return
        if self._verify is not None and not self._verify(self._pin):
            self._pin = ""
            self._error = self._error_message
            self._update_ui()
            return
        self.dismiss(self._pin)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, ControlAction):
            key = action.action
            if not action.is_down:
                self._ignore_keys.discard(key)
                return
            if key in self._ignore_keys:
                return
            if key == 'escape':
                self.dismiss(_PIN_CANCELLED)
            elif key == 'enter':
                self._submit()
            elif key == 'backspace' and self._pin:
                self._pin = self._pin[:-1]
                self._error = ""
                self._update_ui()
            return

        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            char = action.char
            if not char or not char.isdigit() or len(self._pin) >= self._LEN:
                return
            self._pin += char
            self._error = ""
            self._update_ui()
            if len(self._pin) == self._LEN:
                self._submit()


class MusicLoopingScreen(PickerModal):
    """Toggle the music looping setting."""

    TITLE = "Allow Music Looping"
    DESCRIPTION = "Allow recording loops in Music by holding the enter button"
    OPTIONS = [
        (True, "Yes"),
        (False, "No"),
    ]
    escape_value = _MUSIC_LOOPING_CANCELLED

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ..settings import get_music_looping
        self._selected = 0 if get_music_looping() else 1


class MusicKeySwitchingScreen(PickerModal):
    """Toggle the music key switching setting."""

    TITLE = "Allow Music Key Switching"
    DESCRIPTION = "Allow switching musical keys in Music with the arrow buttons"
    OPTIONS = [
        (True, "Yes"),
        (False, "No"),
    ]
    escape_value = _MUSIC_KEY_SWITCHING_CANCELLED

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from ..settings import get_music_key_switching
        self._selected = 0 if get_music_key_switching() else 1





def _flush_terminal_input() -> None:
    """Flush any buffered terminal input to prevent stray characters."""
    try:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (termios.error, OSError):
        pass  # Not a TTY or other error, ignore


def _boot_mode_hint() -> str:
    """Return a human-readable boot mode description for parent-facing UI."""
    if not is_live_boot():
        return "Installed on this computer."
    if is_usb_cached() and not is_usb_present():
        return "Running from USB. Not yet installed.\nReinsert after restart.\nInstall to keep it without the USB."
    if is_usb_cached():
        return "Running from USB. Not yet installed.\nOK to remove USB. Reinsert after restart.\nInstall to keep it without the USB."
    return "Running from USB. Not yet installed.\n\nInstall to keep it without the USB."


def _is_casper_boot() -> bool:
    """Check if running from a casper live boot (USB or otherwise).

    Delegates to shared is_live_boot() in constants.py.
    Kept as a local alias for backward compatibility within this module.
    """
    return is_live_boot()


_USB_LABELS = ("PURPLE_INSTALLER", "PURPLE_DEBUG")
_PAYLOAD_PATH = Path("/cdrom/purple/install.sh")


def _find_usb_device() -> str | None:
    """Return the resolved device path for the Purple USB, or None.

    Checks /dev/disk/by-label/ symlinks, which udev manages. This is a cheap
    sysfs lookup that never touches the actual device.
    """
    for label in _USB_LABELS:
        dev_link = Path(f"/dev/disk/by-label/{label}")
        if dev_link.exists():
            try:
                return str(dev_link.resolve())
            except OSError:
                pass  # Symlink vanished between exists() and resolve()
    return None


def _try_remount_usb(dev: str) -> bool:
    """Remount the USB at /cdrom after removal and re-insertion.

    Casper mounts the USB at /cdrom during boot. After physical removal the
    mount goes stale. This lazy-unmounts the stale mount and remounts the
    device read-only.
    """
    try:
        # Lazy unmount: detaches immediately even if the mount is stale.
        # Regular umount can hang waiting for I/O on a dead device.
        subprocess.run(
            ["sudo", "umount", "-l", "/cdrom"],
            capture_output=True, timeout=5,
        )
        subprocess.run(
            ["sudo", "mount", "-o", "ro", dev, "/cdrom"],
            capture_output=True, timeout=5,
        )
        return _PAYLOAD_PATH.exists()
    except (subprocess.TimeoutExpired, OSError):
        return False


def _is_usb_payload_available() -> bool:
    """Check if the install payload is accessible on the USB.

    Checks device presence first to avoid stat-ing a potentially stale /cdrom
    mount when the USB has been physically removed.
    """
    if os.environ.get("PURPLE_FAKE_USB", "") in ("caching", "cached"):
        return True
    dev = _find_usb_device()
    if dev is None:
        return False
    if _PAYLOAD_PATH.exists():
        return True
    return _try_remount_usb(dev)


def _is_dev_environment() -> bool:
    """Check if running in a development environment.

    Returns True if:
    - PURPLE_TEST_BATTERY env var is set (set by `just run`), OR
    - .git directory exists in project root (git checkout, not installed)

    In production, Purple is installed to /opt/purple without .git,
    and PURPLE_TEST_BATTERY is not set.
    """
    if os.environ.get("PURPLE_TEST_BATTERY"):
        return True
    project_root = Path(__file__).parent.parent.parent
    return (project_root / ".git").is_dir()


def _get_version_label() -> str:
    from ..diagnostics import get_version_label
    return get_version_label()


def _get_menu_items() -> list:
    """Get menu items, including dev-only items when appropriate.

    Items whose id starts with `sec-` are section headers: visual-only,
    skipped by keyboard navigation, no action when activated.
    """
    from ..settings import get_littles_mode, get_code_panel, get_music_looping, get_music_key_switching, get_all_caps, get_silent_mode, get_volume_lock, get_parent_pin

    items = []

    items.append(("menu-help", "Help & Videos"))
    if _is_casper_boot():
        items.append(("menu-install", "Install on this Computer" if _is_usb_payload_available() else "Install (Reinsert USB)"))
    else:
        from ..purple_tui import _read_computer_name
        rename_label = "Rename this Computer" if _read_computer_name() else "Name this Computer"
        items.append(("menu-rename", rename_label))

    items.append(("sec-kid", "Activities"))
    littles = get_littles_mode()
    if littles:
        display_names = {"music": "Music", "music_noscreen": "No-Screen Music", "art": "Art"}
        littles_label = f"Littles Mode: {display_names.get(littles, littles.title())}"
    else:
        littles_label = "Littles Mode: Off"
    items.append(("menu-littles", littles_label))
    if not littles:
        code_label = "Allow Code Space: Yes" if get_code_panel() else "Allow Code Space: No"
        items.append(("menu-code-panel", code_label))
        looping_label = "Allow Music Looping: Yes" if get_music_looping() else "Allow Music Looping: No"
        items.append(("menu-music-looping", looping_label))
        key_switch_label = "Allow Music Key Switching: Yes" if get_music_key_switching() else "Allow Music Key Switching: No"
        items.append(("menu-music-key-switching", key_switch_label))
    caps_label = "ALL CAPS: On" if get_all_caps() else "ALL CAPS: Off"
    items.append(("menu-all-caps", caps_label))

    items.append(("sec-av", "Sound & Display"))
    silent_label = "Silent Mode: On" if get_silent_mode() else "Silent Mode: Off"
    items.append(("menu-silent", silent_label))
    items.append(("menu-volume-lock", _volume_lock_menu_label(get_volume_lock())))
    items.append(("menu-volume", "Adjust Volume"))
    if display_control_available():
        items.append(("menu-display", "Adjust Display"))

    items.append(("sec-advanced", "Advanced"))
    pin_label = "Parent PIN: On" if get_parent_pin() else "Parent PIN: Off"
    items.append(("menu-parent-pin", pin_label))
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


# ComputerNameScreen dismiss values
_INSTALL_NAME_CANCELLED = object()  # User pressed Esc

_NAME_MAX = 24  # Max characters persisted (keeps title bar from overflowing)


class ComputerNameScreen(PurpleModal):
    """Prompt for a computer name. Used both during install and for renaming.

    Returns the trimmed name (possibly empty) or _INSTALL_NAME_CANCELLED.
    Empty string means "no name".
    """

    CSS = """
    #modal-dialog {
        width: 50;
        padding: 1 2;
        max-height: 14;
    }

    #modal-title {
        color: $primary;
    }

    #install-name-desc {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin: 1 0;
    }

    #install-name-desc.error {
        color: $error;
    }

    #install-name-field {
        width: 100%;
        height: 3;
        content-align: left middle;
        text-align: left;
        padding: 0 1;
        border: heavy $accent;
        margin: 1 0;
    }
    """

    _MIN_LEN = 3

    def __init__(self, title: str = "Name this computer",
                 description: str = "Optional. Leave blank to skip.",
                 initial: str = "", **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._description = description
        self._name = initial
        self._blink_on = True
        self._error = ""

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        with Vertical(id="modal-dialog"):
            yield Static(caps(self._title), id="modal-title")
            yield Static(self._description, id="install-name-desc")
            yield Static("", id="install-name-field")
            yield Static(caps("Enter  Esc"), id="modal-hint")

    def on_mount(self) -> None:
        self._update_ui()
        self.set_interval(0.5, self._toggle_blink)

    def _toggle_blink(self) -> None:
        self._blink_on = not self._blink_on
        self._update_ui()

    def _update_ui(self) -> None:
        from ..purple_tui import DEFAULT_COMPUTER_NAME
        try:
            field = self.query_one("#install-name-field", Static)
            desc = self.query_one("#install-name-desc", Static)
        except Exception:
            return
        cursor = "█" if self._blink_on else " "
        if self._name:
            field.update(self._name + cursor)
        else:
            field.update(f"{cursor} [dim]{DEFAULT_COMPUTER_NAME}[/dim]")
        if self._error:
            desc.update(self._error)
            desc.add_class("error")
        else:
            desc.update(self._description)
            desc.remove_class("error")

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, ControlAction) and action.is_down:
            key = action.action
            if key == 'escape':
                self.dismiss(_INSTALL_NAME_CANCELLED)
                return
            if key == 'enter':
                trimmed = self._name.strip()
                if not self._name:
                    self.dismiss("")
                elif len(trimmed) < self._MIN_LEN:
                    self._error = f"Use {self._MIN_LEN}+ letters or leave blank."
                    self._update_ui()
                else:
                    self.dismiss(trimmed[:_NAME_MAX])
                return
            if key == 'backspace' and self._name:
                self._name = self._name[:-1]
                self._error = ""
                self._update_ui()
                return
            if key == 'space' and len(self._name) < _NAME_MAX:
                self._name += " "
                self._error = ""
                self._update_ui()
                return
            return

        if isinstance(action, CharacterAction):
            if action.is_repeat:
                return
            char = action.char
            if not char or len(self._name) >= _NAME_MAX:
                return
            self._name += char
            self._error = ""
            self._update_ui()


# Back-compat alias for the install flow.
InstallNameScreen = ComputerNameScreen


class InstallConfirmScreen(PurpleModal):
    """Confirmation dialog before installing Purple Computer to the internal disk."""

    CSS = """
    #modal-dialog {
        width: 50;
        padding: 1 2;
        max-height: 22;
    }

    #modal-title {
        color: $primary;
    }

    #install-warning {
        width: 100%;
        text-align: center;
        margin: 1 0;
    }

    #install-buttons {
        height: auto;
    }

    .install-btn {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 1 1 0 1;
    }

    .install-btn.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_button = 1  # Default to Cancel (safer)

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static("Install Purple Computer", id="modal-title")
            yield Static(
                "This will set up Purple Computer\n"
                "on this laptop.\n"
                "\n"
                "[bold red]Everything on this computer\n"
                "will be erased.[/]",
                id="install-warning"
            )
            with Vertical(id="install-buttons"):
                yield Static("Yes, install", id="btn-install", classes="install-btn")
                yield Static("No, go back", id="btn-cancel-install", classes="install-btn selected")
            yield Static("\u25b2 \u25bc choose   Enter confirm   Esc cancel", id="modal-hint")

    def _update_buttons(self):
        try:
            install_btn = self.query_one("#btn-install")
            cancel_btn = self.query_one("#btn-cancel-install")
            if self._selected_button == 0:
                install_btn.add_class("selected")
                cancel_btn.remove_class("selected")
            else:
                install_btn.remove_class("selected")
                cancel_btn.add_class("selected")
        except Exception:
            pass

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction in ('up', 'down'):
                self._selected_button = 1 - self._selected_button
                self._update_buttons()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                self.dismiss(self._selected_button == 0)  # True = Install
            elif action.action == 'escape':
                self.dismiss(False)
            return

        if isinstance(action, CharacterAction):
            self.dismiss(False)


_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Maps substrings in [PURPLE] log output to (progress_percent, display_message).
# Progress only moves forward; the writing stage dominates the clock.
_INSTALL_STAGES = [
    ("Detecting internal disk",   5,  "Getting started..."),
    ("Found internal disk",       8,  "Getting started..."),
    ("Writing Purple Computer",   12, "Setting up Purple Computer..."),
    ("Reloading partition table", 82, "Double-checking everything..."),
    ("Verifying disk write",      85, "Double-checking everything..."),
    ("Disk verification passed",  90, "Double-checking everything..."),
    ("Setting up UEFI boot",      92, "Almost ready..."),
    ("UEFI boot setup complete",  97, "Almost ready..."),
]


_REBOOT_BIN = '/run/purple-reboot-mount/purple-reboot'


class InstallProgressScreen(PurpleModal):
    """Install progress modal. Stays in Textual the whole time.

    Runs install.sh as an async subprocess, streams [PURPLE] log lines to
    update a progress bar, then shows the success/error screen and handles
    the reboot.
    """

    CSS = """
    #modal-dialog {
        width: 60;
        padding: 2 3;
    }

    #modal-dialog.diag-scroll {
        width: 100%;
        height: 100%;
        padding: 1 2;
        border: none;
    }

    #modal-title {
        color: $primary;
    }

    #ip-status {
        width: 100%;
        text-align: center;
        color: $text;
        margin-bottom: 1;
    }

    .diag-scroll #ip-status {
        text-align: left;
    }

    #ip-bar {
        width: 100%;
        text-align: center;
        color: $accent;
        margin-bottom: 1;
    }

    #modal-hint {
        margin-top: 0;
    }
    """

    # Seconds between lines during diagnostic scroll (0.25 = 4 lines/sec,
    # same as purple-x11-failed.sh boot error screen).
    _SCROLL_DELAY = 0.25
    # Max visible lines in the scroll window (leaves room for title + hint)
    _SCROLL_VISIBLE = 25

    def __init__(self, computer_name: str = "", **kwargs):
        super().__init__(**kwargs)
        self._progress = 0
        self._status = "Starting..."
        self._phase = "installing"  # "installing", "success", "error"
        self._log_lines: list[str] = []  # All stderr lines for error diagnostics
        self._diag_lines: list[str] = []  # Full diagnostic report (built on error)
        self._diag_scroll_pos = 0  # Current line in auto-scroll
        self._scroll_timer = None  # Timer for auto-scroll
        self._scrolling = False  # True while auto-scrolling
        self._computer_name = computer_name
        self._start_time: float | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static("", id="modal-title")
            yield Static("", id="ip-status")
            yield Static("", id="ip-bar")
            yield Static("", id="modal-hint")

    def on_mount(self) -> None:
        # Suppress idle sleep/shutdown for the duration of the install. The
        # install takes 10-15 minutes with no keyboard activity; without this
        # the sleep screen would overlay the progress modal mid-install.
        try:
            self.app.inhibit_idle("install")
        except Exception:
            pass
        self._start_time = time.monotonic()
        self._update_ui()
        threading.Thread(target=self._run_install_thread, daemon=True).start()

    def on_unmount(self) -> None:
        try:
            self.app.uninhibit_idle("install")
        except Exception:
            pass

    def _eta_hint(self) -> str:
        """Rolling ETA based on elapsed time and current progress."""
        if self._progress < 15 or self._start_time is None:
            return "Usually under 10 minutes."
        if self._progress >= 95:
            return "Almost done."
        elapsed = time.monotonic() - self._start_time
        remaining = elapsed / self._progress * (100 - self._progress)
        minutes = max(1, round(remaining / 60))
        unit = "minute" if minutes == 1 else "minutes"
        return f"About {minutes} {unit} left."

    def _render_bar(self, pct: int) -> str:
        filled = int(36 * pct / 100)
        return "█" * filled + "░" * (36 - filled) + f"  {pct}%"

    def _update_ui(self) -> None:
        try:
            title_w = self.query_one("#modal-title")
            status_w = self.query_one("#ip-status")
            bar_w = self.query_one("#ip-bar")
            hint_w = self.query_one("#modal-hint")
        except Exception:
            return

        if self._phase == "error":
            if self._scrolling or self._diag_lines:
                # Diagnostic scroll view (full screen)
                title_w.update(
                    f"Please record this with your phone and send to {SUPPORT_EMAIL}\n"
                    "Esc: go back   Enter: replay"
                )
                end = self._diag_scroll_pos if self._scrolling else len(self._diag_lines)
                start = max(0, end - self._SCROLL_VISIBLE)
                visible = self._diag_lines[start:end]
                status_w.update("\n".join(visible) if visible else "")
                bar_w.update("")
                hint_w.update("")
            else:
                error_summary = self._get_error_summary()
                status_w.update(
                    f"Setup did not finish.\n\n{error_summary}\n\n"
                    f"If this keeps happening,\ncontact us: {SUPPORT_EMAIL}"
                )
                bar_w.update("")
                hint_w.update(
                    "Press Enter for technical details.\n"
                    "Esc to go back. Power button to turn off."
                )
        else:
            title_w.update("Installing Purple Computer")
            status_w.update(self._status)
            bar_w.update(self._render_bar(self._progress))
            hint_w.update(self._eta_hint())

    def _run_install_thread(self) -> None:
        """Run install.sh in a daemon thread, streaming progress to the UI.

        Uses subprocess.Popen + select.select instead of asyncio subprocess to
        avoid Python 3.13 pipe-hang bugs. UI updates go via call_from_thread().
        """
        _SENTINEL = Path('/run/purple-install-complete')
        proc = subprocess.Popen(
            ["sudo", "-E", "bash", "/cdrom/purple/install.sh"],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            env={
                **os.environ,
                "PURPLE_PAYLOAD_DIR": "/cdrom/purple",
                "PURPLE_COMPUTER_NAME": self._computer_name,
            },
        )
        buf = b""
        while proc.poll() is None and not _SENTINEL.exists():
            ready = select.select([proc.stderr], [], [], 0.1)[0]
            if ready:
                chunk = proc.stderr.read(256)
                if chunk:
                    buf += chunk
                    while b'\n' in buf:
                        line, buf = buf.split(b'\n', 1)
                        self.app.call_from_thread(
                            self._handle_line,
                            line.decode('utf-8', errors='replace'),
                        )
        # Drain any remaining stderr (error messages from pipeline failures
        # may still be buffered after the process exits).
        try:
            remaining = proc.stderr.read()
            if remaining:
                buf += remaining
        except Exception:
            pass
        # Process any remaining buffered lines.
        while b'\n' in buf:
            line, buf = buf.split(b'\n', 1)
            self.app.call_from_thread(
                self._handle_line,
                line.decode('utf-8', errors='replace'),
            )
        if buf.strip():
            self.app.call_from_thread(
                self._handle_line,
                buf.decode('utf-8', errors='replace'),
            )
        # install.sh writes sentinel + reboot binary to /run as root before exit.
        success = _SENTINEL.exists() or proc.poll() == 0
        self.app.call_from_thread(self._on_install_complete, success)

    def _on_install_complete(self, success: bool) -> None:
        self._phase = "done"
        if success and os.path.isfile(_REBOOT_BIN):
            # execv into the static reboot binary on tmpfs. The binary shows
            # "press Enter", waits, then reboots. It's statically linked and
            # on tmpfs, so it works after USB removal (unlike /bin/sh, Python,
            # or anything on overlayfs). execv replaces this process entirely,
            # so Textual cleanup is irrelevant.
            os.system('stty sane')
            os.execv(_REBOOT_BIN, [_REBOOT_BIN, '--wait'])
        # Error or binary missing: stay in Textual with error message
        self._phase = "error"
        self._update_ui()

    def _handle_line(self, text: str) -> None:
        clean = _ANSI_ESCAPE.sub('', text).strip()
        if clean:
            self._log_lines.append(clean)
        if clean.startswith('[PURPLE-PV]'):
            try:
                pv_pct = int(clean[len('[PURPLE-PV]'):].strip())
            except ValueError:
                return
            # pv emits 0-100 over the whole write phase. Map to the 12-80% span
            # of overall progress so verify/UEFI stages still have room above.
            display_pct = 12 + int(max(0, min(100, pv_pct)) * 0.68)
            if display_pct > self._progress:
                self._progress = display_pct
                self._status = "Setting up Purple Computer..."
                self._update_ui()
            return
        if not clean.startswith('[PURPLE]'):
            return
        msg = clean[8:].strip()
        for keyword, pct, display in _INSTALL_STAGES:
            if keyword in msg and pct > self._progress:
                self._progress = pct
                self._status = display
                self._update_ui()
                return

    def _get_error_summary(self) -> str:
        """Extract last ERROR or WARN line as a short summary."""
        for line in reversed(self._log_lines):
            if '[ERROR]' in line or '[PURPLE ERROR]' in line:
                for prefix in ('[PURPLE ERROR] ', '[ERROR] '):
                    if prefix in line:
                        return f"(Technical: {line.split(prefix, 1)[-1]})"
                return f"(Technical: {line})"
        for line in reversed(self._log_lines):
            if '[WARN]' in line or '[PURPLE WARN]' in line:
                for prefix in ('[PURPLE WARN] ', '[WARN] '):
                    if prefix in line:
                        return f"(Technical: {line.split(prefix, 1)[-1]})"
                return f"(Technical: {line})"
        return ""

    def _collect_diagnostics(self) -> list[str]:
        """Collect comprehensive diagnostics for install failure.

        Covers every failure mode: USB issues, disk I/O, partitions,
        EFI boot setup, memory, and kernel state. Parent records a video
        of the pages for support. Also saved to /tmp/purple-install-diag.txt.
        """
        lines: list[str] = []

        def section(title: str) -> None:
            lines.append("")
            lines.append(f"=== {title} ===")

        def cmd(label: str, command: str, max_lines: int = 20) -> None:
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True,
                    text=True, timeout=5,
                )
                output = (result.stdout + result.stderr).strip()
                if output:
                    for line in output.splitlines()[:max_lines]:
                        lines.append(f"  {line}")
                else:
                    lines.append(f"  ({label}: no output)")
            except Exception:
                lines.append(f"  ({label}: failed)")

        def file_info(label: str, path: str) -> None:
            try:
                p = Path(path)
                if p.exists():
                    if p.is_file():
                        size = p.stat().st_size
                        lines.append(f"  {label}: {path} ({size} bytes)")
                    elif p.is_dir():
                        lines.append(f"  {label}: {path} (directory)")
                else:
                    lines.append(f"  {label}: {path} NOT FOUND")
            except Exception:
                lines.append(f"  {label}: {path} (check failed)")

        # Install script output (most important, always first)
        section("Install log (last 40 lines)")
        for line in self._log_lines[-40:]:
            lines.append(f"  {line}")
        if not self._log_lines:
            lines.append("  (no log output captured)")

        # USB / source media state
        section("USB / source media")
        file_info("Golden image", "/cdrom/purple/purple-os.img.zst")
        file_info("Install script", "/cdrom/purple/install.sh")
        file_info("/cdrom mount", "/cdrom")
        cmd("cdrom contents", "ls /cdrom/purple/ 2>&1", max_lines=10)
        cmd("USB device", "blkid -L PURPLE_INSTALLER 2>&1", max_lines=3)

        # Memory (dd + zstd need RAM, OOM kills are possible)
        section("Memory")
        cmd("meminfo", "free -h 2>&1", max_lines=5)

        # Block devices and disk state
        section("Block devices")
        cmd("lsblk", "lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINT 2>&1")

        section("Partition IDs")
        cmd("blkid", "blkid 2>&1")

        section("/proc/partitions")
        cmd("partitions", "cat /proc/partitions 2>&1")

        # Device-mapper (APFS, LVM leftovers that block partition re-read)
        section("Device-mapper")
        cmd("dmsetup", "dmsetup ls 2>&1")

        # Mount state (what's holding disks open?)
        section("Mounts (non-virtual)")
        cmd("mounts", (
            "mount | grep -v"
            " -e 'type proc' -e 'type sys' -e 'type devpts'"
            " -e 'type tmpfs' -e 'type cgroup' -e 'type securityfs'"
            " -e 'type debugfs' -e 'type pstore' -e 'type fusectl'"
            " -e 'type configfs' -e 'type bpf' -e 'type efivarfs'"
            " -e 'type hugetlbfs' -e 'type mqueue' -e 'type tracefs'"
            " 2>&1"
        ))

        # EFI boot state (did NVRAM entry creation work? what's there?)
        section("EFI boot entries")
        cmd("efibootmgr", "efibootmgr -v 2>&1", max_lines=15)

        # EFI partition contents (if mounted/mountable)
        section("EFI partition contents")
        cmd("efi-ls", (
            "for d in /mnt/efi /boot/efi; do"
            "  [ -d \"$d/EFI\" ] && find \"$d/EFI\" -type f 2>&1 && break;"
            "done || echo '  (EFI partition not mounted)'"
        ), max_lines=15)

        # Kernel info
        section("Kernel")
        cmd("uname", "uname -r 2>&1", max_lines=3)
        cmd("cmdline", "cat /proc/cmdline 2>&1", max_lines=5)

        # Input devices (for tilde/keyboard debugging)
        section("Input devices")
        cmd("evdev-diag", "cat /tmp/evdev-diag.log 2>&1", max_lines=10)

        # Kernel messages: I/O errors, USB disconnects, NVMe, OOM
        section("Kernel messages (errors)")
        cmd("dmesg-errors", (
            "dmesg | grep -iE"
            " 'error|fail|oom|kill|nvme|usb.*disconnect|I/O|blk|reset'"
            " | tail -25 2>&1"
        ), max_lines=25)

        # Write to file for recovery shell access
        try:
            diag_path = Path("/tmp/purple-install-diag.txt")
            diag_path.write_text("\n".join(lines) + "\n")
        except Exception:
            pass

        return lines

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()

    def _start_diag_scroll(self) -> None:
        """Collect diagnostics and start auto-scrolling them."""
        self._stop_diag_scroll()
        self._diag_lines = self._collect_diagnostics()
        self._diag_scroll_pos = 0
        self._scrolling = True
        # Switch to full-screen layout
        try:
            self.query_one("#modal-dialog").add_class("diag-scroll")
        except Exception:
            pass
        self._scroll_timer = self.set_interval(
            self._SCROLL_DELAY, self._scroll_tick,
        )
        self._update_ui()

    def _scroll_tick(self) -> None:
        """Advance one line in the diagnostic scroll."""
        self._diag_scroll_pos += 1
        if self._diag_scroll_pos > len(self._diag_lines):
            self._stop_diag_scroll()
        self._update_ui()

    def _stop_diag_scroll(self) -> None:
        """Stop the auto-scroll timer."""
        if self._scroll_timer is not None:
            self._scroll_timer.stop()
            self._scroll_timer = None
        self._scrolling = False

    def _exit_diag_view(self) -> None:
        """Leave diagnostic view, return to error summary."""
        self._stop_diag_scroll()
        self._diag_lines = []
        # Restore normal dialog layout
        try:
            self.query_one("#modal-dialog").remove_class("diag-scroll")
        except Exception:
            pass
        self._update_ui()

    async def handle_keyboard_action(self, action) -> None:
        if self._phase == "error" and isinstance(action, ControlAction) and action.is_down:
            if self._scrolling:
                # Any key stops the scroll
                self._stop_diag_scroll()
                self._update_ui()
                return
            if self._diag_lines:
                # Scroll finished: Enter restarts, Esc goes back to summary
                if action.action == 'enter':
                    self._start_diag_scroll()
                    return
                if action.action == 'escape':
                    self._exit_diag_view()
                    return
            else:
                # Error summary: Enter starts diagnostics, Esc dismisses
                if action.action == 'enter':
                    self._start_diag_scroll()
                    return
                if action.action == 'escape':
                    self.dismiss()
                    return
        # All other input ignored during install


class ParentMenuItem(Static):
    """A menu item that shows selected state via styling"""

    DEFAULT_CSS = """
    ParentMenuItem {
        width: 100%;
        height: 1;
        text-align: left;
        padding: 0 2;
        margin: 0;
    }

    ParentMenuItem.selected {
        background: $primary;
        color: $text;
        text-style: bold;
    }

    ParentMenuItem.disabled {
        color: $text-muted;
        text-style: italic;
    }

    ParentMenuItem.disabled.selected {
        background: $surface;
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, label: str, item_id: str, **kwargs):
        super().__init__(label, id=item_id, **kwargs)
        self.label = label


class ParentMenu(PurpleModal):
    """
    Parent Mode - Admin menu for parents/guardians.

    Provides access to:
    - Bash shell (exit to return to Purple)
    - Future: Settings, content packs, updates, etc.

    Navigation: Up/Down to move, Enter to select, Escape to exit.
    No focus system used (keyboard-only design).
    """

    DEFAULT_CSS = """
    #modal-dialog {
        width: 52;
        padding: 1 2;
    }

    #modal-title {
        height: 1;
        color: $primary;
    }

    #parent-items {
        width: 100%;
        height: auto;
    }

    #modal-hint {
        height: 1;
    }

    .menu-section {
        width: 100%;
        height: 1;
        margin-top: 1;
        padding: 0 2;
        color: $text-muted;
        text-style: italic;
    }

    #menu-shutdown {
        margin-top: 1;
    }

    .parent-footer {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
    }

    #parent-version {
        height: 1;
        margin-top: 1;
    }

    #parent-live-hint {
        margin-bottom: 1;
    }

    #parent-keyboard-note {
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._menu_items = _get_menu_items()
        self._selected_index = self._next_selectable(-1, 1)
        # Escape is always "tainted" since user held it to open this menu
        self._ignore_until_released = {'escape'}
        # Track USB remount attempts to avoid retrying every poll tick
        self._usb_remount_attempted = False

    def _is_section(self, idx: int) -> bool:
        return self._menu_items[idx][0].startswith("sec-")

    def _next_selectable(self, start: int, direction: int) -> int:
        n = len(self._menu_items)
        idx = start
        for _ in range(n):
            idx = (idx + direction) % n
            if not self._is_section(idx):
                return idx
        return 0

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static("Parent Menu", id="modal-title")
            if is_live_boot():
                yield Static(_boot_mode_hint(), id="parent-live-hint", classes="parent-footer")
            with Vertical(id="parent-items"):
                audio_ok = getattr(self.app, "audio_ok", None)
                for item_id, label in self._menu_items:
                    if item_id.startswith("sec-"):
                        yield Static(label, classes="menu-section")
                        continue
                    if item_id == "menu-support" and audio_ok is False:
                        label = f"{label}   (audio not working)"
                    item = ParentMenuItem(label, item_id)
                    if item_id == "menu-install" and not _is_usb_payload_available():
                        item.add_class("disabled")
                    yield item
            yield Static("\u25b2 \u25bc   Enter   Esc", id="modal-hint")
            yield Static(
                "Purple is keyboard only, on purpose!\nKids explore by typing.",
                id="parent-keyboard-note",
                classes="parent-footer",
            )
            version = _get_version_label()
            if version:
                yield Static(version, id="parent-version", classes="parent-footer")

    def on_mount(self) -> None:
        """Highlight the first menu item"""
        self._update_selection()
        # Poll for USB re-insertion/removal so the install item updates live
        if _is_casper_boot():
            self.set_interval(0.5, self._refresh_install_item)

    def _refresh_install_item(self) -> None:
        """Update the install menu item based on USB availability."""
        dev = _find_usb_device()
        if dev is None:
            # Device gone, reset so we retry when it reappears
            usb_available = False
            self._usb_remount_attempted = False
        elif _PAYLOAD_PATH.exists():
            usb_available = True
            self._usb_remount_attempted = False
        elif not self._usb_remount_attempted:
            # Device present but payload not accessible: try remount once
            self._usb_remount_attempted = True
            usb_available = _try_remount_usb(dev)
        else:
            usb_available = False
        if os.environ.get("PURPLE_FAKE_USB", "") in ("caching", "cached"):
            usb_available = True
        for i, (item_id, old_label) in enumerate(self._menu_items):
            if item_id == "menu-install":
                if usb_available:
                    new_label = "Install on this Computer"
                else:
                    new_label = "Install (Reinsert USB)"
                if new_label != old_label:
                    self._menu_items[i] = (item_id, new_label)
                    item = self.query_one(f"#{item_id}", ParentMenuItem)
                    item.update(new_label)
                    if usb_available:
                        item.remove_class("disabled")
                    else:
                        item.add_class("disabled")
                    self._update_selection()
                return

    def _update_selection(self) -> None:
        """Update visual selection state"""
        for i, (item_id, _) in enumerate(self._menu_items):
            if item_id.startswith("sec-"):
                continue
            item = self.query_one(f"#{item_id}", ParentMenuItem)
            if i == self._selected_index:
                item.add_class("selected")
            else:
                item.remove_class("selected")

    def on_key(self, event: events.Key) -> None:
        """Suppress terminal key events - we use evdev exclusively."""
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard actions from evdev."""
        # Navigation always works immediately
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._selected_index = self._next_selectable(self._selected_index, -1)
                self._update_selection()
            elif action.direction == 'down':
                self._selected_index = self._next_selectable(self._selected_index, 1)
                self._update_selection()
            return

        if isinstance(action, ControlAction):
            key = action.action

            # Track key releases to clear "tainted" keys
            if not action.is_down and key in self._ignore_until_released:
                self._ignore_until_released.discard(key)
                return

            # Ignore tainted keys until released
            if key in self._ignore_until_released:
                return

            # Handle key presses
            if action.is_down:
                if key == 'enter':
                    self._activate_selected()
                elif key == 'escape':
                    self.dismiss()
            return

    def _activate_selected(self) -> None:
        """Activate the currently selected menu item"""
        item_id = self._menu_items[self._selected_index][0]
        item_widget = self.query_one(f"#{item_id}", ParentMenuItem)
        if item_widget.has_class("disabled"):
            return
        if item_id == "menu-littles":
            self._open_littles_mode()
        elif item_id == "menu-code-panel":
            self._open_code_panel()
        elif item_id == "menu-music-looping":
            self._open_music_looping()
        elif item_id == "menu-music-key-switching":
            self._open_music_key_switching()
        elif item_id == "menu-all-caps":
            self._open_all_caps()
        elif item_id == "menu-silent":
            self._open_silent_mode()
        elif item_id == "menu-volume-lock":
            self._open_volume_lock()
        elif item_id == "menu-parent-pin":
            self._open_parent_pin()
        elif item_id == "menu-display":
            self._open_display_settings()
        elif item_id == "menu-volume":
            self._open_volume()
        elif item_id == "menu-install":
            self._install_to_disk()
        elif item_id == "menu-rename":
            self._rename_computer()
        elif item_id == "menu-shell":
            self._open_shell()
        elif item_id == "menu-demo":
            self._start_demo()
        elif item_id == "menu-bash":
            self._exit_to_bash()
        elif item_id == "menu-system":
            self._exit_to_system()
        elif item_id == "menu-help":
            self._open_help_videos()
        elif item_id == "menu-support":
            self._open_support_info()
        elif item_id == "menu-shutdown":
            self._shutdown()
        elif item_id == "menu-exit":
            self.dismiss()

    def _open_code_panel(self) -> None:
        """Open the code panel picker modal."""
        def on_result(result):
            if result is _CODE_PANEL_CANCELLED:
                return
            self._apply_code_panel(result)

        self.app.push_screen(CodePanelScreen(), callback=on_result)

    def _apply_code_panel(self, new_value: bool) -> None:
        """Apply a code panel setting change."""
        from ..settings import set_code_panel
        from ..constants import ICON_ROBOT
        set_code_panel(new_value)
        self.app._code_panel_enabled = new_value
        # Fully close code panel mode if disabling
        if not new_value and self.app._code_panel_active:
            self.app._close_repl_panel()
        # Update subtitle for music/art rooms
        if not self.app._code_panel_active:
            try:
                viewport = self.app.query_one("#viewport")
                room_name = self.app.active_room.name.lower()
                if new_value and room_name in ("music", "art"):
                    viewport.border_subtitle = f"{ICON_ROBOT} Hold Space: write code! {ICON_ROBOT}"
                elif not new_value:
                    viewport.border_subtitle = ""
            except Exception:
                pass
        # Update menu label
        label = "Allow Code Space: Yes" if new_value else "Allow Code Space: No"
        try:
            widget = self.query_one("#menu-code-panel", ParentMenuItem)
            widget.update(label)
        except Exception:
            pass

    def _open_music_looping(self) -> None:
        """Open the music looping picker modal."""
        def on_result(result):
            if result is _MUSIC_LOOPING_CANCELLED:
                return
            self._apply_music_looping(result)

        self.app.push_screen(MusicLoopingScreen(), callback=on_result)

    def _apply_music_looping(self, new_value: bool) -> None:
        """Apply a music looping setting change."""
        from ..settings import set_music_looping
        set_music_looping(new_value)
        self.app._music_looping_enabled = new_value
        # If disabling and a music room loop panel is open, stop it.
        if not new_value:
            try:
                from .music_room import MusicMode
                room = getattr(self.app, '_music_room', None)
                if room is None:
                    for mode in self.app.query(MusicMode):
                        room = mode
                        break
                if room is not None and hasattr(room, '_stop_loop'):
                    room._stop_loop()
            except Exception:
                pass
        # Refresh viewport subtitle so the "Hold Enter: record a loop" hint
        # appears or disappears immediately.
        try:
            from ..purple_tui import _viewport_subtitle
            viewport = self.app.query_one("#viewport")
            viewport.border_subtitle = _viewport_subtitle(
                self.app.active_room,
                self.app._code_panel_enabled,
                self.app.active_theme,
                self.app._music_looping_enabled,
            )
        except Exception:
            pass
        # Update menu label
        label = "Allow Music Looping: Yes" if new_value else "Allow Music Looping: No"
        try:
            widget = self.query_one("#menu-music-looping", ParentMenuItem)
            widget.update(label)
        except Exception:
            pass

    def _open_music_key_switching(self) -> None:
        """Open the music key switching picker modal."""
        def on_result(result):
            if result is _MUSIC_KEY_SWITCHING_CANCELLED:
                return
            self._apply_music_key_switching(result)

        self.app.push_screen(MusicKeySwitchingScreen(), callback=on_result)

    def _apply_music_key_switching(self, new_value: bool) -> None:
        """Apply a music key switching setting change."""
        from ..settings import set_music_key_switching
        set_music_key_switching(new_value)
        self.app._music_key_switching_enabled = new_value
        # Refresh the music room hint bar so "Arrows: switch key" appears/disappears.
        # When disabling, reset the current key back to the default so playback
        # and the header indicator match what the kid sees.
        try:
            from .music_room import MusicMode, DEFAULT_ROOT_INDEX
            for mode in self.app.query(MusicMode):
                if not new_value:
                    mode._root_index = DEFAULT_ROOT_INDEX
                    if mode.grid:
                        mode.grid._root_index = DEFAULT_ROOT_INDEX
                        mode.grid.refresh()
                    if mode._header:
                        mode._header.update_pitch(DEFAULT_ROOT_INDEX)
                if hasattr(mode, '_update_hint'):
                    mode._update_hint()
                if mode._header:
                    mode._header.refresh()
        except Exception:
            pass
        # Update menu label
        label = "Allow Music Key Switching: Yes" if new_value else "Allow Music Key Switching: No"
        try:
            widget = self.query_one("#menu-music-key-switching", ParentMenuItem)
            widget.update(label)
        except Exception:
            pass

    def _open_all_caps(self) -> None:
        def on_result(result):
            if result is _ALL_CAPS_CANCELLED:
                return
            self._apply_all_caps(result)
        self.app.push_screen(AllCapsScreen(), callback=on_result)

    def _apply_all_caps(self, new_value: bool) -> None:
        from ..settings import set_all_caps
        from .. import caps as caps_module
        set_all_caps(new_value)
        caps_module.set_enabled(new_value)
        # Force a full repaint so already-rendered Strips get reissued through the patched ctor.
        try:
            for screen in list(self.app.screen_stack):
                for widget in screen.query("*"):
                    widget.refresh()
                screen.refresh(repaint=True, layout=True)
        except Exception:
            pass
        label = "ALL CAPS: On" if new_value else "ALL CAPS: Off"
        try:
            widget = self.query_one("#menu-all-caps", ParentMenuItem)
            widget.update(label)
        except Exception:
            pass

    def _open_silent_mode(self) -> None:
        def on_result(result):
            if result is _SILENT_MODE_CANCELLED:
                return
            self._apply_silent_mode(result)
        self.app.push_screen(SilentModeScreen(), callback=on_result)

    def _apply_silent_mode(self, new_value: bool) -> None:
        from ..settings import set_silent_mode
        set_silent_mode(new_value)
        self.app._silent_mode = new_value
        if new_value and self.app._volume_lock is not None:
            self.app._volume_lock = None
            self._refresh_volume_lock_label()
        self.app._apply_volume()
        label = "Silent Mode: On" if new_value else "Silent Mode: Off"
        try:
            widget = self.query_one("#menu-silent", ParentMenuItem)
            widget.update(label)
        except Exception:
            pass

    def _open_volume_lock(self) -> None:
        def on_result(result):
            if result is _VOLUME_LOCK_CANCELLED:
                # Space-to-test may have nudged the system mixer; restore.
                self.app._apply_volume_system()
                return
            self._apply_volume_lock(result)
        self.app.push_screen(VolumeLockScreen(), callback=on_result)

    def _apply_volume_lock(self, new_value) -> None:
        from ..settings import set_volume_lock
        set_volume_lock(new_value)
        self.app._volume_lock = new_value
        if new_value is not None and self.app._silent_mode:
            self.app._silent_mode = False
            try:
                widget = self.query_one("#menu-silent", ParentMenuItem)
                widget.update("Silent Mode: Off")
            except Exception:
                pass
        self.app._apply_volume()
        self._refresh_volume_lock_label()

    def _refresh_volume_lock_label(self) -> None:
        label = _volume_lock_menu_label(self.app._volume_lock)
        try:
            widget = self.query_one("#menu-volume-lock", ParentMenuItem)
            widget.update(label)
        except Exception:
            pass

    def _open_parent_pin(self) -> None:
        from ..settings import get_parent_pin
        if get_parent_pin() is None:
            self._start_set_pin_flow()
            return

        def on_action(result):
            if result == _PIN_ACTION_CHANGE:
                self._start_set_pin_flow()
            elif result == _PIN_ACTION_CLEAR:
                self._save_pin(None)

        self.app.push_screen(PinActionScreen(), callback=on_action)

    def _start_set_pin_flow(self) -> None:
        def on_first(first):
            if first is _PIN_CANCELLED:
                return

            def on_confirm(second):
                if second is _PIN_CANCELLED:
                    return
                self._save_pin(first)

            self.app.push_screen(
                PinEntryScreen(
                    "Confirm New PIN",
                    verify=lambda p: p == first,
                    error_message="Didn't match, try again.",
                ),
                callback=on_confirm,
            )

        self.app.push_screen(PinEntryScreen("Enter New PIN"), callback=on_first)

    def _save_pin(self, pin: str | None) -> None:
        from ..settings import set_parent_pin
        set_parent_pin(pin)
        label = "Parent PIN: On" if pin else "Parent PIN: Off"
        try:
            widget = self.query_one("#menu-parent-pin", ParentMenuItem)
            widget.update(label)
        except Exception:
            pass

    def _open_littles_mode(self) -> None:
        """Open the Littles Mode picker."""
        def on_result(result):
            if result is _LITTLES_CANCELLED:
                return  # User pressed Escape, no change
            # Dismiss parent menu with the littles mode change
            # result is None (off), "music", or "art"
            self.dismiss({"littles_mode": result})

        self.app.push_screen(LittlesModeScreen(), callback=on_result)

    def _open_display_settings(self) -> None:
        """Open the display settings modal."""
        self.app.push_screen(DisplaySettingsScreen())

    def _open_volume(self) -> None:
        from ..room_picker import VolumeModal
        self.app.push_screen(VolumeModal())

    def _install_to_disk(self) -> None:
        """Prompt for name, confirm, then push the progress screen."""
        def on_name(name) -> None:
            if name is _INSTALL_NAME_CANCELLED:
                return  # Back to parent menu
            chosen_name = name or ""

            def on_confirm(confirmed: bool) -> None:
                if confirmed:
                    self.dismiss()
                    self.app.call_later(
                        lambda: self.app.push_screen(InstallProgressScreen(computer_name=chosen_name))
                    )

            self.app.push_screen(InstallConfirmScreen(), callback=on_confirm)

        self.app.push_screen(ComputerNameScreen(), callback=on_name)

    def _rename_computer(self) -> None:
        """Prompt for a new computer name and persist it. Refreshes the title bar."""
        from ..purple_tui import _read_computer_name, write_computer_name, BootModeIndicator
        current = _read_computer_name() or ""
        title = "Rename this computer" if current else "Name this computer"
        description = "Leave blank to remove the name." if current else "Optional. Leave blank to skip."

        def on_name(name) -> None:
            if name is _INSTALL_NAME_CANCELLED:
                return
            write_computer_name(name or "")
            try:
                self.app.screen_stack[0].query_one(BootModeIndicator)._push_to_title_bar()
            except Exception:
                pass

        self.app.push_screen(
            ComputerNameScreen(title=title, description=description, initial=current),
            callback=on_name,
        )

    def _open_help_videos(self) -> None:
        from .help_videos import HelpVideosScreen
        self.app.push_screen(HelpVideosScreen())

    def _open_support_info(self) -> None:
        """Open the Support info modal."""
        from .support_info import SupportInfoScreen
        self.app.push_screen(SupportInfoScreen())

    def _open_shell(self) -> None:
        """Open a bash shell, suspending the TUI"""
        # Dismiss the modal first
        self.dismiss()

        # Schedule the shell to open after the modal is closed
        self.app.call_later(self._run_shell)

    def _run_shell(self) -> None:
        """Actually run the shell - called after modal dismissed"""
        # Suspend the Textual app and release evdev grab for terminal input
        with self.app.suspend_with_terminal_input():
            # Reset terminal to sane state (ensures echo is on, etc.)
            os.system('stty sane')
            # Clear screen and show message
            os.system('clear')
            print("=" * 60)
            print("Purple Computer - Terminal Mode")
            print(_boot_mode_hint())
            print("=" * 60)
            print()
            print("You are now in a bash shell.")
            print("Type 'exit' to return to Purple Computer.")
            print()
            print("-" * 60)
            print()
            sys.stdout.flush()

            # Get the user's default shell or fall back to bash
            shell = os.environ.get('SHELL', '/bin/bash')

            # Run the shell interactively
            subprocess.run([shell, '-i'])

            # When shell exits, clean up before resuming
            print()
            print("Returning to Purple Computer...")
            sys.stdout.flush()

            # Flush any buffered input to prevent stray characters
            _flush_terminal_input()
            os.system('stty sane')

        # Force redraw after returning from suspend
        self.app.refresh(repaint=True)

    def _shutdown(self) -> None:
        """Shut down the computer via the ByeScreen (same as power button hold)."""
        self.dismiss()
        self.app._show_bye_screen()

    def _exit_to_system(self) -> None:
        """Exit Purple Computer entirely, dropping to the debug shell."""
        self.dismiss()
        self.app.call_later(self._run_exit_to_system)

    def _run_exit_to_system(self) -> None:
        """Actually exit the app. xinitrc will launch the debug shell."""
        _flush_terminal_input()
        os.system('stty sane')
        self.app.exit()

    def _exit_to_bash(self) -> None:
        """Exit Purple Computer cleanly, dropping to bash (dev mode only)."""
        self.dismiss()
        self.app.call_later(self._run_exit_to_bash)

    def _run_exit_to_bash(self) -> None:
        """Actually exit the app back to bash."""
        _flush_terminal_input()
        os.system('stty sane')
        self.app.exit()

    def _start_demo(self) -> None:
        """Start the demo playback (dev mode only)."""
        self.dismiss()
        # Tell the app to start demo after modal is closed
        self.app.call_later(self.app.start_demo)

