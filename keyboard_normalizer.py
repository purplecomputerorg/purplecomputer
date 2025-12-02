"""
Unified keyboard-input normalization layer for Linux.

Uses evdev to read hardware keyboard events and uinput to emit normalized
events through a virtual keyboard. Provides:
- Extra keys (media keys, OEM keys) remapped to F1-F12
- Sticky shift toggle (left meta key)
- Caps lock tracking
- Automatic shift injection for uppercase letters
"""

import sys
from typing import Optional


# Key codes (matching Linux input-event-codes.h)
# These are platform-independent constants used by the event processor
class KeyCodes:
    """Linux key codes for keyboard events."""
    # Event types
    EV_SYN = 0
    EV_KEY = 1

    # Letters A-Z
    KEY_A = 30
    KEY_B = 48
    KEY_C = 46
    KEY_D = 32
    KEY_E = 18
    KEY_F = 33
    KEY_G = 34
    KEY_H = 35
    KEY_I = 23
    KEY_J = 36
    KEY_K = 37
    KEY_L = 38
    KEY_M = 50
    KEY_N = 49
    KEY_O = 24
    KEY_P = 25
    KEY_Q = 16
    KEY_R = 19
    KEY_S = 31
    KEY_T = 20
    KEY_U = 22
    KEY_V = 47
    KEY_W = 17
    KEY_X = 45
    KEY_Y = 21
    KEY_Z = 44

    # Digits 0-9
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

    # Modifiers
    KEY_LEFTSHIFT = 42
    KEY_RIGHTSHIFT = 54
    KEY_LEFTCTRL = 29
    KEY_RIGHTCTRL = 97
    KEY_LEFTALT = 56
    KEY_RIGHTALT = 100
    KEY_LEFTMETA = 125
    KEY_RIGHTMETA = 126
    KEY_CAPSLOCK = 58

    # Navigation
    KEY_UP = 103
    KEY_DOWN = 108
    KEY_LEFT = 105
    KEY_RIGHT = 106
    KEY_HOME = 102
    KEY_END = 107
    KEY_PAGEUP = 104
    KEY_PAGEDOWN = 109
    KEY_INSERT = 110
    KEY_DELETE = 111

    # Common keys
    KEY_ESC = 1
    KEY_BACKSPACE = 14
    KEY_TAB = 15
    KEY_ENTER = 28
    KEY_SPACE = 57

    # Function keys F1-F12
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

    # Extended function keys
    KEY_F13 = 183
    KEY_F14 = 184
    KEY_F15 = 185
    KEY_F16 = 186
    KEY_F17 = 187
    KEY_F18 = 188
    KEY_F19 = 189
    KEY_F20 = 190
    KEY_F21 = 191
    KEY_F22 = 192
    KEY_F23 = 193
    KEY_F24 = 194

    # Punctuation
    KEY_MINUS = 12
    KEY_EQUAL = 13
    KEY_LEFTBRACE = 26
    KEY_RIGHTBRACE = 27
    KEY_SEMICOLON = 39
    KEY_APOSTROPHE = 40
    KEY_GRAVE = 41
    KEY_BACKSLASH = 43
    KEY_COMMA = 51
    KEY_DOT = 52
    KEY_SLASH = 53

    # Numpad
    KEY_NUMLOCK = 69
    KEY_SCROLLLOCK = 70
    KEY_KP7 = 71
    KEY_KP8 = 72
    KEY_KP9 = 73
    KEY_KPMINUS = 74
    KEY_KP4 = 75
    KEY_KP5 = 76
    KEY_KP6 = 77
    KEY_KPPLUS = 78
    KEY_KP1 = 79
    KEY_KP2 = 80
    KEY_KP3 = 81
    KEY_KP0 = 82
    KEY_KPDOT = 83
    KEY_KPENTER = 96
    KEY_KPSLASH = 98
    KEY_KPASTERISK = 55

    # System
    KEY_SYSRQ = 99
    KEY_PAUSE = 119


