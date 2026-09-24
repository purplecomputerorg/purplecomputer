"""purple-kmsg-stream writes kernel lines into a fixed span of a block device."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("kmsg_stream", ROOT / "scripts" / "purple-kmsg-stream.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_records_become_dmesg_style_lines_and_continuations_are_dropped():
    k = _load()
    assert k.format_record(b"6,123,4567890,-;hello world\n SUBSYSTEM=usb\n") == b"[    4.567890] hello world\n"
    assert k.format_record(b"not a record") == b""


def test_ring_stays_inside_its_span_and_wraps_with_a_marker(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 400)
    ring = k.Ring(str(dev), 100, 200)
    ring.write(k.HEAD)
    ring.write(b"a" * 50)
    ring.write(b"b" * 100)
    data = dev.read_bytes()
    assert data[:100] == b"X" * 100 and data[300:] == b"X" * 100
    assert data[100:100 + len(k.HEAD)] == k.HEAD
    assert data[100 + len(k.HEAD):].startswith(k.WRAP)
    assert ring.pos <= 200
