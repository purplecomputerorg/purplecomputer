"""Live boots: whether this laptop already has Purple, from install.sh --probe.

Probed once in the background at startup so the splash can say so; the
Install screen reuses the same result. Only one probe runs at a time, since
each one empties /run/purple-keep and mounts the old root.
"""

import subprocess
import threading
from pathlib import Path

PAYLOAD_PATH = Path("/cdrom/purple/install.sh")
NONE = (None, "")
_lock = threading.Lock()
_result = None


def _run():
    """None when the probe couldn't run (no payload), so a later call tries again."""
    if not PAYLOAD_PATH.exists():
        return None
    try:
        out = subprocess.run(["sudo", "bash", str(PAYLOAD_PATH), "--probe"],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if line.startswith("[PURPLE-FOUND-UNREADABLE]"):
            return "unreadable", ""
        if line.startswith("[PURPLE-FOUND]"):
            return "found", line[len("[PURPLE-FOUND]"):].strip()
    return NONE


def probe() -> tuple:
    """("found", old name), ("unreadable", ""), or (None, ""). Blocks."""
    global _result
    with _lock:
        if _result is None:
            _result = _run()
        return _result or NONE


def known() -> tuple:
    """The probe's result if it has finished, without waiting."""
    return _result or NONE


def start():
    threading.Thread(target=probe, daemon=True, name="old-install").start()
