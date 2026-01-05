"""
Purple Computer: Direct Keyboard Input via evdev

Reads keyboard events directly from Linux evdev, bypassing the terminal.
This gives us true key up/down events, precise timing, and access to all keys.

The terminal (Alacritty) is display-only. Keyboard input flows:
  evdev → EvdevReader → RawKeyEvent → App

IMPORTANT: Purple Computer requires Linux with evdev. macOS is not supported.
See guides/keyboard-architecture-v2.md for details.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Awaitable

from .constants import SUPPORT_EMAIL

logger = logging.getLogger(__name__)


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

    # Spacebar and modifiers
    KEY_SPACE = 57
    KEY_CAPSLOCK = 58

    # Function keys
    KEY_F1 = 59
    KEY_F2 = 60
    KEY_F3 = 61
    KEY_F4 = 62
    KEY_F5 = 63
    KEY_F6 = 64
    KEY_F7 = 65
    KEY_F8 = 66
    KEY_F9 = 67
    KEY_F10 = 68
    KEY_F11 = 87
    KEY_F12 = 88

    # Arrow keys
    KEY_UP = 103
    KEY_LEFT = 105
    KEY_RIGHT = 106
    KEY_DOWN = 108


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
    KeyCode.KEY_SEMICOLON: ';', KeyCode.KEY_APOSTROPHE: "'", KeyCode.KEY_GRAVE: '`',
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
    KeyCode.KEY_F1: 'f1', KeyCode.KEY_F2: 'f2', KeyCode.KEY_F3: 'f3',
    KeyCode.KEY_F4: 'f4', KeyCode.KEY_F5: 'f5', KeyCode.KEY_F6: 'f6',
    KeyCode.KEY_F7: 'f7', KeyCode.KEY_F8: 'f8', KeyCode.KEY_F9: 'f9',
    KeyCode.KEY_F10: 'f10', KeyCode.KEY_F11: 'f11', KeyCode.KEY_F12: 'f12',
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
        scancode: Hardware scancode (for F-key remapping), 0 if unavailable
    """
    keycode: int
    is_down: bool
    timestamp: float
    scancode: int = 0

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
# F-Key Scancode Mapping
# =============================================================================

MAPPING_FILE = Path.home() / ".config" / "purple" / "keyboard-map.json"


def load_scancode_map() -> dict[int, int]:
    """Load calibrated scancode→keycode mapping from disk."""
    if MAPPING_FILE.exists():
        try:
            data = json.loads(MAPPING_FILE.read_text())
            return {int(k): v for k, v in data.get("scancodes", {}).items()}
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    return {}


# =============================================================================
# EvdevReader
# =============================================================================

# Event type constants (from linux/input-event-codes.h)
EV_KEY = 1
EV_MSC = 4
MSC_SCAN = 4


class EvdevReader:
    """
    Reads keyboard events directly from evdev.

    This gives us:
    - True key down/up events (value=1/0)
    - Precise timestamps
    - All keycodes (no terminal filtering)
    - Scancodes for F-key remapping

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
        self._device = None
        self._running = False
        self._pending_scancode = 0
        self._scancode_map = load_scancode_map()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start reading keyboard events in background."""
        import evdev
        from evdev import InputDevice

        # Find or open device
        if self._device_path:
            self._device = InputDevice(self._device_path)
        else:
            self._device = self._find_keyboard()

        if self._device is None:
            raise RuntimeError(
                "Could not find your keyboard.\n"
                "Please make sure a keyboard is connected.\n\n"
                f"If this keeps happening, contact {SUPPORT_EMAIL}"
            )

        logger.info(f"EvdevReader: using {self._device.path} ({self._device.name})")

        # Grab device if requested
        if self._grab:
            try:
                self._device.grab()
                logger.info("EvdevReader: grabbed keyboard exclusively")
            except IOError as e:
                logger.warning(f"EvdevReader: could not grab device: {e}")

        self._running = True
        self._task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        """Stop reading and release the device."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._device:
            if self._grab:
                try:
                    self._device.ungrab()
                except (IOError, OSError):
                    pass
            self._device.close()
            self._device = None

        logger.info("EvdevReader: stopped")

    async def _read_loop(self) -> None:
        """Main event reading loop."""
        try:
            async for event in self._device.async_read_loop():
                if not self._running:
                    break

                # Capture scancode (arrives before key event)
                if event.type == EV_MSC and event.code == MSC_SCAN:
                    self._pending_scancode = event.value
                    continue

                # Process key events (ignore repeats: value=2)
                if event.type == EV_KEY and event.value in (0, 1):
                    keycode = event.code
                    scancode = self._pending_scancode
                    self._pending_scancode = 0

                    # Apply scancode remapping for F-keys
                    if scancode and scancode in self._scancode_map:
                        keycode = self._scancode_map[scancode]

                    raw_event = RawKeyEvent(
                        keycode=keycode,
                        is_down=(event.value == 1),
                        timestamp=event.timestamp(),
                        scancode=scancode,
                    )

                    await self._callback(raw_event)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"EvdevReader error: {e}")
            raise

    def _find_keyboard(self):
        """Find the first keyboard device."""
        import evdev
        from evdev import InputDevice

        # Keys that indicate a real keyboard
        keyboard_keys = set(range(KeyCode.KEY_A, KeyCode.KEY_Z + 1))

        # Prefer by-id path (stable across reboots)
        by_id = Path("/dev/input/by-id")
        if by_id.exists():
            for path in sorted(by_id.iterdir()):
                name = path.name.lower()
                if "kbd" in name or "keyboard" in name:
                    try:
                        dev = InputDevice(str(path.resolve()))
                        caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
                        if set(caps) & keyboard_keys:
                            return dev
                    except (PermissionError, OSError):
                        continue

        # Fall back to scanning all devices
        for dev_path in sorted(evdev.list_devices()):
            try:
                dev = InputDevice(dev_path)
                # Skip virtual devices we might have created
                name_lower = dev.name.lower()
                if "virtual" in name_lower:
                    continue
                # Check for letter keys
                caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
                if set(caps) & keyboard_keys:
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
