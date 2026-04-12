"""
Purple Computer: Direct Keyboard Input via evdev

Reads keyboard events directly from Linux evdev, bypassing the terminal.
This gives us true key up/down events, precise timing, and access to all keys
including media keys (volume).

The terminal (Alacritty) is display-only. Keyboard input flows:
  evdev → EvdevReader → RawKeyEvent → App

IMPORTANT: Purple Computer requires Linux with evdev. macOS is not supported.
See guides/keyboard-architecture.md for details.
"""

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Awaitable

from .constants import SUPPORT_EMAIL

logger = logging.getLogger(__name__)


# =============================================================================
# keyd integration
# =============================================================================
# keyd is a kernel keymap daemon shipped in the golden image. It grabs every
# matching physical keyboard via EVIOCGRAB and re-emits remapped events
# through a single uinput virtual device. See config/keyd/default.conf.

KEYD_VIRTUAL_NAME = "keyd virtual keyboard"
KEYD_CONFIG_PATH = Path("/etc/keyd/default.conf")
KEYD_WAIT_SECS = 2.0


# =============================================================================
# Key Codes (subset of Linux input-event-codes.h)
# =============================================================================

class KeyCode:
    """Linux key codes. See /usr/include/linux/input-event-codes.h"""
    # Row 1: numbers
    KEY_ESC = 1
    KEY_1 = 2
    KEY_2 = 3
    KEY_3 = 4
    KEY_4 = 5
    KEY_5 = 6
    KEY_6 = 7
    KEY_7 = 8
    KEY_8 = 9
    KEY_9 = 10
    KEY_0 = 11
    KEY_MINUS = 12
    KEY_EQUAL = 13
    KEY_BACKSPACE = 14

    # Row 2: QWERTY top
    KEY_TAB = 15
    KEY_Q = 16
    KEY_W = 17
    KEY_E = 18
    KEY_R = 19
    KEY_T = 20
    KEY_Y = 21
    KEY_U = 22
    KEY_I = 23
    KEY_O = 24
    KEY_P = 25
    KEY_LEFTBRACE = 26
    KEY_RIGHTBRACE = 27
    KEY_ENTER = 28

    # Row 3: home row
    KEY_LEFTCTRL = 29
    KEY_A = 30
    KEY_S = 31
    KEY_D = 32
    KEY_F = 33
    KEY_G = 34
    KEY_H = 35
    KEY_J = 36
    KEY_K = 37
    KEY_L = 38
    KEY_SEMICOLON = 39
    KEY_APOSTROPHE = 40
    KEY_GRAVE = 41
    KEY_102ND = 86  # ISO "non-US backslash"; some Apple keyboards send this for grave

    # Row 4: bottom row
    KEY_LEFTSHIFT = 42
    KEY_BACKSLASH = 43
    KEY_Z = 44
    KEY_X = 45
    KEY_C = 46
    KEY_V = 47
    KEY_B = 48
    KEY_N = 49
    KEY_M = 50
    KEY_COMMA = 51
    KEY_DOT = 52
    KEY_SLASH = 53
    KEY_RIGHTSHIFT = 54

    # Function keys
    KEY_F1 = 59
    KEY_F2 = 60

    # Spacebar and modifiers
    KEY_LEFTALT = 56
    KEY_SPACE = 57
    KEY_CAPSLOCK = 58

    # Arrow keys
    KEY_UP = 103
    KEY_LEFT = 105
    KEY_RIGHT = 106
    KEY_DOWN = 108

    # Modifier keys
    KEY_RIGHTCTRL = 97
    KEY_RIGHTALT = 100

    # Media keys (hardware volume buttons)
    KEY_MUTE = 113
    KEY_VOLUMEDOWN = 114
    KEY_VOLUMEUP = 115

    # Compose/Menu key (right of right Alt on many keyboards)
    KEY_COMPOSE = 127

    # Power/system keys
    KEY_POWER = 116

    # Brightness keys
    KEY_BRIGHTNESSDOWN = 224
    KEY_BRIGHTNESSUP = 225


