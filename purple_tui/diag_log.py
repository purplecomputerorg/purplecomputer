"""Always-on diagnostic log writer shared by the boot, power and evdev logs.

Each line goes to the per-boot files (quick to read, copied into the stick
report) and to the journal, which keeps every boot on installed systems while
the files keep only this boot and the last.
"""

import os
import socket

JOURNAL_SOCKET = "/dev/log"
_journal = None


def append(paths, text: str, tag: str) -> None:
    """Append `text` to each path and send its lines to the journal as `tag`. Never raises."""
    data = text.encode("utf-8", errors="replace")
    for path in paths:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        except OSError:
            continue
        try:
            os.write(fd, data)
        except OSError:
            pass
        finally:
            os.close(fd)
    _to_journal(text, tag)


def _to_journal(text: str, tag: str) -> None:
    global _journal
    try:
        if _journal is None:
            _journal = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        for line in text.splitlines():
            if line.strip():
                # MSG_DONTWAIT: a stalled journald must never block the UI
                _journal.sendto(f"<14>{tag}: {line}".encode("utf-8", errors="replace"),
                                socket.MSG_DONTWAIT, JOURNAL_SOCKET)
    except OSError:
        pass
