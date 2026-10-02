"""purple-stick-log writes the report and the kernel log into this start's
slot of one preallocated file, by offset, never outside it."""
import importlib.util
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(report=400, kmsg=200, header=0, keep=0):
    spec = importlib.util.spec_from_file_location("stick_log", ROOT / "scripts" / "purple-stick-log.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if report:
        mod.REPORT_BYTES, mod.KMSG_BYTES, mod.HEADER_BYTES, mod.KMSG_KEEP = report, kmsg, header, keep
    return mod


def _real():
    return _load(report=None)


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
    text = b"start 0 of this stick\nshort" + k.REPORT_END
    assert d[:100] == b"X" * 100 and d[700:] == b"X" * 100
    assert d[100:100 + len(text)] == text
    assert d[100 + len(text):500] == b"O" * (400 - len(text)), "no megabyte blanking during boot"


def test_report_longer_than_its_region_is_cut_says_so_and_still_ends_with_the_marker(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 800)
    s = k.StickFile(str(dev), 100)
    s.write_report(b"r" * 1000)
    d = dev.read_bytes()
    assert d[500:] == b"X" * 300 and d[500 - len(k.REPORT_END):500] == k.REPORT_END
    assert d[500 - len(k.REPORT_END) - len(k.CUT):500 - len(k.REPORT_END)] == k.CUT


def test_kmsg_region_keeps_a_seam_after_the_newest_line_and_wraps_past_the_kept_start(tmp_path):
    k = _load(kmsg=600, keep=20)
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 1200)
    s = k.StickFile(str(dev), 100)
    region = lambda: dev.read_bytes()[500:1100]
    s.write_kmsg(b"a" * 100)
    assert region().startswith(k.KMSG_HEAD + b"a" * 100 + k.SEAM)
    s.write_kmsg(b"b" * 100)
    assert region().startswith(k.KMSG_HEAD + b"a" * 100 + b"b" * 100 + k.SEAM), "the next write overwrites the seam"
    s.write_kmsg(b"c" * 300)
    kept = len(k.KMSG_HEAD) + 20
    assert region()[:kept] == k.KMSG_HEAD + b"a" * 20, "the start of the boot is never wrapped over"
    assert region()[kept:].startswith(k.WRAP + b"c" * 300 + k.SEAM)
    assert s.kmsg_pos + len(k.SEAM) <= 600 and dev.read_bytes()[1100:] == b"X" * 100
    s.write_kmsg(b"d" * 1000 + b"e" * 50)
    assert region()[kept:].startswith(k.WRAP) and b"e" * 50 + k.SEAM in region(), "an oversized batch keeps its newest lines"
    assert s.kmsg_pos + len(k.SEAM) <= 600 and dev.read_bytes()[1100:] == b"X" * 100


def test_each_start_claims_the_next_slot_and_the_initramfs_claim_wins(tmp_path):
    k = _real()
    dev = tmp_path / "dev"
    dev.write_bytes(b"X" * 100 + k.pristine() + b"X" * 100)
    fresh = lambda i: str(tmp_path / f"run{i}" / "stick-start")
    assert [k.StickFile(str(dev), 100).claim(fresh(i)) for i in range(k.SLOTS + 1)] == list(range(1, k.SLOTS + 2))
    assert k.StickFile(str(dev), 100).claim(fresh(0)) == 1, "a restarted service reuses its own claim"
    assert k.starts(dev.read_bytes()[100:]) == k.SLOTS + 1
    (tmp_path / "claimed").write_text("12\n")
    s = k.StickFile(str(dev), 100)
    assert s.claim(str(tmp_path / "claimed")) == 12 and s.base == k.slot_base(12) == k.slot_base(4)
    assert k.starts(dev.read_bytes()[100:]) == k.SLOTS + 1, "an initramfs claim already bumped the count"
    s.write_report(b"r" * (2 * k.REPORT_BYTES))
    s.write_kmsg(b"k" * (2 * k.KMSG_BYTES))
    d = dev.read_bytes()[100:-100]
    size = k.REPORT_BYTES + k.KMSG_BYTES
    assert d[:s.base] == k.pristine()[:s.base].replace(b"starts: 0 ", b"starts: 9 ")
    assert d[s.base + size:] == k.pristine()[s.base + size:], "a start never writes outside its slot"


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


