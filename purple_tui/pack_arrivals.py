"""Purple Packs a USB drive brought, waiting for someone to press Add.

purple_tui/usb_updater.py unpacks each into WAITING_DIR/<sha256 of its file>. One added before
(same id, same file) goes back in without asking: the Purple Key's own packs on a live boot, where
installed packs don't outlast a restart. The rest wait for the app to offer them.
"""

import json
import os
import shutil
from pathlib import Path

from .constants import SUPPORT_EMAIL
from .content import PACK_FORMAT
from .pack_manager import get_installer, read_manifest
from .settings import get_packs_added, set_pack_added
from .usb_updater import READING, SKIPPED

WAITING_DIR = Path.home() / ".purple" / "packs-waiting"


def stamp() -> tuple:
    """Changes whenever the updater starts or finishes a drive, or a pack is taken. The link count
    and the marker catch changes inside one tick of the folder's coarse mtime."""
    try:
        st = os.stat(WAITING_DIR)
        return st.st_mtime_ns, st.st_nlink, reading()
    except OSError:
        return ()


def reading() -> bool:
    return (WAITING_DIR / READING).exists()


def _waiting() -> list[tuple[Path, dict]]:
    if not WAITING_DIR.is_dir():
        return []
    return [(d, m) for d in sorted(WAITING_DIR.iterdir()) if not d.name.startswith(".") and (m := read_manifest(d))]


def _install(pack_dir: Path) -> bool:
    ok = get_installer().install_dir(pack_dir, replace=True)[0]
    shutil.rmtree(pack_dir, ignore_errors=True)
    return ok


def settle() -> tuple[bool, bool, list]:
    """Put back the packs added before and drop the ones already in place. Returns whether
    anything was installed, whether any pack had been added before, and the (dir, manifest)
    pairs left to offer."""
    added, packs_dir = get_packs_added(), get_installer().packs_dir
    installed, known, offer = False, False, []
    for d, m in _waiting():
        if added.get(m["id"]) != d.name:
            offer.append((d, m))
            continue
        known = True
        if (packs_dir / m["id"]).exists():
            shutil.rmtree(d, ignore_errors=True)
        else:
            installed |= _install(d)
    return installed, known, offer


def add(waiting: list) -> list[str]:
    """Install each and remember it. Returns the names that couldn't be added."""
    failed = []
    for d, m in waiting:
        if _install(d):
            set_pack_added(m["id"], d.name)
        else:
            failed.append(m["name"])
    return failed


def decline(waiting: list) -> None:
    for d, _ in waiting:
        shutil.rmtree(d, ignore_errors=True)


def has_rooms(waiting: list) -> bool:
    return any(any((d / "content" / "rooms").glob("*.py")) for d, _ in waiting)


def take_skipped() -> list[dict]:
    """The packs the last drive brought that Purple couldn't take, once."""
    path = WAITING_DIR / SKIPPED
    try:
        items = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    path.unlink(missing_ok=True)
    return items if isinstance(items, list) else []


def skipped_notes(skipped: list[dict]) -> list[tuple[str, str]]:
    """(title, body) for each kind of skipped pack: too new for this Purple, or not readable."""
    newer = [s for s in skipped if s.get("format")]
    broken = [s for s in skipped if not s.get("format")]
    notes = []
    if newer:
        asks = max(s["format"] for s in newer)
        notes.append(("Needs newer Purple software", "\n".join(s["name"] for s in newer) + (
            "\n\nThis Purple Pack was made for a newer Purple release. Put the newest Purple on your Purple Key,"
            " start Purple from it, then plug in this USB drive again."
            f"\n\n(Technical: pack format {asks}, this Purple reads {PACK_FORMAT})")))
    if broken:
        notes.append(("Couldn't add this Purple Pack", "\n".join(s["name"] for s in broken) + (
            f"\n\nTry downloading it from Purple Studio again. Still stuck? Email {SUPPORT_EMAIL}."
            f"\n\n(Technical: {broken[0]['why'][:160]})")))
    return notes
