"""purple-key-save keeps Purple's state in two slots of PURPLE-SAVE, written in
place: never outside the file, and never so that a torn write loses the last good copy."""
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("key_save", ROOT / "scripts" / "purple-key-save.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _save_dev(tmp_path, k):
    k.SLOT_BYTES = 8192
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 100 + k.pristine() + b"X" * 100)
    return dev, k.SaveFile(str(dev), 100)


def test_save_slots_alternate_and_a_torn_write_leaves_the_last_good_copy(tmp_path):
    k = _load()
    dev, f = _save_dev(tmp_path, k)
    assert f.is_ours() and f.read_slots() == []
    assert f.write(1, b"one") and f.write(2, b"two")
    assert [s for s, _ in f.read_slots()] == [2, 1] and f.read_slots()[0][1] == b"two"
    d = bytearray(dev.read_bytes())
    slot1 = 100 + k.HEADER_BYTES + k.SLOT_BYTES
    d[slot1 + k.SLOT_HEAD] ^= 1  # copy 3 was mid-write in slot 1 when the power went
    dev.write_bytes(bytes(d))
    assert f.read_slots() == [(2, b"two")]
    assert d[:100] == b"X" * 100 and d[-100:] == b"X" * 100, "never writes outside the file"
    assert not f.write(3, b"x" * k.SLOT_BYTES), "too big for a slot: the Key is full"


def test_save_refuses_a_device_that_no_longer_holds_the_file(tmp_path):
    k = _load()
    dev, f = _save_dev(tmp_path, k)
    dev.write_bytes(b"\0" * len(dev.read_bytes()))
    assert not f.is_ours()


def test_save_pack_round_trip(tmp_path, monkeypatch):
    k = _load()
    src = tmp_path / "src"
    (src / "saves/art").mkdir(parents=True)
    (src / "saves/art/1-a.json").write_text("{}")
    (src / "settings.json").write_text('{"v": 1}')
    out = tmp_path / "home/.config/purple"
    monkeypatch.setattr(k.os, "chown", lambda *a: None)
    k.unpack(k.pack(str(src)), str(out), os.getuid())
    assert (out / "saves/art/1-a.json").read_text() == "{}" and (out / "settings.json").exists()
