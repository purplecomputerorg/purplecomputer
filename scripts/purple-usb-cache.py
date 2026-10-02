#!/usr/bin/env python3
"""Purple Computer: keep the live system image in RAM so the USB stick can be pulled.

The running system reads the squashfs through a buffered loop device, so its
pages live in the page cache of the file on the stick; mlocking a mapping of
that file keeps them. With room, the whole file is locked. Otherwise only what
a session needs is: every file a process has mapped plus KEEP, which leaves the
other kernel's modules, firmware and /boot (most of the image) on the stick.
If even that does not fit, KEEP_MARKER tells the UI to ask for the stick to stay in.
"""
import ctypes
import glob
import os
import signal
import subprocess
import time
from datetime import datetime

SQUASHFS = "/cdrom/casper/filesystem.squashfs"
LIVE_CONF = "/run/purple-live.conf"  # the 32-bit Key keeps its squashfs elsewhere
MARKER = "/tmp/purple-usb-cached"  # constants.USB_CACHE_MARKER
KEEP_MARKER = "/tmp/purple-usb-keep"  # constants.USB_KEEP_MARKER
UI_READY = "/tmp/purple-ui-ready"  # constants.UI_READY_MARKER
UI_READY_TIMEOUT = 180
BOOT_LOGS = ("/tmp/purple-boot.log", "/var/log/purple/boot.log")
HEADROOM = 512 << 20  # memory left for the session after locking
PRIVATE_MNT = "/run/purple-usb-cache-mnt"
PAGE = os.sysconf("SC_PAGE_SIZE")
PROT_READ, MAP_SHARED = 1, 1

_MODULES = f"usr/lib/modules/{os.uname().release}"
# Needed after boot but not necessarily mapped yet: rooms, voices and sounds
# load lazily, and a USB speaker needs its driver and Pulse's card modules.
KEEP = (
    "opt/purple", "usr/lib/python3", "usr/lib/python3.12", "usr/local/lib/python3.12",
    "etc", "usr/share/X11", "usr/share/alsa", "usr/share/fonts", "usr/lib/udev",
    "usr/lib/x86_64-linux-gnu/alsa-lib", "usr/lib/x86_64-linux-gnu/pulseaudio",
    "usr/lib/pulse-*", "usr/lib/x86_64-linux-gnu/dri", "usr/libexec/sudo",
    f"{_MODULES}/kernel/sound", f"{_MODULES}/kernel/drivers/usb",
    f"{_MODULES}/kernel/drivers/hid", f"{_MODULES}/kernel/drivers/input", f"{_MODULES}/modules.*",
    "usr/bin/sudo", "usr/bin/systemctl", "usr/bin/kmod", "usr/bin/dash", "usr/bin/bash",
)


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


def _libc():
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long)
    libc.mincore.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p)
    libc.mlock.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
    return libc


def map_file(path, size):
    """Read-only shared mapping, held until exit: it is what gets locked."""
    fd = os.open(path, os.O_RDONLY)
    addr = _libc().mmap(None, size, PROT_READ, MAP_SHARED, fd, 0)
    os.close(fd)
    return addr


def resident_runs(addr, size):
    """(offset, length) runs of the file's pages that are in the page cache."""
    pages = (size + PAGE - 1) // PAGE
    vec = ctypes.create_string_buffer(pages)
    if _libc().mincore(addr, size, vec) != 0:
        return []
    runs, start = [], None
    for i, b in enumerate(vec.raw[:pages] + b"\0"):
        if b & 1 and start is None:
            start = i
        elif not b & 1 and start is not None:
            runs.append((start * PAGE, (i - start) * PAGE))
            start = None
    return runs


def lock(addr, runs):
    libc = _libc()
    return all(libc.mlock(addr + off, n) == 0 for off, n in runs)


def mapped_files():
    """Every regular file some process has mapped right now, image-relative."""
    paths = set()
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/maps") as f:
                paths.update(fields[5].strip() for fields in (line.split(None, 5) for line in f) if len(fields) == 6)
        except OSError:
            continue
    return {p.lstrip("/") for p in paths
            if p.startswith("/") and not p.startswith(("/proc", "/sys", "/dev", "/run", "/tmp", "/memfd"))
            and not p.endswith("(deleted)")}


def _files_under(root, pattern):
    for top in glob.glob(os.path.join(root, pattern)):
        if os.path.isfile(top):
            yield top
        for parent, _, names in os.walk(top):
            yield from (os.path.join(parent, n) for n in names)


def read_through_private_mount(squashfs, rels):
    """Read the files through a fresh mount of the same image, so their blocks
    land in the image file's page cache even when the running system already
    holds the unpacked pages (which never touch the file again)."""
    os.makedirs(PRIVATE_MNT, exist_ok=True)
    subprocess.run(["mount", "-t", "squashfs", "-o", "loop,ro", squashfs, PRIVATE_MNT], check=True)
    try:
        buf = bytearray(1 << 20)
        for rel in rels:
            for path in _files_under(PRIVATE_MNT, rel):
                try:
                    with open(path, "rb", buffering=0) as f:
                        while f.readinto(buf):
                            pass
                except OSError:
                    pass
    finally:
        subprocess.run(["umount", PRIVATE_MNT])


def wait_for_ui():
    deadline = time.monotonic() + UI_READY_TIMEOUT
    while not os.path.exists(UI_READY) and time.monotonic() < deadline:
        time.sleep(2)


def plan(squashfs, addr, size):
    """Runs to lock: the whole file when it fits, else what a session needs."""
    if mem_available() > size + HEADROOM:
        return [(0, size)], "whole squashfs"
    wait_for_ui()
    read_through_private_mount(squashfs, sorted(mapped_files() | set(KEEP)))
    return resident_runs(addr, size), "session working set"


def main():
    path = squashfs_path()
    if not os.path.isfile(path):
        return
    log("Caching squashfs for USB safety...")
    size = os.path.getsize(path)
    addr = map_file(path, size)
    runs, what = plan(path, addr, size)
    need, avail = sum(n for _, n in runs), mem_available()
    if not runs or avail - need < HEADROOM or not lock(addr, runs):
        open(KEEP_MARKER, "a").close()
        log(f"Not enough RAM to hold the {what} ({need >> 20}MB, {avail >> 20}MB available), keep the USB in")
        return
    log(f"Locked {what} in RAM ({need >> 20}MB of {size >> 20}MB, {avail >> 20}MB available before)")
    open(MARKER, "a").close()
    log("USB safe to remove")
    signal.pause()  # the lock lasts as long as this process


if __name__ == "__main__":
    main()