# Build key code sets from KeyCodes class
LETTER_KEY_CODES = {
    KeyCodes.KEY_A, KeyCodes.KEY_B, KeyCodes.KEY_C, KeyCodes.KEY_D, KeyCodes.KEY_E,
    KeyCodes.KEY_F, KeyCodes.KEY_G, KeyCodes.KEY_H, KeyCodes.KEY_I, KeyCodes.KEY_J,
    KeyCodes.KEY_K, KeyCodes.KEY_L, KeyCodes.KEY_M, KeyCodes.KEY_N, KeyCodes.KEY_O,
    KeyCodes.KEY_P, KeyCodes.KEY_Q, KeyCodes.KEY_R, KeyCodes.KEY_S, KeyCodes.KEY_T,
    KeyCodes.KEY_U, KeyCodes.KEY_V, KeyCodes.KEY_W, KeyCodes.KEY_X, KeyCodes.KEY_Y,
    KeyCodes.KEY_Z,
}

F_KEY_CODES = [
    KeyCodes.KEY_F1, KeyCodes.KEY_F2, KeyCodes.KEY_F3, KeyCodes.KEY_F4,
    KeyCodes.KEY_F5, KeyCodes.KEY_F6, KeyCodes.KEY_F7, KeyCodes.KEY_F8,
    KeyCodes.KEY_F9, KeyCodes.KEY_F10, KeyCodes.KEY_F11, KeyCodes.KEY_F12,
]

# "Normal" keys that should NOT be remapped to F-keys
NORMAL_KEY_CODES = (
    LETTER_KEY_CODES |
    {KeyCodes.KEY_0, KeyCodes.KEY_1, KeyCodes.KEY_2, KeyCodes.KEY_3, KeyCodes.KEY_4,
     KeyCodes.KEY_5, KeyCodes.KEY_6, KeyCodes.KEY_7, KeyCodes.KEY_8, KeyCodes.KEY_9} |
    {KeyCodes.KEY_UP, KeyCodes.KEY_DOWN, KeyCodes.KEY_LEFT, KeyCodes.KEY_RIGHT} |
    {KeyCodes.KEY_LEFTSHIFT, KeyCodes.KEY_RIGHTSHIFT, KeyCodes.KEY_LEFTCTRL,
     KeyCodes.KEY_RIGHTCTRL, KeyCodes.KEY_LEFTALT, KeyCodes.KEY_RIGHTALT,
     KeyCodes.KEY_LEFTMETA, KeyCodes.KEY_RIGHTMETA, KeyCodes.KEY_CAPSLOCK} |
    {KeyCodes.KEY_SPACE, KeyCodes.KEY_ENTER, KeyCodes.KEY_TAB,
     KeyCodes.KEY_ESC, KeyCodes.KEY_BACKSPACE} |
    set(F_KEY_CODES) |
    {KeyCodes.KEY_F13, KeyCodes.KEY_F14, KeyCodes.KEY_F15, KeyCodes.KEY_F16,
     KeyCodes.KEY_F17, KeyCodes.KEY_F18, KeyCodes.KEY_F19, KeyCodes.KEY_F20,
     KeyCodes.KEY_F21, KeyCodes.KEY_F22, KeyCodes.KEY_F23, KeyCodes.KEY_F24} |
    {KeyCodes.KEY_MINUS, KeyCodes.KEY_EQUAL, KeyCodes.KEY_LEFTBRACE,
     KeyCodes.KEY_RIGHTBRACE, KeyCodes.KEY_SEMICOLON, KeyCodes.KEY_APOSTROPHE,
     KeyCodes.KEY_GRAVE, KeyCodes.KEY_BACKSLASH, KeyCodes.KEY_COMMA,
     KeyCodes.KEY_DOT, KeyCodes.KEY_SLASH} |
    {KeyCodes.KEY_HOME, KeyCodes.KEY_END, KeyCodes.KEY_PAGEUP, KeyCodes.KEY_PAGEDOWN,
     KeyCodes.KEY_INSERT, KeyCodes.KEY_DELETE} |
    {KeyCodes.KEY_KP0, KeyCodes.KEY_KP1, KeyCodes.KEY_KP2, KeyCodes.KEY_KP3,
     KeyCodes.KEY_KP4, KeyCodes.KEY_KP5, KeyCodes.KEY_KP6, KeyCodes.KEY_KP7,
     KeyCodes.KEY_KP8, KeyCodes.KEY_KP9, KeyCodes.KEY_KPASTERISK, KeyCodes.KEY_KPMINUS,
     KeyCodes.KEY_KPPLUS, KeyCodes.KEY_KPDOT, KeyCodes.KEY_KPENTER, KeyCodes.KEY_KPSLASH,
     KeyCodes.KEY_NUMLOCK, KeyCodes.KEY_SCROLLLOCK} |
    {KeyCodes.KEY_SYSRQ, KeyCodes.KEY_PAUSE}
)