def test_a_pulled_stick_backs_off_instead_of_collecting_every_tick(monkeypatch):
    k = _load()
    collected = []
    monkeypatch.setattr(k, "collect", lambda timeout=120: collected.append(1) or b"")
    monkeypatch.setattr(k, "io_busy", lambda: False)

    class Gone:
        def write_report(self, data):
            raise OSError(5, "Input/output error")

    w = k.Writer(Gone())
    w.tick()
    w.tick()
    assert len(collected) == 1 and w.report.due >= k.STRETCH_MAX


def _usb_cache_module():
    spec = importlib.util.spec_from_file_location("usb_cache", ROOT / "scripts" / "purple-usb-cache.py")
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    return c


def _usb_cache(tmp_path, monkeypatch, avail, resident=(), lock_ok=True):
    """Run main() against a sparse 1 GB image; returns (log, safe, keep, held, warmed, locked)."""
    c = _usb_cache_module()
    size = 1 << 30
    img = tmp_path / "fs.squashfs"
    with open(img, "wb") as f:
        f.truncate(size)
    (tmp_path / "boot.log").write_text("")
    c.SQUASHFS, c.LIVE_CONF = str(img), str(tmp_path / "none")
    c.MARKER, c.KEEP_MARKER = str(tmp_path / "cached"), str(tmp_path / "keep")
    c.BOOT_LOGS = (str(tmp_path / "boot.log"), str(tmp_path / "absent.log"))
    warmed, locked, paused = [], [], []
    monkeypatch.setattr(c, "mem_available", lambda: avail)
    monkeypatch.setattr(c, "map_file", lambda path, n: 0x1000)
    monkeypatch.setattr(c, "wait_for_ui", lambda: None)
    monkeypatch.setattr(c, "mapped_files", lambda: {"usr/bin/Xorg"})
    monkeypatch.setattr(c, "read_through_private_mount", lambda sq, rels: warmed.extend(rels))
    monkeypatch.setattr(c, "resident_runs", lambda addr, n: list(resident))
    monkeypatch.setattr(c, "lock", lambda addr, runs: locked.extend(runs) or lock_ok)
    monkeypatch.setattr(c.signal, "pause", lambda: paused.append(1))
    c.main()
    return ((tmp_path / "boot.log").read_text(), (tmp_path / "cached").exists(), (tmp_path / "keep").exists(),
            bool(paused), warmed, locked)


def test_usb_cache_locks_the_whole_image_when_there_is_room(tmp_path, monkeypatch):
    log, safe, keep, held, warmed, locked = _usb_cache(tmp_path, monkeypatch, avail=2 << 30)
    assert locked == [(0, 1 << 30)] and not warmed
    assert "Locked whole squashfs" in log and "USB safe to remove" in log
    assert safe and held and not keep
    assert not (tmp_path / "absent.log").exists(), "never creates a boot log as root"


def test_usb_cache_low_ram_locks_only_the_session_working_set(tmp_path, monkeypatch):
    runs = [(0, 4096), (1 << 20, 8 << 20)]
    log, safe, keep, held, warmed, locked = _usb_cache(tmp_path, monkeypatch, avail=600 << 20, resident=runs)
    assert "usr/bin/Xorg" in warmed and "opt/purple" in warmed, "mapped files and KEEP are both read"
    assert locked == runs and "Locked session working set" in log
    assert safe and held and not keep


def test_usb_cache_says_keep_the_usb_in_when_nothing_fits(tmp_path, monkeypatch):
    for kwargs in ({"avail": 600 << 20, "resident": [(0, 300 << 20)]},
                   {"avail": 2 << 30, "lock_ok": False}):
        log, safe, keep, held, _, _ = _usb_cache(tmp_path, monkeypatch, **kwargs)
        assert keep and not safe and not held and "keep the USB in" in log
        (tmp_path / "keep").unlink()


