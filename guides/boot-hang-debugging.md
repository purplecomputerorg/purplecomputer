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

For a slow (not hung) boot, `sudo purple-boot-timing` prints the lines that bound each phase as seconds since the kernel started, next to `systemd-analyze`, so the gap shows up without reading the raw log. `--timeline` prints just that part.

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
[HH:MM:SS.mmm] [+ 0.623s] [python] power_manager imported; importing .demo
[HH:MM:SS.mmm] [+ 0.640s] [python] .demo imported; importing rooms.art_room
[HH:MM:SS.mmm] [+ 0.660s] [python] rooms.art_room imported; importing rooms.parent_menu
[HH:MM:SS.mmm] [+ 0.675s] [python] rooms.parent_menu imported; importing room_picker
[HH:MM:SS.mmm] [+ 0.690s] [python] room_picker imported; importing repl_panel
[HH:MM:SS.mmm] [+ 0.701s] [python] all purple_tui imports done
[HH:MM:SS.mmm] [+ 0.712s] [python] PurpleApp.__init__ begin
[HH:MM:SS.mmm] [+ 0.984s] [python] PurpleApp.__init__ after App.__init__
[HH:MM:SS.mmm] [+ 1.210s] [python] PurpleApp.on_mount begin
[HH:MM:SS.mmm] [+ 1.880s] [python] PurpleApp.on_mount complete
[HH:MM:SS.mmm] [+ 1.880s] [python] first render reached; watchdog disarmed
```

If the log ends abruptly, **the last phase line is where the hang happened.** That's the whole design.

---

## Customer path: every stick writes its own report

A customer cannot read tty2 or photograph a scrolling log, so a hang report from the field used to mean days of back and forth. Two mechanisms now cover both failure shapes in one round trip.

**`PURPLE-LOG.TXT` on the stick, every live boot.** `purple-diag-dump.service` (`scripts/purple-diag-dump.sh`, live boots only) rewrites that file on the stick's third partition every 5s for the first five minutes of uptime, then once a minute: machine model and BIOS, cmdline, DRM connector state, PCI devices and drivers, failed units and pending jobs, `purple-x11` status, a process list with `wchan`, the boot, xinitrc, Xorg and power logs, and the journal and dmesg tails. The partition is mounted only for each write, so pulling power leaves it clean. The same text also lands at `/var/log/purple/diag.txt`. So the standard stick a customer already has holds the report of its last boot: no second stick needed for anything that got as far as systemd.

**The debug ISO for kernel-level hangs.** Its GRUB entry drops `quiet` and `console=tty63`, so if the kernel wedges before systemd, the last line on screen says where and a phone photo captures it. Its menu auto-continues after 5s.

**USB read errors (`SQUASHFS error: Failed to read block ...: -5`, `I/O error, dev loop0`).** Seen on a 2013 Vaio Pro 13 with two different sticks failing at the same block on both ports, so it was the laptop, not the media. The debug menu's second entry, "try everything", stacks every workaround so the customer boots once: `intel_iommu=off` (the 24.04 kernel turns VT-d on by default, which Ubuntu warned breaks old firmware), `xhci_hcd.quirks=0x800000` (XHCI_NO_64BIT_SUPPORT, 32-bit DMA), `usbcore.autosuspend=-1`, `pcie_aspm=off`, and `purple.toram=1`, which makes the initramfs copy the squashfs into RAM in one sequential pass before casper mounts it (`add_purple_toram` in `01-remaster-iso.sh`; needs the squashfs plus 768M free, else it says so and reads from the stick). A copy that fails prints how many bytes were read before the error, which is the offset that broke, and the boot continues from the stick so the usual errors still show. `log_buf_len=8M` keeps the whole kernel log for the report. The entries after it try one workaround each for narrowing down later. `purple-diag-dump` starts right after udev rather than at multi-user so its 5s reports exist before a stick dies a minute into boot.

**Before systemd, and between snapshots.** The report script lives on the squashfs, so it cannot describe a boot that never mounted it. The initramfs hook (`purple_stick_report` in `add_purple_initramfs_hooks`, `01-remaster-iso.sh`) therefore writes its own `PURPLE-LOG.TXT` (casper's log plus dmesg) when the system image is found on the stick, again right before mounting it (after any RAM copy), and at the end of casper-bottom; the kernel has FAT built in and the initramfs carries `blkid`. `purple-diag-dump` replaces that file seconds later, so finding the initramfs version on a stick means boot stopped between those points. The snapshot's 5s window is covered by `purple-kmsg-stream` (`scripts/purple-kmsg-stream.py`, same unit conditions): at start it mounts `PURPLEUSB` read-only once, finds the sectors of the preallocated 4MB `PURPLE-KMSG.TXT` with `FIBMAP`, unmounts, and from then on writes `/dev/kmsg` lines straight into those sectors of the partition device with `fdatasync`, flushing at most once a second for the first five minutes and every 5s after, only when new lines arrived. No filesystem stays mounted and no FAT metadata changes, so a power cut never dirties the partition; the file's date stays the build date. When it fills it wraps to the top with a marker line. The remaining blind spot is a stick that stops accepting writes altogether, where the screen is the only record.

**The `PURPLEUSB` partition** (`01-remaster-iso.sh`) is a 16MB FAT volume typed as Microsoft basic data. That type is the point: Windows and macOS hide EFI System Partitions, so the report could not live on partition 2. Both desktops mount `PURPLEUSB` like a thumb drive. Since it is also what a parent sees when they plug the stick into a running computer, it carries `HOW TO START PURPLE.txt` (shut down, leave it in, turn on, F12 or Option) and an `autorun.inf` whose label makes Explorer show the drive as "Start Purple Computer". `flash-lib.sh`'s post-settle recheck compares only partitions 1 and 2, since the settle boot writes here too.

What to tell the customer: after it gets stuck, wait two minutes, hold the power button until it turns off, plug the stick into your usual computer, open the drive named `PURPLEUSB`, and email `PURPLE-LOG.TXT`. Warn them about the other partitions: Windows may ask to format a disk and a Mac may say a disk is not readable; answer Cancel or Ignore, never Format or Initialize. If the file is missing, the kernel never reached systemd: send the debug stick and ask for a photo of the screen.

Confirm the layout on a fresh ISO with `xorriso -indev <iso> -report_system_area plain`: partition 3 must show type GUID `a2a0d0eb...` (basic data).

---

## The startup watchdog

A daemon thread started in `boot_log.py` at module import time. It sleeps in 1-second increments, checking a `_first_render_done` flag. At deadlines **10s, 20s, 40s, 80s** from process start, if first render hasn't happened, the watchdog calls `faulthandler.dump_traceback(all_threads=True)` against the boot log file.

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

**Why four deadlines and not one?** A progression tells you what kind of hang it is. If the 10s dump shows thread A blocked on lock L and the 20s dump shows it still there on the same line, it's truly wedged. If 20s shows it moved, it's slow but progressing.

---

## On-demand thread dump (`dump-purple`)

When you suspect a hang *right now* and don't want to wait for the next watchdog deadline, trigger a dump manually from tty2:

```
dump-purple
```

The helper (installed at `/usr/local/bin/dump-purple`) finds the running `purple_tui.purple_tui` process, sends it SIGUSR1, and tails the boot log. `boot_log.py` registers `faulthandler` on SIGUSR1 at startup, so every thread's stack lands in `/var/log/purple/boot.log` without killing the process. You can dump repeatedly to watch a deadlock evolve (or not).

Use this to distinguish:

- **Futex wait in main thread + a C-ext thread blocked on a socket** → classic audio/IPC init deadlock (pygame, pulse, pipewire).
- **Main thread in `_find_and_load` / `_call_with_frames_removed`** → blocked inside an import, usually on disk I/O or a decorator doing AST rewriting at module scope.
- **Main thread waiting on its own lock + no other thread making progress** → Python import-lock + thread-started-during-import race.

SIGUSR1 is passive (zero cost until fired), so this ships in both ISOs.

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

### 3. Ctrl+Alt+F2 into tty2

On laptops with real function keys, `Ctrl+Alt+F2` switches to tty2. From there: `cat /var/log/purple/boot.log` for the currently-hung boot, or any of the other diagnostic commands.

**Touch Bar Macs (no physical F-keys):** keyd remaps Right Alt to F2 at the kernel level (`config/keyd/default.conf`), so press `Ctrl+Alt+RightAlt` to reach tty2. No USB keyboard needed. See the "keyd at boot time" section below. If keyd is not running (dev, VMs, or a broken golden image), there is no F2 without a USB keyboard, so fall back to option 2.

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
| `power_manager imported; importing demo + rooms + repl` (nothing after) | one of `demo/`, `rooms/`, `room_picker`, `repl_panel`. **Historical cause:** `rooms/__init__` → `play_room` → `content` → `inflect` → `typeguard` AST rewriting at ~3s of CPU; see "Case study" below. Check first if a new import somewhere in this chain pulls a package that decorates with `typeguard.@typechecked`. |
| `PurpleApp.__init__ begin` (nothing after) | App() superclass, CSS parsing, Textual App setup |
| `PurpleApp.__init__ after App.__init__` (nothing after) | our `__init__` — keyboard state machine, `detect_keyboard_mode()` which opens evdev, power_manager, evdev readers |
| `PurpleApp.on_mount begin` (nothing after) | theme, `apply_saved_display_settings`, `set_logind_power_key`, settings file read, `_load_room_content` |

The **watchdog dump** narrows this further: it shows the exact line of Python the main thread is parked on.

---

## Case study: the 2016 Touch Bar MBP "hang" was inflect

**Symptom (April 2026).** Purple's boot log ended at `power_manager imported; importing demo + rooms + repl` and never advanced. `ps` showed the Python process alive at ~5% CPU, slowly accumulating CPU time without making progress. The user saw a blank purple screen for minutes.

**Root cause.** `rooms/__init__` imports `play_room`, which imports `content.py`, which did `import inflect` at module scope. `inflect` is a pluralization library that decorates its internals with `typeguard.@typechecked`. At import time, `typeguard` parses each decorated function's AST, rewrites it to inject runtime type checks, and compiles it back to bytecode. This is ~3 seconds of pure CPU work on a fast dev machine. On the 2016 MBP's USB-C-attached live USB, it ballooned into minutes because:

1. Python had to read `inflect`'s many small files from the slow USB
2. xinitrc's concurrent squashfs-to-tmpfs copy was contending for the same USB bandwidth
3. The 5% CPU measurement reflected "mostly blocked on `read()`, occasional AST work" — looked like a hang but wasn't

The 2015 MBP didn't exhibit the hang because its Intel USB 3.0 controller was fast enough to finish the squashfs cp before Python needed to read any inflect files, so Python read from tmpfs (memory speed) and the ~3s cost was tolerable.

**How we found it.** `cProfile` around the import of `rooms.art_room` in a dev-machine REPL:

```python
import cProfile, pstats, io
pr = cProfile.Profile()
pr.enable()
from purple_tui.rooms.art_room import ColorLegend
pr.disable()
pstats.Stats(pr).sort_stats('cumulative').print_stats(30)
```

The profile showed ~2.9s cumulative in `inflect/__init__.py` → `typeguard/_decorators.py:typechecked` → `ast.visit` / `fix_missing_locations` / `compile`.

**The fix.** `purple_tui/content.py` now lazy-loads `inflect` via a `@functools.cache`-decorated zero-arg factory (`_inflect_engine`), and `PurpleApp.on_mount` spawns a daemon thread that calls `warm_inflect_engine()` after `mark_first_render()`. First REPL plural lookup is instant because the engine is already warm by the time a kid types anything; boot time drops by ~1.4s on every machine.

---

## Case study: the same MBP *also* hung on pygame.mixer.init

After the inflect fix, the same 2016 MBP still hung at boot. Root cause: `pygame.mixer.init()` calls SDL2 → PulseAudio/ALSA → kernel audio driver. On T1/T2 MBPs the Cirrus CS8409 codec blocks forever in `snd_pcm_open()`. On a 2015 MacBook Air (plain Intel HDA + CS4208) the same call returns in milliseconds.

**The fix (current architecture).** `rooms/music_room.py` lazy-loads pygame. `warm_mixer()` runs a **subprocess probe**: it spawns a fresh Python process that attempts `mixer.init()` + `mixer.quit()`, with a 10-second timeout. If the subprocess exits 0, the in-process `mixer.init()` follows (safe because the subprocess proved the hardware works). If it times out, `_PROBE_TIMED_OUT` is set and the mixer is marked as broken.

**Why `subprocess.run` is wrong here, and `Popen` + abandon is right.** A genuinely wedged CS8409 leaves the probe child in uninterruptible **D-state** inside the kernel's `snd_pcm_open()`. SIGKILL cannot reap a D-state task. `subprocess.run(timeout=...)` reacts to a timeout by calling `kill()` then a **blocking `wait()`** to reap, and that `wait()` hangs forever on the unkillable child, so `warm_mixer()` never returns and `audio_ok` stays `None`: the screen shows "Audio: checking..." with no resolution (observed on a MacBookPro13,2). The hang is in a separate process, not ours, so the fix is to stop waiting on it: `Popen` + `proc.wait(timeout=...)` (which polls and always returns at the deadline), then on timeout `kill()` and **abandon** the child (a daemon `_reap_orphan` thread collects it if the kernel ever lets go). `_start_mixer_warmup`'s `_warm()` is also wrapped so any unexpected error fails safe to `audio_ok = False` rather than leaving it `None`.

**Retry logic** (in `purple_tui.py:_start_mixer_warmup`): PulseAudio/ALSA may still be initializing at boot, so a fast failure (exit code ≠ 0, not a timeout) triggers retries with delays of 1s, 2s, 4s. `_reset_mixer_state()` clears the cached failure between retries but refuses to reset after a timeout (returns False), so broken hardware stops after one 10s attempt.

**Timing in practice:**

| Scenario | What happens | Time to result |
|---|---|---|
| Audio works immediately (most hw) | Probe succeeds on attempt 1 | ~1s |
| PulseAudio slow at boot (MacBookAir7,2) | Attempt 1 fails fast, retry after 1s succeeds | ~2s |
| PulseAudio very slow (worst case) | All retries needed (1+2+4s delays) | ~9s |
| Hardware broken/hanging (CS8409 MBP) | Probe child wedges in D-state, abandoned at 10s timeout, no retry | ~10s |
| `PURPLE_NO_AUDIO=1` (testing) | No probe, no thread | 0s |

During the retry window, `audio_ok` is `None`. The splash screen shows no audio warning (only appears after confirmed failure). The room picker shows normal "Volume" button. Once `audio_ok` becomes `False`, the splash shows the 🔇 warning and the room picker shows disabled "No Sound."

**Boot log lines to look for:**

```
mixer ok (attempt 1)              # happy path
mixer probe failed, retrying in 1s  # PulseAudio not ready, will retry
mixer ok (retry)                  # retry succeeded
mixer probe timed out (hw broken) # CS8409-style hang, gave up
mixer warmup failed               # all retries exhausted
mixer disabled (PURPLE_NO_AUDIO=1) # env var override
```

### Known audio-risk hardware

Machines where the audio probe path is known to be slow or blocking, so the lazy-mixer / warmup-timeout / modal fallback matters:

- **All T1/T2 Macs** — 2016+ MBP, 2018+ MBA, iMac Pro, 2018+ Mac mini, 2020 iMac. CS8409 via Apple T1/T2 SPI.
- **Surface Pro / Surface Laptop** — SoundWire + Surface Aggregator. Probe can stall for seconds.
- **Newer Intel laptops using SOF** — Dell XPS 13 (9300+), Lenovo X1 Carbon 9th gen+, Framework 13/16, most 2021+ thin-and-lights. Needs `intel/sof*` firmware (kept) and `cirrus/`/`realtek/` codec amp blobs (also kept) — both preserved in `00-build-golden-image.sh`'s firmware prune whitelist.
- **AMD laptops with ACP** — ThinkPad Z13, Yoga 7/9 AMD, EliteBook G9 AMD, Framework AMD. Young driver, flaky init.

Plain Intel HDA codec laptops (pre-2020 ThinkPads/Dells/HPs) don't need per-codec firmware and don't hit this path.

### The silent-but-not-hanging case (CS8409 on newer kernels)

The timeout guard above assumes broken audio *hangs*. That assumption broke once the mainline `snd_hda_codec_cs8409` driver matured: on some MacBook Pros it now binds the codec without blocking, runs a *generic* autoconfig (`speaker_outs=0`, no model quirk matched), and returns from `mixer.init()` in milliseconds. The probe passes, so the old code reported "Audio: working" while the speakers stayed dead. The CS8409 is only an HDA-to-I2C bridge; the real amp lives on an I2C side-channel the generic driver never powers on, so ALSA accepts frames into a dead amp.

No software probe can observe this, because ALSA reports success whether or not the amp is alive. A test tone gives the same false confidence as `init()`. So detection gates on **codec identity**, not topology: `output_is_known_silent()` (in `rooms/music_room.py`) reads `/sys/class/sound/hwC*D*/chip_name`, and if a codec in `_SILENT_HDA_CODECS` is present with no USB audio adapter, `warm_mixer()` returns False up front (no probe, no retry) and `audio_ok` becomes False, so the parent gets the "plug in a USB speaker" path.

Why not gate on `speaker_outs=0`? It both over- and under-fires: plenty of working machines (headphone/line-out-only, HDMI, USB) report `speaker_outs=0`, and on this very MBP the internal speaker pins were filed under `line_outs` anyway. It also only lives in privilege-gated dmesg. Codec name from sysfs is unprivileged and stable. A USB adapter clears the veto (it's a real output Pulse routes to), and the hotplug re-probe re-evaluates, so plugging a speaker in flips audio back on without a restart.

---

## Rule: don't do heavy work at module import time

This bug was latent for months before the 2016 MBP surfaced it. Similar bugs will keep showing up unless we audit imports. The rule:

1. **Module bodies should only contain imports, class definitions, function definitions, and cheap constants.** No calls to anything expensive at module scope.
2. **Be especially suspicious of third-party packages that decorate with `@typechecked`, `@beartype`, `@validate_call`, or any runtime-type-check library.** These typically do AST rewriting at decoration time, which runs at import time of the decorating module.
2b. **Also suspicious: C extensions that open hardware, sockets, or daemons at import or module-scope `init()`.** pygame/SDL, pyaudio, sounddevice, cv2 (with GStreamer), pyserial on a port, any ML runtime that probes GPUs. These can block in C while holding the GIL, starving Python threads (including our boot watchdog). Lazy-load them and run any `init()` on a daemon thread with a timeout.
3. **Before adding a new pip dependency, measure its cold import time.** Any new package whose import takes >100ms on a fast machine should be imported lazily.

**One-liner to measure an import:**

```
.venv/bin/python3 -c "import time; t=time.monotonic(); import PACKAGE; print(f'{PACKAGE}: {time.monotonic()-t:.3f}s')"
```

Or profile what's inside the import:

```
.venv/bin/python3 -X importtime -c "import PACKAGE" 2>&1 | sort -t'|' -k2 -n | tail -20
```

**If a heavy package is unavoidable, lazy-load it:**

```python
from functools import cache

