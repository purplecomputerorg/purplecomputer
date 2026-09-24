#!/usr/bin/env python3
"""Purple Computer: stream the kernel log into PURPLE-KMSG.TXT on the stick.

The file is preallocated at image build (01-remaster-iso.sh). Its sectors are
located once with the partition mounted read-only; from then on lines from
/dev/kmsg are written straight into those sectors of the partition device.
Nothing stays mounted and no FAT metadata changes, so a power cut leaves the
partition clean and the file holding every line up to the last flush.
"""
import fcntl
import os
import select
import struct
import subprocess
import sys
import time

NAME = "PURPLE-KMSG.TXT"
MNT = "/run/purple-diag/kmsg-ro"
FIBMAP, FIGETBSZ = 1, 2
FAST_UNTIL_UPTIME = 300
FLUSH_FAST, FLUSH_SLOW = 1.0, 5.0
HEAD = b"PURPLE-KMSG.TXT: kernel log written live while Purple starts, newest lines last.\n\n"
WRAP = b"\n===== the file filled up and wrapped: lines below this may be older =====\n"
PENDING_MAX = 1 << 20


def log(msg):
    print(f"purple-kmsg-stream: {msg}", flush=True)


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
    """(byte offset on the partition, size) of NAME, or None if not contiguous."""
    os.makedirs(MNT, exist_ok=True)
    subprocess.run(["mount", "-t", "vfat", "-o", "ro", part, MNT], check=True)
    try:
        path = os.path.join(MNT, NAME)
        size = os.stat(path).st_size
        with open(path, "rb") as f:
            bsz = struct.unpack("i", fcntl.ioctl(f, FIGETBSZ, struct.pack("i", 0)))[0]
            first = None
            for i in range((size + bsz - 1) // bsz):
                blk = struct.unpack("i", fcntl.ioctl(f, FIBMAP, struct.pack("i", i)))[0]
                if first is None:
                    first = blk
                elif blk != first + i:
                    return None
        return first * bsz, size
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


class Ring:
    def __init__(self, dev, offset, size):
        self.fd = os.open(dev, os.O_WRONLY)
        self.offset, self.size, self.pos = offset, size, 0

    def write(self, data):
        if self.pos + len(data) > self.size:
            self.pos = len(HEAD)
            data = (WRAP + data)[: self.size - self.pos]
        os.pwrite(self.fd, data, self.offset + self.pos)
        os.fdatasync(self.fd)
        self.pos += len(data)


def stream(ring):
    kmsg = os.open("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK)
    pending = bytearray(HEAD)
    last_flush = time.monotonic()
    while True:
        interval = FLUSH_FAST if uptime() < FAST_UNTIL_UPTIME else FLUSH_SLOW
        wait = max(0.0, last_flush + interval - time.monotonic()) if pending else interval
        if select.select([kmsg], [], [], wait)[0]:
            try:
                rec = os.read(kmsg, 8192)
            except BlockingIOError:
                rec = b""
            except OSError:  # EPIPE: the ring buffer overtook us, keep reading
                pending += b"[kernel log lines were dropped here]\n"
                rec = b""
            if len(pending) < PENDING_MAX:
                pending += format_record(rec) if rec else b""
        if pending and time.monotonic() - last_flush >= interval:
            try:
                ring.write(bytes(pending))
                pending.clear()
            except OSError as e:
                log(f"write failed ({e.strerror}), retrying")
                time.sleep(5)
            last_flush = time.monotonic()


def main():
    part = find_partition()
    if not part:
        log("no PURPLEUSB partition, nothing to do")
        return 0
    for _ in range(10):  # purple-diag-dump mounts the same partition rw for a moment every 5s
        try:
            extent = file_extent(part)
            break
        except (OSError, subprocess.CalledProcessError) as e:
            log(f"cannot locate {NAME} on {part} yet: {e}")
            time.sleep(1)
    else:
        return 0
    if not extent:
        log(f"{NAME} is missing or fragmented on {part}, not streaming")
        return 0
    log(f"streaming to {part} at byte {extent[0]}, {extent[1]} bytes")
    stream(Ring(part, *extent))


if __name__ == "__main__":
    sys.exit(main())
