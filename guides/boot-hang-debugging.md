# Debugging Boot Hangs

When Purple fails to fully start on live boot — you see alacritty (a cursor, maybe a partial render, or typed characters echoing back at you) but Textual never appears — this guide tells you where the logs are and how to read them.

See also: `guides/boot-display-sequence.md` (normal boot path), `purple_tui/boot_log.py` (the module doing the instrumentation).

---

## The boot log

**Always-on, every boot, standard + debug ISO.** Two destinations, same format:

| Path | Standard ISO | Debug ISO | Survives reboot? |
|---|---|---|---|
| `/tmp/purple-boot.log` | tmpfs | tmpfs | No |
| `/var/log/purple/boot.log` | tmpfs (effectively the same as above) | **ext4 on the casper `writable` USB partition** | **Yes, on debug ISO** |
| `journalctl -t purple-boot` | volatile journal | volatile journal | Depends on `Storage=` in `journald.conf` |

On xinitrc entry, `boot.log` is rotated to `boot.log.prev` — so after a hang + power cycle + boot, the previous boot's full trace lives at `/var/log/purple/boot.log.prev`.

**Writers (in order of appearance in a normal boot):**

1. `purple-wait-display.sh` — logs `[wait-display]` lines from systemd's `purple-x11.service` ExecStartPre. Connector states at start and timeout.
2. `config/xinit/xinitrc` — logs `[xinitrc]` lines for every phase of X/WM/audio/alacritty startup.
3. `/usr/local/bin/purple` (the bash launcher inside alacritty) — logs `[launcher]` lines immediately before `exec python3`.
4. `purple_tui/boot_log.py` — logs `[python]` lines at every import checkpoint, `PurpleApp.__init__`, and `on_mount`.

A normal successful boot produces something like:

```
[HH:MM:SS.mmm] [wait-display] === purple-wait-display started === kernel=6.8.0-31-generic
[HH:MM:SS.mmm] [wait-display] Display ready: card0-eDP-1 (waited 0 half-seconds = 0.0s)
[HH:MM:SS.mmm] [xinitrc] === xinitrc started ===  debug_flag=no
[HH:MM:SS.mmm] [xinitrc] X server ready (after 1s wait)
[HH:MM:SS.mmm] [xinitrc] unclutter started
[HH:MM:SS.mmm] [xinitrc] matchbox-window-manager started
[HH:MM:SS.mmm] [xinitrc] Font size: 16
[HH:MM:SS.mmm] [xinitrc] Launching Alacritty...
[HH:MM:SS.mmm] [launcher] launcher entered pid=1234
[HH:MM:SS.mmm] [launcher] exec python3 -m purple_tui.purple_tui
=== purple python starting at ... pid=1234 python=3.12.3 ===
[HH:MM:SS.mmm] [+ 0.002s] [python] boot_log module imported; watchdog arming
[HH:MM:SS.mmm] [+ 0.003s] [python] watchdog armed
[HH:MM:SS.mmm] [+ 0.003s] [python] purple_tui entry: beginning stdlib imports
[HH:MM:SS.mmm] [+ 0.011s] [python] stdlib imports done; importing textual
[HH:MM:SS.mmm] [+ 0.520s] [python] textual/rich imports done; importing purple_tui.constants
[HH:MM:SS.mmm] [+ 0.540s] [python] constants imported; importing keyboard + input
[HH:MM:SS.mmm] [+ 0.612s] [python] keyboard + input imported; importing power_manager
[HH:MM:SS.mmm] [+ 0.623s] [python] power_manager imported; importing demo + rooms + repl
[HH:MM:SS.mmm] [+ 0.701s] [python] all purple_tui imports done
[HH:MM:SS.mmm] [+ 0.712s] [python] PurpleApp.__init__ begin
[HH:MM:SS.mmm] [+ 0.984s] [python] PurpleApp.__init__ after App.__init__
[HH:MM:SS.mmm] [+ 1.210s] [python] PurpleApp.on_mount begin
[HH:MM:SS.mmm] [+ 1.880s] [python] PurpleApp.on_mount complete
[HH:MM:SS.mmm] [+ 1.880s] [python] first render reached; watchdog disarmed
```

If the log ends abruptly, **the last phase line is where the hang happened.** That's the whole design.

---

## The startup watchdog

A daemon thread started in `boot_log.py` at module import time. It sleeps in 1-second increments, checking a `_first_render_done` flag. At deadlines **30s, 60s, 120s** from process start, if first render hasn't happened, the watchdog calls `faulthandler.dump_traceback(all_threads=True)` against the boot log file.

The dump is a full Python stack for every thread: main thread, Textual's render thread, evdev reader threads, asyncio loop, etc. Example of what a hang in `detect_keyboard_mode` would look like in the log:

