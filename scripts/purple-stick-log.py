#!/usr/bin/env python3
"""Purple Computer: PURPLE-LOG on the stick, written in place.

The file is preallocated at image build (01-remaster-iso.sh): a header
holding the number of starts so far, then SLOTS slots, so the last SLOTS
starts (on any mix of machines) each keep their own log. Start n writes slot
(n - 1) % SLOTS. A slot has two fixed regions: the boot report
(purple-diag-collect, rewritten every few seconds until Purple is on screen,
then less and less often, and once more when the service stops at shutdown)
and, after it, the kernel log streamed as it happens. Writes wait while other programs are stalled on disk and are spaced
so they take at most a small share of the time, so a slow stick slows the
log instead of the computer. The file's sectors are located once with the
partition mounted read-only; from then on every write goes straight into
those sectors of the partition device. Nothing stays mounted and no FAT
metadata changes, so a power cut at any moment leaves the partition clean and
the file holding everything up to the last flush. The initramfs claims the
start number and writes the same report region in place before this starts
(purple_stick_report in the casper hook).

--reset (the `cleanlog` command) puts the file back byte for byte as the build
wrote it and powers off, so a stick tested before shipping goes out clean.
"""
import fcntl
import os
import select
import signal
import struct
import subprocess
import sys
import time

NAME = "PURPLE-LOG"
# Keep in sync with purple_stick_report and the build (file size).
HEADER_BYTES, SLOTS, REPORT_BYTES, KMSG_BYTES = 4096, 8, 1 << 20, 512 << 10
KMSG_KEEP = 128 << 10  # the start of the boot's kernel log, never wrapped over
START_FILE = "/run/purple/stick-start"  # the initramfs's claim, moved into the real /run
MNT = "/run/purple-diag/ro"
COLLECT = "/usr/local/bin/purple-diag-collect"
LOCAL_COPY = "/var/log/purple/diag.txt"
FIBMAP, FIGETBSZ = 1, 2
BOOT_LOG = "/tmp/purple-boot.log"
UI_MARK = b"first render reached"  # boot_log.mark_first_render, both UIs
PRESSURE = "/proc/pressure/io"
KMSG = "/dev/kmsg"
REPORT_BOOTING, REPORT_UI, REPORT_IDLE, UI_BUSY_FOR = 10.0, 60.0, 600.0, 600.0
KMSG_BOOTING, KMSG_UI = 1.0, 5.0
WRITE_SHARE = 0.02  # a write that took t seconds waits at least t / WRITE_SHARE before the next
STRETCH_MAX = 300.0
BUSY_PERCENT, BUSY_RETRY, BUSY_WAIT_MAX = 10.0, 2.0, 30.0
FINAL_TIMEOUT = 2  # shutdown waits on this
REPORT_END = b"\n===== end of report: anything below, up to the kernel log, is empty space or left from an earlier report =====\n"
KMSG_HEAD = b"===== live kernel log, written as it happens, newest lines last =====\n"
SEAM = b"===== newest kernel log line above: anything below is older =====\n"
WRAP = b"\n===== the kernel log filled up and wrapped: lines above are the start of the boot, lines below the newest =====\n"
CUT = b"\n[the report was cut off here: it did not fit in its slot]\n"
STARTS = b"starts: %-10d"  # fixed width so it is rewritten in place; the initramfs writes the same
PENDING_MAX = 1 << 20
# The build reads this line with sed (01-remaster-iso.sh): keep it one plain string.
PRISTINE_HEAD = "PURPLE-LOG: Purple's boot reports from the last 8 starts of this stick, one section per start (plain text, no extension so a double-click does not open 12MB)."


def file_bytes():
    return HEADER_BYTES + SLOTS * (REPORT_BYTES + KMSG_BYTES)


def slot_base(start):
    return HEADER_BYTES + (start - 1) % SLOTS * (REPORT_BYTES + KMSG_BYTES)


def starts(header):
    """The start count on the header's second line, 0 if unreadable."""
    try:
        return int(header.split(b"\n")[1].split(b":")[1])
    except (IndexError, ValueError):
        return 0


def log(msg):
    print(f"purple-stick-log: {msg}", flush=True)


def find_partition(tries=60):
    for _ in range(tries):
        out = subprocess.run(["blkid", "-L", "PURPLEUSB"], capture_output=True, text=True).stdout.strip()
        if out:
            return out
        time.sleep(1)
    return None


