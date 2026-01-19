"""
Keyboard F-Key Calibration for Purple Computer.

This tool is used ONLY for calibrating F-key scancodes on new keyboards.
The calibration maps physical F-row keys to logical F1-F12 using scancodes
(MSC_SCAN), which identify physical keys regardless of Fn Lock state.

Usage:
    python keyboard_normalizer.py --calibrate

The mapping is saved to ~/.config/purple/keyboard-map.json and loaded
by the main Purple Computer app (purple_tui) when it starts.

NOTE: The runtime keyboard processing has moved to purple_tui/input.py
which reads evdev directly, bypassing the terminal. This file is kept
only for calibration mode. See guides/keyboard-architecture.md.
"""

import json
import sys
from pathlib import Path

try:
    from purple_tui.constants import SUPPORT_EMAIL
except ImportError:
    SUPPORT_EMAIL = "support@purplecomputer.org"

# =============================================================================
# Constants (matching Linux input-event-codes.h)
# =============================================================================

class KeyCodes:
    """Linux input event codes for F-keys."""
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

    # Letters (for keyboard detection)
    KEY_A, KEY_Z = 30, 44

    # Common non-F-keys (for rejection during calibration)
    KEY_ESC = 1
    KEY_TAB = 15
    KEY_ENTER = 28
    KEY_BACKSPACE = 14
    KEY_SPACE = 57
    KEY_CAPSLOCK = 58
    KEY_LEFTSHIFT = 42
    KEY_RIGHTSHIFT = 54
    KEY_LEFTCTRL = 29
    KEY_RIGHTCTRL = 97
    KEY_LEFTALT = 56
    KEY_RIGHTALT = 100
    KEY_LEFTMETA = 125  # Windows/Super key
    KEY_RIGHTMETA = 126


# Keys that are definitely NOT F-keys (reject during calibration)
# This uses a subtractive approach: reject known non-F-keys rather than
# trying to enumerate all possible F-key scancodes across keyboards.
REJECT_KEYCODES = {
    # Escape, Tab, Enter, Backspace, Space
    KeyCodes.KEY_ESC, KeyCodes.KEY_TAB, KeyCodes.KEY_ENTER,
    KeyCodes.KEY_BACKSPACE, KeyCodes.KEY_SPACE, KeyCodes.KEY_CAPSLOCK,
    # Number row (1-9, 0, minus, equals)
    2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
    # Letter keys (Q-P row: 16-25, A-L row: 30-38, Z-M row: 44-50)
    *range(16, 26), *range(30, 39), *range(44, 51),
    # Punctuation around letters
    26, 27,  # [ ]
    39, 40, 41,  # ; ' `
    43,  # backslash
    51, 52, 53,  # , . /
    # Modifier keys
    KeyCodes.KEY_LEFTSHIFT, KeyCodes.KEY_RIGHTSHIFT,
    KeyCodes.KEY_LEFTCTRL, KeyCodes.KEY_RIGHTCTRL,
    KeyCodes.KEY_LEFTALT, KeyCodes.KEY_RIGHTALT,
    KeyCodes.KEY_LEFTMETA, KeyCodes.KEY_RIGHTMETA,
    # Arrow keys
    103, 105, 106, 108,  # up, left, right, down
    # Other common keys
    110, 111,  # Insert, Delete
    102, 107,  # Home, End
    104, 109,  # Page Up, Page Down
    119,  # Pause
    70,  # Scroll Lock
    99,  # Print Screen
}

# Friendly names for common rejected keys
KEYCODE_NAMES = {
    KeyCodes.KEY_ESC: "Escape",
    KeyCodes.KEY_TAB: "Tab",
    KeyCodes.KEY_ENTER: "Enter",
    KeyCodes.KEY_BACKSPACE: "Backspace",
    KeyCodes.KEY_SPACE: "Space",
    KeyCodes.KEY_CAPSLOCK: "Caps Lock",
    KeyCodes.KEY_LEFTSHIFT: "Shift",
    KeyCodes.KEY_RIGHTSHIFT: "Shift",
    KeyCodes.KEY_LEFTCTRL: "Ctrl",
    KeyCodes.KEY_RIGHTCTRL: "Ctrl",
    KeyCodes.KEY_LEFTALT: "Alt",
    KeyCodes.KEY_RIGHTALT: "Alt",
    KeyCodes.KEY_LEFTMETA: "Windows/Super",
    KeyCodes.KEY_RIGHTMETA: "Windows/Super",
    103: "Up Arrow", 105: "Left Arrow", 106: "Right Arrow", 108: "Down Arrow",
    110: "Insert", 111: "Delete", 102: "Home", 107: "End",
    104: "Page Up", 109: "Page Down",
}

# Add letter names
for i, letter in enumerate("QWERTYUIOP"):
    KEYCODE_NAMES[16 + i] = letter
for i, letter in enumerate("ASDFGHJKL"):
    KEYCODE_NAMES[30 + i] = letter
for i, letter in enumerate("ZXCVBNM"):
    KEYCODE_NAMES[44 + i] = letter
