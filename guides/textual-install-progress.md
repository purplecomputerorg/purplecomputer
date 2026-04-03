# Textual Install Progress Screen

How the install progress modal works and why it's built the way it is.

---

## What it does

`InstallProgressScreen` (in `purple_tui/rooms/parent_menu.py`) is a Textual `ModalScreen` that:

1. Runs `install.sh` as a subprocess in a background thread
2. Streams `[PURPLE]`-prefixed stderr lines to update a progress bar
3. When install finishes, exits Textual and `execv`s into a static reboot binary on tmpfs
4. The binary (with `--wait`) shows "press Enter to restart", waits, then reboots

Textual stays running the whole time. There is no terminal handoff.

---

## Why a daemon thread, not asyncio subprocess

The first implementation used `asyncio.create_subprocess_exec`. Python 3.13 introduced regressions that caused cascading hangs:

- **`proc.wait()` hangs:** asyncio ties it to pipe state, not process state.
- **`proc.returncode` never set:** `install.sh` spawns `setsid bash` on tty2, which keeps the bash wrapper alive as a child even after `install.sh` exits. asyncio never gets SIGCHLD from the wrapper.
- **`StreamReader.read()` can't be cancelled:** `stderr_task.cancel()` + `await stderr_task` would hang. Omitting the await left a dangling task.
- **`sudo` from within Textual hangs:** DNS resolution, PAM, and terminal state checks inside sudo all block when called from the Textual event loop.

The fix: `threading.Thread(daemon=True)` + `subprocess.Popen` + `select.select`. Synchronous subprocess in a thread has none of these issues. UI updates go via `app.call_from_thread()`.

```python
def on_mount(self) -> None:
    self._update_ui()
    threading.Thread(target=self._run_install_thread, daemon=True).start()

def _run_install_thread(self) -> None:
    _SENTINEL = Path('/run/purple-install-complete')
    proc = subprocess.Popen(
        ["sudo", "-E", "bash", "/cdrom/purple/install.sh"],
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        env={**os.environ, "PURPLE_PAYLOAD_DIR": "/cdrom/purple"},
    )
    buf = b""
    while proc.poll() is None and not _SENTINEL.exists():
        ready = select.select([proc.stderr], [], [], 0.1)[0]
        if ready:
            chunk = proc.stderr.read(256)
            if chunk:
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    self.app.call_from_thread(
                        self._handle_line,
                        line.decode('utf-8', errors='replace'),
                    )
    success = _SENTINEL.exists() or proc.poll() == 0
    self.app.call_from_thread(self._on_install_complete, success)
```

Key design points:

- `select.select(..., timeout=0.1)`: non-blocking stderr poll. The loop exits as soon as the sentinel appears, even if the bash wrapper is still alive.
- `proc.poll()`: synchronous, never blocks.
- Daemon thread: dies automatically if the app exits. Never needs to be joined.
- No sudo after install.sh: all root work is done by install.sh before it signals done.

---

## Completion detection: the sentinel file

`proc.returncode` is unreliable as the completion signal because `setsid bash` on tty2 keeps the bash wrapper alive after `install.sh` exits. Instead, `install.sh` writes `/run/purple-install-complete` as its last act before `exit 0`.

Python polls for this sentinel. When it appears, the install is done regardless of what `proc.poll()` returns.

---

## USB removal safety

After install, the USB drive can be removed and the system must still reboot cleanly.

### The core problem