def file_extent(part, name=NAME, expected=None, mnt=MNT):
    """Byte offset of name on the partition, or None if it is missing, the wrong size, or not one contiguous run."""
    expected = expected or file_bytes()
    os.makedirs(mnt, exist_ok=True)
    subprocess.run(["mount", "-t", "vfat", "-o", "ro", part, mnt], check=True)
    try:
        path = os.path.join(mnt, name)
        if not os.path.exists(path):
            log(f"no {name} on {part}")
            return None
        size = os.stat(path).st_size
        if size != expected:
            log(f"{name} is {size} bytes, expected {expected}")
            return None
        with open(path, "rb") as f:
            bsz = struct.unpack("i", fcntl.ioctl(f, FIGETBSZ, struct.pack("i", 0)))[0]
            first = None
            for i in range((size + bsz - 1) // bsz):
                blk = struct.unpack("i", fcntl.ioctl(f, FIBMAP, struct.pack("i", i)))[0]
                if first is None:
                    first = blk
                elif blk != first + i:
                    return None
        return first * bsz
    finally:
        subprocess.run(["umount", mnt])


def pristine():
    head = PRISTINE_HEAD.encode() + b"\n" + STARTS % 0 + b"\n"
    return head + b"\n" * (file_bytes() - len(head))


def format_record(rec):
    header, _, body = rec.partition(b";")
    fields = header.split(b",")
    try:
        us = int(fields[2])
    except (IndexError, ValueError):
        return body
    return b"[%5d.%06d] %s" % (us // 1000000, us % 1000000, body.split(b"\n", 1)[0] + b"\n")


class StickFile:
    """In-place writer for this start's slot of NAME, by raw sector writes.

    Leftovers from earlier writes are never blanked (that would mean
    rewriting megabytes during boot); the end-of-report and seam markers
    label them instead."""

    def __init__(self, dev, offset):
        self.fd = os.open(dev, os.O_RDWR)
        self.offset = offset
        self.kmsg_pos = 0
        self.start, self.base = 0, HEADER_BYTES

    def _write(self, pos, data):
        os.pwrite(self.fd, data, self.offset + pos)
        os.fdatasync(self.fd)

    def claim(self, start_file=START_FILE):
        """Pick this start's slot: the initramfs's claim, else bump the header's count here."""
        try:
            with open(start_file) as f:
                self.start = int(f.read())
        except (OSError, ValueError):
            header = os.pread(self.fd, HEADER_BYTES, self.offset)
            self.start = starts(header) + 1
            self._write(header.index(b"\n") + 1, STARTS % self.start)
            try:  # so a restart of this service reuses the slot instead of claiming another
                os.makedirs(os.path.dirname(start_file), exist_ok=True)
                with open(start_file, "w") as f:
                    f.write(f"{self.start}\n")
            except OSError:
                pass
        self.base = slot_base(self.start)
        return self.start

    def write_report(self, data):
        data = b"start %d of this stick\n" % self.start + data
        room = REPORT_BYTES - len(REPORT_END)
        if len(data) > room:
            data = data[: room - len(CUT)] + CUT
        self._write(self.base, data + REPORT_END)

    def write_kmsg(self, data):
        mark = b""
        if self.kmsg_pos == 0:
            mark = KMSG_HEAD
        elif self.kmsg_pos + len(data) + len(SEAM) > KMSG_BYTES:
            self.kmsg_pos = len(KMSG_HEAD) + KMSG_KEEP
            mark = WRAP
        room = KMSG_BYTES - self.kmsg_pos - len(mark) - len(SEAM)
        data = mark + data[max(0, len(data) - room):]  # a batch too big for the room keeps its newest lines
        self._write(self.base + REPORT_BYTES + self.kmsg_pos, data + SEAM)  # the next write overwrites the seam
        self.kmsg_pos += len(data)

    def reset(self):
        """Rewrite the whole file as built; True once a read from the device, not the cache, matches."""
        data = pristine()
        self._write(0, data)
        os.posix_fadvise(self.fd, self.offset, len(data), os.POSIX_FADV_DONTNEED)
        return os.pread(self.fd, len(data), self.offset) == data


def io_busy():
    """True while other programs spend a noticeable share of time waiting on disk."""
    try:
        with open(PRESSURE) as f:
            some = f.readline().split()
        return float(some[1].split("=")[1]) > BUSY_PERCENT
    except (OSError, IndexError, ValueError):
        return False


def ui_up():
    try:
        with open(BOOT_LOG, "rb") as f:
            return UI_MARK in f.read()
    except OSError:
        return False


class Schedule:
    """When one kind of write is next due: its base interval, stretched when
    writes are slow and held back while the disk is busy, within limits so
    the log never goes quiet on a struggling machine."""

    def __init__(self):
        self.due = 0.0
        self.held_since = None
        self.last_cost = 0.0

    def ready(self, now):
        if now < self.due:
            return False
        self.held_since = self.held_since or now
        if now - self.held_since < BUSY_WAIT_MAX and io_busy():
            self.due = now + BUSY_RETRY
            return False
        return True

    def done(self, now, cost, interval):
        self.held_since = None
        self.last_cost = cost
        self.due = now + max(interval, min(cost / WRITE_SHARE, STRETCH_MAX))


def collect(timeout=120):
    try:
        out = subprocess.run([COLLECT], capture_output=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"") + b"\n[the report stopped here: collecting it took over %ds]\n" % timeout
    try:
        os.makedirs(os.path.dirname(LOCAL_COPY), exist_ok=True)
        with open(LOCAL_COPY, "wb") as f:
            f.write(out)
    except OSError:
        pass
    return out


def timed(write, *args):
    t0 = time.monotonic()
    write(*args)
    return time.monotonic() - t0


class Writer:
    def __init__(self, stick):
        self.stick = stick
        self.pending = bytearray()
        self.report, self.kmsg = Schedule(), Schedule()
        self.ui_since = None

    def add(self, rec):
        if len(self.pending) < PENDING_MAX:
            self.pending += rec

    def report_interval(self, now):
        if self.ui_since is None and ui_up():
            self.ui_since = now
        if self.ui_since is None:
            return REPORT_BOOTING
        return REPORT_UI if now - self.ui_since < UI_BUSY_FOR else REPORT_IDLE

    def next_due(self):
        return min(self.report.due, self.kmsg.due) if self.pending else self.report.due

    def flush_kmsg(self):
        cost = timed(self.stick.write_kmsg, bytes(self.pending))
        self.pending.clear()
        return cost

    def write_report(self, timeout=120):
        header = b"stick log: the last report took %.2fs to write, the kernel log %.2fs\n" % (
            self.report.last_cost, self.kmsg.last_cost)
        return timed(self.stick.write_report, header + collect(timeout))

    def tick(self):
        now = time.monotonic()
        try:
            if self.pending and self.kmsg.ready(now):
                self.kmsg.done(now, self.flush_kmsg(), KMSG_BOOTING if self.ui_since is None else KMSG_UI)
            if self.report.ready(now):
                interval = self.report_interval(now)
                self.report.done(now, self.write_report(), interval)
        except OSError as e:  # stick pulled or failing: try again in a few minutes, not every tick
            log(f"write failed ({e.strerror}), retrying in {STRETCH_MAX:.0f}s")
            self.report.due = self.kmsg.due = now + STRETCH_MAX

    def final(self):
        if self.pending:
            self.flush_kmsg()
        self.write_report(FINAL_TIMEOUT)


def read_kmsg(kmsg):
    try:
        return format_record(os.read(kmsg, 8192))
    except BlockingIOError:
        return b""
    except OSError:  # EPIPE: the ring buffer overtook us, keep reading
        return b"[kernel log lines were dropped here]\n"


def run(stick):
    kmsg = os.open(KMSG, os.O_RDONLY | os.O_NONBLOCK)
    w = Writer(stick)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        while True:
            if select.select([kmsg], [], [], max(0.0, w.next_due() - time.monotonic()))[0]:
                w.add(read_kmsg(kmsg))
            w.tick()
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            w.final()
        except OSError:
            pass


def reset():
    # Stop first: the service writes a last report as it stops.
    subprocess.run(["systemctl", "stop", "purple-stick-log.service"])
    parts = subprocess.run(["blkid", "-c", "/dev/null", "-o", "device", "-t", "LABEL=PURPLEUSB"],
                           capture_output=True, text=True).stdout.split()
    if len(parts) != 1:
        print(f"Expected one Purple stick plugged in, found {len(parts)}. Nothing was changed.")
        return 1
    try:
        offset = file_extent(parts[0])
        ok = offset is not None and StickFile(parts[0], offset).reset()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Error: {e}")
        ok = False
    if not ok:
        print("PURPLE-LOG was NOT cleared. Do not ship this stick without reflashing it.")
        return 1
    print("PURPLE-LOG cleared and checked. Turning off; do not start from this stick again before shipping.")
    time.sleep(3)
    subprocess.run(["systemctl", "poweroff", "--force"])
    return 0


def main():
    if sys.argv[1:] == ["--reset"]:
        return reset()
    part = find_partition()
    if not part:
        log("no PURPLEUSB partition, nothing to do")
        return 0
    for _ in range(10):
        try:
            offset = file_extent(part)
            break
        except (OSError, subprocess.CalledProcessError) as e:
            log(f"cannot locate {NAME} on {part} yet: {e}")
            time.sleep(1)
    else:
        return 0
    if offset is None:
        log(f"{NAME} is missing, wrong size or fragmented on {part}, not writing")
        return 0
    stick = StickFile(part, offset)
    log(f"writing start {stick.claim()} of {NAME} in place on {part} at byte {offset + stick.base}")
    run(stick)


if __name__ == "__main__":
    sys.exit(main())
