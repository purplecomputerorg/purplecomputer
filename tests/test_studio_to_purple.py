"""Packs Studio's own code builds (studio/sdk, via studio/scripts/fixture-packs.ts), carried to a
running Purple on a drive the way families carry them, then looked for where a kid meets each part;
and saved work going the other way, onto a real FAT filesystem. Python's make_pack fixtures can
drift from what Studio writes; these can't, since Studio writes them."""

import os
import shutil
import subprocess
import tarfile
import threading
import time
from pathlib import Path

import pytest

from purplecomputer import pack_arrivals, settings
from purplecomputer import theme
from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.rooms import save_export
from purplecomputer.usb_updater import sha256, update_from
from tests.pack_journey import check, deliver, isolate
from tests.real_purple import (ADD_PACK, ART_FIRST_PICTURE, PICTURE_COLORS, SAVE, menu_downs, page_has_colors, play_word,
                                      replay, to_menu_item)

STUDIO = Path(__file__).parents[1] / "studio"
VITE_NODE = STUDIO / "node_modules" / ".bin" / "vite-node"
EVERYTHING, WORDS = "pack-e2e00001", "pack-e2e00002"


@pytest.fixture(scope="session")
def sdk_packs(tmp_path_factory) -> dict[str, Path]:
    if not shutil.which("node") or not VITE_NODE.exists():
        pytest.skip("node or studio/node_modules not found (npm install in studio/): Studio→Purple seam tests skipped")
    out = tmp_path_factory.mktemp("sdk-packs")
    subprocess.run([str(VITE_NODE), "scripts/fixture-packs.ts", str(out)], cwd=STUDIO, check=True, timeout=120)
    return {p.stem: p for p in out.glob("*.purplepack")}


@pytest.fixture
def purple(tmp_path, monkeypatch):
    isolate(tmp_path / "purple", monkeypatch)
    yield tmp_path
    theme.apply({})


def drive_with(tmp_path, files: dict[str, bytes | Path]) -> Path:
    """A drive's files, oldest first, a second apart, as downloads land."""
    drive = tmp_path / "drive"
    for i, (name, data) in enumerate(files.items()):
        path = drive / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.read_bytes() if isinstance(data, Path) else data)
        os.utime(path, (time.time() - 100 + i, time.time() - 100 + i))
    return drive


def test_everything_studio_can_put_in_a_pack_reaches_the_kid(sdk_packs, purple):
    async def go():
        app = make_app()
        seen = await deliver(app, drive_with(purple, {"the-tests-purple.purplepack": sdk_packs["everything"]}))
        assert app.top is None, seen
        assert seen[0].startswith("Confirm") and "The Tests' Purple" in seen[0]
        failed = [c.what for c in await check(app, sdk_packs["everything"]) if not c.ok]
        assert not failed, failed
    run(go())


def test_two_downloads_of_one_pack_offer_the_newer(sdk_packs, purple):
    async def go():
        app = make_app()
        drive = drive_with(purple, {"the-tests-purple.purplepack": sdk_packs["everything-before"],
                                    "the-tests-purple (1).purplepack": sdk_packs["everything"]})
        seen = await deliver(app, drive)
        assert len([s for s in seen if s.startswith("Confirm")]) == 1
        assert settings.get_packs_added() == {EVERYTHING: sha256(drive / "the-tests-purple (1).purplepack")}
    run(go())


@pytest.mark.parametrize("layout", ["downloads folder", "renamed", "mac copy"])
def test_packs_are_found_however_the_drive_was_filled(sdk_packs, purple, layout):
    files = {
        "downloads folder": {"Downloads/everything.purplepack": sdk_packs["everything"], "Downloads/words.purplepack": sdk_packs["words"]},
        "renamed": {"Grandma's Purple!.purplepack": sdk_packs["everything"], "flib.purplepack": sdk_packs["words"]},
        "mac copy": {"everything.purplepack": sdk_packs["everything"], "._everything.purplepack": b"\x00\x05\x16\x07Mac OS X",
                     ".Spotlight-V100/Store-V2/x.purplepack": b"junk", "words.purplepack": sdk_packs["words"]},
    }[layout]

    async def go():
        app = make_app()
        seen = await deliver(app, drive_with(purple, files))
        assert not [s for s in seen if "Couldn't" in s], seen
        assert set(settings.get_packs_added()) == {EVERYTHING, WORDS}
    run(go())


