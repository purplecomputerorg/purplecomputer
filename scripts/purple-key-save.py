#!/usr/bin/env python3
"""Purple Computer: PURPLE-SAVE on the stick, Purple's state across live boots.

The file sits beside PURPLE-LOG on PURPLEUSB, preallocated at image build
(01-remaster-iso.sh): a first line saying what it is, then two slots, each a
header and a tar.gz of ~/.config/purple (settings, Time Travel, saves). Like
purple-stick-log, whose helpers this reuses, it locates the file's sectors
with the partition mounted read-only and then reads and writes them raw, so
nothing stays mounted and no FAT metadata changes.

--restore (purple-key-save.service, before Purple starts) unpacks the newest
good copy and leaves MARKER, which tells Purple this Key keeps work.
--write (Purple, through sudo) packs the state into the older slot and writes
that slot's header last, so a power cut or a pulled stick mid-write leaves
the other copy as the newest good one. --reset (cleanlog) clears the file.
Kept apart from purple-stick-log so that script stays as release/1.x has it.
"""
import fcntl
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pwd
import subprocess
import sys
import tarfile


def _load_stick_log():
    here = os.path.dirname(os.path.realpath(__file__))
    for name in ("purple-stick-log", "purple-stick-log.py"):  # installed, then the repo
        path = os.path.join(here, name)
        if os.path.exists(path):
            loader = importlib.machinery.SourceFileLoader("purple_stick_log", path)
            mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
            loader.exec_module(mod)
            return mod
    raise ImportError("purple-stick-log not found beside purple-key-save")


stick = _load_stick_log()


def log(msg):
    print(f"purple-key-save: {msg}", flush=True)


NAME = "PURPLE-SAVE"
HEADER_BYTES, SLOT_BYTES, SLOT_HEAD = 4096, 32 << 20, 512
MNT = "/run/purple-diag/save-ro"
MARKER = "/run/purple/key-save"  # "partition offset sequence": Purple reads it to know saving works
LOCK = "/run/purple/key-save.lock"
CONFIG_DIR = "/home/purple/.config/purple"
USER = "purple"
# Exit codes Purple reads (purple_tui/canvas/key_save.py)
OK, NO_FILE, GONE, FULL = 0, 2, 3, 4
# The build reads this line with sed (01-remaster-iso.sh): keep it one plain string.
PRISTINE_HEAD = "PURPLE-SAVE: what your kid made on this Key (settings, Time Travel and saved work). Purple writes it in place; please don't delete or edit it."


def file_bytes():
    return HEADER_BYTES + 2 * SLOT_BYTES


def pristine():
    head = PRISTINE_HEAD.encode() + b"\n"
    return head + b"\0" * (file_bytes() - len(head))


def pack(folder):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tar:
        tar.add(folder, arcname=".")
    return buf.getvalue()


def unpack(payload, folder, owner):
    os.makedirs(folder, exist_ok=True)
    os.chown(os.path.dirname(folder), owner, owner)  # ~/.config, if this just made it
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        tar.extractall(folder, filter="data")
    for root, dirs, files in os.walk(folder):
        for name in [root] + [os.path.join(root, n) for n in dirs + files]:
            os.chown(name, owner, owner)


