"""
Keyboard normalization layer for Linux using evdev.

Maps physical F-row keys to logical F1-F4/F12 using scancodes (MSC_SCAN),
which identify physical keys regardless of Fn Lock state or firmware decisions.

Mapping priority:
1. Calibrated scancode mapping (from /etc/purple/keyboard-map.json)
2. Native F-keys (if firmware sends KEY_F1-F12 directly)
3. Passthrough (unknown keys unchanged)

Also provides:
- Tap-vs-hold shift (tap = sticky shift for next char)
- Long-press Escape (1s) emits F24 for parent mode
- Caps lock tracking
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Import DoubleTapDetector for shared double-tap logic
try:
    from purple_tui.keyboard import DoubleTapDetector
except ImportError:
    # Fallback for standalone operation (e.g., running directly)
    DoubleTapDetector = None

# =============================================================================
# Constants (matching Linux input-event-codes.h)
# =============================================================================

class KeyCodes:
    """Linux input event codes."""
    # Event types
    EV_SYN = 0
    EV_KEY = 1
    EV_MSC = 4

    # MSC codes
    MSC_SCAN = 4

    # Modifiers
    KEY_LEFTSHIFT = 42
    KEY_RIGHTSHIFT = 54
    KEY_CAPSLOCK = 58

    # Common keys
    KEY_ESC = 1
    KEY_BACKSPACE = 14
    KEY_TAB = 15
    KEY_ENTER = 28
    KEY_SPACE = 57

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
    KEY_F24 = 194

    # Letters (for keyboard detection)
    KEY_A, KEY_Z = 30, 44

# F-keys we care about remapping (all 12)
TARGET_FKEYS = {
    1: KeyCodes.KEY_F1, 2: KeyCodes.KEY_F2, 3: KeyCodes.KEY_F3, 4: KeyCodes.KEY_F4,
    5: KeyCodes.KEY_F5, 6: KeyCodes.KEY_F6, 7: KeyCodes.KEY_F7, 8: KeyCodes.KEY_F8,
    9: KeyCodes.KEY_F9, 10: KeyCodes.KEY_F10, 11: KeyCodes.KEY_F11, 12: KeyCodes.KEY_F12,
}

# Keys that indicate a real keyboard (not a mouse/gamepad)
KEYBOARD_INDICATOR_KEYS = set(range(KeyCodes.KEY_A, KeyCodes.KEY_Z + 1))

# Mapping file location
MAPPING_FILE = Path("/etc/purple/keyboard-map.json")

# Keys that can be double-tapped for shifted version (letters, numbers, punctuation)
DOUBLE_TAP_KEYS = set(range(2, 14)) | set(range(16, 26)) | set(range(30, 39)) | set(range(44, 53)) | {40, 41, 43}
# 2-13: 1-9,0,-,=  |  16-25: qwertyuiop  |  30-38: asdfghjkl  |  44-52: zxcvbnm,./  |  40,41,43: '`\

# =============================================================================
# Scancode Mapping
# =============================================================================

def load_scancode_map() -> dict[int, int]:
    """Load calibrated scancode→keycode mapping from disk."""
    if MAPPING_FILE.exists():
        try:
            data = json.loads(MAPPING_FILE.read_text())
            # Convert string keys back to ints (JSON limitation)
            return {int(k): v for k, v in data.get("scancodes", {}).items()}
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    return {}

def save_scancode_map(mapping: dict[int, int]) -> bool:
    """Save scancode→keycode mapping to disk."""
    try:
        MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"scancodes": {str(k): v for k, v in mapping.items()}}
        MAPPING_FILE.write_text(json.dumps(data, indent=2))
        return True
    except OSError:
        return False

# =============================================================================
# Event Processor (pure logic, no I/O)
# =============================================================================

class KeyEventProcessor:
    """
    Processes keyboard events with scancode-based F-key remapping.

    Also handles:
    - Sticky shift (tap shift key = shift next character)
    - Double-tap shift (tap same key twice = shifted version)
    - Long-press Escape (1s) → F24 (parent mode signal)
    - Caps lock tracking
    """

    SHIFT_TAP_THRESHOLD = 0.3      # Max seconds for shift "tap"
    DOUBLE_TAP_THRESHOLD = 0.4     # Max seconds between taps for double-tap
    ESCAPE_HOLD_THRESHOLD = 1.0    # Seconds to hold Escape for parent mode

    def __init__(self, scancode_map: dict[int, int] = None):
        self.scancode_map = scancode_map or {}

        # Scancode tracking (MSC_SCAN arrives before EV_KEY)
        self._pending_scancode: Optional[int] = None

        # Shift state
        self.sticky_shift = False
        self.caps_lock = False
        self._shift_press_time = 0.0
        self._shift_key_held: Optional[int] = None
        self._key_during_shift = False

        # Double-tap detection (uses shared DoubleTapDetector if available)
        if DoubleTapDetector is not None:
            self._double_tap = DoubleTapDetector(
                threshold=self.DOUBLE_TAP_THRESHOLD,
                allowed_keys=DOUBLE_TAP_KEYS,
            )
        else:
            self._double_tap = None
        self._double_tap_shift_held: bool = False  # True if we injected shift for double-tap

        # Escape long-press
        self._escape_press_time = 0.0
        self._escape_pending = False
        self._escape_fired = False

    def process_event(self, ev_type: int, code: int, value: int,
                      timestamp: float = None) -> list[tuple[int, int, int]]:
        """Process input event, return output events to emit."""
        timestamp = time.time() if timestamp is None else timestamp

        # Capture scancode (arrives before the key event)
        if ev_type == KeyCodes.EV_MSC and code == KeyCodes.MSC_SCAN:
            self._pending_scancode = value
            return []

        # Pass through non-key events
        if ev_type != KeyCodes.EV_KEY:
            return [(ev_type, code, value)]

        # Use scancode to remap if available
        scancode = self._pending_scancode
        self._pending_scancode = None

        if scancode and scancode in self.scancode_map:
            code = self.scancode_map[scancode]

        # Handle special keys
        if code in (KeyCodes.KEY_LEFTSHIFT, KeyCodes.KEY_RIGHTSHIFT):
            return self._handle_shift(code, value, timestamp)

        if code == KeyCodes.KEY_ESC:
            return self._handle_escape(value, timestamp)

        if code == KeyCodes.KEY_CAPSLOCK and value == 1:
            self.caps_lock = not self.caps_lock

        # Track key press during shift hold
        if self._shift_key_held and value == 1:
            self._key_during_shift = True

        # Double-tap detection: tap same key twice quickly = shifted version
        if code in DOUBLE_TAP_KEYS:
            if value == 1:  # Key press
                is_double_tap = self._check_double_tap(code, timestamp)
                if is_double_tap:
                    self._double_tap_shift_held = True
                    # Backspace to delete first char, then emit shifted version
                    return [
                        (KeyCodes.EV_KEY, KeyCodes.KEY_BACKSPACE, 1),
                        (KeyCodes.EV_KEY, KeyCodes.KEY_BACKSPACE, 0),
                        (KeyCodes.EV_KEY, KeyCodes.KEY_LEFTSHIFT, 1),
                        (KeyCodes.EV_KEY, code, 1),
                    ]

            elif value == 0 and self._double_tap_shift_held:
                # Key release after double-tap: release shift too
                self._double_tap_shift_held = False
                return [
                    (KeyCodes.EV_KEY, code, 0),
                    (KeyCodes.EV_KEY, KeyCodes.KEY_LEFTSHIFT, 0),
                ]

        return [(KeyCodes.EV_KEY, code, value)]

    def _check_double_tap(self, code: int, timestamp: float) -> bool:
        """
        Check if this keycode completes a double-tap.

        Uses shared DoubleTapDetector if available, otherwise inline fallback.
        """
        if self._double_tap is not None:
            return self._double_tap.check(code, timestamp)

        # Fallback: inline implementation for standalone operation
        if not hasattr(self, '_last_key'):
            self._last_key = None
            self._last_key_time = 0.0

        if self._last_key == code and (timestamp - self._last_key_time) < self.DOUBLE_TAP_THRESHOLD:
            self._last_key = None  # Reset to prevent triple-tap
            return True

        self._last_key = code
        self._last_key_time = timestamp
        return False

    def _handle_shift(self, code: int, value: int, ts: float) -> list[tuple[int, int, int]]:
        """Tap shift = sticky shift, hold shift = normal."""
        out = [(KeyCodes.EV_KEY, code, value)]

        if value == 1:  # Press
            self._shift_press_time = ts
            self._shift_key_held = code
            self._key_during_shift = False
        elif value == 0 and self._shift_key_held == code:  # Release
            if (ts - self._shift_press_time) < self.SHIFT_TAP_THRESHOLD and not self._key_during_shift:
                self.sticky_shift = not self.sticky_shift
            self._shift_key_held = None

        return out

    def _handle_escape(self, value: int, ts: float) -> list[tuple[int, int, int]]:
        """Hold Escape 1s = F24 (parent mode), tap = normal Escape."""
        if value == 1:  # Press
            self._escape_press_time = ts
            self._escape_pending = True
            self._escape_fired = False
            return []  # Buffer until we know tap vs hold

        if value == 0:  # Release
            if self._escape_fired:
                result = []
            elif self._escape_pending:
                # Was a tap - emit buffered Escape
                result = [(KeyCodes.EV_KEY, KeyCodes.KEY_ESC, 1),
                          (KeyCodes.EV_KEY, KeyCodes.KEY_ESC, 0)]
            else:
                result = []
            self._escape_pending = False
            self._escape_fired = False
            return result

        if value == 2:  # Repeat - check for long-press
            return self._check_escape_long_press(ts)

        return []

    def _check_escape_long_press(self, ts: float) -> list[tuple[int, int, int]]:
        """Check if Escape held long enough for parent mode."""
        if self._escape_pending and not self._escape_fired:
            if (ts - self._escape_press_time) >= self.ESCAPE_HOLD_THRESHOLD:
                self._escape_fired = True
                self._escape_pending = False
                return [(KeyCodes.EV_KEY, KeyCodes.KEY_F24, 1),
                        (KeyCodes.EV_KEY, KeyCodes.KEY_F24, 0)]
        return []

    def check_pending(self, ts: float = None) -> list[tuple[int, int, int]]:
        """Check for pending timed events (call periodically)."""
        return self._check_escape_long_press(time.time() if ts is None else ts)


# =============================================================================
# Keyboard Normalizer (I/O layer)
# =============================================================================

try:
    import evdev
    from evdev import InputDevice, UInput, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    evdev = ecodes = InputDevice = UInput = None


class KeyboardNormalizer:
    """
    Grabs hardware keyboard, remaps keys via scancodes, emits to virtual keyboard.
    """

    def __init__(self, grab: bool = True):
        if not EVDEV_AVAILABLE:
            raise RuntimeError("evdev not available - requires Linux with python-evdev")

        self.grab = grab
        self._running = False
        self.hw_device: Optional[InputDevice] = None
        self.virtual_device: Optional[UInput] = None

        self._find_keyboard()
        self._create_virtual_keyboard()

        scancode_map = load_scancode_map()
        self._processor = KeyEventProcessor(scancode_map)

    def _find_keyboard(self) -> None:
        """Find first real hardware keyboard."""
        for path in sorted(evdev.list_devices()):
            try:
                dev = InputDevice(path)
                if 'virtual' in dev.name.lower() or 'normalizer' in dev.name.lower():
                    continue
                caps = dev.capabilities().get(ecodes.EV_KEY, [])
                if set(caps) & KEYBOARD_INDICATOR_KEYS:
                    self.hw_device = dev
                    return
            except (PermissionError, OSError):
                continue
        raise RuntimeError("No keyboard found. Need root or 'input' group membership.")

    def _create_virtual_keyboard(self) -> None:
        """Create virtual keyboard with F-key support."""
        caps = list(self.hw_device.capabilities().get(ecodes.EV_KEY, []))
        # Ensure we can emit F1-F12 and F24
        for fkey in list(TARGET_FKEYS.values()) + [KeyCodes.KEY_F24]:
            if fkey not in caps:
                caps.append(fkey)
        self.virtual_device = UInput({ecodes.EV_KEY: caps}, name="Purple Keyboard Normalizer")

    def run(self) -> None:
        """Main event loop. Blocks until stop() or interrupt."""
        import select

        self._running = True
        try:
            if self.grab:
                self.hw_device.grab()

            while self._running:
                readable, _, _ = select.select([self.hw_device.fd], [], [], 0.1)

                if readable:
                    for event in self.hw_device.read():
                        for ev in self._processor.process_event(event.type, event.code, event.value):
                            self.virtual_device.write(*ev)
                            self.virtual_device.syn()

                # Check pending (Escape long-press)
                for ev in self._processor.check_pending():
                    self.virtual_device.write(*ev)
                    self.virtual_device.syn()

        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        if self.hw_device:
            try:
                if self.grab:
                    self.hw_device.ungrab()
            except OSError:
                pass
            self.hw_device.close()
            self.hw_device = None
        if self.virtual_device:
            self.virtual_device.close()
            self.virtual_device = None


# =============================================================================
# Calibration Mode
# =============================================================================

def calibrate() -> bool:
    """
    Interactive calibration: prompts user to press F1, F2, F3, F4, F12.
    Captures scancodes and saves mapping.

    Returns True if successful.
    """
    if not EVDEV_AVAILABLE:
        print("evdev not available")
        return False

    print("Purple Computer Keyboard Setup")
    print("=" * 40)
    print()
    print("Let's set up your keyboard!")
    print()
    print("Press each key when asked. Don't worry about")
    print("holding any extra keys. Just press the key shown.")
    print()

    # Find keyboard
    hw_device = None
    for path in sorted(evdev.list_devices()):
        try:
            dev = InputDevice(path)
            if 'virtual' in dev.name.lower():
                continue
            caps = dev.capabilities().get(ecodes.EV_KEY, [])
            if set(caps) & KEYBOARD_INDICATOR_KEYS:
                hw_device = dev
                break
        except (PermissionError, OSError):
            continue

    if not hw_device:
        print("ERROR: No keyboard found. Need root or 'input' group.")
        return False

    print(f"Using keyboard: {hw_device.name}")
    print()

    mapping = {}
    keys_to_calibrate = [(i, f"F{i}") for i in range(1, 13)]

    try:
        hw_device.grab()

        for fnum, fname in keys_to_calibrate:
            print(f"Press {fname}... ", end="", flush=True)

            scancode = None
            while scancode is None:
                for event in hw_device.read():
                    if event.type == ecodes.EV_MSC and event.code == ecodes.MSC_SCAN:
                        scancode = event.value
                    elif event.type == ecodes.EV_KEY and event.value == 0:
                        # Key released - done with this one
                        break
                if scancode:
                    break

            if scancode:
                mapping[scancode] = TARGET_FKEYS[fnum]
                print("OK!")
            else:
                print("(no response)")

        hw_device.ungrab()

    except KeyboardInterrupt:
        print("\nCalibration cancelled.")
        try:
            hw_device.ungrab()
        except:
            pass
        return False
    finally:
        hw_device.close()

    # Save mapping
    print()
    if save_scancode_map(mapping):
        print("Keyboard setup complete!")
        print("Restart Purple Computer to use the new settings.")
        return True
    else:
        print("Could not save settings.")
        print("Try running with: sudo python3 keyboard_normalizer.py --calibrate")
        return False


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    if not EVDEV_AVAILABLE:
        print("evdev not available - requires Linux")
        print("Install with: pip install evdev")
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        sys.exit(0 if calibrate() else 1)

    # Normal operation
    print("Purple Keyboard Normalizer")
    print("=" * 40)

    try:
        mapping = load_scancode_map()
        if mapping:
            print(f"Loaded keyboard settings ({len(mapping)} keys)")
        else:
            print("No keyboard setup found. F-keys may not work correctly.")
            print("Run with --calibrate to set up your keyboard.")
        print()

        normalizer = KeyboardNormalizer(grab=True)
        print(f"Keyboard: {normalizer.hw_device.name}")
        print("Running... (Ctrl+C to exit)")
        normalizer.run()

    except PermissionError:
        print("Permission denied. Run as root or add user to 'input' group:")
        print("  sudo usermod -a -G input $USER")
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