def test_a_download_cut_short_says_so_and_the_rest_still_go_in(sdk_packs, purple):
    whole = sdk_packs["everything"].read_bytes()

    async def go():
        app = make_app()
        seen = await deliver(app, drive_with(purple, {"words.purplepack": whole[: len(whole) // 2],
                                                      "everything.purplepack.crdownload": whole[:100],
                                                      "everything.purplepack": whole}))
        assert any(s.startswith("Notice | Couldn't add this Purple Pack") for s in seen), seen
        assert set(settings.get_packs_added()) == {EVERYTHING}
    run(go())


def test_a_studio_pack_from_a_newer_format_is_refused_whole(sdk_packs, purple):
    from purplecomputer.content import PACK_FORMAT
    newer = purple / "newer.purplepack"
    with tarfile.open(sdk_packs["words"]) as src, tarfile.open(newer, "w:gz") as dst:
        for m in src.getmembers():
            data = src.extractfile(m).read() if m.isfile() else None
            if m.name.endswith("manifest.json"):
                data = data.replace(b'"format": 1', f'"format": {PACK_FORMAT + 1}'.encode())
                m.size = len(data)
            dst.addfile(m, __import__("io").BytesIO(data) if data is not None else None)

    async def go():
        app = make_app()
        seen = await deliver(app, drive_with(purple, {"words.purplepack": newer}))
        assert seen[0].startswith("Notice | Needs newer Purple software"), seen
        assert settings.get_packs_added() == {}
    run(go())


# ----------------------------------------------------------- saved work onto a drive

def _fat_image(tmp_path) -> Path | None:
    if not (shutil.which("mkfs.fat") and shutil.which("mcopy")):
        return None
    img = tmp_path / "drive.img"
    subprocess.run(["mkfs.fat", "-C", "-n", "KIDS", str(img), "16384"], check=True, capture_output=True)
    return img


def _fat_files(img: Path) -> list[str]:
    """Every file on the image, as a Windows or Mac reading the drive sees it."""
    out = subprocess.run(["mdir", "-i", str(img), "-/", "-b", "::/"], check=True, capture_output=True, text=True).stdout
    return sorted(line.removeprefix("::/") for line in out.splitlines() if not line.endswith("/"))


@pytest.fixture
def stick(purple, monkeypatch):
    """A plugged-in drive, already mounted at the returned folder; inline(app) then runs the copy's
    thread and its hops back to the UI at once, so the copy is done when the screen opens."""
    mounted = purple / "mounted"
    mounted.mkdir()
    monkeypatch.setattr(save_export, "find_stick", lambda *_: ("/dev/sdz1", str(mounted)))

    class Now:
        def __init__(self, target, args=(), **_):
            self.start = lambda: target(*args)

    def inline(app):
        monkeypatch.setattr(app, "call_from_thread", lambda fn, *a: fn(*a))
        monkeypatch.setattr(threading, "Thread", Now)
    return mounted, inline


def test_saved_work_copies_onto_a_fat_drive_with_its_names(purple, stick):
    img = _fat_image(purple)
    if img is None:
        pytest.skip("mtools/dosfstools not found: FAT export test skipped")
    stick, inline = stick

    async def go():
        app = make_app()
        app.action_switch_room("art")
        await type_text(app, "qwerty")
        await press(app, "escape")
        await press(app, "s")
        app.set_room_off("write", False)
        app.action_switch_room("write")
        await type_text(app, "my cat is purple")
        await press(app, "escape")
        await press(app, "s")
        inline(app)
        screen = save_export.SaveExportScreen(app)
        app.push(screen)
        assert screen.body_lines[0] == "Copied 2 pictures.", screen.body_lines
    run(go())

    written = sorted(str(p.relative_to(stick)) for p in stick.rglob("*") if p.is_file())
    assert [Path(p).parts[:2] for p in written] == [("Purple Computer", "Art"), ("Purple Computer", "Write"), ("Purple Computer", "Write")]
    subprocess.run(["mcopy", "-s", "-i", str(img), str(stick / "Purple Computer"), "::/"], check=True, capture_output=True)
    assert _fat_files(img) == written
    text = next(p for p in written if p.endswith(".txt"))
    got = subprocess.run(["mtype", "-i", str(img), f"::/{text}"], check=True, capture_output=True, text=True).stdout
    assert "my cat is purple" in got.lower()


def test_the_vm_key_script_adds_uses_and_copies_out_here(sdk_packs, purple, stick):
    """scripts/e2e_vm.py presses these keys blind on a booted ISO; here each one is checked."""
    stick, inline = stick

    async def go():
        app = make_app()
        update_from(drive_with(purple, {"everything.purplepack": sdk_packs["everything"]}), pack_arrivals.WAITING_DIR)
        app._check_pack_arrivals()
        await replay(app, ADD_PACK)
        assert app.top is None and EVERYTHING in settings.get_packs_added() and settings.get_rooms_on()
        await replay(app, play_word("zorb"))
        assert app.active_room == "play" and "🐙" in app.rooms["play"].history[-1].markup
        await replay(app, SAVE + ART_FIRST_PICTURE + SAVE)
        assert app.active_room == "art" and app.top is None
        inline(app)
        await replay(app, to_menu_item(menu_downs(app, "menu-export")))
        assert isinstance(app.top, save_export.SaveExportScreen) and app.top.body_lines[0] == "Copied 2 pictures."
    run(go())
    [art] = (stick / "Purple Computer" / "Art").glob("*.png")
    assert page_has_colors(art, PICTURE_COLORS) == []
