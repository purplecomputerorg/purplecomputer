"""Parent Menu: copy every save to a USB stick as printable pictures.

Pictures land in a "Purple Computer" folder, one subfolder per room, named
by when they were saved. A picture already on the stick is not copied again.
"""

import json
import os
import subprocess
import threading
from pathlib import Path

import pygame

from .. import saves
from ..paper import compose, mark_surface
from ..ui import Dialog

MOUNT = "/run/purple-export"
FOLDER = "Purple Computer"
_PURPLE_LABELS = {"PURPLE_INSTALLER", "PURPLE_DEBUG", "PURPLEUSB", "PURPLE_ROOT", "PURPLE_EFI"}
_FILESYSTEMS = {"vfat", "exfat", "ntfs"}


def find_stick() -> tuple:
    """(device, mountpoint or None) for a plugged-in USB stick that isn't a Purple one, else (None, None)."""
    try:
        out = subprocess.run(["lsblk", "-J", "-p", "-o", "NAME,TRAN,FSTYPE,LABEL,MOUNTPOINT"],
                             capture_output=True, text=True, timeout=10).stdout
        disks = json.loads(out).get("blockdevices", [])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None, None
    for disk in disks:
        parts = disk.get("children") or [disk]
        if disk.get("tran") != "usb" or any(p.get("label") in _PURPLE_LABELS for p in parts):
            continue
        for p in parts:
            if p.get("fstype") in _FILESYSTEMS:
                return p["name"], p.get("mountpoint")
    return None, None


def export_saves(dest: Path, page_for) -> int:
    """Write every save's printed page under dest; returns how many pictures are new."""
    copied = 0
    root = saves.saves_dir()
    for room in sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        for save in saves.list_saves(room):
            out = dest / FOLDER / room.title() / f"{save.made:%Y-%m-%d %H.%M.%S}.png"
            page = None if out.exists() else page_for(save)
            if page is None:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(page, str(out))
            copied += 1
    return copied


class SaveExportScreen(Dialog):
    title = "Copy Saved Work to USB"
    hint = "Enter: close"
    width_pct = 50

    def __init__(self, app):
        super().__init__(app)
        self.body_lines = ["Looking for a USB stick..."]
        self.done = False

    def on_open(self):
        mark_surface(self.app.g, self.app.computer_name())  # rendered here so the worker only reads the text cache
        threading.Thread(target=self._work, daemon=True, name="save-export").start()

    def _say(self, *lines, done=False):
        def apply():
            self.body_lines, self.done = list(lines), done
            self.app.invalidate()
        self.app.call_from_thread(apply)

    def _page(self, save):
        work = save.image()
        return None if work is None else compose(work, save.landscape, self.app.g, self.app.computer_name())[0]

    def _work(self):
        dev, mounted = find_stick()
        if dev is None:
            return self._say("Plug in a USB stick, then try again.", "",
                             "(Technical: no FAT, exFAT or NTFS USB stick found.)", done=True)
        self._say("Copying pictures...")
        mnt = mounted or MOUNT
        try:
            if not mounted:
                subprocess.run(["sudo", "mkdir", "-p", MOUNT], check=True, timeout=10)
                subprocess.run(["sudo", "mount", "-o", f"uid={os.getuid()},gid={os.getgid()}", dev, MOUNT],
                               check=True, capture_output=True, timeout=30)
            copied = export_saves(Path(mnt), self._page)
            os.sync()
        except (OSError, subprocess.SubprocessError, pygame.error) as e:
            return self._say("Couldn't copy to that USB stick.", "", f"(Technical: {e})", done=True)
        finally:
            if not mounted:
                subprocess.run(["sudo", "umount", MOUNT], capture_output=True, timeout=30)
        if copied:
            self._say(f"Copied {copied} picture{'s' if copied != 1 else ''}.", "",
                      f'They are in the "{FOLDER}" folder.', "You can unplug the USB stick now.", done=True)
        else:
            self._say("Nothing new to copy.", "", "Saved work you haven't copied yet goes over next time.", done=True)

    async def handle(self, action):
        from ...keyboard import ControlAction
        if self.done and isinstance(action, ControlAction) and action.is_down and action.action in ("enter", "escape"):
            self.close()
