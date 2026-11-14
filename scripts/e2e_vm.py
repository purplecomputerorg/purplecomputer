#!/usr/bin/env python3
"""A built ISO booted in QEMU (scripts/vm.sh) the way a family's laptop boots its Purple Key: a USB drive
holding a Purple Pack is plugged in, a parent adds it, a kid uses it, and the parent copies the saved
work back onto that same drive, which is then read here as a Windows or Mac would read it.

    just e2e-vm [PACK] [--ref COMMIT] [--out DIR] [--keep-running]

PACK defaults to the SDK's fixture pack (studio/scripts/fixture-packs.ts); with it the screen's color
and the copied picture's colors are checked too. Needs KVM and a built ISO (just build). The keys are
tests/real_purple.py's, which test_studio_to_purple.py replays headless to keep them honest.
Screens: DIR/NN-step.png (default $TMPDIR/purple-e2e-vm)."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from tests.pack_journey import read_pack  # noqa: E402
from tests.real_purple import (ADD_PACK, ART_FIRST_PICTURE, PICTURE_COLORS, SAVE, page_has_colors,  # noqa: E402
                                      play_word, qemu_keys, to_menu_item)

VM = ROOT / "scripts" / "vm.sh"
FIXTURE_ID = "pack-e2e00001"
BOOT_COLOR = "#1d1234"  # palette.BG, Purple's screen before any pack changes it


def vm(*args: str) -> str:
    return subprocess.run([str(VM), *args], check=True, capture_output=True, text=True).stdout.strip()


class Screens:
    def __init__(self, out: Path):
        self.out, self.n, self.tmp = out, 0, Path(tempfile.mkdtemp(prefix="vm-frame-"))

    def frame(self) -> pygame.Surface:
        path = self.tmp / "now.png"
        vm("shot", str(path))
        return pygame.image.load(str(path))

    def save(self, name: str) -> pygame.Surface:
        self.n += 1
        path = self.out / f"{self.n:02}-{name}.png"
        vm("shot", str(path))
        print(f"  screen: {path}")
        return pygame.image.load(str(path))

    def settle(self, timeout: float, until=lambda s: True, every: float = 3.0) -> pygame.Surface | None:
        """The screen once two looks in a row match and until(screen) holds, or None at timeout."""
        last, end = None, time.time() + timeout
        while time.time() < end:
            now = self.frame()
            raw = pygame.image.tobytes(now, "RGB")
            if raw == last and until(now):
                return now
            last = raw
            time.sleep(every)
        return None


def share_of(surface: pygame.Surface, color: str, tolerance: int = 12) -> float:
    rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    w, h = surface.get_size()
    points = [(x, y) for x in range(0, w, 8) for y in range(0, h, 8)]
    return sum(max(abs(a - b) for a, b in zip(rgb, surface.get_at(p)[:3])) <= tolerance for p in points) / len(points)


def press(script: list, pause: float = 0.6) -> None:
    for key in qemu_keys(script):
        vm("key", key)
        time.sleep(pause)


def fixture_pack(out: Path) -> Path:
    subprocess.run([str(ROOT / "studio" / "node_modules" / ".bin" / "vite-node"), "scripts/fixture-packs.ts", str(out)],
                   cwd=ROOT / "studio", check=True)
    return out / "everything.purplepack"


def drive_image(pack: Path, out: Path) -> Path:
    img = out / "family-drive.img"
    img.unlink(missing_ok=True)
    subprocess.run(["mkfs.fat", "-C", "-n", "FAMILY", str(img), "65536"], check=True, capture_output=True)
    subprocess.run(["mcopy", "-i", str(img), str(pack), "::/"], check=True)
    return img


def export_downs(pack: Path) -> int:
    """Down presses to Copy Saved Work to USB, from this checkout's menu with the pack added."""
    from tests.pack_journey import isolate
    isolate(Path(tempfile.mkdtemp(prefix="vm-menu-")))
    from purplecomputer.harness import make_app, run
    from purplecomputer.pack_manager import get_installer
    from tests.real_purple import menu_downs
    get_installer().install_pack(pack, replace=True)

    async def count():
        return menu_downs(make_app(), "menu-export")
    return run(count())


def copied_art(img: Path, out: Path) -> Path | None:
    listing = subprocess.run(["mdir", "-i", str(img), "-/", "-b", "::/"], capture_output=True, text=True).stdout.split()
    art = sorted(p for p in listing if "/Art/" in p and p.endswith(".png"))
    if not art:
        return None
    dest = out / "copied-art.png"
    subprocess.run(["mcopy", "-n", "-i", str(img), art[-1], str(dest)], check=True)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pack", nargs="?", type=Path)
    ap.add_argument("--ref", help="boot the build of this commit (default: the newest build)")
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("TMPDIR", "/tmp")) / "purple-e2e-vm")
    ap.add_argument("--keep-running", action="store_true", help="leave the VM up to look around (just vm-stop ends it)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pack = (args.pack or fixture_pack(args.out)).resolve()
    files = read_pack(pack)
    fixture = json.loads(files["manifest.json"])["id"] == FIXTURE_ID
    word, glyph = next(iter((json.loads(files.get("content/emoji.json", b"{}")) or {"cat": "🐱"}).items()))
    theme = json.loads(files.get("content/theme.json", b"{}")).get("colors", {}).get("bg")
    downs = export_downs(pack)
    img = drive_image(pack, args.out)
    screens, results = Screens(args.out), []

    def expect(ok, what):
        results.append((bool(ok), what))
        print(f"  {'ok  ' if ok else 'FAIL'} {what}")

    print("vm: booting" + (f" the build of {args.ref}" if args.ref else " the newest build"))
    vm("start", "--fresh", *([args.ref] if args.ref else []))
    try:
        booted = screens.settle(600, until=lambda s: share_of(s, BOOT_COLOR) > 0.3)
        screens.save("booted")
        expect(booted, "Purple started")
        if not booted:
            return 1
        print("vm: plugging in the drive with the pack")
        vm("plug", str(img), "family")
        offered = screens.settle(90, until=lambda s: pygame.image.tobytes(s, "RGB") != pygame.image.tobytes(booted, "RGB"))
        screens.save("offered")
        expect(offered, "plugging the drive in changed the screen (the pack was offered)")
        press(ADD_PACK)
        added = screens.settle(30)
        screens.save("added")
        if theme:
            expect(added and share_of(added, theme) > 0.3, f"the screen turned the pack's {theme}")
        press(play_word(word))
        screens.settle(20)
        screens.save(f"play-{word}")
        print(f"  (look for {glyph} in that screen)")
        press(SAVE + ART_FIRST_PICTURE + SAVE)
        screens.settle(20)
        screens.save("art-picture-saved")
        press(to_menu_item(downs))
        screens.settle(60, every=4)
        screens.save("copied-to-usb")
        press(["enter"])
        time.sleep(3)
        vm("unplug", "family")
        art = copied_art(img, args.out)
        expect(art, "the drive has the saved Art page in Purple Computer/Art")
        if art and fixture:
            missing = page_has_colors(art, PICTURE_COLORS)
            expect(not missing, "the copied page is the pack's picture" + (f" (no {', '.join(missing)})" if missing else ""))
    finally:
        if not args.keep_running:
            vm("stop")
    ok = all(r for r, _ in results)
    print(f"vm: {'everything made it there and back' if ok else 'SOMETHING DID NOT MAKE IT'}; screens in {args.out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