@cache
def _thing():
    import expensive_package
    return expensive_package.make_thing()

def public_api(x):
    return _thing().do(x)
```

And if first-call latency matters, warm the cache from a daemon thread after first render (pattern in `purple_tui.py` `on_mount`).

---

## Logging policy (important)

This instrumentation follows the project's logging rules:

- **Standard + debug ISO both get the boot log**, because the writes are non-visual (file descriptors, never stdout/stderr), non-expensive (cheap appends + a sleeping thread), and non-interfering (no subprocesses, no stderr spam, no impact on Textual's display).
- **Only debug ISO gets heavy diagnostics** like `xrandr`, `glxinfo`, `xdotool`, or any subprocess-spawning or screen-painting output. These are gated on `/opt/purple/debug`.
- **Exception**: user-facing error/diagnostic scroll screens (like `purple-x11-failed`) are visual but ship on both ISOs, because diagnosing those failures matters more than hiding them.

When adding new instrumentation, ask: "is this write-to-fd, cheap, and invisible?" If yes, it can ship on standard. If no, gate it on debug.

---

## keyd at boot time

Full rationale (why keyd, why not systemd-hwdb, the Apple SPI gotcha): see [keyboard-architecture.md § Remap Layer Choice](keyboard-architecture.md#remap-layer-choice).

This section covers the boot-debugging angle: what keyd does to the startup path, how to tell whether it's working during a hang, and what to check first when a keyboard is silent.

### What keyd adds to the boot path

`keyd.service` is enabled on the golden image and starts during `multi-user.target`. `purple-x11.service` has `After=keyd.service` (advisory). On the happy path, keyd grabs physical keyboards and creates its uinput device before Purple reaches `_find_keyboards()`. Purple sees `keyd virtual keyboard` in the device list and reads from it.

The startup race to watch for: `keyd.service` is `Type=simple`, so systemd considers it "started" the moment its main process forks, *before* keyd has enumerated inputs and created its uinput device. Purple's `_find_keyboards()` polls up to `KEYD_WAIT_SECS = 2.0` for the virtual device to appear when `/etc/keyd/default.conf` exists. If keyd is taking longer than 2 seconds to come up, Purple gives up waiting and falls through to physical keyboards (which keyd then grabs a moment later, causing a silent keyboard until the next reconnect).

### Verifying keyd at runtime during a hang

Get to a shell (tty2 via `Ctrl+Alt+RightAlt`, or the parent-menu shell on debug ISO), then:

```
systemctl status keyd                       # is it active?
ls /dev/input/by-id/ 2>&1 | grep -i keyd    # does the virtual device exist?
sudo keyd monitor                           # watch events live, press keys
```

Press grave — it should print `esc`. Press right alt — it should print `f2`. If either fails, the remap isn't being applied.

### Reading `purple-boot.log` for keyd status

`purple_tui/input.py:_find_keyboards()` logs every device it opens. In the boot log you want to see:

```
KBD SCAN: strict via scan: /dev/input/eventN (keyd virtual keyboard)
```

If instead you see only `KBD SCAN: strict via scan: /dev/input/eventN (Apple SPI Keyboard)` (or similar physical-keyboard name) with no `keyd virtual keyboard` entry, keyd's virtual device isn't present. Check in order:

1. `systemctl status keyd` — did it fail to start? Read `journalctl -u keyd -b`.
2. `journalctl -b | grep keyd` — did it crash?
3. Did the `/etc/keyd/default.conf` ship to the image? `cat /etc/keyd/default.conf`.
4. Is `/usr/bin/keyd` present? Check the build ran `make install` successfully.

### When keyd is NOT running (dev, VMs, broken golden image)

Purple's `_find_keyboards()` falls through to the existing physical-keyboard scan. No grave→Esc remap, no RightAlt→F2 remap. Use the real Escape and (if present) real F2. On dev machines this is the intended behavior; on a broken golden image it's a signal that something in the keyd install pipeline failed.
