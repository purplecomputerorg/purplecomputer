#!/usr/bin/env python3
"""List all input devices and listen for events on one.

Usage:
  python3 debug-evtest.py           # List devices, then listen on first power button
  python3 debug-evtest.py 3         # Listen on /dev/input/event3
  python3 debug-evtest.py --list    # Just list devices, don't listen

Replaces evtest for Purple Computer debugging (evtest isn't installed).
"""

import sys

try:
    import evdev
    from evdev import InputDevice
except ImportError:
    print("evdev not available")
    sys.exit(1)


def list_devices():
    """List all input devices with capabilities."""
    devices = sorted(evdev.list_devices())
    if not devices:
        print("No input devices found.")
        print("Are you in the 'input' group? Check: groups")
        return []

    print(f"Input devices ({len(devices)}):\n")
    power_devs = []

    for path in devices:
        try:
            dev = InputDevice(path)
            key_caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
            sw_caps = dev.capabilities().get(evdev.ecodes.EV_SW, [])

            tags = []
            if evdev.ecodes.KEY_POWER in key_caps:
                tags.append("POWER")
                power_devs.append(dev)
            if evdev.ecodes.KEY_SLEEP in key_caps:
                tags.append("SLEEP")
            if 0 in sw_caps:  # SW_LID
                tags.append("LID")
            if len(key_caps) > 50:
                tags.append("keyboard")

            num = path.split("event")[-1]
            tag_str = f"  [{', '.join(tags)}]" if tags else ""
            print(f"  event{num}: {dev.name} ({len(key_caps)} keys){tag_str}")

            if dev not in power_devs:
                dev.close()
        except PermissionError:
            num = path.split("event")[-1]
            print(f"  event{num}: (permission denied)")
        except OSError as e:
            num = path.split("event")[-1]
            print(f"  event{num}: (error: {e})")

    return power_devs


def listen(dev):
    """Listen for all events on a device."""
    print(f"\nListening on {dev.path} ({dev.name})")
    print("Press Ctrl+C to stop.\n")

    try:
        for event in dev.read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                key_name = evdev.ecodes.KEY.get(event.code, f"KEY_{event.code}")
                if isinstance(key_name, list):
                    key_name = key_name[0]
                action = {0: "UP", 1: "DOWN", 2: "REPEAT"}.get(event.value, f"?{event.value}")
                print(f"  KEY  {key_name} {action}  (code={event.code})")
            elif event.type == evdev.ecodes.EV_SW:
                sw_name = evdev.ecodes.SW.get(event.code, f"SW_{event.code}")
                state = "CLOSED" if event.value else "OPEN"
                print(f"  SW   {sw_name} {state}  (code={event.code})")
            elif event.type not in (evdev.ecodes.EV_SYN, evdev.ecodes.EV_MSC):
                print(f"  type={event.type} code={event.code} value={event.value}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        dev.close()


def main():
    args = sys.argv[1:]

    if "--list" in args or "-l" in args:
        power_devs = list_devices()
        for d in power_devs:
            d.close()
        return

    if args and args[0].isdigit():
        # Listen on specific event number
        path = f"/dev/input/event{args[0]}"
        try:
            dev = InputDevice(path)
            print(f"Device: {dev.name}")
            listen(dev)
        except PermissionError:
            print(f"Permission denied: {path}")
            print("Try: sudo python3 debug-evtest.py " + args[0])
        except OSError as e:
            print(f"Error opening {path}: {e}")
        return

    # Default: list devices, then listen on first power button
    power_devs = list_devices()

    if not power_devs:
        print("\nNo power button device found.")
        return

    # Pick the one with fewest keys (dedicated power button, same logic as app)
    power_devs.sort(key=lambda d: len(d.capabilities().get(evdev.ecodes.EV_KEY, [])))
    chosen = power_devs[0]
    for d in power_devs[1:]:
        d.close()

    listen(chosen)


if __name__ == "__main__":
    main()