```
[HH:MM:SS.mmm] [+30.001s] [python] WATCHDOG deadline 30s exceeded, dumping stacks
Thread 0x00007f... (most recent call first):
  File "/opt/purple/purple_tui/keyboard.py", line 812 in detect_keyboard_mode
  File "/opt/purple/purple_tui/purple_tui.py", line 763 in __init__
  ...
--- end dump at +30s ---
```

When `PurpleApp.on_mount` finishes, it calls `boot_log.mark_first_render()` which sets the flag; the watchdog wakes, sees the flag, and exits. Zero overhead after startup.

**Why three deadlines and not one?** A progression tells you what kind of hang it is. If the 30s dump shows thread A blocked on lock L and the 60s dump shows it still there on the same line, it's truly wedged. If 60s shows it moved, it's slow but progressing.

**Dump destination:** `faulthandler` requires a persistent file descriptor. We open `/var/log/purple/boot.log` (falling back to `/tmp/purple-boot.log`) and keep the fd open for the life of the process. The faulthandler is also armed for signals (SIGSEGV/SIGFPE/SIGBUS/SIGILL) against the same file, so a segfault during startup lands in the log instead of Textual's stderr.

---

## Reading the log after a hang

You hit a hang. The MBP is stuck on a cursor. Options, in order of ease:

### 1. Power cycle, boot again, read `boot.log.prev` (debug ISO only)

Hold the power button, power back on, boot the **debug ISO**. If the second boot succeeds, you can now read the failed boot's log from any shell:

```
cat /var/log/purple/boot.log.prev
```

The parent menu has a "Shell" option in debug mode that will drop you into bash. From there the file is readable.

If the second boot also hangs, you're in a loop. Go to option 2 or 3.

### 2. Pull the USB and read the log on a dev machine

The casper `writable` partition is a normal ext4 filesystem. Plug the USB into your Linux dev machine, mount the `writable` partition, and read `var/log/purple/boot.log.prev` directly. This works even if every boot on the target machine hangs.

```
# On the dev machine
lsblk                                  # find the USB (e.g. /dev/sdb)
mount /dev/sdb4 /mnt                   # casper writable is usually p4
cat /mnt/var/log/purple/boot.log.prev
```

### 3. Ctrl+Alt+F2 into tty2 (requires USB keyboard on Touch Bar Macs)

On laptops with real function keys (or Touch Bar Macs with a USB keyboard attached), `Ctrl+Alt+F2` switches to tty2. From there: `cat /var/log/purple/boot.log` for the currently-hung boot, or any of the other diagnostic commands.

**Touch Bar Macs without USB keyboard:** there is no key combo. F-keys don't exist as physical keys without the `apple-ib-tb` driver. Either use a USB keyboard or fall back to option 2. A planned fix uses `keyd` to remap a physical key (e.g. Right Alt) to F2 at the kernel level — see the "Planned: keyd remapping" section below.

---

## What each log line lets you localise

| Last line in log | Hang is likely in |
|---|---|
| `=== purple-wait-display started ===` (nothing after) | shell/dash itself, or systemd is not executing ExecStart |
| `Waiting for display...` with no "Display ready" | i915 async init, connector never reports `connected` |
| `=== xinitrc started ===` (nothing after) | X server is running but xinitrc is blocked extremely early |
| `matchbox-window-manager started` (nothing after) | font sizer, config copy, or alacritty exec |
| `Launching Alacritty...` (nothing after) | alacritty itself (font loading, GPU init, pty setup) |
| `launcher entered` (nothing after) | between bash and python interpreter — check PATH, libs, very rare |
| `exec python3 -m purple_tui.purple_tui` (nothing after) | Python interpreter startup, site-packages scan |
| `boot_log module imported` (nothing after) | the Python import machinery itself is broken — very rare |
| `stdlib imports done; importing textual` (nothing after) | first-time bytecode compilation of textual/rich, or the rich module doing something at import |
| `constants imported; importing keyboard + input` (nothing after) | `from .input import ...` — check for module-level evdev opens |
| `keyboard + input imported; importing power_manager` (nothing after) | power_manager's imports (dbus, upower, subprocess calls at import?) |
| `PurpleApp.__init__ begin` (nothing after) | App() superclass, CSS parsing, Textual App setup |
| `PurpleApp.__init__ after App.__init__` (nothing after) | our `__init__` — keyboard state machine, `detect_keyboard_mode()` which opens evdev, power_manager, evdev readers |
| `PurpleApp.on_mount begin` (nothing after) | theme, `apply_saved_display_settings`, `set_logind_power_key`, settings file read, `_load_room_content` |

The **watchdog dump** narrows this further: it shows the exact line of Python the main thread is parked on.

---

## Logging policy (important)

This instrumentation follows the project's logging rules:

