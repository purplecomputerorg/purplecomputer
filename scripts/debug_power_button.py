#!/usr/bin/env python3
"""Debug script to check power button evdev detection.

Run with: just python scripts/debug_power_button.py

Shows all input devices, their capabilities, and whether any
report KEY_POWER. If a power button device is found, listens
for events and prints them live.
"""

import sys

try:
    import evdev
    from evdev import InputDevice
except ImportError:
    print("evdev not installed. Run: just python -m pip install evdev")
    sys.exit(1)


def main():
    devices = sorted(evdev.list_devices())
    if not devices:
        print("No input devices found!")
        print("Check: are you in the 'input' group?")
        print("  Run: groups")
        print("  Run: ls -la /dev/input/")
        return

    print(f"Found {len(devices)} input devices:\n")

    power_devices = []

    for dev_path in devices:
        try:
            dev = InputDevice(dev_path)
            key_caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
            has_power = evdev.ecodes.KEY_POWER in key_caps
            marker = " ** HAS KEY_POWER **" if has_power else ""
            print(f"  {dev.path}: {dev.name} ({len(key_caps)} keys){marker}")
            if has_power:
                power_devices.append(dev)
            else:
                dev.close()
        except PermissionError:
            print(f"  {dev_path}: (permission denied)")
        except OSError as e:
            print(f"  {dev_path}: (error: {e})")

    print()

    if not power_devices:
        print("No device with KEY_POWER found!")
        print()
        print("On Mac hardware, the power button may not be exposed via evdev.")
        print("Check if there's an ACPI power button driver loaded:")
        print("  Run: grep -i power /proc/bus/input/devices")
        print("  Run: dmesg | grep -i 'power button'")
        return

    # Pick the same device the app would pick (fewest keys first)
    power_devices.sort(key=lambda d: len(d.capabilities().get(evdev.ecodes.EV_KEY, [])))
    chosen = power_devices[0]
    for dev in power_devices[1:]:
        dev.close()

    print(f"Power button device: {chosen.path} ({chosen.name})")
    print(f"Key capabilities: {len(chosen.capabilities().get(evdev.ecodes.EV_KEY, []))} keys")
    print()
    print("Listening for power button events (press Ctrl+C to stop)...")
    print()

    try:
        for event in chosen.read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                key_name = evdev.ecodes.KEY.get(event.code, f"unknown({event.code})")
                action = {0: "release", 1: "press", 2: "repeat"}.get(event.value, f"?{event.value}")
                print(f"  KEY {key_name} {action} (code={event.code}, value={event.value})")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        chosen.close()


if __name__ == "__main__":
    main()
