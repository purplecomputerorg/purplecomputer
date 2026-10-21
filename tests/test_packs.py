"""User packs end to end: what the loader reads, what the installer refuses,
the USB updater, and the purplepack CLI, all against a Studio-shaped pack."""

import json
import os
import sys
import tarfile
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui import content as content_mod  # noqa: E402
from purple_tui import tts  # noqa: E402
from purple_tui.content import ContentManager  # noqa: E402
from purple_tui.music_constants import INSTRUMENTS, instruments, pitch_filename, reachable_pitches  # noqa: E402
from purple_tui.pack_manager import PackInstaller, check_pack  # noqa: E402
from purple_tui.usb_updater import sha256, update_from  # noqa: E402
from scripts.purplepack import build_pack, render_instruments  # noqa: E402


def write_wav(path: Path, rate: int = 22050, frames: int = 220) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)
    return path


def make_pack(root: Path, pack_id: str = "the-tests-pack", fmt: int | None = 1, instrument: str | None = "kitchen") -> Path:
    """A pack shaped like Studio's output, unpacked at root/pack_id."""
    d = root / pack_id
    c = d / "content"
    c.mkdir(parents=True)
    manifest = {"id": pack_id, "name": "The Tests' Purple", "version": "1.0.0", "type": "emoji"}
    if fmt is not None:
        manifest["format"] = fmt
    (d / "manifest.json").write_text(json.dumps(manifest))
    (c / "emoji.json").write_text(json.dumps({"zorb": "🐙"}))
    (c / "synonyms.json").write_text(json.dumps({"zorbo": "zorb"}))
    write_wav(c / "letters" / "a.wav")
    write_wav(c / "voice" / "hi_there.wav")
    (c / "pictures").mkdir()
    (c / "pictures" / "palm.json").write_text(json.dumps({"name": "palm", "ops": [[43, 0, "#ffffff"], [44, 1, "#fefefe"]]}))
    (c / "pictures" / "grandmas-dog.json").write_text(json.dumps({"name": "Grandma's dog", "ops": [[0, 0, "#000000"]], "letters": [[1, 0, "D", "#ffffff"]]}))
    (c / "rooms").mkdir()
    (c / "rooms" / "farm.py").write_text('from purple import *\n\ndef on_key(key):\n    show("🐄")\n    say("cow")\n')
    (c / "rooms" / "farm.studio.json").write_text("{}")
    if instrument:
        (c / "instruments").mkdir()
        (c / "instruments" / f"{instrument}.json").write_text(json.dumps(
            {"name": instrument, "base": "marimba", "params": {"duration": 0.02, "wood": 0.9}}))
        write_wav(c / instrument / "c4.wav", rate=44100)
    return d


@pytest.fixture
def packs(tmp_path, monkeypatch):
    """A packs dir with one Studio-shaped pack, made the global content."""
    make_pack(tmp_path)
    cm = ContentManager(packs_dir=tmp_path)
    cm.load_all()
    monkeypatch.setattr(content_mod, "_content", cm)
    return cm