- **Standard + debug ISO both get the boot log**, because the writes are non-visual (file descriptors, never stdout/stderr), non-expensive (cheap appends + a sleeping thread), and non-interfering (no subprocesses, no stderr spam, no impact on Textual's display).
- **Only debug ISO gets heavy diagnostics** like `xrandr`, `glxinfo`, `xdotool`, or any subprocess-spawning or screen-painting output. These are gated on `/opt/purple/debug`.
- **Exception**: user-facing error/diagnostic scroll screens (like `purple-x11-failed`) are visual but ship on both ISOs, because diagnosing those failures matters more than hiding them.

When adding new instrumentation, ask: "is this write-to-fd, cheap, and invisible?" If yes, it can ship on standard. If no, gate it on debug.

---

## keyd: kernel-level remapping

### Why

The old Python-side grave/tilde → Escape remap in `keyboard.py` only worked while Purple was running. If Purple hung on startup, there was no Escape key. And on Touch Bar MacBooks there are no F-keys at all, so `Ctrl+Alt+F2` to reach tty2 was physically impossible without a USB keyboard.

Both problems have the same fix: a keymap daemon that sits below every application. `keyd` runs as a systemd service, grabs every matching keyboard via `EVIOCGRAB`, and re-emits remapped events through a uinput virtual device. Because it runs at the kernel level, the remaps work at a rescue shell, in systemd emergency mode, at a getty, inside Purple, *and before Purple even starts*.

### Config

`/etc/keyd/default.conf` (shipped from `config/keyd/default.conf` in the repo):

```
[ids]
*

[main]
grave = esc
102nd = esc
rightalt = f2
```

- `grave = esc` / `102nd = esc` — tilde/grave (and the ISO non-US backslash scancode some Apple keyboards emit for that key) act as Escape always. Covers both PC and Mac layouts in one config.
- `rightalt = f2` — makes `Ctrl+Alt+RightAlt` act as `Ctrl+Alt+F2`, the standard Linux tty2 switch chord. Left Alt is untouched, so normal Alt combos still work.

### How Purple's keyboard reader cooperates

When keyd is running, the physical `/dev/input/event*` keyboard nodes are `EVIOCGRAB`'d and return zero events to any other reader. If Purple opened *only* a grabbed device it would see a silent keyboard. But there's also an inverse failure: if we used *only* keyd's virtual device and keyd had failed to grab some exotic physical keyboard (Apple SPI, etc.), we'd have no real keyboard behind the virtual device and input would also be dead.

`purple_tui/input.py:_find_keyboards()` handles both failure modes by **adding keyd's virtual device to the keyboard list and then still falling through to the existing physical-device scan**. The result:

- If keyd grabbed every physical keyboard: virtual device delivers all events, physicals emit nothing (grabbed), no doubling.
- If keyd grabbed some but not all: virtual device delivers events for the grabbed ones, ungrabbed physicals deliver their own events. No key press can come out of both paths at once.
- If keyd is not running / config absent: physical keyboards work as before, same code path as dev machines and VMs.

The function also **polls briefly for the keyd virtual device at startup** (up to 2 seconds) when `/etc/keyd/default.conf` exists. This closes a startup race: `purple-x11.service` has `After=keyd.service`, but `keyd.service` is `Type=simple`, so systemd considers it "started" the moment its main process forks — before keyd has actually enumerated inputs and created its uinput device. Without the poll, Purple could scan past keyd's startup, pick up physicals, and then have keyd grab them a moment later, leaving Purple with a silent keyboard until the next reconnect. The poll is skipped entirely if `/etc/keyd/default.conf` is absent, so dev machines pay zero cost.

`purple-x11.service` has `After=keyd.service` (advisory, not `Requires=`) so Purple still boots on machines where keyd is disabled or fails to start. The poll plus the add-don't-replace device selection mean keyd being broken, slow, or missing some keyboards all degrade gracefully instead of bricking input.

### Verifying keyd is doing its job

On a running debug ISO, get to a shell (tty2 via `Ctrl+Alt+RightAlt`, or the parent-menu shell) and run:

```
systemctl status keyd
ls -la /dev/input/by-id/ | grep -i keyd
sudo keyd monitor             # shows events as keyd sees them
```

You should see `keyd.service` active and a `keyd-virtual-keyboard` device. `keyd monitor` lets you press keys and confirm the remaps are firing.

Inside Purple, `/tmp/purple-boot.log` will contain a line like `KBD SCAN: found keyd virtual keyboard: /dev/input/event23 (keyd virtual keyboard)` and `KBD SCAN: using keyd virtual keyboard exclusively; skipping physical device scan`. If you see `KBD SCAN: found via by-id` or `found via scan` *instead*, keyd is either not running or its virtual device hasn't appeared yet — check `systemctl status keyd` and the `After=keyd.service` ordering in `purple-x11.service`.

### When keyd is NOT running (dev, VMs)

Purple falls through to the existing physical-keyboard scan. The grave/tilde → Escape remap does NOT happen in this case — in dev mode you just use the Escape key directly. The Touch Bar F2 workaround also doesn't apply in dev (you have real F-keys on your development machine).
