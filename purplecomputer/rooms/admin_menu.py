"""Admin menu, opened by typing "admin" (or "tavi") in the Parent Menu: record performance, then copy
every log, the recording and a snapshot of the machine to a USB drive."""

import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pygame

from .. import diagnostics, perf_trace
from ..ui import Picker
from .save_export import UsbCopyScreen

WORDS = ("admin", "tavi")
FOLDER = "Purple Logs"
LOGS = ("/tmp/purple-*.log", "/tmp/xinitrc.log", "/tmp/evdev-diag.log", str(perf_trace.DIR), "/var/log/purple")
COMMANDS = {
    "dmesg.txt": "sudo -n dmesg -T",
    "journal.txt": "sudo -n journalctl -b --no-pager -n 50000",
    "lspci.txt": "lspci -nnk",
    "lsusb.txt": "lsusb",
    "lsblk.txt": "lsblk -f",
    "xrandr.txt": "xrandr --verbose",
    "glxinfo.txt": "glxinfo -B",
    "cpu.txt": "cat /proc/cpuinfo; grep . /sys/devices/system/cpu/cpu*/cpufreq/scaling_* /sys/devices/system/cpu/intel_pstate/* 2>/dev/null",
    "memory.txt": "free -m; cat /proc/meminfo",
    "processes.txt": "ps aux --sort=-%cpu",
    "thermal.txt": "grep . /sys/class/thermal/thermal_zone*/type /sys/class/thermal/thermal_zone*/temp 2>/dev/null",
    "uname.txt": "uname -a; cat /proc/cmdline",
}
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def app_info(app) -> dict:
    """The display as the app sees it, read on the UI thread."""
    g = app.g
    return {"room": app.room.name, "size": [g.w, g.h], "bits": g.surface.get_bitsize(), "kms": bool(g._kms),
            "driver": pygame.display.get_driver() if pygame.display.get_init() else None,
            "pygame": pygame.version.ver, "sdl": ".".join(map(str, pygame.get_sdl_version())), "python": sys.version.split()[0]}


def _run(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        return f"(timed out: {e})"


def _record_label() -> str:
    return "Stop Recording" if perf_trace.active() else "Record Performance"


class AdminMenu(Picker):
    title = "Admin"
    DESCRIPTION = f"Recording stops by itself after {perf_trace.SECONDS // 60} minutes."

    def __init__(self, app):
        super().__init__(app, [("record", _record_label()), ("copy", "Copy Logs to USB")])

    def _on_confirm(self, value):
        if value == "copy":
            return self.app.push(LogExportScreen(self.app))
        if perf_trace.active():
            perf_trace.stop()
            self.options[0] = ("record", _record_label())
            return self.app.invalidate()
        perf_trace.start(app_info(self.app))
        self.close("recording")


class LogExportScreen(UsbCopyScreen):
    title = "Copy Logs to USB"
    working = "Copying logs..."

    def __init__(self, app):
        super().__init__(app)
        self._info = app_info(app)

    def copy(self, dest: Path) -> tuple:
        out = dest / FOLDER / time.strftime("%Y-%m-%d %H.%M.%S")
        out.mkdir(parents=True)
        perf_trace.flush()
        found = sorted({p for pattern in LOGS for p in glob.glob(pattern)})
        if found:   # some are root's, and FAT can't take Linux owners or modes
            subprocess.run(["sudo", "-n", "cp", "-rL", "--no-preserve=all", *found, str(out)], capture_output=True, timeout=120)
        for name, cmd in COMMANDS.items():
            (out / name).write_text(_run(cmd), encoding="utf-8")
        report = perf_trace.sampler("report")
        (out / "performance-report.txt").write_text(ANSI.sub("", report.stdout) if report else "(log-performance missing)")
        (out / "device.txt").write_text(f"{diagnostics.get_version_label()}\n\n{diagnostics.collect_device_info()}\n")
        (out / "app.json").write_text(json.dumps({**self._info, "recording": perf_trace.active()}, indent=2))
        size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) >> 20
        return (f'Copied to "{FOLDER}/{out.name}" ({size} MB).', "", "You can unplug the USB drive now.")
