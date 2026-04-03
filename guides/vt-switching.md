# VT Switching (Emergency TTY Access)

How to switch from the Purple Computer UI to a root shell on tty2 for debugging, and how the implementation ensures it always works.

## Quick Reference

| Combo | Effect | Hold needed? |
|-------|--------|-------------|
| **Ctrl+Alt+F2** | Switch to tty2 | No (immediate) |
| **Ctrl+\\** (Ctrl+Backslash) | Switch to tty2 | 3 seconds |
| **Ctrl+Alt+F1** | Switch back to tty1 | No (immediate) |
| **Ctrl+\\** again | Switch back to tty1 | 3 seconds |

All combos release the evdev grab so tty2 actually receives keyboard input.

## The Problem

Standard Linux VT switching (Ctrl+Alt+Fn) relies on the kernel's keyboard handler. Alacritty (and X11 before it) sets the tty1 keyboard mode to `K_OFF`, which disables kernel keyboard processing entirely. This means the standard combos do nothing.

Meanwhile, the app reads keyboard input via evdev (`EVIOCGRAB`), bypassing the terminal. When evdev has an exclusive grab, no other process (including tty2's console) receives key events.

So switching to tty2 requires two things: (1) calling `chvt 2` since the kernel won't do it, and (2) releasing the evdev grab so tty2 can receive input.

## Three Layers of Coverage

The VT switch must work any time the user sees a purple screen. Three independent mechanisms ensure there are no gaps:

### Layer 1: Kernel VT switching (boot until X11 starts)

During early boot (initramfs splash, systemd splash, GPU wait), tty1 is in normal `K_UNICODE` mode. The kernel handles Ctrl+Alt+F2 natively. No special code needed.

**Covers:** Power on through `startx` launching X11.

### Layer 2: Standalone watcher (`purple-vt-switch.py`)

A lightweight Python script started as the first thing in xinitrc. Reads evdev directly (no grab, no X11 dependency). Detects Ctrl+Alt+F2 and Ctrl+\\ and calls `chvt`.

- Starts before Alacritty, before the app, before anything else in xinitrc
- Reads without grab, so it coexists with normal input processing
- Once the app grabs evdev, the watcher stops receiving events naturally
- If the app crashes and releases the grab, the watcher resumes (safety net)
- Near-zero CPU when idle (sleeps in `select()` with 60s timeout)

**Covers:** X11 start (K_OFF set) through app's evdev handler initialization. Also covers app crashes.

**File:** `scripts/purple-vt-switch.py`, installed to `/opt/purple/purple-vt-switch.py`

### Layer 3: App's evdev handler (`EvdevReader` in `input.py`)

The main app's keyboard read loop includes VT switch detection at the evdev level, before any Textual processing. This means it works even when the Textual UI is frozen or hung.

On switch:
1. Releases evdev grab (`release_grab()`)
2. Sets `_vt_away` flag to suppress forwarding events to the app (no music playing while on tty2)
3. Calls `chvt 2`

On return (detected via `/sys/class/tty/tty0/active` check on each key event while away):
1. Reacquires evdev grab
2. Clears `_vt_away` flag, resuming normal operation

**Covers:** Normal app operation (the majority of the time).

**File:** `purple_tui/input.py`, in `EvdevReader._read_loop()`

## Timeline

```
Power on
  |  Kernel VT switching works (K_UNICODE mode)
  v
Initramfs splash (purple VT background)
  |  Kernel VT switching works
  v
Systemd splash service
  |  Kernel VT switching works
  v
purple-x11.service starts, X11 initializes
  |  X sets K_OFF on tty1 -- kernel VT switching stops
  |  Standalone watcher starts (first line of xinitrc)
  v
xinitrc setup (PulseAudio, window manager, font calc...)
  |  Standalone watcher handles VT switching
  v
Alacritty launches, Python app starts loading
  |  Standalone watcher handles VT switching
  v
App's EvdevReader.start() grabs keyboards
  |  App handler takes over (watcher stops receiving events)
  v
Normal operation
  |  App handler handles VT switching
  v
App crash / exit
  |  Grab released, watcher resumes receiving events
  v
xinitrc restarts (exec "$0")
  |  Old watcher killed, new one started immediately
  v
(cycle repeats)
```

## Returning to tty1

Two methods:

1. **Ctrl+Alt+F1** on tty2: Works because tty2 is in normal `K_UNICODE` mode. The app auto-detects the return by checking `/sys/class/tty/tty0/active` on the next key event and reacquires the grab.

2. **Ctrl+\\** held 3 seconds: The app's evdev handler (which still reads events without grab while away) detects this and calls `chvt 1` + reacquires grab.

## SSH access

`sudo chvt 2` from SSH switches the display but does NOT release the evdev grab, so the keyboard still sends to the app. Use the keyboard combos instead. (SSH users who need keyboard access on tty2 can also `sudo evdev-ungrab` or restart the app.)

## Debug ISO differences

The debug ISO additionally enables SysRq (`kernel.sysrq=1`), which provides a kernel-level escape hatch: Alt+PrtSc+R releases the evdev grab, then Ctrl+Alt+F2 works at the kernel level. See `guides/debug-shell-escape.md`. This is disabled in production so kids can't accidentally trigger SysRq sequences.

## Key files

- `purple_tui/input.py`: `EvdevReader` class, VT switch detection in `_read_loop()`, grab management
- `scripts/purple-vt-switch.py`: Standalone early-boot watcher
- `config/xinit/xinitrc`: Watcher startup
- `build-scripts/00-build-golden-image.sh`: Installs watcher to `/opt/purple/`