# Keycode to character mapping (printable keys only)
KEYCODE_TO_CHAR: dict[int, str] = {
    KeyCode.KEY_1: '1', KeyCode.KEY_2: '2', KeyCode.KEY_3: '3',
    KeyCode.KEY_4: '4', KeyCode.KEY_5: '5', KeyCode.KEY_6: '6',
    KeyCode.KEY_7: '7', KeyCode.KEY_8: '8', KeyCode.KEY_9: '9',
    KeyCode.KEY_0: '0', KeyCode.KEY_MINUS: '-', KeyCode.KEY_EQUAL: '=',
    KeyCode.KEY_Q: 'q', KeyCode.KEY_W: 'w', KeyCode.KEY_E: 'e',
    KeyCode.KEY_R: 'r', KeyCode.KEY_T: 't', KeyCode.KEY_Y: 'y',
    KeyCode.KEY_U: 'u', KeyCode.KEY_I: 'i', KeyCode.KEY_O: 'o',
    KeyCode.KEY_P: 'p', KeyCode.KEY_LEFTBRACE: '[', KeyCode.KEY_RIGHTBRACE: ']',
    KeyCode.KEY_A: 'a', KeyCode.KEY_S: 's', KeyCode.KEY_D: 'd',
    KeyCode.KEY_F: 'f', KeyCode.KEY_G: 'g', KeyCode.KEY_H: 'h',
    KeyCode.KEY_J: 'j', KeyCode.KEY_K: 'k', KeyCode.KEY_L: 'l',
    KeyCode.KEY_SEMICOLON: ';', KeyCode.KEY_APOSTROPHE: "'",
    KeyCode.KEY_BACKSLASH: '\\', KeyCode.KEY_Z: 'z', KeyCode.KEY_X: 'x',
    KeyCode.KEY_C: 'c', KeyCode.KEY_V: 'v', KeyCode.KEY_B: 'b',
    KeyCode.KEY_N: 'n', KeyCode.KEY_M: 'm', KeyCode.KEY_COMMA: ',',
    KeyCode.KEY_DOT: '.', KeyCode.KEY_SLASH: '/', KeyCode.KEY_SPACE: ' ',
}

# Keycode to name mapping (special keys)
KEYCODE_TO_NAME: dict[int, str] = {
    KeyCode.KEY_ESC: 'escape',
    KeyCode.KEY_BACKSPACE: 'backspace',
    KeyCode.KEY_TAB: 'tab',
    KeyCode.KEY_ENTER: 'enter',
    KeyCode.KEY_LEFTCTRL: 'ctrl',
    KeyCode.KEY_LEFTSHIFT: 'shift',
    KeyCode.KEY_RIGHTSHIFT: 'shift',
    KeyCode.KEY_SPACE: 'space',
    KeyCode.KEY_CAPSLOCK: 'caps_lock',
    KeyCode.KEY_MUTE: 'mute', KeyCode.KEY_VOLUMEDOWN: 'volume_down',
    KeyCode.KEY_VOLUMEUP: 'volume_up',
    KeyCode.KEY_BRIGHTNESSDOWN: 'brightness_down',
    KeyCode.KEY_BRIGHTNESSUP: 'brightness_up',
    KeyCode.KEY_UP: 'up', KeyCode.KEY_DOWN: 'down',
    KeyCode.KEY_LEFT: 'left', KeyCode.KEY_RIGHT: 'right',
}


# =============================================================================
# RawKeyEvent
# =============================================================================

@dataclass
class RawKeyEvent:
    """
    A single keyboard event from evdev.

    Attributes:
        keycode: Linux key code (KEY_SPACE, KEY_A, etc.)
        is_down: True for key press, False for key release
        timestamp: Monotonic timestamp in seconds
        scancode: Hardware scancode, 0 if unavailable
        is_repeat: True if this is a key repeat event (key held down)
    """
    keycode: int
    is_down: bool
    timestamp: float
    scancode: int = 0
    is_repeat: bool = False

    @property
    def char(self) -> Optional[str]:
        """Get the character for this key, or None if not printable."""
        return KEYCODE_TO_CHAR.get(self.keycode)

    @property
    def name(self) -> str:
        """Get a name for this key (e.g., 'space', 'escape', 'a')."""
        if self.keycode in KEYCODE_TO_NAME:
            return KEYCODE_TO_NAME[self.keycode]
        if self.keycode in KEYCODE_TO_CHAR:
            return KEYCODE_TO_CHAR[self.keycode]
        return f"key_{self.keycode}"

    def __repr__(self) -> str:
        arrow = "↓" if self.is_down else "↑"
        return f"RawKeyEvent({self.name} {arrow} @{self.timestamp:.3f})"


# =============================================================================
# EvdevReader
# =============================================================================

# Event type constants (from linux/input-event-codes.h)
EV_KEY = 1
EV_SW = 5    # Switch events (lid, headphone jack, etc.)
EV_MSC = 4
MSC_SCAN = 4
SW_LID = 0   # Lid switch code