# Add number names
for i in range(1, 10):
    KEYCODE_NAMES[i + 1] = str(i)
KEYCODE_NAMES[11] = "0"


# F-keys we care about remapping (all 12)
TARGET_FKEYS = {
    1: KeyCodes.KEY_F1, 2: KeyCodes.KEY_F2, 3: KeyCodes.KEY_F3, 4: KeyCodes.KEY_F4,
    5: KeyCodes.KEY_F5, 6: KeyCodes.KEY_F6, 7: KeyCodes.KEY_F7, 8: KeyCodes.KEY_F8,
    9: KeyCodes.KEY_F9, 10: KeyCodes.KEY_F10, 11: KeyCodes.KEY_F11, 12: KeyCodes.KEY_F12,
}

# Keys that indicate a real keyboard (not a mouse/gamepad)
KEYBOARD_INDICATOR_KEYS = set(range(KeyCodes.KEY_A, KeyCodes.KEY_Z + 1))

# Mapping file location (user-writable, no sudo needed)
MAPPING_FILE = Path.home() / ".config" / "purple" / "keyboard-map.json"


# =============================================================================
# Scancode Mapping I/O
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
# Calibration Mode
# =============================================================================

try:
    import evdev
    from evdev import InputDevice, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    evdev = ecodes = InputDevice = None


def calibrate(debug: bool = False) -> bool:
    """
    Interactive calibration: prompts user to press F1-F12.
    Captures scancodes and saves mapping.

    Args:
        debug: If True, show raw event data for troubleshooting.

    Returns True if successful.
    """
    import select

    if not EVDEV_AVAILABLE:
        print("evdev not available")
        return False

    print("Purple Computer Keyboard Setup")
    print("=" * 40)
    print()
    if debug:
        print("[Debug mode enabled]")
        print()
    print("Let's set up your keyboard!")
    print()
    print("Press each key when asked.")
    print("Just press and release the key shown.")
    print()
    print("If a key doesn't work (captured by your system), just press Space to skip it.")
    print()

    # Find keyboard - prefer /dev/input/by-id (stable, works in VMs)
    hw_device = None
    by_id = Path("/dev/input/by-id")
    if by_id.exists():
        for path in sorted(by_id.iterdir()):
            name = path.name.lower()
            if "kbd" in name or "keyboard" in name:
                try:
                    dev = InputDevice(str(path.resolve()))
                    caps = dev.capabilities().get(ecodes.EV_KEY, [])
                    if set(caps) & KEYBOARD_INDICATOR_KEYS:
                        hw_device = dev
                        break
                except (PermissionError, OSError):
                    continue

    # Fall back to scanning all devices
    if not hw_device:
        for path in sorted(evdev.list_devices()):
            try:
                dev = InputDevice(path)
                # Check for letter keys (indicates a real keyboard)
                caps = dev.capabilities().get(ecodes.EV_KEY, [])
                if set(caps) & KEYBOARD_INDICATOR_KEYS:
                    hw_device = dev
                    break
            except (PermissionError, OSError):
                continue

    if not hw_device:
        print("Could not find your keyboard.")
        print("Please make sure a keyboard is connected and try again.")
        print()
        print(f"If this keeps happening, contact us at {SUPPORT_EMAIL}")
        print()
        print("(Technical: no keyboard in /dev/input or permission denied)")
        return False

    print(f"Using keyboard: {hw_device.name}")
    if debug:
        print(f"  Device path: {hw_device.path}")
        print(f"  Phys: {hw_device.phys}")
        # Check if device reports MSC_SCAN
        msc_caps = hw_device.capabilities().get(ecodes.EV_MSC, [])
        has_msc_scan = ecodes.MSC_SCAN in msc_caps if msc_caps else False
        print(f"  Reports scancodes (MSC_SCAN): {'yes' if has_msc_scan else 'NO'}")
        if not has_msc_scan:
            print("  WARNING: This device may not report scancodes. Calibration may not work.")
    print()

    mapping = {}
    keys_to_calibrate = [(i, f"F{i}") for i in range(1, 13)]

    try:
        hw_device.grab()

        for fnum, fname in keys_to_calibrate:
            print(f"Press {fname}... ", end="", flush=True)

            scancode = None
            keycode = None
            key_released = False
            skipped = False

            while not key_released:
                # Use select to wait for events (avoids EAGAIN errors)
                readable, _, _ = select.select([hw_device.fd], [], [], 10.0)

                if not readable:
                    # Timeout waiting for key
                    print("(skipped, no response)")
                    skipped = True
                    break

                # Read available events
                try:
                    for event in hw_device.read():
                        if debug:
                            # Show all events for troubleshooting
                            type_name = ecodes.EV.get(event.type, event.type)
                            if event.type == ecodes.EV_KEY:
                                code_name = ecodes.KEY.get(event.code, event.code)
                                val_name = {0: "up", 1: "down", 2: "repeat"}.get(event.value, event.value)
                                print(f"  [event: {type_name} {code_name} {val_name}]")
                            elif event.type == ecodes.EV_MSC:
                                code_name = ecodes.MSC.get(event.code, event.code)
                                print(f"  [event: {type_name} {code_name} value={event.value} (0x{event.value:x})]")
                            elif event.type != ecodes.EV_SYN:  # Skip sync events
                                print(f"  [event: type={type_name} code={event.code} value={event.value}]")

                        if event.type == ecodes.EV_MSC and event.code == ecodes.MSC_SCAN:
                            scancode = event.value
                        elif event.type == ecodes.EV_KEY:
                            if event.value == 1:  # Key down
                                keycode = event.code
                            elif event.value == 0:  # Key released
                                key_released = True
                                break
                except BlockingIOError:
                    # Device returned EAGAIN, just continue waiting
                    continue

            if skipped:
                continue
            elif keycode in REJECT_KEYCODES:
                # User pressed a key that's definitely not an F-key
                key_name = KEYCODE_NAMES.get(keycode, f"key {keycode}")
                print(f"(you pressed {key_name}, skipping. {fname} may not work)")
                continue
            elif scancode:
                mapping[scancode] = TARGET_FKEYS[fnum]
                if debug:
                    print(f"OK! (scancode=0x{scancode:x}, keycode={keycode})")
                else:
                    print("OK!")
            elif key_released and keycode:
                # Key was pressed but no scancode (some keyboards don't report MSC_SCAN)
                # This is common on laptops where F-keys may go through different paths
                if debug:
                    key_name = ecodes.KEY.get(keycode, keycode) if ecodes else keycode
                    print(f"(no scancode, keycode={key_name}. {fname} may not work)")
                else:
                    print(f"(detected, but {fname} may not work without scancode)")
            elif key_released:
                # Key released but we got neither scancode nor keycode - very unusual
                if debug:
                    print("(key released but no scancode or keycode captured)")
                else:
                    print(f"(could not capture {fname})")

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

    # Check if we got any mappings
    if not mapping:
        print()
        print("Setup completed, but your keyboard may already work without")
        print("extra configuration. Try running Purple Computer normally.")
        print()
        print(f"If the F1, F2, F3 keys don't switch modes, contact us at {SUPPORT_EMAIL}")
        return True  # Not a failure, keyboard might work fine without remapping

    # Save mapping
    print()
    if save_scancode_map(mapping):
        print(f"Keyboard setup complete! ({len(mapping)} keys mapped)")
        print("Restart Purple Computer to use the new settings.")
        return True
    else:
        print("Could not save settings.")
        print("Check that ~/.config/purple/ is writable.")
        return False


