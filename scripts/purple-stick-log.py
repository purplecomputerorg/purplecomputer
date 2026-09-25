#!/usr/bin/env python3
"""Purple Computer: PURPLE-LOG.TXT on the stick, written in place.

The file is preallocated at image build (01-remaster-iso.sh) with two fixed
regions: the boot report (purple-diag-collect, rewritten every few seconds
during boot, then once a minute) and, after it, the kernel log streamed as it
happens. Its sectors are located once with the partition mounted read-only;
from then on every write goes straight into those sectors of the partition
device. Nothing stays mounted and no FAT metadata changes, so a power cut at
any moment leaves the partition clean and the file holding everything up to
the last flush. The initramfs writes the same report region in place before
this starts (purple_stick_report in the casper hook).
"""
import fcntl
import os
import select
import struct
import subprocess
import sys
import time

NAME = "PURPLE-LOG.TXT"
REPORT_BYTES = 8 << 20  # keep in sync with purple_stick_report and the build
KMSG_BYTES = 4 << 20
MNT = "/run/purple-diag/ro"
COLLECT = "/usr/local/bin/purple-diag-collect"
LOCAL_COPY = "/var/log/purple/diag.txt"
FIBMAP, FIGETBSZ = 1, 2
FAST_UNTIL_UPTIME = 300
REPORT_FAST, REPORT_SLOW = 5.0, 60.0
KMSG_FAST, KMSG_SLOW = 1.0, 5.0
REPORT_END = b"\n===== end of report (the empty lines below are reserved space, the kernel log follows them) =====\n"
KMSG_HEAD = b"===== live kernel log, written as it happens, newest lines last =====\n"
WRAP = b"\n===== the kernel log filled up and wrapped: lines below this may be older =====\n"
PENDING_MAX = 1 << 20


def log(msg):
    print(f"purple-stick-log: {msg}", flush=True)


def uptime():
    with open("/proc/uptime") as f:
        return float(f.read().split()[0])


def find_partition(tries=60):
    for _ in range(tries):
        out = subprocess.run(["blkid", "-L", "PURPLEUSB"], capture_output=True, text=True).stdout.strip()
        if out:
            return out
        time.sleep(1)
    return None


def file_extent(part):
    """Byte offset of NAME on the partition, or None if it is not one contiguous run."""
    os.makedirs(MNT, exist_ok=True)
    subprocess.run(["mount", "-t", "vfat", "-o", "ro", part, MNT], check=True)
    try:
        path = os.path.join(MNT, NAME)
        size = os.stat(path).st_size
        if size != REPORT_BYTES + KMSG_BYTES:
            log(f"{NAME} is {size} bytes, expected {REPORT_BYTES + KMSG_BYTES}")
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
        subprocess.run(["umount", MNT])


def format_record(rec):
    header, _, body = rec.partition(b";")
    fields = header.split(b",")
    try:
        us = int(fields[2])
    except (IndexError, ValueError):
        return body
    return b"[%5d.%06d] %s" % (us // 1000000, us % 1000000, body.split(b"\n", 1)[0] + b"\n")


class StickFile:
    """In-place writer for the two regions of NAME, by raw sector writes."""

    def __init__(self, dev, offset):
        self.fd = os.open(dev, os.O_WRONLY)
        self.offset = offset
        self.report_len = REPORT_BYTES  # first write blanks the whole region: an earlier boot's report may be there
        self.kmsg_pos = 0

    def _write(self, pos, data):
        os.pwrite(self.fd, data, self.offset + pos)
        os.fdatasync(self.fd)

    def write_report(self, data):
        data = data[: REPORT_BYTES - len(REPORT_END)] + REPORT_END
        self._write(0, data + b"\n" * max(0, self.report_len - len(data)))
        self.report_len = len(data)

    def write_kmsg(self, data):
        if self.kmsg_pos == 0:
            data = KMSG_HEAD + data
        elif self.kmsg_pos + len(data) > KMSG_BYTES:
            self.kmsg_pos = len(KMSG_HEAD)
            data = (WRAP + data)[: KMSG_BYTES - self.kmsg_pos]
        self._write(REPORT_BYTES + self.kmsg_pos, data)
        self.kmsg_pos += len(data)


def collect():
    out = subprocess.run([COLLECT], capture_output=True, timeout=120).stdout
    try:
        os.makedirs(os.path.dirname(LOCAL_COPY), exist_ok=True)
        with open(LOCAL_COPY, "wb") as f:
            f.write(out)
    except OSError:
        pass
    return out


def run(stick):
    kmsg = os.open("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK)
    pending = bytearray()
    last_kmsg = time.monotonic()
    next_report = 0.0
    while True:
        fast = uptime() < FAST_UNTIL_UPTIME
        kmsg_interval = KMSG_FAST if fast else KMSG_SLOW
        due = min(next_report, last_kmsg + kmsg_interval if pending else next_report)
        if select.select([kmsg], [], [], max(0.0, due - time.monotonic()))[0]:
            try:
                rec = os.read(kmsg, 8192)
            except BlockingIOError:
                rec = b""
            except OSError:  # EPIPE: the ring buffer overtook us, keep reading
                pending += b"[kernel log lines were dropped here]\n"
                rec = b""
            if rec and len(pending) < PENDING_MAX:
                pending += format_record(rec)
        now = time.monotonic()
        try:
            if pending and now - last_kmsg >= kmsg_interval:
                stick.write_kmsg(bytes(pending))
                pending.clear()
                last_kmsg = now
            if now >= next_report:
                stick.write_report(collect())
                next_report = now + (REPORT_FAST if fast else REPORT_SLOW)
        except OSError as e:
            log(f"write failed ({e.strerror}), retrying")
            time.sleep(5)
            last_kmsg = next_report = time.monotonic()


def main():
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
    log(f"writing {NAME} in place on {part} at byte {offset}")
    run(StickFile(part, offset))


if __name__ == "__main__":
    sys.exit(main())
