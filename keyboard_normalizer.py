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


def calibrate() -> bool:
    """
    Interactive calibration: prompts user to press F1-F12.
    Captures scancodes and saves mapping.

    Returns True if successful.
    """
    import select

    if not EVDEV_AVAILABLE:
        print("evdev not available")
        return False

    print("Purple Computer Keyboard Setup")
    print("=" * 40)
    print()
    print("Let's set up your keyboard!")
    print()
    print("Press each key when asked.")
    print("Just press and release the key shown.")
    print()
    print("If a key doesn't work (captured by your system), press Space to skip it.")
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
    print()

    mapping = {}
    keys_to_calibrate = [(i, f"F{i}") for i in range(1, 13)]

    try:
        hw_device.grab()

        KEY_SPACE = 57  # Linux keycode for space

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
            elif keycode == KEY_SPACE:
                print("(skipped)")
                continue
            elif scancode:
                mapping[scancode] = TARGET_FKEYS[fnum]
                print("OK!")
            elif key_released:
                # Key was pressed but no scancode (some keyboards don't report MSC_SCAN)
                print("OK")  # Don't confuse parents, just continue

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

def main():
    """Entry point: calibration mode only."""
    if not EVDEV_AVAILABLE:
        print("This tool requires Linux.")
        print("Please run this on your Purple Computer device.")
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        sys.exit(0 if calibrate() else 1)

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