# =============================================================================
# Main
# =============================================================================

def list_keyboard_devices():
    """List all keyboard-like devices for debugging."""
    print("Available keyboard devices:")
    print("=" * 60)
    print()

    found_any = False
    for path in sorted(evdev.list_devices()):
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            key_caps = caps.get(ecodes.EV_KEY, [])
            msc_caps = caps.get(ecodes.EV_MSC, [])

            # Check if it looks like a keyboard
            has_letters = bool(set(key_caps) & KEYBOARD_INDICATOR_KEYS)
            has_fkeys = bool(set(key_caps) & {59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 87, 88})
            has_msc_scan = ecodes.MSC_SCAN in msc_caps if msc_caps else False

            if has_letters or has_fkeys:
                found_any = True
                print(f"Device: {dev.name}")
                print(f"  Path: {path}")
                print(f"  Phys: {dev.phys}")
                print(f"  Has letter keys: {'yes' if has_letters else 'no'}")
                print(f"  Has F-keys: {'yes' if has_fkeys else 'no'}")
                print(f"  Reports scancodes: {'yes' if has_msc_scan else 'no'}")
                print()
                dev.close()
        except (PermissionError, OSError) as e:
            print(f"Device: {path}")
            print(f"  Error: {e}")
            print()

    if not found_any:
        print("No keyboard devices found.")
        print("Make sure you have permission to read /dev/input devices.")


def main():
    """Entry point: calibration mode only."""
    if not EVDEV_AVAILABLE:
        print("This tool requires Linux.")
        print("Please run this on your Purple Computer device.")
        sys.exit(1)

    args = set(sys.argv[1:])
    debug = "--debug" in args or "-d" in args

    if "--list-devices" in args:
        list_keyboard_devices()
        sys.exit(0)

    if "--calibrate" in args:
        sys.exit(0 if calibrate(debug=debug) else 1)

    # Show help
    print("Purple Computer Keyboard Setup")
    print("=" * 40)
    print()
    print("This tool helps set up your keyboard's F-keys.")
    print()
    print("To start setup, run:")
    print("  python keyboard_normalizer.py --calibrate")
    print()

    # Show current status
    mapping = load_scancode_map()
    if mapping:
        print(f"Your keyboard is already set up ({len(mapping)} keys configured).")
        print("Run the command above if you want to redo the setup.")
    else:
        print("Your keyboard hasn't been set up yet.")
        print("Run the command above to get started.")

    sys.exit(0)


if __name__ == "__main__":
    main()
