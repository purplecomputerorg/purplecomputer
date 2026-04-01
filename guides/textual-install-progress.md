# Textual Install Progress Screen

How the install progress modal works and why it's built the way it is.

---

## What it does

`InstallProgressScreen` (in `purple_tui/rooms/parent_menu.py`) is a Textual `ModalScreen` that:

1. Runs `install.sh` as a subprocess in a background thread
2. Streams `[PURPLE]`-prefixed stderr lines to update a progress bar
3. Shows a success or error screen when the install finishes
4. On Enter: replaces Python with a RAM-resident sysrq reboot script

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

After install, the USB drive can be removed and the system must still reboot cleanly. This is the hardest constraint in the entire install flow.

### The core problem

Python runs as a regular user. Rebooting requires root (`reboot`, `systemctl reboot`, `/proc/sysrq-trigger` all need root). After USB removal, the live overlayfs backing is gone and loading ANY binary from disk (including `sudo`, `/bin/sh`, `reboot`) causes an infinite hang because the page fault tries to read from the dead squashfs on the removed USB.

So: unprivileged user + no way to escalate to root after USB removal.

### The solution: pre-forked root watcher

`install.sh` runs as root (via sudo). Before exiting, while the USB is still present, it forks a root shell that blocks on a FIFO in `/run` (tmpfs, RAM-only). This shell is already loaded in memory and needs no disk access to run.

The sequence:

1. `install.sh` (running as root) writes to `/run` (tmpfs):
   - `/run/casper-no-prompt`: suppresses the casper "remove media" prompt
   - `/run/purple-reboot-fifo`: a named FIFO
   - `/run/purple-install-complete`: the sentinel (written last)
   - A root shell is pre-forked via `setsid` to block on the FIFO
2. Python sees the sentinel, shows "Press Enter to restart"
3. User removes USB drive (optional)
4. User presses Enter, Python writes to the FIFO (pure tmpfs write, no overlayfs)
5. The root shell wakes up and runs `echo b > /proc/sysrq-trigger`
6. If FIFO fails for any reason, falls through to `PowerManager.shutdown()` which has a sysrq nuclear fallback (poweroff in 8s)

### Why `setsid` is critical

`install.sh` runs via `sudo -E bash install.sh`. When sudo exits, it kills its entire process group. A plain `&` background job is in the same process group and dies with it. `setsid` puts the watcher in its own process group so it survives.

This was discovered via debug logging on real hardware: `FIFO reader PIDs: NONE (watcher dead!)`.

### Why not simpler alternatives?

- **`os.execv('/bin/sh', ...)`**: must load `/bin/sh` from overlayfs. After USB removal, hangs.
- **`subprocess.run(['sudo', 'reboot'])`**: must load `sudo` from overlayfs. Same hang.
- **Software eject USB before reboot**: BIOS re-enumerates USB hardware on reboot regardless of OS-level eject. Would boot from USB again.
- **`efibootmgr --bootnext`**: viable for the USB-still-present case, but doesn't help if the user already removed the USB before pressing Enter.

### `_trigger_reboot()` safety

Python's `_trigger_reboot()` uses `O_NONBLOCK` when opening the FIFO. If the watcher is dead (no reader), `os.open` returns ENXIO immediately instead of blocking forever. On any failure (FIFO missing, watcher dead, not a FIFO), it falls through to `PowerManager.shutdown()` which has a sysrq nuclear fallback that works even with dead overlayfs.

### Debug logging

On debug ISO, `_trigger_reboot` writes breadcrumbs to `/tmp/purple-reboot-debug.log` at each step: stat, open, write, fallback. After install completes, it also logs whether the FIFO watcher is alive by scanning `/proc/*/fd/*` for readers. On debug ISO, a shell auto-opens after 30s idle on the success screen.

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

## Tests

`tests/test_install_progress.py` documents the pipe-hang bug and proves the fix:

- `test_eof_only_hangs_with_pipe_holder`: proves the old asyncio pattern hangs (test passes by timing out in 3s)
- `test_cancel_on_exit_completes_with_pipe_holder`: proves `proc.returncode` polling completes even when a child holds stderr open
- `test_cancel_on_exit_collects_all_lines_without_pipe_holder`: sanity check for the normal case

`tests/test_install_reboot.py` covers the FIFO reboot flow:

- Bash end-section: sentinel, FIFO creation (with setsid watcher)
- `_trigger_reboot()`: FIFO write, O_NONBLOCK, PowerManager.shutdown() fallback, dead watcher handling
- Watcher survival: proves watcher lives after parent bash exits (the `setsid` fix)
- Full flow integration: mock install.sh + sentinel detection + FIFO signal

Run with: `just test`, `just test-install`, or `pytest tests/test_install_reboot.py -v`

---

## Files

| File | Role |
|------|------|
| `purple_tui/rooms/parent_menu.py` | `InstallProgressScreen`, `_trigger_reboot()` |
| `build-scripts/install.sh` | Writes sentinel + FIFO + reboot script to `/run`, forks watcher |
| `tests/test_install_progress.py` | Documents and tests the pipe-hang fix |
| `tests/test_install_reboot.py` | Tests the FIFO reboot flow and watcher survival |