class TestLoader:
    def test_reads_every_studio_directory(self, packs, tmp_path):
        c = tmp_path / "the-tests-pack" / "content"
        assert packs.exact_emoji("zorbo") == "🐙"
        assert packs.pack_dirs("letters") == [c / "letters"]
        assert packs.pack_dirs("voice") == [c / "voice"]
        assert packs.pack_dirs("nope") == []
        assert [(i.id, i.name, i.path) for i in packs.instruments] == [("kitchen", "Kitchen", c / "kitchen")]
        assert packs.instrument_dir("kitchen") == c / "kitchen"
        assert packs.instrument_dir("marimba") is None
        assert [(p.name, p.title, p.ops, p.letters) for p in packs.pictures] == [
            ("grandmas-dog", "Grandma's dog", [(0, 0, "#000000")], [(1, 0, "D", "#ffffff")]),
            ("palm", "Palm", [(43, 0, "#ffffff"), (44, 1, "#fefefe")], [])]
        assert [(r.name, r.title, r.path) for r in packs.rooms] == [("farm", "Farm", c / "rooms" / "farm.py")]

    def test_picture_with_a_bad_letter_is_not_listed(self, tmp_path):
        d = make_pack(tmp_path)
        (d / "content" / "pictures" / "palm.json").write_text(json.dumps({"ops": [], "letters": [[0, 0, "AB", "#ffffff"]]}))
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        assert [p.name for p in cm.pictures] == ["grandmas-dog"]

    def test_room_with_a_syntax_error_is_refused_by_the_installer(self, tmp_path):
        d = make_pack(tmp_path)
        (d / "content" / "rooms" / "bad.py").write_text("def on_key(key)\n    show(key)\n")
        assert any("rooms/bad.py: line 1" in p for p in check_pack(d))

    def test_code_anywhere_but_rooms_is_refused(self, tmp_path):
        d = make_pack(tmp_path)
        (d / "content" / "evil.py").write_text("print('hi')\n")
        (d / "content" / "rooms" / "Not_A_Name.py").write_text("print('hi')\n")
        problems = check_pack(d)
        assert any("content/evil.py: packs may not contain code" in p for p in problems)
        assert any("Not_A_Name.py: packs may not contain code" in p for p in problems)
        assert not any("farm.py" in p for p in problems)

    def test_the_room_library_rides_beside_the_rooms_and_is_not_a_room(self, tmp_path):
        d = make_pack(tmp_path)
        lib = d / "content" / "rooms" / "purple.py"
        lib.write_text("def run(start):\n    pass\n")
        assert check_pack(d) == []
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        assert [(r.name, r.lib, r.key) for r in cm.rooms] == [("farm", lib, "the-tests-pack/farm")]
        lib.write_text("def run(start)\n")
        assert any("rooms/purple.py: line 1" in p for p in check_pack(d))

    def test_rooms_see_the_packs_png_images_and_wav_sounds(self, tmp_path):
        import pygame
        d = make_pack(tmp_path)
        images, sounds = d / "content" / "images", d / "content" / "sounds"
        images.mkdir()
        pygame.image.save(pygame.Surface((16, 8)), str(images / "hero.png"))
        write_wav(sounds / "meow.wav")
        assert check_pack(d) == []
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        room, = cm.rooms
        assert room.images == {"hero": images / "hero.png"} and room.sounds == {"meow": sounds / "meow.wav"}
        assert content_mod.png_size(images / "hero.png") == (16, 8)
        (images / "photo.jpg").write_bytes(b"\xff\xd8")
        (images / "Big Cat.png").write_bytes((images / "hero.png").read_bytes())
        write_wav(sounds / "fast.wav", rate=44100)
        problems = check_pack(d)
        assert any("images/photo.jpg: only PNG" in p for p in problems)
        assert any("images/Big Cat.png: names are" in p for p in problems)
        assert any("sounds/fast.wav: expected 22050 Hz" in p for p in problems)

    def test_pack_instruments_follow_the_built_ins(self, packs):
        assert instruments() == INSTRUMENTS + [("kitchen", "Kitchen")]

    def test_pack_instrument_with_a_built_in_id_replaces_it(self, tmp_path, monkeypatch):
        make_pack(tmp_path, instrument="marimba")
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        monkeypatch.setattr(content_mod, "_content", cm)
        assert instruments() == [("marimba", "Marimba"), *INSTRUMENTS[1:]]
        assert cm.instrument_dir("marimba") == tmp_path / "the-tests-pack" / "content" / "marimba"

    def test_instrument_json_without_samples_is_not_listed(self, tmp_path):
        d = make_pack(tmp_path)
        (d / "content" / "instruments" / "silent.json").write_text(json.dumps({"name": "silent", "base": "ukulele", "params": {}}))
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        assert [i.id for i in cm.instruments] == ["kitchen"]

    def test_newer_format_is_skipped_whole(self, tmp_path):
        make_pack(tmp_path, fmt=2)
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        assert cm.exact_emoji("zorb") is None
        assert cm.user_content == [] and cm.instruments == [] and cm.pictures == []

    def test_newest_pack_wins_lookups_whatever_its_name(self, tmp_path):
        for pack_id, built in (("a-pack", 2000), ("b-pack", 1000)):
            d = make_pack(tmp_path, pack_id)
            (d / "content" / "emoji.json").write_text(json.dumps({"zorb": pack_id}))
            os.utime(d / "manifest.json", (built, built))
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        assert cm.exact_emoji("zorb") == "a-pack"
        assert cm.pack_dirs("letters")[0] == tmp_path / "a-pack" / "content" / "letters"
        assert cm.instrument_dir("kitchen") == tmp_path / "a-pack" / "content" / "kitchen"

    def test_voice_clip_from_pack_beats_core(self, packs, tmp_path):
        assert tts._get_voice_clip("Hi there") == tmp_path / "the-tests-pack" / "content" / "voice" / "hi_there.wav"
        assert tts._get_voice_clip("definitely not a clip") is None

    def test_a_rooms_own_line_beats_every_other_clip_only_in_that_room(self, packs, tmp_path):
        room_voice = tmp_path / "the-tests-pack" / "content" / "room-voice"
        write_wav(room_voice / "hi_there.wav")
        assert tts._get_voice_clip("Hi there", room_voice) == room_voice / "hi_there.wav"
        assert tts._get_voice_clip("Hi there") == tmp_path / "the-tests-pack" / "content" / "voice" / "hi_there.wav"


