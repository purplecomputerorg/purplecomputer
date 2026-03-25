#!/usr/bin/env python3
"""Check power button and power management state.

Usage: python3 debug-power.py

Shows:
  - Whether power button device is found
  - logind HandlePowerKey setting
  - Lid state, charger state
  - Current idle timers and thresholds
"""

import os
import subprocess
import sys

try:
    import evdev
    from evdev import InputDevice
except ImportError:
    print("evdev not available")
    sys.exit(1)


def check_power_button():
    """Check if power button evdev device is accessible."""
    print("=== Power Button Device ===\n")

    found = []
    for path in sorted(evdev.list_devices()):
        try:
            dev = InputDevice(path)
            caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
            if evdev.ecodes.KEY_POWER in caps:
                n_keys = len(caps)
                print(f"  Found: {dev.path} ({dev.name}, {n_keys} keys)")
                found.append((dev.path, dev.name, n_keys))
            dev.close()
        except PermissionError:
            num = path.split("event")[-1]
            print(f"  event{num}: PERMISSION DENIED")
        except OSError:
            pass

    if not found:
        print("  No device with KEY_POWER found!")
        print("  The TUI power button handler won't work.")
    else:
        # Show which one the app would pick (fewest keys, same as PowerButtonReader)
        found.sort(key=lambda x: x[2])
        print(f"\n  App would use: {found[0][0]} ({found[0][1]})")

    print()


def check_logind():
    """Check logind power key configuration."""
    print("=== logind Configuration ===\n")

    conf_path = "/etc/systemd/logind.conf.d/purple-power.conf"
    if os.path.exists(conf_path):
        with open(conf_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    print(f"  {line}")
    else:
        print(f"  {conf_path} NOT FOUND")
        print("  logind will use defaults (power button = poweroff!)")

    # Check actual runtime setting
    try:
        result = subprocess.run(
            ["busctl", "get-property", "org.freedesktop.login1",
             "/org/freedesktop/login1", "org.freedesktop.login1.Manager",
             "HandlePowerKey"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            print(f"\n  Runtime HandlePowerKey: {result.stdout.strip()}")
    except Exception:
        pass

    print()


def check_power_state():
    """Check current power state."""
    print("=== Power State ===\n")

    # Lid
    for lid_path in [
        "/proc/acpi/button/lid/LID0/state",
        "/proc/acpi/button/lid/LID/state",
        "/proc/acpi/button/lid/LID1/state",
    ]:
        if os.path.exists(lid_path):
            try:
                with open(lid_path) as f:
                    print(f"  Lid: {f.read().strip()} ({lid_path})")
                break
            except Exception:
                pass
    else:
        print("  Lid: not detected")

    # Charger
    ps_path = "/sys/class/power_supply"
    if os.path.exists(ps_path):
        for entry in os.listdir(ps_path):
            type_file = os.path.join(ps_path, entry, "type")
            try:
                with open(type_file) as f:
                    ptype = f.read().strip()
                if ptype == "Mains":
                    online_file = os.path.join(ps_path, entry, "online")
                    with open(online_file) as f:
                        online = f.read().strip()
                    status = "plugged in" if online == "1" else "on battery"
                    print(f"  Charger: {status} ({entry})")
            except Exception:
                pass

    # User groups
    groups = os.getgroups()
    import grp
    group_names = []
    for gid in groups:
        try:
            group_names.append(grp.getgrgid(gid).gr_name)
        except KeyError:
            group_names.append(str(gid))
    has_input = "input" in group_names
    print(f"  User: {os.getlogin() if hasattr(os, 'getlogin') else 'unknown'}")
    print(f"  Groups: {', '.join(sorted(group_names))}")
    print(f"  In 'input' group: {'yes' if has_input else 'NO (power button will fail!)'}")

    print()


def check_debug_log():
    """Check if purple debug log has power button info."""
    print("=== Debug Log ===\n")

    log_path = "/tmp/purple-debug.log"
    if not os.path.exists(log_path):
        print(f"  {log_path} not found")
        print()
        return

    with open(log_path) as f:
        lines = f.readlines()

    power_lines = [l.strip() for l in lines if "power" in l.lower() or "PowerButton" in l]
    if power_lines:
        for line in power_lines[-10:]:
            print(f"  {line}")
    else:
        print("  No power-related entries in log")

    print()


def main():
    check_power_button()
    check_logind()
    check_power_state()
    check_debug_log()


if __name__ == "__main__":
    main()
