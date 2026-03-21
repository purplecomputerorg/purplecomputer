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

## The Fix

Made `_find_keyboard()` in `purple_tui/input.py` use strict validation instead of just checking for the presence of any letter keys.

A real keyboard must have:
- All 26 letter keys (KEY_A through KEY_Z)
- KEY_ENTER, KEY_SPACE, KEY_LEFTSHIFT
- EV_REP capability (auto-repeat, which real keyboards support but HID interfaces don't)

Falls back to a looser check (just letter keys) if nothing passes the strict test, to avoid breaking on exotic hardware.

This is hardware-agnostic: no vendor name checks, no Apple-specific logic. It works because the test is "can this device type full sentences?" which only real keyboards can do.

---

## Devices That Can Fool a Loose Keyboard Detector

- Apple secondary HID interfaces (05ac:820a, 05ac:820b)
- USB flash drives that expose HID keyboard interfaces (BadUSB-style)
- Barcode scanners and similar HID devices that register some key capabilities
- KVM switches that present virtual keyboard devices

All of these may have some `EV_KEY` capabilities and even "kbd" in their by-id names, but none have the full key set + EV_REP of a real keyboard.
