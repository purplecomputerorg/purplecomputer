"""Live boots: keeping ~/.config/purple in PURPLE-SAVE on the Key.

purple-key-save.service unpacked the newest copy before Purple started and
left MARKER, which is how Purple knows this Key can keep work. Writes go
through `purple-key-save --write` (root, in place, see its docstring):
a few seconds after the last change, one at a time, and once more before
the computer turns off.
"""

import os
import subprocess
import threading

from ..constants import is_live_boot, is_usb_present

MARKER = os.environ.get("PURPLE_KEY_SAVE_MARKER", "/run/purple/key-save")
WRITER = ["sudo", "-n", "ionice", "-c3", "/usr/local/bin/purple-key-save", "--write"]
DEBOUNCE_S = 5.0
FLUSH_TIMEOUT_S = 8.0
OK, NO_FILE, GONE, FULL = 0, 2, 3, 4  # purple-key-save's exit codes


def active() -> bool:
    """This live session's work is kept on the Key."""
    return is_live_boot() and os.path.exists(MARKER)


def unavailable() -> str | None:
    """Why Save is greyed out, or None: a live Key with nowhere to keep work, or one pulled out."""
    if not is_live_boot():
        return None
    if not os.path.exists(MARKER):
        return "Needs Install"
    return None if is_usb_present() else "Needs USB"


class KeySave:
    def __init__(self, app):
        self.app = app
        self.full = False
        self._dirty = False
        self._timer = None
        self._running = False

    def changed(self):
        if not active() or not is_usb_present():
            return
        self._dirty = True
        if self._timer:
            self._timer.stop()
        self._timer = self.app.timers.after(DEBOUNCE_S, self._start)

    def _start(self):
        self._timer = None
        if self._running:
            return self.changed()  # one write at a time; try again once this one lands
        self._running = True
        self._dirty = False
        threading.Thread(target=lambda: self.app.call_from_thread(self._done, self._write()),
                         daemon=True, name="key-save").start()

    def _done(self, code):
        self._running = False
        if code in (OK, FULL) and self.full != (code == FULL):
            self.full = code == FULL
            self.app.invalidate()

    def _write(self, timeout: float = 60.0) -> int:
        try:
            return subprocess.run(WRITER, capture_output=True, timeout=timeout).returncode
        except (OSError, subprocess.TimeoutExpired):
            return GONE

    def flush(self):
        """Before turning off: write what hasn't been written yet, briefly blocking."""
        if not (self._dirty or self._timer) or not active() or not is_usb_present():
            return
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._dirty = False
        self._write(FLUSH_TIMEOUT_S)