class TestCheckPack:
    def test_studio_shaped_pack_is_clean(self, tmp_path):
        assert check_pack(make_pack(tmp_path)) == []

    @pytest.mark.parametrize("break_it, expect", [
        (lambda d: write_wav(d / "content" / "letters" / "b.wav", rate=44100), "letters/b.wav: expected 22050 Hz"),
        (lambda d: write_wav(d / "content" / "room-voice" / "hi.wav", rate=24000), "room-voice/hi.wav: expected 22050 Hz"),
        (lambda d: (d / "content" / "kitchen.py").write_text("print(1)"), "may not contain code"),
        (lambda d: (d / "content" / "emoji.json").write_text('{"cat": 3}'), "emoji.json: every entry"),
        (lambda d: (d / "content" / "instruments" / "kitchen.json").write_text(json.dumps({"name": "k", "base": "marimba", "params": {"reverb": 1}})), "no parameter 'reverb'"),
        (lambda d: (d / "content" / "instruments" / "kitchen.json").write_text(json.dumps({"name": "k", "base": "piano"})), "base must be one of"),
        (lambda d: (d / "content" / "pictures" / "palm.json").write_text(json.dumps({"ops": [[999, 0, "#ffffff"]]})), "off the 56 by 24 Art grid"),
        (lambda d: (d / "content" / "pictures" / "palm.json").write_text(json.dumps({"ops": [], "letters": [[0, 0, " ", "#ffffff"]]})), "letters must be a list"),
        (lambda d: (d / "manifest.json").write_text(json.dumps({"id": "x", "name": "x", "version": "1.0", "type": "emoji"})), "Invalid version"),
        (lambda d: (d / "manifest.json").write_text(json.dumps({"id": "../x", "name": "x", "version": "1.0.0", "type": "emoji"})), "Invalid pack id"),
        (lambda d: (d / "manifest.json").write_text(json.dumps({"id": "x", "name": "x", "version": "1.0.0", "type": "emoji", "format": 9})), "newer format"),
    ])
    def test_each_rule(self, tmp_path, break_it, expect):
        d = make_pack(tmp_path)
        break_it(d)
        problems = check_pack(d)
        assert any(expect in p for p in problems), problems


