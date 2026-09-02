"""Keep C-level stderr noise off the Textual screen.

Textual paints its UI to fd 2, and libraries we link against write warnings to
that same fd from C: onnxruntime's "onnxruntime cpuid_info warning: Unknown CPU
vendor" when cpuinfo can't identify a VM's CPU, ALSA device chatter, espeak
notes. Swapping sys.stderr cannot stop those (they write to the descriptor, not
the Python object), so main() hands Textual its own dup of the terminal and
points fd 2 at a log file instead.
"""

from __future__ import annotations

import io
import os
import sys

LOG_PATH = "/tmp/purple-stderr.log"

# Holds the dup'd terminal for the life of the process: letting it be collected
# would close the fd and take Textual's display with it.
_terminal: io.TextIOWrapper | None = None


def terminal_stderr() -> io.TextIOWrapper | None:
    """The real terminal, for children that must be seen (interactive shells).

    fd 2 points at the log file once the guard is active, and bash writes its
    prompt and readline's echo to stderr, so a child that inherits fd 2 runs
    invisibly. Returns None when the guard never ran (fd 2 is still the tty).
    """
    return _terminal


def hide_native_stderr(log_path: str = LOG_PATH) -> bool:
    """Point fd 2 at `log_path` and give Textual a private handle on the terminal.

    Must run before app.run(): Textual's driver captures sys.__stderr__ when it
    starts. Returns False without changing anything when stderr is not a
    terminal, so captured-stderr runs (tests, headless preview, art_ai) behave
    exactly as before.
    """
    global _terminal
    if _terminal is not None:
        return True
    try:
        if sys.__stderr__ is None or not sys.__stderr__.isatty():
            return False
        terminal = io.TextIOWrapper(
            io.FileIO(os.dup(2), "w"),
            encoding="utf-8",
            errors="replace",
            write_through=True,
        )
        try:
            log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        except OSError:
            log_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(log_fd, 2)
        os.close(log_fd)
        sys.__stderr__ = terminal
        _terminal = terminal
        return True
    except Exception:
        return False