class EvdevReader:
    """
    Reads keyboard events directly from evdev.

    This gives us:
    - True key down/up events (value=1/0)
    - Precise timestamps
    - All keycodes (no terminal filtering)
    - Scancodes

    Usage:
        async def handle_key(event: RawKeyEvent):
            print(f"{event.name} {'down' if event.is_down else 'up'}")

        reader = EvdevReader(handle_key)
        await reader.start()
        # ... later ...
        await reader.stop()
    """

    def __init__(
        self,
        callback: Callable[[RawKeyEvent], Awaitable[None]],
        device_path: Optional[str] = None,
        grab: bool = True,
    ):
        """
        Initialize the evdev reader.

        Args:
            callback: Async function called for each RawKeyEvent
            device_path: Path to input device, or None to auto-detect
            grab: If True, grab device exclusively (other apps won't see keys)
        """
        self._callback = callback
        self._device_path = device_path
        self._grab = grab
        self._devices: list = []  # All keyboard evdev devices
        self._running = False
        self._pending_scancodes: dict = {}  # Per-device pending scancodes
        self._tasks: list[asyncio.Task] = []
        self._logged_keycodes: set = set()  # Keycodes logged to diag (first-occurrence)

        # Emergency VT switch: Ctrl+\ held 3s or Ctrl+Alt+F2 → chvt 2
        self._ctrl_held = False
        self._alt_held = False
        self._ctrl_backslash_start: float | None = None
        self._vt_switch_fired = False
        self._vt_away = False  # True while switched away to another VT
        self._vt_away_time: float = 0  # When _vt_away was set (for chvt race guard)

    @property
    def _device(self):
        """Primary device (for backward compat with logging)."""
        return self._devices[0] if self._devices else None

    @staticmethod
    def _diag(msg):
        """Write to /tmp/evdev-diag.log (readable from recovery shell via Ctrl+\\)."""
        try:
            with open("/tmp/evdev-diag.log", "a") as f:
                f.write(f"{msg}\n")
        except Exception:
            pass
        logger.info(msg)

    async def start(self) -> None:
        """Start reading keyboard events in background."""
        from evdev import InputDevice

        self._diag("EvdevReader.start() called")

        # Find or open devices
        if self._device_path:
            self._devices = [InputDevice(self._device_path)]
        else:
            self._devices = self._find_keyboards()

        if not self._devices:
            self._diag("ERROR: no keyboard found")
            raise RuntimeError(
                "Could not find your keyboard.\n"
                "Please make sure a keyboard is connected.\n\n"
                f"If this keeps happening, contact {SUPPORT_EMAIL}"
            )

        for dev in self._devices:
            self._diag(f"EvdevReader: using {dev.path} ({dev.name})")

        # Grab devices if requested
        if self._grab:
            for dev in self._devices:
                try:
                    dev.grab()
                    logger.info(f"EvdevReader: grabbed {dev.path} exclusively")
                except IOError as e:
                    logger.warning(f"EvdevReader: could not grab {dev.path}: {e}")

        self._running = True
        for dev in self._devices:
            self._tasks.append(asyncio.create_task(self._read_loop(dev)))

    async def stop(self) -> None:
        """Stop reading and release all devices."""
        self._running = False

        # Close all devices first to unblock async_read_loop() immediately.
        # Virtual devices (UTM, QEMU) may not wake up on cancel alone.
        for dev in self._devices:
            if self._grab:
                try:
                    dev.ungrab()
                except (IOError, OSError):
                    pass
            try:
                dev.close()
            except Exception:
                pass
        self._devices = []

        for task in self._tasks:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._tasks = []

        logger.info("EvdevReader: stopped")

    @staticmethod
    def _is_on_tty1() -> bool:
        """Check if tty1 is the active virtual terminal."""
        try:
            with open("/sys/class/tty/tty0/active") as f:
                return f.read().strip() == "tty1"
        except Exception:
            return True  # Assume tty1 if we can't tell

    def _switch_to_tty2(self) -> None:
        """Switch to tty2 with a usable bash shell.

        Uses openvt (from kbd package) to spawn a clean login shell on
        tty2. openvt handles terminal setup correctly, avoiding the
        broken-echo / wrong-keymap issues that happen when manually
        redirecting to /dev/tty2.
        """
        # openvt -s switches to the VT, -f forces even if VT is in use,
        # -c 2 targets tty2, -- separates openvt args from the command.
        # login -f skips password for the purple user.
        subprocess.Popen(
            ["sudo", "openvt", "-s", "-f", "-c", "2", "--",
             "login", "-f", "purple"],
        )

    def release_grab(self) -> None:
        """
        Temporarily release the keyboard grab.

        Call this before suspending the app to allow terminal input
        (e.g., for input() to receive keystrokes).
        Call reacquire_grab() after resuming.
        """
        if self._grab:
            for dev in self._devices:
                try:
                    dev.ungrab()
                    logger.info(f"EvdevReader: released grab on {dev.path}")
                except (IOError, OSError) as e:
                    logger.warning(f"EvdevReader: could not release grab on {dev.path}: {e}")

    def reacquire_grab(self) -> None:
        """
        Re-acquire the keyboard grab after suspend.

        Call this after the terminal session ends and before
        the TUI resumes normal operation.
        """
        import select

        if self._grab:
            for dev in self._devices:
                try:
                    # Flush any pending events before reacquiring grab
                    try:
                        flush_deadline = time.monotonic() + 1.0
                        while time.monotonic() < flush_deadline:
                            readable, _, _ = select.select([dev.fd], [], [], 0)
                            if not readable:
                                break
                            dev.read_one()
                    except Exception:
                        pass

                    dev.grab()
                    logger.info(f"EvdevReader: reacquired grab on {dev.path}")
                except (IOError, OSError) as e:
                    logger.warning(f"EvdevReader: could not reacquire grab on {dev.path}: {e}")

    async def _read_loop(self, device) -> None:
        """Main event reading loop for one keyboard device."""
        dev_path = device.path
        self._diag(f"Read loop started: {dev_path} ({device.name})")
        try:
            async for event in device.async_read_loop():
                if not self._running:
                    break

                # Capture scancode (arrives before key event), tracked per-device
                if event.type == EV_MSC and event.code == MSC_SCAN:
                    self._pending_scancodes[dev_path] = event.value
                    continue

                # Process key events: 0=up, 1=down, 2=repeat
                if event.type == EV_KEY and event.value in (0, 1, 2):
                    keycode = event.code
                    is_down = event.value in (1, 2)

                    # Log first occurrence of each unmapped keycode with its
                    # scancode to help debug keys that send unexpected codes.
                    if is_down and keycode not in self._logged_keycodes:
                        self._logged_keycodes.add(keycode)
                        if keycode not in KEYCODE_TO_CHAR and keycode not in KEYCODE_TO_NAME:
                            scancode = self._pending_scancodes.get(dev_path, 0)
                            self._diag(
                                f"Unmapped keycode={keycode} "
                                f"scancode=0x{scancode:x} on {dev_path}"
                            )

                    # Emergency VT switch: Ctrl+\ held 3s or Ctrl+Alt+F2 → chvt 2
                    # Runs at evdev level so it works even when Textual is hung.
                    if keycode in (KeyCode.KEY_LEFTCTRL, KeyCode.KEY_RIGHTCTRL):
                        self._ctrl_held = is_down
                        if not is_down:
                            self._ctrl_backslash_start = None
                            self._vt_switch_fired = False
                    if keycode in (KeyCode.KEY_LEFTALT, KeyCode.KEY_RIGHTALT):
                        self._alt_held = is_down

                    # Ctrl+Alt+F2: immediate VT switch (standard Linux combo)
                    # Ctrl+Alt+F1: immediate switch back
                    if keycode == KeyCode.KEY_F2 and is_down and self._ctrl_held and self._alt_held:
                        if not self._vt_away:
                            self._vt_switch_fired = True
                            self._vt_away = True
                            self._vt_away_time = time.monotonic()
                            self.release_grab()
                            logger.warning("Emergency VT switch: Ctrl+Alt+F2, switching to tty2")
                            self._switch_to_tty2()
                    if keycode == KeyCode.KEY_F1 and is_down and self._ctrl_held and self._alt_held:
                        if self._vt_away:
                            self._vt_switch_fired = True
                            logger.warning("Emergency VT switch: Ctrl+Alt+F1, switching back to tty1")
                            subprocess.Popen(["sudo", "chvt", "1"])
                            self._vt_away = False
                            self.reacquire_grab()

                    # Ctrl+\ held 3s: toggle VT switch
                    if keycode == KeyCode.KEY_BACKSLASH:
                        if is_down and self._ctrl_held and not self._vt_switch_fired:
                            if self._ctrl_backslash_start is None:
                                self._ctrl_backslash_start = time.monotonic()
                            elif time.monotonic() - self._ctrl_backslash_start >= 3.0:
                                self._vt_switch_fired = True
                                self._ctrl_backslash_start = None
                                if self._vt_away:
                                    logger.warning("Emergency VT switch: Ctrl+\\ held 3s, switching back to tty1")
                                    subprocess.Popen(["sudo", "chvt", "1"])
                                    self._vt_away = False
                                    self.reacquire_grab()
                                else:
                                    logger.warning("Emergency VT switch: Ctrl+\\ held 3s, switching to tty2")
                                    self._vt_away = True
                                    self._vt_away_time = time.monotonic()
                                    self.release_grab()
                                    self._switch_to_tty2()
                        if not is_down:
                            self._ctrl_backslash_start = None
                            self._vt_switch_fired = False

                    # While switched away to another VT, check if user
                    # returned to tty1 (via Ctrl+Alt+F1 on tty2). Reacquire
                    # grab and resume normal operation.
                    if self._vt_away:
                        # Guard: chvt is async (Popen), so key-up events from
                        # the switch combo arrive before chvt completes. Without
                        # this cooldown, _is_on_tty1() returns True (still on
                        # tty1), causing an immediate grab reacquire that blocks
                        # tty2 input once chvt finishes.
                        if time.monotonic() - self._vt_away_time > 0.5 and self._is_on_tty1():
                            logger.info("VT switch: back on tty1, reacquiring grab")
                            self._vt_away = False
                            self.reacquire_grab()
                        else:
                            continue  # Don't forward events while away

                    scancode = self._pending_scancodes.pop(dev_path, 0)

                    raw_event = RawKeyEvent(
                        keycode=keycode,
                        is_down=is_down,
                        timestamp=event.timestamp(),
                        scancode=scancode,
                        is_repeat=(event.value == 2),
                    )

                    await self._callback(raw_event)

        except asyncio.CancelledError:
            self._diag(f"Read loop cancelled: {dev_path}")
            return  # Clean shutdown, no reconnect
        except OSError as e:
            if self._running:
                self._diag(f"Read loop LOST DEVICE: {dev_path}: {e}")
            else:
                self._diag(f"Read loop stopped: {dev_path}")
                return  # Clean shutdown, no reconnect
        except Exception as e:
            self._diag(f"Read loop ERROR: {dev_path}: {e}")
            logger.error(f"EvdevReader error on {dev_path}: {e}")

        # Device lost while we're still supposed to be running: try to
        # reconnect. USB devices can briefly disappear during bus resets
        # or heavy I/O. The kernel re-creates the device node quickly.
        if self._running:
            # Remove the dead device
            self._devices = [d for d in self._devices if d.path != dev_path]
            try:
                device.close()
            except Exception:
                pass
            asyncio.ensure_future(self._reconnect(dev_path))

    async def _reconnect(self, lost_path: str) -> None:
        """Scan for keyboards and restart read loops on new devices.

        Called when a read loop exits unexpectedly. Retries every second
        for up to 30 seconds, which covers USB bus resets (typically
        ~1-2 seconds) and slower device re-enumeration.
        """
        active_paths = {d.path for d in self._devices}

        for attempt in range(30):
            if not self._running:
                return
            await asyncio.sleep(1)

            found = self._find_keyboards()
            new_devices = [d for d in found if d.path not in active_paths]

            # Close devices we didn't need (already being read)
            for d in found:
                if d.path in active_paths:
                    d.close()

            if new_devices:
                for dev in new_devices:
                    self._diag(f"Reconnected: {dev.path} ({dev.name})")
                    if self._grab:
                        try:
                            dev.grab()
                        except IOError as e:
                            self._diag(f"Reconnect grab failed: {dev.path}: {e}")
                    self._devices.append(dev)
                    active_paths.add(dev.path)
                    self._tasks.append(asyncio.create_task(self._read_loop(dev)))
                return

        self._diag(f"Reconnect gave up after 30s (lost {lost_path})")

    def _find_keyboards(self):
        """Find all real keyboard input devices.

        Some laptops expose two keyboard devices (e.g. AT Translated Set 2
        keyboard on two different event nodes). Which one delivers key events
        can change when USB devices are plugged/unplugged, so listen on all
        of them, just like PowerButtonReader listens on all power buttons.

        Must not be fooled by USB flash drives that expose HID interfaces with
        partial keyboard capabilities.

        A real keyboard has: all 26 letter keys, Enter, Space, at least one
        Shift, and EV_REP (auto-repeat). USB drive HID interfaces typically
        report some key capabilities but lack the full set or EV_REP.
        """
        import evdev
        from evdev import InputDevice

        _diag = self._diag

        letter_keys = set(range(KeyCode.KEY_A, KeyCode.KEY_Z + 1))
        required_keys = letter_keys | {
            KeyCode.KEY_ENTER,
            KeyCode.KEY_SPACE,
            KeyCode.KEY_LEFTSHIFT,
        }

        def _is_real_keyboard(dev):
            caps = dev.capabilities()
            key_caps = set(caps.get(evdev.ecodes.EV_KEY, []))
            return required_keys.issubset(key_caps) and evdev.ecodes.EV_REP in caps

        def _has_letter_keys(dev):
            return letter_keys.issubset(set(dev.capabilities().get(evdev.ecodes.EV_KEY, [])))

        def _gather(predicate, label):
            """Iterate by-id first (stable names), then all event nodes.

            Returns every device passing `predicate`. The keyd virtual keyboard
            is matched by the same strict predicate as any physical keyboard,
            so there is no keyd-specific branch here. Devices keyd has grabbed
            via EVIOCGRAB emit no events to other readers, so opening them
            alongside the virtual device is harmless: no key press can emerge
            from two paths at once.
            """
            found = []
            seen_paths = set()

            by_id = Path("/dev/input/by-id")
            if by_id.exists():
                for link in sorted(by_id.iterdir()):
                    name = link.name.lower()
                    if "kbd" not in name and "keyboard" not in name:
                        continue
                    try:
                        real_path = str(link.resolve())
                        if real_path in seen_paths:
                            continue
                        dev = InputDevice(real_path)
                    except (PermissionError, OSError):
                        continue
                    if predicate(dev):
                        _diag(f"KBD SCAN: {label} via by-id: {real_path} ({dev.name})")
                        found.append(dev)
                        seen_paths.add(real_path)
                    else:
                        dev.close()

            for dev_path in sorted(evdev.list_devices()):
                if dev_path in seen_paths:
                    continue
                try:
                    dev = InputDevice(dev_path)
                except (PermissionError, OSError):
                    continue
                if predicate(dev):
                    _diag(f"KBD SCAN: {label} via scan: {dev_path} ({dev.name})")
                    found.append(dev)
                    seen_paths.add(dev_path)
                else:
                    dev.close()

            return found

        def _keyd_virtual_present():
            for p in evdev.list_devices():
                try:
                    dev = InputDevice(p)
                except (PermissionError, OSError):
                    continue
                try:
                    if KEYD_VIRTUAL_NAME in dev.name.lower():
                        return True
                finally:
                    dev.close()
            return False

        # purple-x11.service has After=keyd.service, but keyd is Type=simple,
        # so "started" means "forked", not "uinput device ready". Without this
        # poll we race keyd's device creation at cold boot and pick up a
        # physical keyboard keyd grabs a moment later -> silent input.
        if KEYD_CONFIG_PATH.exists():
            deadline = time.monotonic() + KEYD_WAIT_SECS
            while not _keyd_virtual_present() and time.monotonic() < deadline:
                time.sleep(0.1)

        found = _gather(_is_real_keyboard, "strict")
        if found:
            _diag(f"KBD SCAN: listening on {len(found)} keyboard device(s)")
            return found

        # Loose fallback: some keyboards (e.g. Apple SPI in Touch Bar Macs)
        # lack EV_REP but are still the user's only keyboard.
        _diag("KBD SCAN: no strict matches, falling back to loose match")
        logger.warning("No keyboard passed strict check, falling back to loose match")
        found = _gather(_has_letter_keys, "loose")
        if found:
            _diag(f"KBD SCAN: {len(found)} device(s) via loose match")
        return found


