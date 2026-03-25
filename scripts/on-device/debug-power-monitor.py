#!/usr/bin/env python3
"""Real-time power state monitor for debugging shutdown/sleep issues.

On-device: python3 /opt/purple/scripts/debug-power-monitor.py
Dev:       just python scripts/on-device/debug-power-monitor.py

Continuously polls and logs:
  - Charger state (raw sysfs reads)
  - Lid state (both /proc/acpi and evdev)
  - Battery level (if available)
  - What the power manager would decide given current state

Logs to stdout and optionally to a file (--log FILE).
All entries are timestamped. State changes are highlighted.

Typical usage:
  1. Open parent menu terminal (or SSH into the laptop)
  2. Start this script
  3. Reproduce the issue (close lid, plug/unplug charger, wait)
  4. Review the log to see what happened

Examples:
  python3 /opt/purple/scripts/debug-power-monitor.py
  python3 /opt/purple/scripts/debug-power-monitor.py --log /tmp/power.log
  python3 /opt/purple/scripts/debug-power-monitor.py --interval 1
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path


def find_mains_path():
    """Find AC mains power supply path in sysfs."""
    base = "/sys/class/power_supply"
    if not os.path.exists(base):
        return None
    for entry in os.listdir(base):
        type_file = os.path.join(base, entry, "type")
        try:
            with open(type_file) as f:
                if f.read().strip() == "Mains":
                    online_file = os.path.join(base, entry, "online")
                    if os.path.exists(online_file):
                        return os.path.join(base, entry)
        except (IOError, OSError, PermissionError):
            continue
    return None


def find_battery_path():
    """Find battery power supply path in sysfs."""
    base = "/sys/class/power_supply"
    if not os.path.exists(base):
        return None
    for entry in os.listdir(base):
        type_file = os.path.join(base, entry, "type")
        try:
            with open(type_file) as f:
                if f.read().strip() == "Battery":
                    return os.path.join(base, entry)
        except (IOError, OSError, PermissionError):
            continue
    return None


def read_file(path):
    """Read a sysfs/procfs file, return content or None."""
    try:
        with open(path) as f:
            return f.read().strip()
    except (IOError, OSError, PermissionError):
        return None


def find_lid_path():
    """Find lid state path in /proc/acpi."""
    for path in [
        "/proc/acpi/button/lid/LID0/state",
        "/proc/acpi/button/lid/LID/state",
        "/proc/acpi/button/lid/LID1/state",
    ]:
        if os.path.exists(path):
            return path
    return None


def get_charger_raw(mains_path):
    """Read raw charger online state. Returns '1', '0', or None."""
    if not mains_path:
        return None
    return read_file(os.path.join(mains_path, "online"))


def get_lid_state(lid_path):
    """Read lid state. Returns 'open', 'closed', or None."""
    if not lid_path:
        return None
    content = read_file(lid_path)
    if content is None:
        return None
    if "open" in content.lower():
        return "open"
    elif "closed" in content.lower():
        return "closed"
    return content


def get_battery_info(battery_path):
    """Read battery capacity and status."""
    if not battery_path:
        return None, None
    capacity = read_file(os.path.join(battery_path, "capacity"))
    status = read_file(os.path.join(battery_path, "status"))
    return capacity, status


def check_logind_config():
    """Read current logind power key config."""
    path = "/etc/systemd/logind.conf.d/purple-power.conf"
    content = read_file(path)
    if content is None:
        return "not found"
    for line in content.split("\n"):
        if line.startswith("HandlePowerKey="):
            return line.split("=", 1)[1]
    return "not set"


def check_evdev_devices():
    """Check for power button and lid switch evdev devices."""
    try:
        import evdev
    except ImportError:
        return "evdev not installed"

    results = []
    for dev_path in sorted(evdev.list_devices()):
        try:
            dev = evdev.InputDevice(dev_path)
            key_caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
            sw_caps = dev.capabilities().get(evdev.ecodes.EV_SW, [])

            if evdev.ecodes.KEY_POWER in key_caps:
                results.append(f"power_button={dev.path} ({dev.name})")
            if evdev.ecodes.SW_LID in sw_caps:
                # Read current lid state from evdev
                sw_state = dev.active_keys()  # doesn't work for switches
                results.append(f"lid_switch={dev.path} ({dev.name})")
            dev.close()
        except (PermissionError, OSError):
            continue

    return "; ".join(results) if results else "no power/lid devices"


def predict_behavior(charger_raw, lid_state, is_demo):
    """Predict what the power manager would do given current state."""
    on_charger = charger_raw == "1"
    lid_closed = lid_state == "closed"

    if is_demo:
        sleep_time = "3s" if on_charger else "2s"
        shutdown_time = "never" if (on_charger and not lid_closed) else ("8s" if lid_closed else "10s")
    else:
        sleep_time = "5min" if on_charger else "2min"
        if lid_closed:
            shutdown_time = "10min (lid closed)"
        elif on_charger:
            shutdown_time = "never (on charger, lid open)"
        else:
            shutdown_time = "10min (battery)"

    return f"sleep_after={sleep_time}, shutdown_after={shutdown_time}"


def main():
    parser = argparse.ArgumentParser(description="Monitor power state for debugging")
    parser.add_argument("--log", help="Also write to this log file")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Poll interval in seconds (default: 2)")
    parser.add_argument("--once", action="store_true",
                        help="Print state once and exit")
    args = parser.parse_args()

    log_file = None
    if args.log:
        log_file = open(args.log, "a")

    def log(msg, highlight=False):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = ">>>" if highlight else "   "
        line = f"[{ts}] {prefix} {msg}"
        print(line)
        if log_file:
            log_file.write(line + "\n")
            log_file.flush()

    # Probe hardware
    mains_path = find_mains_path()
    battery_path = find_battery_path()
    lid_path = find_lid_path()
    is_demo = bool(os.environ.get("PURPLE_SLEEP_DEMO"))

    log("=== Purple Computer Power State Monitor ===", highlight=True)
    log(f"Mains path: {mains_path or 'NOT FOUND'}")
    log(f"Battery path: {battery_path or 'NOT FOUND'}")
    log(f"Lid path: {lid_path or 'NOT FOUND'}")
    log(f"Demo mode: {is_demo}")
    log(f"Logind HandlePowerKey: {check_logind_config()}")
    log(f"Evdev devices: {check_evdev_devices()}")
    log("")

    if not mains_path:
        log("WARNING: No AC mains found. Charger detection will always return unknown.", highlight=True)
        log("         Power manager treats unknown as battery (conservative).", highlight=True)
        log("")

    # Track previous state for change detection
    prev = {"charger": None, "lid": None, "battery": None, "status": None}

    try:
        while True:
            charger_raw = get_charger_raw(mains_path)
            lid = get_lid_state(lid_path)
            bat_cap, bat_status = get_battery_info(battery_path)
            prediction = predict_behavior(charger_raw, lid, is_demo)

            # Detect changes
            charger_label = {"1": "ON_CHARGER", "0": "ON_BATTERY", None: "UNKNOWN"}[charger_raw]
            changed = []
            if charger_label != prev["charger"]:
                changed.append(f"charger: {prev['charger']} -> {charger_label}")
                prev["charger"] = charger_label
            if lid != prev["lid"]:
                changed.append(f"lid: {prev['lid']} -> {lid}")
                prev["lid"] = lid
            if bat_cap != prev["battery"]:
                prev["battery"] = bat_cap
            if bat_status != prev["status"]:
                changed.append(f"battery_status: {prev['status']} -> {bat_status}")
                prev["status"] = bat_status

            if changed:
                for change in changed:
                    log(f"STATE CHANGE: {change}", highlight=True)

            bat_info = f", battery={bat_cap}% ({bat_status})" if bat_cap else ""
            log(f"charger={charger_label}, lid={lid}{bat_info} | {prediction}")

            if args.once:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        log("\nStopped.", highlight=True)
    finally:
        if log_file:
            log_file.close()


if __name__ == "__main__":
    main()
