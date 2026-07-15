"""
Purple Computer: Boot heartbeat log + startup-hang watchdog.

Purpose
-------
When a customer reports "purple takes forever to start" or "purple hangs on
boot on my old MacBook", we need to know *which line* of startup is stuck.
Symptoms up to this module have been: alacritty is visible, cursor is blinking,
Textual never appears. Gathering anything useful after that requires physical
access, function keys (which Touch Bar Macs don't have), and a USB keyboard.

This module gives us two things instead:

1. **Heartbeat**: `heartbeat(phase)` appends a timestamped line to a boot-log
   file. Called at every import checkpoint and init phase in purple_tui. The
   last line in the log before a hang tells us which phase hung.

2. **Startup watchdog**: a background thread started at import time. If
   `mark_first_render()` has not been called within escalating deadlines
   (10s / 20s / 40s / 80s from launcher start), the watchdog dumps every Python
   thread's stack trace to the boot log using `faulthandler.dump_traceback`.
   The dump tells us the exact line of Python that is stuck.

Design rules (so this can ship in standard AND debug ISOs)
---------------------------------------------------------
- Only stdlib imports (no side effects from third-party packages).
- File descriptors only. Never touches stdout or stderr. Textual owns stderr
  for its UI, so printing there would corrupt the display.
- Writes are single-line appends to a tmpfs path and (when writable) a
  casper-persistent path. No flushing of anything else, no fsync.
- The watchdog thread sleeps most of the time; when `mark_first_render` is
  called it exits cleanly.
- Failure is silent. No exceptions escape heartbeat() or the watchdog.

Log locations
-------------
- `/tmp/purple-boot.log` — tmpfs, always writable, current boot only.
- `/var/log/purple/boot.log` — on the standard ISO this is tmpfs (same as
  above, effectively). On the debug ISO, casper mounts the USB's ext4
  `writable` partition at `/var/log`, so this file SURVIVES REBOOT. That's
  the whole point: after a hang + power-cycle, the prior boot's trace is
  still on disk. xinitrc rotates boot.log -> boot.log.prev on each entry.

See also: guides/install-partition-detection.md for the casper writable
partition layout on the debug ISO.
"""

from __future__ import annotations

import faulthandler
import os
import signal
import sys
import threading
import time
from datetime import datetime
from typing import Optional

_BOOT_LOG_TMP = "/tmp/purple-boot.log"
_BOOT_LOG_PERSIST = "/var/log/purple/boot.log"

# Process start time in monotonic seconds, captured at module import.
# Used for "seconds since import" deltas in heartbeat entries.
_START_MONO = time.monotonic()

# Flag set by mark_first_render(). Watchdog reads this under no lock because
# a stale-read of False just produces one extra (harmless) dump.
_first_render_done = False
_first_render_lock = threading.Lock()

# Keep the faulthandler log file reference alive for the life of the process.
# faulthandler requires the fd to remain open; closing it silently drops
# subsequent dumps.
_fault_fd: Optional[int] = None


