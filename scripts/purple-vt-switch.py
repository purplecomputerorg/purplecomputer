#!/usr/bin/env python3
"""
Early-boot VT switch watcher.

Provides emergency Ctrl+\\ (3s hold) and Ctrl+Alt+F2 VT switching before the
main Purple Computer app starts its evdev handler. Runs without grab so it
coexists with normal input processing. Once the main app grabs evdev, this
watcher stops receiving events naturally (but stays alive as a safety net in
case the app crashes and releases the grab).

Started from xinitrc before Alacritty launches.
"""

import struct
import time
import os
import subprocess
from pathlib import Path

# evdev event struct: time_sec(L) time_usec(L) type(H) code(H) value(i)
EVENT_SIZE = struct.calcsize("LLHHi")
EV_KEY = 0x01

# Key codes (from linux/input-event-codes.h)
KEY_F1 = 59
KEY_F2 = 60
KEY_BACKSLASH = 43
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_LEFTALT = 56
KEY_RIGHTALT = 100

LOG_PATH = "/tmp/purple-vt-switch.log"


def log(msg):
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def find_keyboards():
    """Find keyboard input devices (simplified version of EvdevReader logic)."""
    keyboards = []
    for entry in sorted(Path("/dev/input").iterdir()):
        if not entry.name.startswith("event"):
            continue
        try:
            # Check if device has EV_KEY capability via sysfs
            devnum = entry.name[5:]  # "event0" -> "0"
            caps_path = Path(f"/sys/class/input/event{devnum}/device/capabilities/key")
            if not caps_path.exists():
                continue
            caps = caps_path.read_text().strip()
            # A real keyboard has many key bits set; USB drives have very few.
            # Check that the capability bitmap has at least 4 hex groups
            # (letter keys are in the 0x10-0x40 range).
            if len(caps.split()) < 3:
                continue
            keyboards.append(str(entry))
        except Exception:
            continue
    return keyboards


def do_vt_switch(target_tty):
    """Switch to the given tty."""
    log(f"Switching to tty{target_tty}")
    try:
        subprocess.Popen(["sudo", "chvt", str(target_tty)])
    except Exception as e:
        log(f"chvt failed: {e}")


def main():
    keyboards = find_keyboards()
    if not keyboards:
        log("No keyboards found, exiting")
        return

    log(f"Watching keyboards: {keyboards}")

    # Open all keyboard devices (no grab)
    fds = []
    for path in keyboards:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            fds.append(fd)
        except OSError as e:
            log(f"Cannot open {path}: {e}")

    if not fds:
        log("No devices opened, exiting")
        return

    ctrl_held = False
    alt_held = False
    backslash_start = None
    switch_fired = False

    import select

    while True:
        # Short timeout while tracking a hold, long sleep otherwise (no CPU waste)
        timeout = 0.25 if backslash_start is not None else 60.0
        try:
            readable, _, _ = select.select(fds, [], [], timeout)
        except (OSError, ValueError):
            # Device removed or closed
            break

        # Check Ctrl+\ hold timer even when no new events
        if backslash_start is not None and ctrl_held and not switch_fired:
            if time.monotonic() - backslash_start >= 3.0:
                switch_fired = True
                backslash_start = None
                do_vt_switch(2)

        for fd in readable:
            try:
                data = os.read(fd, EVENT_SIZE * 32)
            except OSError:
                continue

            for offset in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
                _, _, ev_type, code, value = struct.unpack_from("LLHHi", data, offset)

                if ev_type != EV_KEY or value not in (0, 1, 2):
                    continue

                is_down = value in (1, 2)

                if code in (KEY_LEFTCTRL, KEY_RIGHTCTRL):
                    ctrl_held = is_down
                    if not is_down:
                        backslash_start = None
                        switch_fired = False

                if code in (KEY_LEFTALT, KEY_RIGHTALT):
                    alt_held = is_down

                # Ctrl+Alt+F2: immediate switch to tty2
                if code == KEY_F2 and is_down and ctrl_held and alt_held and not switch_fired:
                    switch_fired = True
                    do_vt_switch(2)

                # Ctrl+Alt+F1: immediate switch back to tty1
                if code == KEY_F1 and is_down and ctrl_held and alt_held:
                    do_vt_switch(1)

                # Ctrl+\ hold tracking
                if code == KEY_BACKSLASH:
                    if is_down and ctrl_held and not switch_fired:
                        if backslash_start is None:
                            backslash_start = time.monotonic()
                    if not is_down:
                        backslash_start = None
                        switch_fired = False

    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass


if __name__ == "__main__":
    log("Starting purple-vt-switch watcher")
    try:
        main()
    except Exception as e:
        log(f"Fatal error: {e}")
    log("Exiting")