# =============================================================================
# PowerButtonReader
# =============================================================================


@dataclass
class PowerButtonEvent:
    """A high-level power button event.

    Attributes:
        action: "tap" (short press) or "hold" (held for threshold)
        timestamp: Monotonic timestamp of the original press
    """
    action: str  # "tap" or "hold"
    timestamp: float


class PowerButtonReader:
    """
    Reads power button events from evdev and detects tap vs hold.

    Hold detection uses asyncio timers, independent of Textual's event loop.
    This ensures reliable detection even if the TUI is suspended.

    Usage:
        async def handle_power(event: PowerButtonEvent):
            print(f"Power {event.action}")

        reader = PowerButtonReader(handle_power, hold_seconds=3)
        await reader.start()
    """

    def __init__(self, callback: Callable[[PowerButtonEvent], Awaitable[None]],
                 hold_seconds: float = 3):
        self._callback = callback
        self._hold_seconds = hold_seconds
        self._devices: list = []  # All power button evdev devices
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._hold_task: Optional[asyncio.Task] = None
        self._press_time: Optional[float] = None

    @property
    def _device(self):
        """Primary device (for backward compat with init logging)."""
        return self._devices[0] if self._devices else None

    async def start(self) -> None:
        """Start reading power button events in background."""
        self._devices = self._find_power_buttons()

        if not self._devices:
            logger.info("PowerButtonReader: no power button device found (OK on desktops)")
            return

        for dev in self._devices:
            logger.info(f"PowerButtonReader: listening on {dev.path} ({dev.name})")

        self._running = True
        for dev in self._devices:
            self._tasks.append(asyncio.create_task(self._read_loop(dev)))
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def stop(self) -> None:
        """Stop reading and release all devices."""
        self._running = False
        self._cancel_hold_task()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        # Close all devices first to unblock async_read_loop()
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices = []

        for task in self._tasks:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._tasks = []

        logger.info("PowerButtonReader: stopped")

    async def _heartbeat(self) -> None:
        """Periodic check that read loop tasks are still alive (debug only)."""
        from .power_manager import _power_log
        try:
            await asyncio.sleep(30)
            while self._running:
                for i, task in enumerate(self._tasks):
                    state = "alive" if not task.done() else "DEAD"
                    if task.done():
                        exc = task.exception() if not task.cancelled() else "cancelled"
                        state = f"DEAD ({exc})"
                    dev_path = self._devices[i].path if i < len(self._devices) else "?"
                    _power_log(f"POWER HEARTBEAT: task[{i}]={state} dev={dev_path}")
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    def _cancel_hold_task(self) -> None:
        if self._hold_task and not self._hold_task.done():
            self._hold_task.cancel()
        self._hold_task = None

    async def _hold_timer(self) -> None:
        """Wait for hold threshold, then emit hold event."""
        try:
            await asyncio.sleep(self._hold_seconds)
            # Held long enough: emit hold
            if self._press_time is not None:
                await self._callback(PowerButtonEvent(
                    action="hold",
                    timestamp=self._press_time,
                ))
                self._press_time = None  # Prevent tap on late release
        except asyncio.CancelledError:
            pass

    async def _read_loop(self, device) -> None:
        """Main event reading loop for one power button device."""
        from .power_manager import _power_log
        _power_log(f"POWER READ LOOP: starting on {device.path} ({device.name})")
        event_count = 0
        try:
            async for event in device.async_read_loop():
                if not self._running:
                    _power_log("POWER READ LOOP: stopped (_running=False)")
                    break

                event_count += 1
                # Log first few events to confirm device is alive
                if event_count <= 5:
                    _power_log(f"POWER READ LOOP: event #{event_count} type={event.type} "
                               f"code={event.code} value={event.value}")

                if event.type == EV_KEY and event.code == KeyCode.KEY_POWER:
                    _power_log(f"POWER KEY: value={event.value} (1=press, 0=release)")
                    if event.value == 1:  # press
                        self._press_time = event.timestamp()
                        self._cancel_hold_task()
                        self._hold_task = asyncio.create_task(self._hold_timer())
                    elif event.value == 0:  # release
                        if self._hold_task and not self._hold_task.done():
                            # Released before hold threshold: tap
                            self._cancel_hold_task()
                            if self._press_time is not None:
                                await self._callback(PowerButtonEvent(
                                    action="tap",
                                    timestamp=self._press_time,
                                ))
                        self._press_time = None

        except asyncio.CancelledError:
            _power_log("POWER READ LOOP: cancelled")
        except OSError as e:
            _power_log(f"POWER READ LOOP: OSError (device closed?): {e}")
        except Exception as e:
            _power_log(f"POWER READ LOOP: unexpected error: {e}")
            logger.error(f"PowerButtonReader error: {e}")
        else:
            _power_log(f"POWER READ LOOP: exited normally after {event_count} events")

    def _find_power_buttons(self):
        """Find all dedicated power button input devices.

        Linux often exposes two ACPI power buttons (LNXPWRBN and PNP0C0C).
        Only one receives the physical press, but which one varies by hardware.
        Listen on all dedicated ones to be safe.
        """
        import evdev
        from evdev import InputDevice
        from .power_manager import _power_log

        dedicated = []   # Few keys (dedicated power button devices)
        keyboards = []   # Many keys (keyboards that also have KEY_POWER)

        for dev_path in sorted(evdev.list_devices()):
            try:
                dev = InputDevice(dev_path)
                caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
                if evdev.ecodes.KEY_POWER in caps:
                    n_keys = len(caps)
                    _power_log(f"POWER SCAN: {dev_path} name={dev.name!r} keys={n_keys}")
                    if n_keys < 20:
                        dedicated.append(dev)
                    else:
                        keyboards.append(dev)
                else:
                    dev.close()
            except (PermissionError, OSError) as e:
                _power_log(f"POWER SCAN: {dev_path} error: {e}")
                continue

        if not dedicated and not keyboards:
            _power_log("POWER SCAN: no devices with KEY_POWER found")
            return []

        # Use all dedicated power button devices (listen on all of them).
        # Only fall back to keyboards if no dedicated device exists.
        if dedicated:
            for dev in keyboards:
                dev.close()
            chosen = dedicated
        else:
            chosen = keyboards

        for dev in chosen:
            _power_log(f"POWER SCAN: will listen on {dev.path} ({dev.name})")

            # Test if another process has an exclusive grab
            try:
                import fcntl
                EVIOCGRAB = 0x40044590
                fcntl.ioctl(dev.fd, EVIOCGRAB, 1)
                fcntl.ioctl(dev.fd, EVIOCGRAB, 0)
                _power_log(f"POWER GRAB TEST: {dev.path} NOT grabbed")
            except OSError as e:
                _power_log(f"POWER GRAB TEST: {dev.path} IS grabbed: {e}")

        return chosen


