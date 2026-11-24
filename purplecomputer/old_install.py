"""Live boots: whether this laptop already has Purple, from install.sh --probe.

Probed once in the background at startup so the splash can say so; the
Install screen reuses the same result. Only one probe runs at a time, since
each one empties /run/purple-keep and mounts the old root.
"""

import re
import subprocess
import threading
from pathlib import Path

PAYLOAD_PATH = Path("/cdrom/purple/install.sh")
KEEP_DIR = Path("/run/purple-keep")
NONE = (None, "")
UPDATES = ("found", "empty")  # Purple that this Key updates: with the kid's work, or with only settings (v1)
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
        for state, tag in (("found", "[PURPLE-FOUND]"), ("empty", "[PURPLE-EMPTY]")):
            if line.startswith(tag):
                return state, line[len(tag):].strip()
    return NONE


def probe() -> tuple:
    """("found" | "empty", old name), ("unreadable", ""), or (None, ""). Blocks."""
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


def _build_date(version: str) -> str | None:
    m = re.search(r"(\d{8})(?:-(\d{4}))?$", version.replace(".", ""))
    return m and m.group(1) + (m.group(2) or "")


def key_is_newer(key_version: str, old_version: str) -> bool:
    """True unless the versions show otherwise: the same, or the Key's build is no later."""
    if key_version == old_version:
        return False
    key, old = _build_date(key_version), _build_date(old_version)
    if not key or not old:
        return True
    n = min(len(key), len(old))
    if key[:n] != old[:n]:
        return key[:n] > old[:n]
    return len(key) != len(old)  # same day, but only one says when: can't tell


def key_has(version_file: Path = Path("/etc/purple-version")) -> str:
    """How the update screens describe this Key's Purple next to the laptop's."""
    def read(path):
        try:
            return path.read_text().strip()
        except OSError:
            return ""
    old = read(KEEP_DIR / "purple-version")
    newer = not old or key_is_newer(read(version_file), old)
    return f"This Key has a {'new' if newer else 'different'} version of Purple."