# Check if we're on Linux with evdev available
try:
    import evdev
    from evdev import ecodes, InputDevice, UInput
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    evdev = None
    ecodes = None


class KeyEventProcessor:
    """
    Pure logic for processing keyboard events. No I/O dependencies.

    This class handles:
    - Sticky shift toggle
    - Caps lock tracking
    - Extra key remapping to F1-F12
    - Shift injection for uppercase letters
    - Key held state tracking

    Use process_event() to transform input events into output events.
    """

    def __init__(
        self,
        extra_key_map: dict[int, int],
        sticky_shift_key: int = KeyCodes.KEY_LEFTMETA,
        caps_lock_key: int = KeyCodes.KEY_CAPSLOCK,
    ):
        """
        Initialize the event processor.

        Args:
            extra_key_map: Mapping of extra key codes to F1-F12 codes
            sticky_shift_key: Key code that toggles sticky shift
            caps_lock_key: Key code for caps lock
        """
        self.extra_key_map = extra_key_map
        self.sticky_shift_key = sticky_shift_key
        self.caps_lock_key = caps_lock_key

        # State
        self.sticky_shift: bool = False
        self.caps_lock: bool = False
        self.held_keys: dict[int, bool] = {}
        self.injected_shift: bool = False

    def process_event(
        self, event_type: int, code: int, value: int
    ) -> list[tuple[int, int, int]]:
        """
        Process an input event and return output events to emit.

        Args:
            event_type: Event type (EV_KEY, EV_SYN, etc.)
            code: Key code
            value: 0=up, 1=down, 2=repeat

        Returns:
            List of (event_type, code, value) tuples to emit
        """
        # Non-key events pass through unchanged
        if event_type != KeyCodes.EV_KEY:
            return [(event_type, code, value)]

        output: list[tuple[int, int, int]] = []

        # Track key held state
        if value == 1:
            self.held_keys[code] = True
        elif value == 0:
            self.held_keys.pop(code, None)

        # Handle sticky shift toggle (on key down only)
        if code == self.sticky_shift_key and value == 1:
            self.sticky_shift = not self.sticky_shift
            # Don't forward the sticky shift key itself
            return []

        # Handle caps lock toggle (on key down only)
        if code == self.caps_lock_key and value == 1:
            self.caps_lock = not self.caps_lock
            # Forward the caps lock key
            output.append((KeyCodes.EV_KEY, code, value))
            return output

        # Remap extra keys to F1-F12
        if code in self.extra_key_map:
            code = self.extra_key_map[code]

        # Handle letter keys with sticky shift / caps lock
        if code in LETTER_KEY_CODES:
            # Determine if we should uppercase: caps_lock XOR sticky_shift
            should_uppercase = self.caps_lock != self.sticky_shift

            # Check if physical shift is held
            physical_shift_held = (
                self.held_keys.get(KeyCodes.KEY_LEFTSHIFT, False) or
                self.held_keys.get(KeyCodes.KEY_RIGHTSHIFT, False)
            )

            # XOR with physical shift: if shift is held, invert the case
            should_uppercase = should_uppercase != physical_shift_held

            if should_uppercase and not physical_shift_held:
                if value == 1:  # Key down
                    # Inject shift press before letter
                    output.append((KeyCodes.EV_KEY, KeyCodes.KEY_LEFTSHIFT, 1))
                    self.injected_shift = True
                    output.append((KeyCodes.EV_KEY, code, value))
                elif value == 0:  # Key up
                    output.append((KeyCodes.EV_KEY, code, value))
                    # Release injected shift after letter
                    if self.injected_shift:
                        output.append((KeyCodes.EV_KEY, KeyCodes.KEY_LEFTSHIFT, 0))
                        self.injected_shift = False
                else:  # Repeat
                    output.append((KeyCodes.EV_KEY, code, value))
            else:
                output.append((KeyCodes.EV_KEY, code, value))
        else:
            # Forward all other keys
            output.append((KeyCodes.EV_KEY, code, value))

        return output

    @property
    def state(self) -> dict:
        """Get current state for debugging."""
        return {
            'sticky_shift': self.sticky_shift,
            'caps_lock': self.caps_lock,
            'held_keys': list(self.held_keys.keys()),
            'injected_shift': self.injected_shift,
        }


