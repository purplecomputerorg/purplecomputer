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

Ctrl+Alt+F2 is available from power-on through app shutdown via three distinct mechanisms, each covering a different window:

### Layer 1: Kernel VT switching (boot until X11 starts)

During early boot (initramfs splash, systemd splash, GPU wait), tty1 is in normal `K_UNICODE` mode. The kernel handles Ctrl+Alt+F2 natively. No special code needed.

**Covers:** Power on through `startx` launching X11.

### Layer 2: X server VT switch (X running, app not yet grabbing)

X handles Ctrl+Alt+F2 via its default xkb VT-switch binding, reading evdev through libinput and issuing a `VT_ACTIVATE` ioctl. Requires `DontVTSwitch` to be unset in `config/xorg/10-modesetting.conf` (it is). This is the critical path when Purple hangs during Python startup: Layer 3 isn't running yet, so Layer 2 is the only non-power-button escape.

**Covers:** X startup through `EvdevReader.start()` (called in `PurpleApp.on_mount`).

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

### chvt race guard

`chvt` is spawned via `Popen` (non-blocking) so the evdev handler doesn't block. But this creates a race: key-up events from the Ctrl+Alt+F2 combo arrive before `chvt` completes, and `_is_on_tty1()` still returns True, causing the handler to immediately reacquire the grab. By the time `chvt 2` finishes, the grab is back and tty2 can't receive input.

Fix: a 500ms cooldown after setting `_vt_away` before checking `_is_on_tty1()`. This gives `chvt` time to complete. See `input.py` `_read_loop()`, the `_vt_away_time` field.

## SSH access

`sudo chvt 2` from SSH switches the display but does NOT release the evdev grab, so the keyboard still sends to the app. Use the keyboard combos instead. (SSH users who need keyboard access on tty2 can also `sudo evdev-ungrab` or restart the app.)

## Debug ISO differences

The debug ISO additionally enables SysRq (`kernel.sysrq=1`), which provides a kernel-level escape hatch: Alt+PrtSc+R releases the evdev grab, then Ctrl+Alt+F2 works at the kernel level. See `guides/debug-shell-escape.md`. This is disabled in production so kids can't accidentally trigger SysRq sequences.

## Post-install reboot failure fallback

After install completes, Python `execv`s into `purple-reboot` (a static C binary on tmpfs). This binary shows "Press Enter to restart", waits for input, then calls `reboot(2)`. At this point:

- The Python process and evdev handler are gone (replaced by `execv`)
- X11 is still running with `K_OFF` on tty1 (no kernel VT switching)
- The standalone watcher may have SIGBUS'd if the USB was removed
- Normal VT switch mechanisms are unavailable

### Signal safety

The binary ignores terminal signals (SIGHUP, SIGQUIT, SIGINT, SIGTSTP) at startup. This is critical for surviving USB removal: when the USB is ejected, Alacritty SIGBUSes on dead overlayfs code pages and dies. The pty master side closes, and the kernel sends SIGHUP to the binary (foreground process on the slave pty). Without ignoring SIGHUP, the binary dies before reaching `reboot()`, xinitrc tries to restart, and the user is stuck on a blank purple screen (the X root window). SIGQUIT/SIGINT/SIGTSTP are also ignored so Ctrl+\, Ctrl+C, and Ctrl+Z from the pty can't kill it.

### Reboot fallback chain

If `reboot()` fails (setuid issue, security module, etc.):

1. Retry `reboot()` after 1 second
2. Try sysrq 'b' (hard reboot via `/proc/sysrq-trigger`)
3. If still alive: switch to tty2 via `VT_ACTIVATE` ioctl and print a message telling the user to hold the power button, with the support email

The tty2 switch works because `/dev/console` and `/dev/tty2` are on devtmpfs (survive USB removal), the `VT_ACTIVATE` ioctl bypasses `K_OFF`, and tty2 is in `K_UNICODE` mode so the user can type. The binary then loops on `pause()` so the message stays visible until the user power-cycles.

**File:** `tools/purple-reboot.c`, tests in `tools/test_purple_reboot.c` (`just test-reboot`)

## Key files

- `purple_tui/input.py`: `EvdevReader` class, VT switch detection in `_read_loop()`, grab management
- `tools/purple-reboot.c`: Static reboot binary with fallback chain
- `config/xinit/xinitrc`: X11 startup
- `build-scripts/00-build-golden-image.sh`: Golden image build