class TestInstaller:
    def test_install_replace_and_refuse(self, tmp_path):
        pack = build_pack(make_pack(tmp_path / "src"))
        assert pack.name == "the-tests-pack.purplepack"
        installer = PackInstaller(tmp_path / "packs")
        ok, msg = installer.install_pack(pack)
        assert ok, msg
        assert (tmp_path / "packs" / "the-tests-pack" / "content" / "kitchen" / "c4.wav").exists()
        assert installer.install_pack(pack) == (False, "Pack already installed: the-tests-pack")
        ok, _ = installer.install_pack(pack, replace=True)
        assert ok
        assert [p["id"] for p in installer.list_installed()] == ["the-tests-pack"]
        assert not (tmp_path / "packs" / ".tmp" / "the-tests-pack").exists()

    def test_refuses_broken_content_and_symlinks(self, tmp_path):
        d = make_pack(tmp_path / "src")
        (d / "content" / "run.py").write_text("")
        bad = build_pack(d)
        ok, msg = PackInstaller(tmp_path / "packs").install_pack(bad)
        assert not ok and "may not contain code" in msg

        (d / "content" / "run.py").unlink()
        os.symlink("/etc/passwd", d / "content" / "link")
        linked = build_pack(d, tmp_path / "linked.purplepack")
        assert PackInstaller(tmp_path / "packs").install_pack(linked) == (False, "Security error: Invalid path in pack")
        assert not (tmp_path / "packs" / "the-tests-pack").exists()


class TestUsbUpdater:
    def test_sets_aside_each_good_pack_by_its_hash_and_installs_nothing(self, tmp_path):
        stick = tmp_path / "stick"
        stick.mkdir()
        build_pack(make_pack(tmp_path / "a", "a-pack"), stick / "a-pack.purplepack")
        build_pack(make_pack(tmp_path / "b", "b-pack"), stick / "b-pack.purplepack")
        bad = make_pack(tmp_path / "bad", "bad-pack")
        (bad / "content" / "run.py").write_text("")
        build_pack(bad, stick / "bad.purplepack")
        (stick / "notes.txt").write_text("ignored")
        waiting = tmp_path / "home" / ".purple" / "packs-waiting"
        first = update_from(stick, waiting)
        assert [(name, ok) for name, ok, _ in first] == [("a-pack.purplepack", True), ("b-pack.purplepack", True), ("bad.purplepack", False)]
        assert sorted(d.name for d in waiting.iterdir() if not d.name.startswith(".")) == sorted(sha256(stick / f"{p}.purplepack") for p in ("a-pack", "b-pack"))
        assert [s["name"] for s in json.loads((waiting / ".skipped.json").read_text())] == ["The Tests' Purple"]
        assert [msg for _, _, msg in update_from(stick, waiting)][:2] == ["already waiting"] * 2
        assert not (tmp_path / "home" / ".purple" / "packs").exists()

    def test_two_copies_of_one_pack_set_aside_only_the_newer(self, tmp_path):
        stick = tmp_path / "stick"
        stick.mkdir()
        new = make_pack(tmp_path / "new", "a-pack")
        (new / "content" / "theme.json").write_text("{}")
        build_pack(make_pack(tmp_path / "old", "a-pack"), stick / "a-pack (1).purplepack")
        build_pack(new, stick / "a-pack.purplepack")
        os.utime(stick / "a-pack (1).purplepack", (1, 1))
        waiting = tmp_path / "waiting"
        for _ in range(2):
            results = update_from(stick, waiting)
            assert [(name, ok) for name, ok, _ in results] == [("a-pack (1).purplepack", False), ("a-pack.purplepack", True)]
            assert [d.name for d in waiting.iterdir()] == [sha256(stick / "a-pack.purplepack")]


class TestRender:
    def test_python_renders_the_missing_samples(self, tmp_path):
        d = make_pack(tmp_path)
        written = render_instruments(d)
        samples = d / "content" / "kitchen"
        assert len(written) == len(reachable_pitches()) - 1  # c4.wav was already there
        assert sorted(p.stem for p in samples.glob("*.wav")) == sorted(pitch_filename(n, o) for n, o in reachable_pitches())
        with wave.open(str(samples / "a4.wav")) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (44100, 1, 2)
            assert w.getnframes() == int(44100 * 0.02)
        assert check_pack(d) == []
        assert render_instruments(d) == []


def test_build_is_a_plain_gzipped_tar(tmp_path):
    pack = build_pack(make_pack(tmp_path))
    with tarfile.open(pack) as tar:
        names = tar.getnames()
    assert "manifest.json" in names and "content/emoji.json" in names and "content/kitchen/c4.wav" in names
