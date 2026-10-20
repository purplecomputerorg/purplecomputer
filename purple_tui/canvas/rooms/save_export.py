"""Parent Menu: copy every save to a USB drive as printable pictures.

Pictures land in a "Purple Computer" folder, one subfolder per room, named
by when they were saved, with a .txt of the same name for work that has words
(Room.plain_text). A picture already on the drive is not copied again.
"""

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pygame

from .. import saves
from ..paper import compose
from ..ui import Dialog

MOUNT = "/run/purple-export"
FOLDER = "Purple Computer"
_FILESYSTEMS = {"vfat", "exfat", "ntfs"}
_EFI_TYPES = {"c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "0xef"}  # GPT and MBR; a Purple Key's EFI partition is FAT too


def find_stick() -> tuple:
    """(device, mountpoint or None) for a data partition on a plugged-in USB drive, a Purple Key's PURPLEUSB included, else (None, None)."""
    try:
        out = subprocess.run(["lsblk", "-J", "-p", "-o", "NAME,TRAN,FSTYPE,PARTTYPE,MOUNTPOINT"],
                             capture_output=True, text=True, timeout=10).stdout
        disks = json.loads(out).get("blockdevices", [])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None, None
    for disk in disks:
        if disk.get("tran") != "usb":
            continue
        for p in disk.get("children") or [disk]:
            if p.get("fstype") in _FILESYSTEMS and (p.get("parttype") or "").lower() not in _EFI_TYPES:
                return p["name"], p.get("mountpoint")
    return None, None


def _nearly_full(path) -> bool:
    try:
        return shutil.disk_usage(path).free < 1 << 20
    except OSError:
        return False


def export_saves(dest: Path, export_for) -> int:
    """Write every save's printed page, and its text when export_for gives one, under dest;
    returns how many pictures are new. export_for(save) is (page or None, text)."""
    copied = 0
    root = saves.saves_dir()
    for room in sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        for save in saves.list_saves(room):
            out = dest / FOLDER / room.title() / f"{save.made:%Y-%m-%d %H.%M.%S}.png"
            page, text = (None, "") if out.exists() else export_for(save)
            if page is None:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            if text:
                out.with_suffix(".txt").write_text(text, encoding="utf-8")
            pygame.image.save(page, str(out))
            copied += 1
    return copied


class SaveExportScreen(Dialog):
    title = "Copy Saved Work to USB"
    hint = "Enter: close"
    width_pct = 50

    def __init__(self, app):
        super().__init__(app)
        self.body_lines = ["Looking for a USB drive..."]
        self.done = False

    def on_open(self):
        threading.Thread(target=self._work, daemon=True, name="save-export").start()

    def _say(self, *lines, done=False):
        def apply():
            self.body_lines, self.done = list(lines), done
            self.app.invalidate()
        self.app.call_from_thread(apply)

    def _export(self, save):
        """(the save's printed page, its text), made on the UI thread (pygame text and rooms are not thread-safe)."""
        done, out = threading.Event(), []

        def draw():
            try:
                work = self.app.save_artwork(save)
                if work is not None:
                    out.append((compose(work, save.landscape, self.app.g, self.app.computer_name())[0],
                                self.app.save_text(save)))
            finally:
                done.set()
        self.app.call_from_thread(draw)
        done.wait(30)
        return out[0] if out else (None, "")

    def _work(self):
        dev, mounted = find_stick()
        if dev is None:
            return self._say("Plug in a USB drive, then try again.", "",
                             "(Technical: no FAT, exFAT or NTFS USB drive found.)", done=True)
        self._say("Copying pictures...")
        mnt = mounted or MOUNT
        try:
            if not mounted:
                subprocess.run(["sudo", "mkdir", "-p", MOUNT], check=True, timeout=10)
                subprocess.run(["sudo", "mount", "-o", f"uid={os.getuid()},gid={os.getgid()},nosuid,nodev", dev, MOUNT],
                               check=True, capture_output=True, timeout=30)
            copied = export_saves(Path(mnt), self._export)
            os.sync()
        except (OSError, subprocess.SubprocessError, pygame.error) as e:
            if _nearly_full(mnt):  # pygame.image.save reports a full drive as a plain pygame.error
                return self._say("The USB drive is full.", "", "The pictures that fit were copied.",
                                 "You can unplug the USB drive now.", done=True)
            return self._say("Couldn't copy to that USB drive.", "", f"(Technical: {e})", done=True)
        finally:
            if not mounted:
                subprocess.run(["sudo", "umount", MOUNT], capture_output=True, timeout=30)
        if copied:
            self._say(f"Copied {copied} picture{'s' if copied != 1 else ''}.", "",
                      f'They are in the "{FOLDER}" folder.', "You can unplug the USB drive now.", done=True)
        else:
            self._say("Nothing new to copy.", "", "Saved work you haven't copied yet goes over next time.", done=True)

    async def handle(self, action):
        from ...keyboard import ControlAction
        if self.done and isinstance(action, ControlAction) and action.is_down and action.action in ("enter", "escape"):
            self.close()
