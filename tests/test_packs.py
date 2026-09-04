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
from purple_tui.usb_updater import update_from  # noqa: E402
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
        assert [(p.name, p.ops) for p in packs.pictures] == [("palm", [(43, 0, "#ffffff"), (44, 1, "#fefefe")])]

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

    def test_later_pack_wins_lookups(self, tmp_path):
        make_pack(tmp_path, "a-pack")
        make_pack(tmp_path, "b-pack")
        cm = ContentManager(packs_dir=tmp_path)
        cm.load_all()
        assert cm.pack_dirs("letters")[0] == tmp_path / "b-pack" / "content" / "letters"
        assert cm.instrument_dir("kitchen") == tmp_path / "b-pack" / "content" / "kitchen"

    def test_voice_clip_from_pack_beats_core(self, packs, tmp_path):
        assert tts._get_voice_clip("Hi there") == tmp_path / "the-tests-pack" / "content" / "voice" / "hi_there.wav"
        assert tts._get_voice_clip("definitely not a clip") is None


class TestCheckPack:
    def test_studio_shaped_pack_is_clean(self, tmp_path):
        assert check_pack(make_pack(tmp_path)) == []

    @pytest.mark.parametrize("break_it, expect", [
        (lambda d: write_wav(d / "content" / "letters" / "b.wav", rate=44100), "letters/b.wav: expected 22050 Hz"),
        (lambda d: (d / "content" / "kitchen.py").write_text("print(1)"), "may not contain code"),
        (lambda d: (d / "content" / "emoji.json").write_text('{"cat": 3}'), "emoji.json: every entry"),
        (lambda d: (d / "content" / "instruments" / "kitchen.json").write_text(json.dumps({"name": "k", "base": "marimba", "params": {"reverb": 1}})), "no parameter 'reverb'"),
        (lambda d: (d / "content" / "instruments" / "kitchen.json").write_text(json.dumps({"name": "k", "base": "piano"})), "base must be one of"),
        (lambda d: (d / "content" / "pictures" / "palm.json").write_text(json.dumps({"ops": [[999, 0, "#ffffff"]]})), "off the 132 by 25 canvas"),
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
    def test_installs_every_pack_on_the_stick_and_replaces_on_rerun(self, tmp_path):
        stick = tmp_path / "stick"
        stick.mkdir()
        build_pack(make_pack(tmp_path / "a", "a-pack"), stick / "a-pack.purplepack")
        build_pack(make_pack(tmp_path / "b", "b-pack"), stick / "b-pack.purplepack")
        (stick / "notes.txt").write_text("ignored")
        packs_dir = tmp_path / "home" / ".purple" / "packs"
        first = update_from(stick, packs_dir)
        assert [(name, ok) for name, ok, _ in first] == [("a-pack.purplepack", True), ("b-pack.purplepack", True)]
        second = update_from(stick, packs_dir)
        assert all(ok for _, ok, _ in second)
        assert sorted(p.name for p in packs_dir.iterdir()) == ["a-pack", "b-pack"]


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