class SaveFile:
    """PURPLE-SAVE by raw reads and writes at its offset on the partition."""

    def __init__(self, dev, offset):
        self.dev, self.offset = dev, offset

    @staticmethod
    def clear(part):
        """None when this stick has no PURPLE-SAVE (an older build), "reset" once cleared and checked, else "failed"."""
        offset = stick.file_extent(part, NAME, file_bytes(), MNT)
        if offset is None:
            return None
        data = pristine()
        fd = os.open(part, os.O_RDWR)
        try:
            os.pwrite(fd, data, offset)
            os.fdatasync(fd)
            os.posix_fadvise(fd, offset, len(data), os.POSIX_FADV_DONTNEED)
            return "reset" if os.pread(fd, len(data), offset) == data else "failed"
        finally:
            os.close(fd)

    def _slot(self, i):
        return self.offset + HEADER_BYTES + i * SLOT_BYTES

    def is_ours(self):
        """The file's own first line is still at the offset: never write into anything else."""
        try:
            fd = os.open(self.dev, os.O_RDONLY)
        except OSError:
            return False
        try:
            head = PRISTINE_HEAD.encode()
            return os.pread(fd, len(head), self.offset) == head
        except OSError:
            return False
        finally:
            os.close(fd)

    def read_slots(self):
        """[(sequence, payload)] for each slot whose header and checksum hold up."""
        good = []
        fd = os.open(self.dev, os.O_RDONLY)
        try:
            for i in (0, 1):
                try:
                    head = json.loads(os.pread(fd, SLOT_HEAD, self._slot(i)).rstrip(b"\0"))
                    payload = os.pread(fd, head["len"], self._slot(i) + SLOT_HEAD)
                    if len(payload) == head["len"] and hashlib.sha256(payload).hexdigest() == head["sha256"]:
                        good.append((head["seq"], payload))
                except (ValueError, KeyError, TypeError, OSError):
                    continue
        finally:
            os.close(fd)
        return sorted(good, reverse=True)

    def write(self, seq, payload):
        """Payload first, header last: until the header lands, this slot does not count."""
        if len(payload) > SLOT_BYTES - SLOT_HEAD:
            return False
        head = json.dumps({"seq": seq, "len": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}).encode()
        fd = os.open(self.dev, os.O_RDWR)
        try:
            base = self._slot(seq % 2)
            os.pwrite(fd, b"\0" * SLOT_HEAD, base)
            os.fdatasync(fd)
            os.pwrite(fd, payload, base + SLOT_HEAD)
            os.fdatasync(fd)
            os.pwrite(fd, head.ljust(SLOT_HEAD, b"\0"), base)
            os.fdatasync(fd)
        finally:
            os.close(fd)
        return True


def write_marker(part, offset, seq):
    os.makedirs(os.path.dirname(MARKER), exist_ok=True)
    tmp = MARKER + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"{part} {offset} {seq}\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, MARKER)


def restore():
    """Before Purple starts: unpack the newest good copy and leave the marker that says saving works."""
    part = stick.find_partition(tries=2)  # blkid probes directly; a stick without PURPLEUSB must not hold up boot
    if not part:
        log("no PURPLEUSB partition: this session keeps nothing")
        return 0
    try:
        offset = stick.file_extent(part, NAME, file_bytes(), MNT)
    except (OSError, subprocess.CalledProcessError) as e:
        log(f"cannot locate {NAME}: {e}")
        return 0
    if offset is None:
        return 0
    slots = SaveFile(part, offset).read_slots()
    seq = 0
    for seq, payload in slots:
        try:
            unpack(payload, CONFIG_DIR, pwd.getpwnam(USER).pw_uid)
            log(f"restored copy {seq} ({len(payload)} bytes) from {NAME}")
            break
        except (OSError, tarfile.TarError, KeyError, TypeError) as e:  # TypeError: a Python without safe extraction
            log(f"copy {seq} would not unpack ({e}), trying the other")
    else:
        seq = max((s for s, _ in slots), default=0)
        log(f"{NAME} holds nothing yet")
    write_marker(part, offset, seq)
    return 0


def write():
    try:
        lock = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(MARKER) as f:
            part, offset, seq = f.read().split()
        offset, seq = int(offset), int(seq)
    except (OSError, ValueError):
        return NO_FILE
    save = SaveFile(part, offset)
    if not save.is_ours():
        return GONE
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not save.write(seq + 1, pack(CONFIG_DIR)):
            return FULL
    except OSError as e:
        log(f"{NAME} write failed: {e}")
        return GONE
    write_marker(part, offset, seq + 1)
    return OK


def reset():
    """cleanlog: clear the file, and remove MARKER (under the write lock) so Purple writes nothing more before shipping."""
    try:
        lock = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        os.unlink(MARKER)
    except OSError:
        pass
    parts = subprocess.run(["blkid", "-c", "/dev/null", "-o", "device", "-t", "LABEL=PURPLEUSB"],
                           capture_output=True, text=True).stdout.split()
    if len(parts) != 1:
        print(f"Expected one Purple stick plugged in, found {len(parts)}. Nothing was changed.")
        return 1
    try:
        result = SaveFile.clear(parts[0])
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Error: {e}")
        result = "failed"
    if result == "failed":
        print("PURPLE-SAVE was NOT cleared. Do not ship this stick without reflashing it.")
        return 1
    print("PURPLE-SAVE cleared and checked." if result else "No PURPLE-SAVE on this stick (an older build).")
    return 0


def main():
    command = {"--restore": restore, "--write": write, "--reset": reset}.get(" ".join(sys.argv[1:]))
    if command is None:
        print("usage: purple-key-save --restore | --write | --reset")
        return 1
    return command()


if __name__ == "__main__":
    sys.exit(main())
