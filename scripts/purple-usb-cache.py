#!/usr/bin/env python3
"""Purple Computer: keep the live system image in RAM so the USB stick can be pulled.

The running system reads the squashfs through a buffered loop device, so its
pages live in the page cache of the file on the stick. This reads that file
once and, when there is room, mlocks the mapping and holds it for the whole
session, so the kernel can never drop those pages and a pulled stick is never
read again. With too little RAM it only warms the cache, as before. The unit
runs it at idle disk priority so Purple's own reads always go first. The
marker file tells the UI the stick is safe to remove.
"""
import ctypes
import mmap
import os
import signal
from datetime import datetime

SQUASHFS = "/cdrom/casper/filesystem.squashfs"
LIVE_CONF = "/run/purple-live.conf"  # the 32-bit Key keeps its squashfs elsewhere
MARKER = "/tmp/purple-usb-cached"  # constants.USB_CACHE_MARKER
BOOT_LOGS = ("/tmp/purple-boot.log", "/var/log/purple/boot.log")
HEADROOM = 1 << 30  # memory left for the session after locking
MCL_CURRENT = 1


def log(msg):
    """Same line format as xinitrc's xlog; appends only, so a root-owned file is never created."""
    line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [usb-cache] {msg}\n".encode()
    print(msg, flush=True)
    for path in BOOT_LOGS:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        except OSError:
            continue
        os.write(fd, line)
        os.close(fd)


def squashfs_path():
    try:
        with open(LIVE_CONF) as f:
            for line in f:
                if line.startswith("SQUASHFS="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return SQUASHFS


def mem_available():
    with open("/proc/meminfo") as f:
        return next(int(line.split()[1]) * 1024 for line in f if line.startswith("MemAvailable:"))


def main():
    path = squashfs_path()
    if not os.path.isfile(path):
        return
    log("Caching squashfs for USB safety...")
    size, avail = os.path.getsize(path), mem_available()
    locked = False
    with open(path, "rb") as f:
        if avail > size + HEADROOM:
            _mapping = mmap.mmap(f.fileno(), 0, prot=mmap.PROT_READ)  # held until exit: it is what gets locked
            locked = ctypes.CDLL(None, use_errno=True).mlockall(MCL_CURRENT) == 0
            log(f"Squashfs locked in RAM ({size >> 20}MB, {avail >> 20}MB available)" if locked else
                f"Could not lock the squashfs (errno {ctypes.get_errno()}), using page cache warmup")
        else:
            log(f"Low RAM ({avail >> 20}MB available, need {(size + HEADROOM) >> 20}MB), using page cache warmup")
        if not locked:
            buf = bytearray(1 << 20)
            while f.readinto(buf):
                pass
    open(MARKER, "a").close()
    log("USB safe to remove")
    if locked:
        signal.pause()  # the lock lasts as long as this process


if __name__ == "__main__":
    main()