After USB removal, the live overlayfs is dead. Any page fault to code not already in memory hangs forever (kernel tries to read from the removed USB's squashfs). This means Python's event loop, Textual, and any new binary loading all hang. Python cannot process keypresses or exec new binaries after USB removal.

### The solution: static binary that does everything

The only thing that reliably runs after USB removal is a statically linked binary on tmpfs. Even `/bin/sh` gets SIGBUS because its code pages fault on the dead overlayfs.

1. `install.sh` (running as root, USB still present) writes to `/run` (tmpfs):
   - `/run/purple-reboot-mount/purple-reboot`: static setuid binary that calls `reboot(2)` directly
   - `/run/purple-install-complete`: sentinel (written last)
2. Python detects the sentinel, exits Textual, calls `os.execv` on the binary with `--wait`
3. The binary ignores terminal signals (SIGHUP, SIGQUIT, SIGINT, SIGTSTP) so it survives pty hangup when Alacritty dies after USB removal
4. The binary (on tmpfs, statically linked) shows "press Enter to restart" and waits
5. User removes USB drive whenever they want. Alacritty SIGBUSes on dead overlayfs and its pty closes, but the binary survives (SIGHUP ignored, code on tmpfs)
6. User presses Enter (or read() returns EOF from dead pty). Binary calls `sync()` then `reboot(RB_AUTOBOOT)`. Machine reboots.

If `reboot()` fails (setuid issue, security module, hardware quirk), the binary falls back through:
1. Retry `reboot()` after 1 second
2. sysrq 'b' (hard reboot via `/proc/sysrq-trigger`)
3. Switch to tty2 via `VT_ACTIVATE` ioctl, print a message telling the user to hold the power button and providing the support email, then loop on `pause()` so the message stays visible

The tty2 fallback works even with X11's `K_OFF` on tty1 because `VT_ACTIVATE` is a kernel ioctl that bypasses keyboard mode. `/dev/console` and `/dev/tty2` are on devtmpfs, so they survive USB removal. Without this fallback, a failed `reboot()` causes the binary to exit, xinitrc restarts the app, and the user is stuck on a purple screen with no way to escape.

### Why a dedicated tmpfs mount

Ubuntu mounts `/run` with `nosuid,noexec`. systemd manages it and resists remounting. So `install.sh` creates its own tmpfs at `/run/purple-reboot-mount` with `exec,suid` flags for the setuid reboot binary.

### Approaches that didn't work

- **FIFO watcher**: pre-forked root shell blocking on a FIFO. Killed by sudo's process group cleanup, FIFO permission issues, dead watchers.
- **Handling Enter in Textual after USB removal**: Python's event loop hangs on overlayfs page faults, so `handle_keyboard_action` never runs.
- **Shell script on tmpfs**: `/bin/sh` itself gets SIGBUS after USB removal (code pages not fully loaded).
- **Remounting `/run`**: systemd re-applies `nosuid,noexec` silently.

---

## Progress bar stages

`_handle_line()` matches `[PURPLE]`-prefixed log lines from `install.sh` against `_INSTALL_STAGES`:

```python
_INSTALL_STAGES = [
    ("Detecting internal disk",   5,  "Getting started..."),
    ("Found internal disk",       8,  "Getting started..."),
    ("Writing Purple Computer",   12, "Setting up Purple Computer..."),
    ("Reloading partition table", 82, "Double-checking everything..."),
    ("Verifying disk write",      85, "Double-checking everything..."),
    ("Disk verification passed",  90, "Double-checking everything..."),
    ("Setting up UEFI boot",      92, "Almost ready..."),
    ("UEFI boot setup complete",  97, "Almost ready..."),
]
```

Progress only moves forward (enforced by `pct > self._progress`). The friendly display strings are what the user sees, no technical jargon.

---

## Shutdown paths overview

All shutdown and reboot paths on Purple Computer:

| Trigger | Entry point | Mechanism |
|---------|------------|-----------|
| Idle timeout (battery) | `SleepScreen._do_shutdown()` | `pm.shutdown()` |
| Lid closed 10min | `SleepScreen._check_idle_shutdown()` | `pm.shutdown()` |
| Power button tap+confirm | `ByeScreen.on_mount()` | `pm.shutdown()` |
| Power button hold 3s | `ByeScreen.on_mount()` | `pm.shutdown()` |
| Parent menu "Shut Down" | `ParentMenu._shutdown()` | `pm.shutdown()` |
| Post-install Enter | `InstallProgressScreen._on_install_complete()` | `execv` into static reboot binary on tmpfs |

`pm.shutdown()` uses `sudo systemctl poweroff --force` with a two-stage watchdog: stage 1 (5s) retries systemctl, stage 2 (8s) uses sysrq 'o' (direct kernel poweroff via ACPI). The watchdog runs in a detached process group so it survives TUI death.

All shutdown commands use `sudo` because `systemctl poweroff` without sudo fails with permission denied on the live USB (and Popen doesn't detect this since it only checks if the process spawned, not if it succeeded). The purple user has passwordless sudo everywhere via `/etc/sudoers.d/purple-nopasswd`.

Shutdown events are always logged to `/tmp/purple-power.log` for diagnostics.

---

## Tests

`tests/test_install_progress.py` documents the pipe-hang bug and proves the fix:

- `test_eof_only_hangs_with_pipe_holder`: proves the old asyncio pattern hangs (test passes by timing out in 3s)
- `test_cancel_on_exit_completes_with_pipe_holder`: proves `proc.returncode` polling completes even when a child holds stderr open
- `test_cancel_on_exit_collects_all_lines_without_pipe_holder`: sanity check for the normal case

`tests/test_install_reboot.py` covers the reboot flow:

- Bash end-section: sentinel write, reboot script creation, idempotency
- Full flow integration: mock install.sh + sentinel detection
- Pipe-holding child doesn't block sentinel detection
- Sentinel detection polling loop

Run with: `just test`, or `pytest tests/test_install_reboot.py -v`

---

## Files

| File | Role |
|------|------|
| `purple_tui/rooms/parent_menu.py` | `InstallProgressScreen`, `_trigger_reboot()` |
| `purple_tui/power_manager.py` | `PowerManager.shutdown()`, always-on shutdown logging |
| `build-scripts/install.sh` | Copies setuid reboot binary to `/run`, writes sentinel |
| `build-scripts/00-build-golden-image.sh` | Compiles static reboot binary during image build |
| `tools/purple-reboot.c` | Source for static reboot binary (fallback chain, tty2 escape) |
| `tools/test_purple_reboot.c` | C tests for reboot binary (`just test-reboot`) |
| `config/xinit/xinitrc` | Squashfs tmpfs copy (replaces page cache warmup) |
| `tests/test_install_progress.py` | Documents and tests the pipe-hang fix |
| `tests/test_install_reboot.py` | Tests the reboot flow and sentinel detection |
