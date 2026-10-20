"""The room checker plays a pack's rooms as Purple would and names what would stop them, from this
repo or as the one-file purple-room-check.pyz Studio serves."""

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from purple_tui.roomkit import check

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import studio_bundle  # noqa: E402


@pytest.fixture
def make_pack(tmp_path):
    def make(**rooms):
        pack = tmp_path / "pack"
        (pack / "content" / "rooms").mkdir(parents=True, exist_ok=True)
        (pack / "manifest.json").write_text(json.dumps({"id": "pack-t", "name": "T", "version": "1.0.0", "type": "emoji"}))
        for name, source in rooms.items():
            (pack / "content" / "rooms" / f"{name}.py").write_text(source)
        return pack
    return make


def test_a_good_room_passes_and_shows_its_screen(make_pack, capsys):
    pack = make_pack(walk='from purple import *\nx = 0\ngrid.set(x, 0, "🐱")\nstatus("Walk")\n'
                          'def on_key(key):\n    global x\n    grid.erase(x, 0)\n    x += key == "right"\n    grid.set(x, 0, "🐱")\n')
    assert check.main([str(pack), "--show", "--keys", "right right"]) == 0
    out = capsys.readouterr().out
    assert "After right:\n+---" in out and "|    🐱" in out and "Walk" in out and "All good." in out


def test_a_broken_room_names_its_line(make_pack, capsys):
    pack = make_pack(oops='from purple import *\ndef on_key(key):\n    if key == "space":\n        drum("snar")\n')
    assert check.main([str(pack)]) == 1
    assert "NEEDS FIXING: line 4: ValueError: there's no drum called 'snar'" in capsys.readouterr().out


def test_a_room_file_is_tried_alone_with_its_pack(make_pack, capsys, tmp_path):
    pack = make_pack(good="from purple import *\n", oops='from purple import *\ndef on_key(key):\n    drum("snar")\n')
    assert check.main([str(pack / "content" / "rooms" / "oops.py")]) == 1
    out = capsys.readouterr().out
    assert "oops:" in out and "good:" not in out
    loose = tmp_path / "loose.py"
    loose.write_text("from purple import *\n")
    assert check.main([str(loose)]) == 0


def test_with_nothing_named_it_asks_which(make_pack, capsys, monkeypatch):
    pack = make_pack(walk="from purple import *\n")
    monkeypatch.setattr(check, "PLACES", (pack.parent,))
    monkeypatch.setattr("builtins.input", lambda _: "1")
    assert check.main([]) == 0
    assert "  1. walk" in capsys.readouterr().out


def test_a_room_that_hangs_is_caught(make_pack, capsys, monkeypatch):
    monkeypatch.setattr(check.L, "STEP_TIMEOUT_S", 0.5)
    pack = make_pack(stuck='from purple import *\ndef on_key(key):\n    while key == "down":\n        pass\n')
    assert check.main([str(pack)]) == 1
    assert "to answer the down key" in capsys.readouterr().out


def test_a_pack_purple_would_refuse_says_why(make_pack, capsys, tmp_path):
    pack = make_pack(fine="from purple import *\n")
    (pack / "content" / "rooms" / "__pycache__").mkdir()
    (pack / "content" / "rooms" / "__pycache__" / "fine.cpython-313.pyc").write_bytes(b"")
    file = tmp_path / "t.purplepack"
    with tarfile.open(file, "w:gz") as tar:
        tar.add(pack / "manifest.json", "manifest.json")
        tar.add(pack / "content", "content")
    assert check.main([str(file)]) == 1
    assert "Purple would refuse this pack: content/rooms/__pycache__/fine.cpython-313.pyc" in capsys.readouterr().out


def test_the_one_file_checker_runs_on_plain_python(make_pack, tmp_path):
    pack = make_pack(hello='from purple import *\nshow("hi")\n')
    pyz = studio_bundle.build_checker(tmp_path / "purple-room-check.pyz")
    out = subprocess.run([sys.executable, "-I", str(pyz), str(pack)], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0 and "All good." in out.stdout, out.stderr