def test_usb_cache_resident_runs_reads_the_real_page_cache(tmp_path):
    c = _usb_cache_module()
    f = tmp_path / "img"
    f.write_bytes(os.urandom(c.PAGE * 8))
    size = c.PAGE * 8
    addr = c.map_file(str(f), size)
    os.posix_fadvise(os.open(f, os.O_RDONLY), 0, 0, os.POSIX_FADV_DONTNEED)
    with open(f, "rb") as fh:
        fh.seek(c.PAGE * 2)
        fh.read(c.PAGE * 3)
    runs = c.resident_runs(addr, size)
    assert (c.PAGE * 2, c.PAGE * 3) in runs or any(o <= c.PAGE * 2 and o + n >= c.PAGE * 5 for o, n in runs)
    assert c.lock(addr, [(c.PAGE * 2, c.PAGE)]) in (True, False)  # EPERM without CAP_IPC_LOCK is fine here


def test_build_and_cleanlog_write_the_same_bytes(tmp_path):
    k = _real()
    remaster = (ROOT / "build-scripts" / "01-remaster-iso.sh").read_text()
    build = remaster[remaster.index("    LOG_HEAD=$("):remaster.index('> "$LOG_MNT/PURPLE-LOG"') + len('> "$LOG_MNT/PURPLE-LOG"')]
    build = build.replace("/purple-src/", f"{ROOT}/")
    subprocess.run(["bash", "-ec", build], env={"LOG_MNT": str(tmp_path), "PATH": os.environ["PATH"]}, check=True)
    assert (tmp_path / "PURPLE-LOG").read_bytes() == k.pristine() and len(k.pristine()) == k.file_bytes()


def test_reset_rewrites_only_the_file_and_checks_it(tmp_path):
    k = _load()
    dev = tmp_path / "dev"
    n = k.file_bytes()
    dev.write_bytes(b"X" * 100 + b"O" * n + b"X" * 100)
    assert k.StickFile(str(dev), 100).reset()
    d = dev.read_bytes()
    assert d[:100] == b"X" * 100 and d[100 + n:] == b"X" * 100 and d[100:100 + n] == k.pristine()


def test_initramfs_hook_claims_a_start_and_writes_only_its_slot(tmp_path):
    k = _real()
    remaster = (ROOT / "build-scripts" / "01-remaster-iso.sh").read_text()
    hook = remaster.split("<< 'HOOKS_EOF'")[1].split("HOOKS_EOF")[0]
    hook = hook.replace("/purple-stick", str(tmp_path / "stick")).replace("/run/purple", str(tmp_path / "run"))
    (tmp_path / "stick").mkdir()
    log = tmp_path / "stick" / "PURPLE-LOG"
    log.write_bytes(k.pristine())
    stubs = 'blkid() { echo /dev/x; }; mount() { :; }; umount() { :; }; dmesg() { yes "[ 1.0 ] kernel line" | head -c 2000000; }'
    run = lambda steps: subprocess.run(["sh", "-c", f"{hook}\n{stubs}\n{steps}"], check=True)
    run('purple_stick_report one; purple_stick_report two')
    run(f'rm {tmp_path}/run/stick-start; purple_stick_report three')
    d = log.read_bytes()
    size = k.REPORT_BYTES + k.KMSG_BYTES
    first, second = d[k.slot_base(1):k.slot_base(1) + size], d[k.slot_base(2):k.slot_base(2) + size]
    assert len(d) == k.file_bytes() and k.starts(d) == 2
    assert first.startswith(b"start 1 of this stick\npurple-initramfs: two ") and second.startswith(b"start 2 of this stick\n")
    assert b"===== end of this report" in first and len(first[:k.REPORT_BYTES].rstrip(b"\n")) < k.REPORT_BYTES
    assert d[k.slot_base(1) + k.REPORT_BYTES:k.slot_base(2)] == k.pristine()[k.slot_base(1) + k.REPORT_BYTES:k.slot_base(2)]
    assert d[k.slot_base(3):] == k.pristine()[k.slot_base(3):]
    assert (tmp_path / "run" / "stick-start").read_text() == "2\n"


def test_usb_cache_mapped_files_are_image_relative_regular_files():
    files = _usb_cache_module().mapped_files()
    assert any("libc" in p or "python" in p for p in files), "this test's own process maps them"
    assert not any(p.startswith(("/", "proc/", "dev/", "tmp/")) or p.endswith("(deleted)") for p in files)
