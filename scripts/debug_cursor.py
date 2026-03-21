#!/usr/bin/env python3
"""Debug terminal cursor visibility.

Intercepts all writes to stdout/stderr to detect when something sends
\x1b[?25h (show cursor) or \x1b[?25l (hide cursor). Logs every occurrence
with a timestamp and stack trace to /tmp/cursor-debug.log.

Usage:
    just python scripts/debug_cursor.py

Then in another terminal:
    tail -f /tmp/cursor-debug.log

Works with evdev keyboard input (no need for PURPLE_NO_EVDEV).
"""

import sys
import os
import time
import traceback
import threading

LOG_PATH = "/tmp/cursor-debug.log"
_start_time = time.monotonic()

# Open log file
_log_file = open(LOG_PATH, "w")
_log_file.write(f"=== Cursor debug started at {time.strftime('%H:%M:%S')} ===\n\n")
_lock = threading.Lock()


def _elapsed():
    return f"{time.monotonic() - _start_time:.3f}s"


def _log(msg):
    with _lock:
        _log_file.write(msg)
        _log_file.flush()


def _check_for_cursor_codes(data, stream_name):
    """Scan data for cursor show/hide escape sequences and log them."""
    if not isinstance(data, (str, bytes)):
        return

    if isinstance(data, bytes):
        show = b'\x1b[?25h'
        hide = b'\x1b[?25l'
    else:
        show = '\x1b[?25h'
        hide = '\x1b[?25l'

    found = []
    if show in data:
        found.append("SHOW_CURSOR \\x1b[?25h")
    if hide in data:
        found.append("HIDE_CURSOR \\x1b[?25l")

    if found:
        for code in found:
            stack = traceback.format_stack()
            # Filter out our wrapper frames
            stack = [f for f in stack if 'debug_cursor.py' not in f]
            lines = [f"[{_elapsed()}] [{stream_name}] {code}\n"]
            lines.append("  Stack trace:\n")
            for frame in stack[-8:]:
                for line in frame.strip().split('\n'):
                    lines.append(f"    {line}\n")
            lines.append("\n")
            _log("".join(lines))


class CursorSpyWriter:
    """Wraps a file object, logging cursor escape sequences."""

    def __init__(self, original, name):
        self._original = original
        self._name = name

    def write(self, data):
        _check_for_cursor_codes(data, self._name)
        return self._original.write(data)

    def __getattr__(self, name):
        return getattr(self._original, name)


class CursorSpyBuffer:
    """Wraps a buffer (like stdout.buffer), logging cursor escape sequences."""

    def __init__(self, original, name):
        self._original = original
        self._name = name

    def write(self, data):
        _check_for_cursor_codes(data, self._name)
        return self._original.write(data)

    def __getattr__(self, name):
        return getattr(self._original, name)


# Patch stdout and stderr
_real_stdout = sys.stdout
_real_stderr = sys.stderr

sys.stdout = CursorSpyWriter(_real_stdout, "stdout")
sys.stderr = CursorSpyWriter(_real_stderr, "stderr")

# Also patch the buffer layers if they exist
if hasattr(_real_stdout, 'buffer'):
    sys.stdout.buffer = CursorSpyBuffer(_real_stdout.buffer, "stdout.buffer")
if hasattr(_real_stderr, 'buffer'):
    sys.stderr.buffer = CursorSpyBuffer(_real_stderr.buffer, "stderr.buffer")

# Also patch os.write to catch low-level writes
_real_os_write = os.write

def _spy_os_write(fd, data):
    if fd in (1, 2):  # stdout=1, stderr=2
        name = "os.write(stdout)" if fd == 1 else "os.write(stderr)"
        _check_for_cursor_codes(data, name)
    return _real_os_write(fd, data)

os.write = _spy_os_write

_log(f"[{_elapsed()}] Patches installed (stdout, stderr, os.write). Starting app...\n\n")

# Periodic heartbeat so we know the logger is alive
def _periodic_status():
    while True:
        time.sleep(10)
        _log(f"[{_elapsed()}] (heartbeat)\n")

t = threading.Thread(target=_periodic_status, daemon=True)
t.start()

# Now start the actual app (with evdev, same as normal run)
from purple_tui.purple_tui import PurpleApp
app = PurpleApp()
app.run()

_log(f"\n[{_elapsed()}] App exited.\n")
_log_file.close()