def _open_append(path: str) -> Optional[int]:
    """Open `path` for append as a low-level fd. Returns None on failure."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    try:
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    except Exception:
        return None


def _write_line(line: str) -> None:
    """Append a single line to both log destinations. Never raises."""
    data = (line + "\n").encode("utf-8", errors="replace")
    for path in (_BOOT_LOG_TMP, _BOOT_LOG_PERSIST):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        except Exception:
            continue
        try:
            os.write(fd, data)
        except Exception:
            pass
        finally:
            try:
                os.close(fd)
            except Exception:
                pass


def heartbeat(phase: str) -> None:
    """Append a timestamped heartbeat entry to the boot log.

    Called at every important checkpoint during purple_tui startup. Cheap
    (two file appends). Never touches stdout/stderr. Never raises.

    Example line:
        [13:42:07.832] [+0.412s] [python] textual imported
    """
    try:
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        delta = time.monotonic() - _START_MONO
        _write_line(f"[{now}] [+{delta:6.3f}s] [python] {phase}")
    except Exception:
        pass


def mark_first_render() -> None:
    """Signal that Textual has painted its first frame.

    After this is called, the startup watchdog stops dumping. Idempotent.
    Safe to call from any thread.
    """
    global _first_render_done
    with _first_render_lock:
        if _first_render_done:
            return
        _first_render_done = True
    heartbeat("first render reached; watchdog disarmed")


def _watchdog_target(deadlines: tuple[int, ...]) -> None:
    """Background thread: wait for first render, dump stacks if deadlines pass.

    `deadlines` are seconds-from-start after which we dump traces. Between
    dumps the thread sleeps; it exits as soon as `mark_first_render()` is
    called OR all deadlines have been consumed (whichever comes first).
    """
    for deadline in deadlines:
        # Sleep until deadline (checking first-render flag each second so we
        # exit promptly on success without cancelling the thread).
        while True:
            if _first_render_done:
                return
            remaining = deadline - (time.monotonic() - _START_MONO)
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))

        if _first_render_done:
            return

        # Deadline exceeded and still no render. Dump every thread's stack.
        try:
            heartbeat(f"WATCHDOG deadline {deadline}s exceeded, dumping stacks")
            if _fault_fd is not None:
                # faulthandler.dump_traceback writes to the given fd and is
                # safe to call from any thread. We pass all_threads=True so
                # we can see whether the main thread is blocked on evdev,
                # an import lock, a subprocess, etc.
                faulthandler.dump_traceback(file=_fault_fd, all_threads=True)
                # Add a marker so successive dumps are greppable.
                try:
                    os.write(_fault_fd, f"--- end dump at +{int(time.monotonic() - _START_MONO)}s ---\n".encode())
                except Exception:
                    pass
        except Exception:
            pass

    heartbeat("WATCHDOG final deadline passed; thread exiting")


def _install_watchdog() -> None:
    """Start the watchdog thread and register the faulthandler fd.

    Called once at module import. Silent on failure.
    """
    global _fault_fd
    # Open the persistent log for faulthandler. We reuse it across dumps so
    # the fd stays open for the life of the process. Prefer persistent path
    # because that's the one that survives reboot; fall back to tmp.
    for path in (_BOOT_LOG_PERSIST, _BOOT_LOG_TMP):
        _fault_fd = _open_append(path)
        if _fault_fd is not None:
            break
    if _fault_fd is None:
        return

    # PYTHONFAULTHANDLER=1 in the launcher enables stderr dumps on signals;
    # faulthandler.enable(file=...) redirects those to our log file too, so
    # a SIGSEGV during startup lands in the boot log instead of corrupting
    # the Textual screen.
    try:
        faulthandler.enable(file=_fault_fd, all_threads=True)
    except Exception:
        pass

    # SIGUSR1 → on-demand thread dump. From tty2: `sudo kill -USR1 <pid>`
    # (or the `dump-purple` helper) and every thread's stack lands in the
    # boot log. Lets us inspect a live hang without killing the process.
    try:
        faulthandler.register(signal.SIGUSR1, file=_fault_fd, all_threads=True, chain=False)
    except Exception:
        pass

    # Deadlines: 10s is "this should have been done by now on any machine",
    # 20s and 40s are "definitely stuck", 80s is "last chance before we stop
    # dumping". Four dumps give us a progression (is it making progress? is it
    # a lock that eventually resolves? or is it truly wedged?).
    thread = threading.Thread(
        target=_watchdog_target,
        args=((10, 20, 40, 80),),
        name="purple-boot-watchdog",
        daemon=True,
    )
    try:
        thread.start()
    except Exception:
        pass


# Module import side effects (intentional): write a "module imported" line
# and start the watchdog. This runs before any purple_tui imports happen,
# so the watchdog is armed from the earliest possible moment.
_write_line(
    f"\n=== purple python starting at {datetime.now().isoformat()} "
    f"pid={os.getpid()} python={sys.version.split()[0]} ==="
)
heartbeat("boot_log module imported; watchdog arming")
_install_watchdog()
heartbeat("watchdog armed")
