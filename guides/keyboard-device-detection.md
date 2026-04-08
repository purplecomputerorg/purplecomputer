# Keyboard Device Detection: HID Interface Bug

How we diagnosed and fixed the EvdevReader picking the wrong input device.

---

## The Problem

On an Apple MacBook running Purple Computer, the app loaded normally but keyboard input did nothing. The sleep screen could detect keypresses (via Textual's terminal input), but the main app (which reads input via evdev) was unresponsive.

---

## Root Cause

Linux exposes each USB/HID interface as a separate `/dev/input/event*` device. The Apple Internal Keyboard registers multiple event devices:

```
/dev/input/event4  Apple Inc. Apple Internal Keyboard / Trackpad  (real keyboard)
/dev/input/event5  HID 05ac:820a                                  (media/special keys HID interface)
/dev/input/event6  HID 05ac:820b                                  (another HID interface)
/dev/input/event7  bcm5974                                        (trackpad)
```

Both event4 and event5 had `kbd` in their `/dev/input/by-id/` symlink names:

```
usb-05ac_820a-event-kbd                                    -> ../event5
usb-Apple_Inc._Apple_Internal_Keyboard___Trackpad_...-kbd  -> ../event4
```

The `_find_keyboard()` method scanned `/dev/input/by-id/` in sorted order looking for entries with "kbd" in the name. `usb-05ac_820a...` sorts before `usb-Apple_Inc...`, so it picked event5 (the HID interface that reports some key capabilities but never produces actual key events).

The EvdevReader grabbed event5 and sat in its read loop forever, waiting for events that never came.

---

## What Changed

This surfaced after build changes that replaced the `xorg` metapackage with minimal X11 packages and added `--no-install-recommends`. The likely mechanism: with the full `xorg` package, X11's libinput driver previously opened all input devices during startup. When `_find_keyboard()` tried to open event5, it would get a PermissionError or IOError (device already grabbed by X11), skip it, and correctly land on event4.

With the minimal X11 setup, X11 may not claim event5 anymore, leaving it available for the app to open. The `_find_keyboard()` scanner was not robust enough to tell the difference between a real keyboard and a HID interface that happens to report some key capabilities.

---

## How We Debugged It

1. **Recovery shell**: confirmed `/dev/input/event*` devices exist and `evdev.list_devices()` finds the keyboard. Ruled out missing kernel modules and permissions.

2. **evdev is built-in**: discovered `lsmod | grep evdev` returning nothing is normal on Ubuntu 24.04 (evdev is compiled into the kernel, not a loadable module). This was a red herring for several rounds of debugging.

3. **Diagnostic logging**: added logging to `EvdevReader.start()` that writes to `/tmp/evdev-diag.log`, showing which device was picked.

4. **Input test GRUB entry**: added a `purple.inputtest=1` kernel parameter and debug GRUB entry that exits the app to a debug shell after 60 seconds of no keyboard input. This solved the problem of not being able to access logs when the keyboard doesn't work and tty2 switching isn't available (Mac keyboards lack Alt).

5. **Confirmed wrong device**: the diag log showed `EvdevReader: using /dev/input/event5 (HID 05ac:820a)`. From the debug shell, we listed all devices and confirmed event4 was the real keyboard. Reading from event5 in a Python test produced no events; reading from event4 worked immediately.

---

## The Fix (Phase 1: Strict Detection)

Made `_find_keyboard()` in `purple_tui/input.py` use strict validation instead of just checking for the presence of any letter keys.

A real keyboard must have:
- All 26 letter keys (KEY_A through KEY_Z)
- KEY_ENTER, KEY_SPACE, KEY_LEFTSHIFT
- EV_REP capability (auto-repeat, which real keyboards support but HID interfaces don't)

Falls back to a looser check (just letter keys) if nothing passes the strict test, to avoid breaking on exotic hardware.

This is hardware-agnostic: no vendor name checks, no Apple-specific logic. It works because the test is "can this device type full sentences?" which only real keyboards can do.

## The Fix (Phase 2: Multi-Device Support)

After fixing detection, we hit a related issue: some laptops expose two keyboard input devices. During live boot (with USB drive present), device numbering differs from after install (no USB). The app would find one device that happened to work in live boot, but a different one after install.

The fix mirrors what was done for the power button: `_find_keyboard()` became `_find_keyboards()` and returns ALL matching devices. EvdevReader creates one async read loop per device and delivers events from any of them. Same pattern as PowerButtonReader listening on all power button devices.

This ensures keyboard input works regardless of which evdev device delivers the actual key events, across all laptop hardware and USB configurations.

## The Fix (Phase 3: Device Reconnection)

The multi-device read loops silently died on `OSError` when a device disconnected, with no recovery. This was observed on a Touch Bar MacBook where the keyboard stopped responding after a failed install attempt (heavy NVMe I/O may cause USB bus resets on Apple hardware where the internal keyboard connects via USB).

Symptoms: typing works initially, then after some event (install, heavy I/O), escape-related features stop working. The evdev read loop exited, keys fell through to the terminal, and evdev-only features (tilde-as-escape, backslash hold) broke.

The fix: when a read loop exits unexpectedly (`_running` is still True), it schedules `_reconnect()` which re-scans for keyboards every second for up to 30 seconds. If the device reappears (possibly on a different event node), it's grabbed and a new read loop starts. This matches how libinput and other serious evdev consumers handle hotplug.

Diagnostic log (`/tmp/evdev-diag.log`) for a reconnection event:
```
Read loop LOST DEVICE: /dev/input/event3: [Errno 19] No such device
Reconnected: /dev/input/event5 (Apple Internal Keyboard)
Read loop started: /dev/input/event5 (Apple Internal Keyboard)
```

The log also records:
- First occurrence of the grave/escape remap firing (confirms tilde works)
- Any unrecognized keycodes with their scancodes (catches keys sending unexpected codes)
- Read loop start/stop for each device

To access the log when the keyboard is misbehaving: hold Ctrl+\\ for 3 seconds to switch to tty2, then `cat /tmp/evdev-diag.log`.

---

## Devices That Can Fool a Loose Keyboard Detector

- Apple secondary HID interfaces (05ac:820a, 05ac:820b)
- USB flash drives that expose HID keyboard interfaces (BadUSB-style)
- Barcode scanners and similar HID devices that register some key capabilities
- KVM switches that present virtual keyboard devices

All of these may have some `EV_KEY` capabilities and even "kbd" in their by-id names, but none have the full key set + EV_REP of a real keyboard.
