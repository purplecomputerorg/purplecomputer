"""purple-stick-log writes the report and the kernel log into fixed regions of
one preallocated file, by offset, never outside it."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(report=400, kmsg=200):
    spec = importlib.util.spec_from_file_location("stick_log", ROOT / "scripts" / "purple-stick-log.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.REPORT_BYTES, mod.KMSG_BYTES = report, kmsg
    return mod


def test_records_become_dmesg_style_lines_and_continuations_are_dropped():
    k = _load()
    assert k.format_record(b"6,123,4567890,-;hello world\n SUBSYSTEM=usb\n") == b"[    4.567890] hello world\n"
    assert k.format_record(b"not a record") == b""


def test_report_region_is_blanked_once_then_padded_to_the_previous_length(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 100 + b"O" * 600 + b"X" * 100)  # O = an earlier boot's text
    s = k.StickFile(str(dev), 100)
    s.write_report(b"first report " * 5)
    d = dev.read_bytes()
    assert d[:100] == b"X" * 100 and d[700:] == b"X" * 100
    assert d[100:].startswith(b"first report ") and b"O" not in d[100:500]
    s.write_report(b"short")
    d = dev.read_bytes()
    assert d[100:105] == b"short" and d[105:].startswith(k.REPORT_END)
    assert d[105 + len(k.REPORT_END):500] == b"\n" * (500 - 105 - len(k.REPORT_END)), "pad with newlines, not spaces"


def test_report_longer_than_its_region_is_cut_and_still_ends_with_the_marker(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 800)
    s = k.StickFile(str(dev), 100)
    s.write_report(b"r" * 1000)
    d = dev.read_bytes()
    assert d[500:] == b"X" * 300 and d[500 - len(k.REPORT_END):500] == k.REPORT_END


def test_kmsg_region_starts_with_its_header_and_wraps_with_a_marker(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 800)
    s = k.StickFile(str(dev), 100)
    s.write_kmsg(b"a" * 50)
    s.write_kmsg(b"b" * 150)
    d = dev.read_bytes()
    assert d[500:].startswith(k.KMSG_HEAD)
    assert d[500 + len(k.KMSG_HEAD):].startswith(k.WRAP) and s.kmsg_pos <= 200
    assert d[700:] == b"X" * 100