# =============================================================================
# Lid Switch Reader (evdev)
# =============================================================================

@dataclass
class LidSwitchEvent:
    """A lid switch event.

    Attributes:
        is_open: True if lid was opened, False if closed
        timestamp: Monotonic timestamp of the event
    """
    is_open: bool
    timestamp: float


class LidSwitchReader:
    """
    Reads lid switch events from evdev for instant lid open/close detection.

    Uses the kernel's SW_LID switch event (same mechanism systemd-logind uses).
    Falls back gracefully if no lid switch device is found (desktops, some hardware).

    Also reads the initial lid state on start so we don't miss a lid that's
    already closed when the app launches.

    Usage:
        async def handle_lid(event: LidSwitchEvent):
            if event.is_open:
                wake_up()
            else:
                show_sleep_face()

        reader = LidSwitchReader(handle_lid)
        await reader.start()
    """

    def __init__(self, callback: Callable[[LidSwitchEvent], Awaitable[None]]):
        self._callback = callback
        self._device = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start reading lid switch events in background."""
        self._device = self._find_lid_switch()

        if self._device is None:
            logger.info("LidSwitchReader: no lid switch device found (OK on desktops)")
            return

        logger.info(f"LidSwitchReader: using {self._device.path} ({self._device.name})")

        # Read initial state so we catch "lid already closed at boot"
        try:
            import fcntl
            # EVIOCGSW(len) = _IOC(_IOC_READ, 'E', 0x1b, len)
            EVIOCGSW = 0x8001451b  # _IOR('E', 0x1b, 1 byte)
            buf = bytearray(1)
            fcntl.ioctl(self._device.fd, EVIOCGSW, buf)
            lid_closed = bool(buf[0] & (1 << SW_LID))
            if lid_closed:
                await self._callback(LidSwitchEvent(
                    is_open=False,
                    timestamp=time.monotonic(),
                ))
        except Exception:
            pass  # Non-critical, we'll get events going forward

        self._running = True
        self._task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Stop reading and release the device."""
        self._running = False

        if self._task:
            self._task.cancel()
            if self._device:
                self._device.close()
                self._device = None
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None
        elif self._device:
            self._device.close()
            self._device = None

        logger.info("LidSwitchReader: stopped")

    async def _read_loop(self) -> None:
        """Main event reading loop."""
        try:
            async for event in self._device.async_read_loop():
                if not self._running:
                    break

                if event.type == EV_SW and event.code == SW_LID:
                    # value 1 = lid closed, value 0 = lid open
                    await self._callback(LidSwitchEvent(
                        is_open=(event.value == 0),
                        timestamp=event.timestamp(),
                    ))

        except asyncio.CancelledError:
            pass
        except OSError:
            # Device was closed (normal during shutdown)
            pass
        except Exception as e:
            logger.error(f"LidSwitchReader error: {e}")

    def _find_lid_switch(self):
        """Find the lid switch input device."""
        import evdev
        from evdev import InputDevice

        for dev_path in sorted(evdev.list_devices()):
            try:
                dev = InputDevice(dev_path)
                sw_caps = dev.capabilities().get(evdev.ecodes.EV_SW, [])
                if evdev.ecodes.SW_LID in sw_caps:
                    return dev
            except (PermissionError, OSError):
                continue

        return None


# =============================================================================
# Utility
# =============================================================================

def check_evdev_available() -> None:
    """
    Verify evdev is available. Raises RuntimeError with helpful message if not.

    Call this at app startup to fail fast with a clear error.
    """
    try:
        import evdev
    except ImportError as e:
        logger.error(f"evdev import failed: {e}")
        raise RuntimeError(
            "Purple Computer needs to be set up before it can run.\n\n"
            f"Please contact {SUPPORT_EMAIL} for help.\n\n"
            "(Technical: evdev library not installed)"
        )

    try:
        devices = evdev.list_devices()
    except PermissionError as e:
        logger.error(f"Permission denied accessing input devices: {e}")
        raise RuntimeError(
            "Purple Computer doesn't have permission to use the keyboard.\n\n"
            "Please restart your Purple Computer. If this keeps happening,\n"
            f"contact {SUPPORT_EMAIL}\n\n"
            "(Technical: user not in 'input' group)"
        )

    if not devices:
        logger.error("No input devices found")
        raise RuntimeError(
            "Could not find your keyboard.\n"
            "Please make sure a keyboard is connected.\n\n"
            f"If this keeps happening, contact {SUPPORT_EMAIL}"
        )