def build_extra_key_map(available_keys: set[int]) -> dict[int, int]:
    """
    Build a mapping of extra keys to F1-F12.

    Args:
        available_keys: Set of key codes available on the device

    Returns:
        Dict mapping extra key codes to F1-F12 codes
    """
    extra_keys = sorted(available_keys - NORMAL_KEY_CODES)
    return {
        extra_key: F_KEY_CODES[i]
        for i, extra_key in enumerate(extra_keys[:12])
    }


class KeyboardNormalizer:
    """
    Normalizes keyboard input by:
    - Grabbing the hardware keyboard exclusively
    - Remapping extra keys (media, OEM) to F1-F12
    - Implementing sticky shift (toggle with left meta)
    - Tracking caps lock state
    - Injecting shift for uppercase letters
    - Emitting normalized events through a virtual keyboard

    This class handles I/O (evdev). The event processing logic is in KeyEventProcessor.
    """

    def __init__(self, sticky_shift_key: Optional[int] = None, grab: bool = True):
        """
        Initialize the keyboard normalizer.

        Args:
            sticky_shift_key: Key code to toggle sticky shift (default: KEY_LEFTMETA)
            grab: Whether to grab the hardware keyboard exclusively (default: True)
        """
        if not EVDEV_AVAILABLE:
            raise RuntimeError(
                "evdev is not available. This module requires Linux with "
                "python-evdev installed."
            )

        self.grab = grab

        # Device handles
        self.hw_device: Optional[InputDevice] = None
        self.virtual_device: Optional[UInput] = None

        # Initialize devices
        self._find_hardware_keyboard()
        extra_key_map = self._build_extra_key_map()
        self._create_virtual_keyboard()

        # Create event processor with the discovered extra key mapping
        self._processor = KeyEventProcessor(
            extra_key_map=extra_key_map,
            sticky_shift_key=sticky_shift_key or KeyCodes.KEY_LEFTMETA,
        )

    @staticmethod
    def _is_virtual_device(device: 'InputDevice') -> bool:
        """Check if a device is a virtual/uinput device."""
        name_lower = device.name.lower()
        virtual_indicators = ['uinput', 'virtual', 'py-evdev', 'python', 'normalizer']
        return any(indicator in name_lower for indicator in virtual_indicators)

    def _find_hardware_keyboard(self) -> None:
        """Find and open the first real hardware keyboard."""
        for path in sorted(evdev.list_devices()):
            try:
                device = InputDevice(path)
                capabilities = device.capabilities()

                if ecodes.EV_KEY not in capabilities:
                    continue
                if self._is_virtual_device(device):
                    continue

                key_caps = set(capabilities.get(ecodes.EV_KEY, []))
                if key_caps & LETTER_KEY_CODES:
                    self.hw_device = device
                    return

            except (PermissionError, OSError):
                continue

        raise RuntimeError(
            "No hardware keyboard found. Ensure you have read access to "
            "/dev/input/event* devices (usually requires root or input group)."
        )

    def _build_extra_key_map(self) -> dict[int, int]:
        """Build extra key mapping from hardware device capabilities."""
        if not self.hw_device:
            return {}
        capabilities = self.hw_device.capabilities()
        key_caps = set(capabilities.get(ecodes.EV_KEY, []))
        return build_extra_key_map(key_caps)

    def _create_virtual_keyboard(self) -> None:
        """Create a virtual keyboard using uinput."""
        if not self.hw_device:
            return

        capabilities = self.hw_device.capabilities()
        key_caps = list(capabilities.get(ecodes.EV_KEY, []))

        # Ensure we have F1-F12 and shift keys
        needed_keys = set(F_KEY_CODES) | {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
        for key in needed_keys:
            if key not in key_caps:
                key_caps.append(key)

        self.virtual_device = UInput(
            {ecodes.EV_KEY: key_caps},
            name="Purple Keyboard Normalizer",
        )

    def _handle_event(self, event) -> None:
        """Process an input event through the processor and emit results."""
        output_events = self._processor.process_event(event.type, event.code, event.value)
        for ev_type, code, value in output_events:
            if self.virtual_device:
                self.virtual_device.write(ev_type, code, value)
                self.virtual_device.syn()

    def run(self) -> None:
        """
        Start the event loop. Reads from hardware keyboard and emits
        normalized events to the virtual keyboard.

        This method blocks indefinitely until interrupted.
        """
        if not self.hw_device:
            raise RuntimeError("No hardware keyboard device available")

        try:
            # Optionally grab the device exclusively
            if self.grab:
                self.hw_device.grab()

            # Event loop
            for event in self.hw_device.read_loop():
                self._handle_event(event)

        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def close(self) -> None:
        """Clean up resources."""
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

    def get_extra_key_mappings(self) -> dict[int, tuple[int, str, str]]:
        """
        Get the extra key mappings for debugging/display.

        Returns:
            Dict mapping extra key code to (F key code, extra key name, F key name)
        """
        result = {}
        for extra_code, f_code in self._processor.extra_key_map.items():
            extra_name = ecodes.KEY.get(extra_code, f"KEY_{extra_code}")
            f_name = ecodes.KEY.get(f_code, f"KEY_{f_code}")
            result[extra_code] = (f_code, extra_name, f_name)
        return result

    @property
    def state(self) -> dict:
        """Get current state for debugging."""
        return self._processor.state

    @property
    def extra_key_map(self) -> dict[int, int]:
        """Get the extra key mapping."""
        return self._processor.extra_key_map


# Debug/test entrypoint for development on Mac or Linux without root
if __name__ == "__main__":
    if not EVDEV_AVAILABLE:
        print("evdev not available - this module requires Linux")
        print()
        print("On Linux, install with: pip install evdev")
        print()
        print("Module structure:")
        print("  KeyboardNormalizer - Main class")
        print("    .run()           - Start event loop")
        print("    .close()         - Clean up resources")
        print("    .state           - Current state dict")
        print("    .sticky_shift    - Sticky shift enabled")
        print("    .caps_lock       - Caps lock enabled")
        print("    .extra_key_map   - Extra key -> F key mapping")
        print()
        print("Example usage:")
        print("  normalizer = KeyboardNormalizer()")
        print("  print(normalizer.get_extra_key_mappings())")
        print("  normalizer.run()  # Blocks until Ctrl+C")
        sys.exit(0)

    # On Linux, try to run
    print("Purple Keyboard Normalizer")
    print("=" * 40)

    try:
        normalizer = KeyboardNormalizer(grab=False)  # Don't grab for testing

        print(f"Hardware keyboard: {normalizer.hw_device.name}")
        print(f"Hardware path: {normalizer.hw_device.path}")
        print(f"Virtual keyboard: {normalizer.virtual_device.name}")
        print()
        print("Extra key mappings:")
        for extra_code, (f_code, extra_name, f_name) in normalizer.get_extra_key_mappings().items():
            print(f"  {extra_name} -> {f_name}")
        print()
        print("Controls:")
        print(f"  Left Meta: Toggle sticky shift")
        print(f"  Caps Lock: Toggle caps lock")
        print()
        print("Starting event loop (Ctrl+C to exit)...")
        print("Note: Running with grab=False for testing, events go to both")
        print("the virtual device AND normal system input.")
        print()

        normalizer.run()

    except PermissionError:
        print("Permission denied. Run as root or add user to 'input' group:")
        print("  sudo usermod -a -G input $USER")
        print("Then log out and back in.")
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
