"""Admin menu, opened by typing "admin" (or "tavi") in the Parent Menu: record performance, time the
screen, try the display without the compositor or (next start) without GPU acceleration, then copy
every log, the recording and a snapshot of the machine to a USB drive. guides/admin-menu.md"""

import glob
import json
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import pygame

from .. import boot_log, diagnostics, perf_trace, screen_test
from ..ui import Notice, Picker
from .save_export import UsbCopyScreen

WORDS = ("admin", "tavi")
FOLDER = "Purple Logs"
# Next-start switches, read by scripts/purple-admin-boot.sh before X starts: name, what it turns off.
SWITCHES = {"noaccel": "GPU Acceleration"}
NEXT_START = Path("/var/log/purple/admin-next-start")
THIS_START = Path("/run/purple-admin-start")
LOGS = ("/tmp/purple-*.log", "/tmp/xinitrc.log", "/tmp/evdev-diag.log", str(perf_trace.DIR), "/var/log/purple",
        str(Path.home() / ".local/share/xorg/Xorg.*.log"), "/var/log/Xorg.*.log", str(THIS_START))
COMMANDS = {
    "dmesg.txt": "sudo -n dmesg -T",
    "journal.txt": "sudo -n journalctl -b --no-pager -n 50000",
    "lspci.txt": "lspci -nnk",
    "lsusb.txt": "lsusb",
    "lsblk.txt": "lsblk -f",
    "xrandr.txt": "xrandr --verbose",
    "xorg-conf.txt": "head -50 /usr/share/X11/xorg.conf.d/*.conf /etc/X11/xorg.conf.d/*.conf 2>/dev/null",
    "cpu.txt": "cat /proc/cpuinfo; grep . /sys/devices/system/cpu/cpu*/cpufreq/scaling_* /sys/devices/system/cpu/intel_pstate/* 2>/dev/null",
    "memory.txt": "free -m; cat /proc/meminfo",
    "processes.txt": "ps aux --sort=-%cpu; ps -eLo pid,tid,pcpu,comm --sort=-pcpu | head -40",
    "thermal.txt": "grep . /sys/class/thermal/thermal_zone*/type /sys/class/thermal/thermal_zone*/temp 2>/dev/null",
    "uname.txt": "uname -a; cat /proc/cmdline",
}
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def app_info(app) -> dict:
    """The display as the app sees it, read on the UI thread."""
    g = app.g
    return {"room": app.room.name, "size": [g.w, g.h], "bits": g.surface.get_bitsize(), "kms": bool(g._kms),
            "driver": pygame.display.get_driver() if pygame.display.get_init() else None, "compositor": compositor_on(),
            "switches": sorted(_switches(THIS_START)), "pygame": pygame.version.ver,
            "sdl": ".".join(map(str, pygame.get_sdl_version())), "python": sys.version.split()[0]}


def _run(cmd, **kw) -> str:
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=60, **kw)
        return r.stdout + r.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return f"({e})"


def compositor_on() -> bool:
    return bool(_run(["pgrep", "-x", "picom"]).strip())


def _switches(path: Path) -> set:
    try:
        return set(path.read_text().split())
    except OSError:
        return set()


def _set_next_start(switches: set):
    text = "".join(f"{s}\n" for s in sorted(switches))
    try:
        NEXT_START.write_text(text)
    except OSError:     # the log partition's folder may be root's
        subprocess.run(["sudo", "-n", "tee", str(NEXT_START)], input=text, capture_output=True, text=True, timeout=10)


def _threads_text() -> str:
    names = {t.ident: t.name for t in threading.enumerate()}
    return "\n".join(f"--- {names.get(ident, ident)}\n{''.join(traceback.format_stack(frame))}"
                     for ident, frame in sys._current_frames().items())


class AdminMenu(Picker):
    title = "Admin"

    def __init__(self, app):
        super().__init__(app, self._rows())

    def _rows(self) -> list:
        nxt, now = _switches(NEXT_START), _switches(THIS_START)
        self.DESCRIPTION = (f"Recording stops by itself after {perf_trace.SECONDS // 60} minutes."
                            + "".join(f"\n{label} is off this start." for s, label in SWITCHES.items() if s in now))
        return ([("record", "Stop Recording" if perf_trace.active() else "Record Performance"),
                 ("speed", "Screen Speed Test"),
                 ("compositor", f"Compositor: {'On' if compositor_on() else 'Off'}")]
                + [(s, f"Next Start: {label} {'Off' if s in nxt else 'On'}") for s, label in SWITCHES.items()]
                + [("copy", "Copy Logs to USB")])

    def _on_confirm(self, value):
        if value == "record" and not perf_trace.active():
            perf_trace.start(app_info(self.app))
            return self.close("recording")
        actions = {"record": perf_trace.stop, "speed": self._speed_test, "compositor": self._toggle_compositor,
                   "copy": lambda: self.app.push(LogExportScreen(self.app))}
        actions.get(value, lambda: _set_next_start(_switches(NEXT_START) ^ {value}))()
        self.options = self._rows()
        self.app.invalidate()

    def _toggle_compositor(self):
        _run(["pkill", "-x", "picom"] if compositor_on() else ["purple-start-compositor"])
        boot_log.heartbeat(f"admin: compositor {'on' if compositor_on() else 'off'}")

    def _speed_test(self):
        """Blocks the UI for several seconds: nothing else should draw while it times the screen."""
        g = self.app.g
        inside = screen_test.time_presents(g.surface, g.present)
        alone = _run([sys.executable, "-m", "purplecomputer.screen_test", str(g.w), str(g.h)], cwd=Path(screen_test.__file__).parents[1])
        try:
            alone = json.loads(alone.strip().splitlines()[-1])
        except (ValueError, IndexError):
            alone = {"error": alone[-500:]}
        result = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), **app_info(self.app), "inside": inside, "alone": alone}
        perf_trace.DIR.mkdir(parents=True, exist_ok=True)
        with open(perf_trace.DIR / "screen-tests.jsonl", "a") as f:
            f.write(json.dumps(result) + "\n")
        boot_log.heartbeat(f"admin: screen test {json.dumps(result)}")
        self.app.invalidate()
        rows = [f"{where} {kind}: {r[kind]['wall']['p50']}ms (cpu {r[kind]['cpu']['p50']}ms)"
                for where, r in (("Inside", inside), ("Alone", alone)) if "error" not in r for kind in ("1px", "full")]
        self.app.push(Notice(self.app, "Screen Speed Test", "\n".join(rows or [str(alone)[:200]])))


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
        (out / "threads.txt").write_text(_threads_text())
        (out / "app.json").write_text(json.dumps({**self._info, "recording": perf_trace.active()}, indent=2))
        size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) >> 20
        return (f'Copied to "{FOLDER}/{out.name}" ({size} MB).', "", "You can unplug the USB drive now.")
