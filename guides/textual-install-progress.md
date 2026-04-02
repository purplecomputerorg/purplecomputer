# Textual Install Progress Screen

How the install progress modal works and why it's built the way it is.

---

## What it does

`InstallProgressScreen` (in `purple_tui/rooms/parent_menu.py`) is a Textual `ModalScreen` that:

1. Runs `install.sh` as a subprocess in a background thread
2. Streams `[PURPLE]`-prefixed stderr lines to update a progress bar
3. Shows a success or error screen when the install finishes
4. On Enter: reboots via a static setuid binary on tmpfs

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

## USB removal safety: static reboot binary

After install, the USB drive can be removed and the system must still reboot cleanly. This is the hardest constraint in the entire install flow.

### The core problem

Python runs as a regular user. Rebooting requires root. After USB removal, the live overlayfs lower layer (squashfs on USB) is gone. Any page fault to code not in memory causes an infinite hang because the kernel tries to read from the dead squashfs on the removed USB. This means loading ANY binary from disk (including `sudo`, `/bin/sh`, `reboot`) can hang.

So: unprivileged user + no way to exec new binaries or escalate to root after USB removal.

### The solution: static setuid reboot binary on tmpfs

A tiny C program (~6 lines) calls `reboot(RB_AUTOBOOT)` directly via the kernel syscall. It's compiled statically (zero shared library dependencies) during the golden image build and placed at `/opt/purple/bin/purple-reboot`.

When `install.sh` runs as root (while USB is still present):
1. Remounts `/run` with `exec,suid` (Ubuntu mounts `/run` `nosuid,noexec` by default)
2. Copies the binary to `/run/purple-reboot` (tmpfs, RAM-only)
3. Sets it setuid root (`chmod 4755`)

When the user presses Enter to reboot:
1. Python calls `os.execv('/run/purple-reboot', ...)` 
2. The binary is on tmpfs (survives USB removal) and is static (no page faults to shared libs)
3. Setuid means it runs as root despite Python being unprivileged
4. It calls `sync()` then `reboot(RB_AUTOBOOT)` directly

If the binary is missing or not executable, falls through to `PowerManager.shutdown()` which has a sysrq watchdog fallback (powers off instead of rebooting, but the machine doesn't hang).

### Why this replaced the previous FIFO approach

The original approach pre-forked a root shell via `setsid` that blocked on a FIFO in `/run`. Python would write to the FIFO to trigger `sysrq-trigger` reboot. This was plagued with bugs:

- Process group kills: `sudo` killing the watcher on exit (fixed by `setsid` but fragile)
- Permission denied on FIFO writes
- Dead watchers with no recovery
- Complex debug logging and shell drop needed to diagnose failures
- Required `O_NONBLOCK` to avoid blocking when watcher died

The static binary approach eliminates all of this: one `os.execv` call with a PowerManager fallback. No background processes, no FIFOs, no process group management.

### Page cache vs tmpfs for squashfs caching

The system also copies the squashfs to tmpfs during boot (`config/xinit/xinitrc`). Unlike the previous `cat > /dev/null` page cache warmup, tmpfs pages are non-evictable. This keeps Python and the system alive after USB removal more reliably, since page cache entries can be evicted under memory pressure.

On low-RAM systems (< squashfs + 1GB available), falls back to the old page cache warmup.

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
| Post-install Enter | `InstallProgressScreen` | `_trigger_reboot()` → setuid binary |

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

- Bash end-section: sentinel write, reboot binary creation, idempotency
- `_trigger_reboot()`: execv to binary, PowerManager fallback when missing/not-executable
- Full flow integration: mock install.sh + sentinel detection + binary creation
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
| `tools/purple-reboot.c` | Source for static reboot binary |
| `config/xinit/xinitrc` | Squashfs tmpfs copy (replaces page cache warmup) |
| `tests/test_install_progress.py` | Documents and tests the pipe-hang fix |
| `tests/test_install_reboot.py` | Tests the reboot flow and sentinel detection |
