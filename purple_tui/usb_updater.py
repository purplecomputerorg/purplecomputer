"""Set aside every .purplepack at the top level of a USB drive, for Purple to offer.

Run by config/systemd/purple-usb-update@.service, as root, with the drive
already mounted read-only at the path given on the command line. Each pack
that passes check_pack is unpacked into the purple user's waiting folder,
named by the file's sha256, and chowned to that user. Nothing is installed
here: the app (purple_tui/pack_arrivals.py) asks before it adds one. Only
stdlib and the pure-data parts of purple_tui are imported: this runs under
the system python3, outside the app's venv.

    python3 -m purple_tui.usb_updater /run/purple-update/sdb1
"""

import hashlib
import json
import os
import pwd
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from .content import PACK_FORMAT
from .pack_manager import check_pack, extract_pack, read_manifest

APP_USER = "purple"
LOG_PATH = Path("/var/log/purple/usb-update.log")
WAITING = Path(".purple") / "packs-waiting"
READING = ".reading"  # there while a drive's packs are being unpacked, so the app can say so
SKIPPED = ".skipped.json"  # the packs the last drive brought that Purple couldn't take, and why, for the app to say


def app_user_waiting_dir() -> Path:
    try:
        home = Path(pwd.getpwnam(APP_USER).pw_dir)
    except KeyError:
        home = Path.home()
    return home / WAITING


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    for path in [root, *root.rglob("*")]:
        os.chown(path, uid, gid, follow_symlinks=False)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _first_copy(dest: Path, seen: set, msg: str) -> tuple[bool, str]:
    pack_id = (read_manifest(dest) or {}).get("id")
    if pack_id in seen:
        shutil.rmtree(dest, ignore_errors=True)
        return False, "a newer copy of this pack is on the drive"
    seen.add(pack_id)
    return True, msg


def _skipped(pack: Path, unpacked: Path, why: str) -> dict:
    """A refused pack as the app tells it: its name, and the format it asks for when that's newer than this Purple reads."""
    try:
        m = json.loads((unpacked / "manifest.json").read_text())
    except (OSError, ValueError):
        m = None
    m = m if isinstance(m, dict) else {}
    fmt = m.get("format")
    name = m.get("name")
    return {"name": name if isinstance(name, str) and name.strip() else pack.stem, "why": why,
            "format": fmt if isinstance(fmt, int) and fmt > PACK_FORMAT else None}


def stage(pack: Path, waiting: Path, seen: set, skipped: list) -> tuple[bool, str]:
    """Unpack and check one pack into waiting/<sha256>, unless a pack with its id is in seen; a
    refused one joins skipped. Dot-named while it is being written, so the app never sees half a pack."""
    dest = waiting / sha256(pack)
    if dest.exists():
        return _first_copy(dest, seen, "already waiting")
    tmp = Path(tempfile.mkdtemp(prefix=".", dir=waiting))
    try:
        refused = extract_pack(pack, tmp) or "; ".join(check_pack(tmp)[:5])
        if refused:
            skipped.append(_skipped(pack, tmp, refused))
            return False, refused
        tmp.rename(dest)
        return _first_copy(dest, seen, "waiting to be added")
    except (tarfile.TarError, OSError) as e:
        skipped.append(_skipped(pack, tmp, f"unreadable: {e}"))
        return False, f"unreadable: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def update_from(mount: Path, waiting: Path | None = None) -> list[tuple[str, bool, str]]:
    """Stage each pack on the drive. Returns (filename, ok, message) per pack."""
    waiting = waiting or app_user_waiting_dir()
    waiting.mkdir(parents=True, exist_ok=True)
    reading = waiting / READING
    reading.touch()
    try:
        # Newest file first, so two downloads of one pack offer the newer and skip the other.
        # Dot names skipped: a Mac leaves a ._<name> metadata file beside each pack it copies.
        packs = sorted((p for p in mount.glob("*.purplepack") if not p.name.startswith(".")),
                       key=lambda p: (-p.stat().st_mtime, p.name))
        seen: set = set()
        skipped: list = []
        results = sorted((p.name, *stage(p, waiting, seen, skipped)) for p in packs)
        if skipped:
            (waiting / SKIPPED).write_text(json.dumps(skipped))
        else:
            (waiting / SKIPPED).unlink(missing_ok=True)
    finally:
        reading.unlink(missing_ok=True)
    try:
        user = pwd.getpwnam(APP_USER)
        if os.geteuid() == 0:
            _chown_tree(waiting.parent, user.pw_uid, user.pw_gid)
    except (KeyError, OSError):
        pass
    return results


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not Path(argv[1]).is_dir():
        print("usage: python3 -m purple_tui.usb_updater <mounted drive>", file=sys.stderr)
        return 2
    results = update_from(Path(argv[1]))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"{stamp} {name}: {'ok' if ok else 'skipped'}: {msg}" for name, ok, msg in results] or [f"{stamp} no .purplepack files on the drive"]
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
