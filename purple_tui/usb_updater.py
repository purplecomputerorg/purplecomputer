"""Install every .purplepack on a stick labeled PURPLE_UPDATE.

Run by config/systemd/purple-usb-update@.service, as root, with the stick
already mounted read-only at the path given on the command line. Packs go to
the purple user's ~/.purple/packs, replacing any pack with the same id, and
are chowned to that user so the app can read them. Purple picks them up the
next time it starts. Only stdlib and the pure-data parts of purple_tui are
imported: this runs under the system python3, outside the app's venv.

    python3 -m purple_tui.usb_updater /mnt/purple-update
"""

import os
import pwd
import sys
import time
from pathlib import Path

from .pack_manager import PackInstaller

APP_USER = "purple"
LOG_PATH = Path("/var/log/purple/usb-update.log")


def app_user_packs_dir() -> Path:
    try:
        home = Path(pwd.getpwnam(APP_USER).pw_dir)
    except KeyError:
        home = Path.home()
    return home / ".purple" / "packs"


def _chown_tree(root: Path, uid: int, gid: int) -> None:
    for path in [root, *root.rglob("*")]:
        os.chown(path, uid, gid)


def update_from(mount: Path, packs_dir: Path | None = None) -> list[tuple[str, bool, str]]:
    """Install each pack on the stick. Returns (filename, ok, message) per pack."""
    packs_dir = packs_dir or app_user_packs_dir()
    installer = PackInstaller(packs_dir)
    results = [(p.name, *installer.install_pack(p, replace=True)) for p in sorted(mount.glob("*.purplepack"))]
    try:
        user = pwd.getpwnam(APP_USER)
        if os.geteuid() == 0:
            _chown_tree(packs_dir.parent, user.pw_uid, user.pw_gid)
    except (KeyError, OSError):
        pass
    return results


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not Path(argv[1]).is_dir():
        print("usage: python3 -m purple_tui.usb_updater <mounted stick>", file=sys.stderr)
        return 2
    results = update_from(Path(argv[1]))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"{stamp} {name}: {'ok' if ok else 'skipped'}: {msg}" for name, ok, msg in results] or [f"{stamp} no .purplepack files on the stick"]
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
