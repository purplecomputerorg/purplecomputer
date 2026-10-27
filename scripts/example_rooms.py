#!/usr/bin/env python3
"""Studio's starter rooms (studio/src/examples) as a pack, Example Rooms, built fresh each time.

    just example-rooms               # install it here and turn its rooms on (test-vm-setup's `run`)
    just example-rooms --out FILE    # only write the .purplepack (just vm-rooms)

No purple.py in the pack, so the rooms run on the library of the Purple that loads them.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from purplepack import build_pack  # noqa: E402
from purple_tui.canvas.room_picker import MAX_FAMILY_ROOMS  # noqa: E402
from purple_tui.content import Room  # noqa: E402
from purple_tui.pack_manager import get_installer  # noqa: E402
from purple_tui.settings import set_room_on  # noqa: E402

PACK_ID = "examples"


def make_pack(dest: Path) -> Path:
    rooms = dest / "content" / "rooms"
    rooms.mkdir(parents=True)
    for src in sorted((ROOT / "studio" / "src" / "examples").glob("*.py")):
        shutil.copy(src, rooms)
    manifest = {"id": PACK_ID, "name": "Example Rooms", "version": "1.0.0", "type": "emoji"}
    (dest / "manifest.json").write_text(json.dumps(manifest))
    return dest


def install() -> None:
    """Swap in the fresh pack and turn on as many of its rooms as the Esc menu holds."""
    installer = get_installer()
    with tempfile.TemporaryDirectory() as tmp:
        ok, msg = installer.install_dir(make_pack(Path(tmp) / PACK_ID), replace=True)
    if not ok:
        raise SystemExit(msg)
    paths = sorted((installer.packs_dir / PACK_ID / "content" / "rooms").glob("*.py"))
    for i, path in enumerate(paths):
        room = Room(path.stem, path)
        set_room_on(room.key, room.digest if i < MAX_FAMILY_ROOMS else None)
    print(f"Example Rooms: {', '.join(p.stem for p in paths[:MAX_FAMILY_ROOMS])} on")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="write the .purplepack here instead of installing it")
    args = parser.parse_args()
    if not args.out:
        return install()
    with tempfile.TemporaryDirectory() as tmp:
        print(f"wrote {build_pack(make_pack(Path(tmp) / PACK_ID), Path(args.out))}")


if __name__ == "__main__":
    main()
