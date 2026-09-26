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


def test_report_is_written_in_place_and_leftovers_stay_below_the_end_marker(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 100 + b"O" * 600 + b"X" * 100)  # O = an earlier boot's text
    s = k.StickFile(str(dev), 100)
    s.write_report(b"short")
    d = dev.read_bytes()
    assert d[:100] == b"X" * 100 and d[700:] == b"X" * 100
    assert d[100:105 + len(k.REPORT_END)] == b"short" + k.REPORT_END
    assert d[105 + len(k.REPORT_END):500] == b"O" * (395 - len(k.REPORT_END)), "no megabyte blanking during boot"


def test_report_longer_than_its_region_is_cut_and_still_ends_with_the_marker(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 800)
    s = k.StickFile(str(dev), 100)
    s.write_report(b"r" * 1000)
    d = dev.read_bytes()
    assert d[500:] == b"X" * 300 and d[500 - len(k.REPORT_END):500] == k.REPORT_END


def test_kmsg_region_keeps_a_seam_after_the_newest_line_and_wraps_with_a_marker(tmp_path):
    k = _load(kmsg=430)
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 1000)
    s = k.StickFile(str(dev), 100)
    region = lambda: dev.read_bytes()[500:930]
    s.write_kmsg(b"a" * 50)
    assert region().startswith(k.KMSG_HEAD + b"a" * 50 + k.SEAM)
    s.write_kmsg(b"b" * 50)
    assert region().startswith(k.KMSG_HEAD + b"a" * 50 + b"b" * 50 + k.SEAM), "the next write overwrites the seam"
    s.write_kmsg(b"c" * 200)
    assert region()[len(k.KMSG_HEAD):].startswith(k.WRAP + b"c" * 200 + k.SEAM)
    assert s.kmsg_pos + len(k.SEAM) <= 430 and dev.read_bytes()[930:] == b"X" * 70


def test_schedule_stretches_after_slow_writes_and_holds_while_the_disk_is_busy_but_not_forever():
    k = _load()
    sched = k.Schedule()
    sched.done(0.0, 0.01, 10.0)
    assert sched.due == 10.0, "fast writes keep the base interval"
    sched.done(0.0, 2.0, 10.0)
    assert sched.due == 2.0 / k.WRITE_SHARE
    sched.done(0.0, 60.0, 10.0)
    assert sched.due == k.STRETCH_MAX, "a very slow stick still gets a report every few minutes"
    k.io_busy = lambda: True
    sched = k.Schedule()
    assert not sched.ready(1.0) and sched.due == 1.0 + k.BUSY_RETRY
    assert sched.ready(1.0 + k.BUSY_WAIT_MAX), "a busy disk delays a write, never skips it"


def test_reports_slow_down_once_purple_is_on_screen(tmp_path):
    k = _load()
    k.BOOT_LOG = str(tmp_path / "boot.log")
    w = k.Writer(None)
    assert w.report_interval(0.0) == k.REPORT_BOOTING
    (tmp_path / "boot.log").write_bytes(b"[python] " + k.UI_MARK + b"; watchdog disarmed\n")
    assert w.report_interval(100.0) == k.REPORT_UI
    assert w.report_interval(100.0 + k.UI_BUSY_FOR) == k.REPORT_IDLE


def test_log_summary_reads_the_file_the_writer_produces(tmp_path, capsys):
    k = _load(report=4000, kmsg=2000)
    spec = importlib.util.spec_from_file_location("log_summary", ROOT / "scripts" / "purple-log-summary.py")
    summary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summary)
    dev = tmp_path / "PURPLE-LOG"
    dev.write_bytes(b"\n" * 6000)
    s = k.StickFile(str(dev), 0)
    s.write_report(b"stick log: the last report took 0.05s to write, the kernel log 0.01s\n"
                   b"purple-boot-report 2026-09-25 uptime=40s\n\n===== boot log =====\n"
                   b"[10:00:01] xinitrc] === start\n\n===== processes (wchan) =====\n"
                   b"  PID  PPID STAT ETIMES WCHAN COMMAND\n  812     1 D        30 io_schedule python3\n")
    s.write_kmsg(b"[   12.000000] blk_update_request: I/O error, dev sdb, sector 1234\n")
    s.write_kmsg(b"[   13.000000] blk_update_request: I/O error, dev sdb, sector 5678\n")
    summary.summarize(dev.read_text())
    out = capsys.readouterr().out
    assert "NEVER reached" in out and "io_schedule" in out
    assert "I/O error, dev sdb, sector 1234  (x2)" in out, "repeats collapse to one line with a count"
    assert "newest kernel log line above" not in out


def test_a_pulled_stick_backs_off_instead_of_collecting_every_tick(monkeypatch):
    k = _load()
    collected = []
    monkeypatch.setattr(k, "collect", lambda timeout=120: collected.append(1) or b"")

    class Gone:
        def write_report(self, data):
            raise OSError(5, "Input/output error")

    w = k.Writer(Gone())
    w.tick()
    w.tick()
    assert len(collected) == 1 and w.report.due >= k.STRETCH_MAX


def _usb_cache(tmp_path, monkeypatch, avail, mlock_rc):
    spec = importlib.util.spec_from_file_location("usb_cache", ROOT / "scripts" / "purple-usb-cache.py")
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    (tmp_path / "fs.squashfs").write_bytes(b"s" * 5000)
    (tmp_path / "boot.log").write_text("")
    c.SQUASHFS, c.LIVE_CONF = str(tmp_path / "fs.squashfs"), str(tmp_path / "none")
    c.MARKER, c.BOOT_LOGS = str(tmp_path / "cached"), (str(tmp_path / "boot.log"), str(tmp_path / "absent.log"))
    monkeypatch.setattr(c, "mem_available", lambda: avail)
    monkeypatch.setattr(c.ctypes, "CDLL", lambda *a, **kw: type("L", (), {"mlockall": staticmethod(lambda f: mlock_rc)})())
    paused = []
    monkeypatch.setattr(c.signal, "pause", lambda: paused.append(1))
    c.main()
    return (tmp_path / "boot.log").read_text(), (tmp_path / "cached").exists(), bool(paused)


def test_usb_cache_locks_when_there_is_room_and_holds_the_lock(tmp_path, monkeypatch):
    log, marker, held = _usb_cache(tmp_path, monkeypatch, avail=4 << 30, mlock_rc=0)
    assert "[usb-cache] Squashfs locked in RAM" in log and "USB safe to remove" in log
    assert marker and held
    assert not (tmp_path / "absent.log").exists(), "never creates a boot log as root"


def test_usb_cache_only_warms_with_low_ram_or_a_failed_lock(tmp_path, monkeypatch):
    log, marker, held = _usb_cache(tmp_path, monkeypatch, avail=512 << 20, mlock_rc=0)
    assert "Low RAM" in log and marker and not held
    log, marker, held = _usb_cache(tmp_path, monkeypatch, avail=4 << 30, mlock_rc=-1)
    assert "Could not lock" in log and marker and not held
