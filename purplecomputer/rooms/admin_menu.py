"""Admin menu, opened by typing "admin" (or "tavi") in the Parent Menu: record performance, time the
screen, try the display without the compositor or (next start) without GPU acceleration, then copy
every log, the recording and a snapshot of the machine to a USB drive. guides/admin-menu.md"""

import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
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
    "i915.txt": "sudo -n sh -c 'for f in /sys/kernel/debug/dri/*/i915_drrs_status /sys/kernel/debug/dri/*/i915_display_info "
                "/sys/kernel/debug/dri/*/i915_fbc_status /sys/kernel/debug/dri/*/i915_edp_psr_status; do echo \"== $f\"; cat \"$f\"; done'",
    "switches.txt": "ls -la /var/log/purple; findmnt /var/log; cat /run/purple-admin-start; sudo -n journalctl -b -u purple-x11 --no-pager | grep -i admin",
}
# How a process of its own reaches the screen, as (arguments, environment): SDL's own way (X shared memory), then
# through the GPU's OpenGL (the session's is software), not waiting for the refresh, then X drawing with no SDL.
_GPU = {"LIBGL_ALWAYS_SOFTWARE": "0", "vblank_mode": "0"}
ALONE = {"Alone": ((), {}), "Alone GL": ((), {"SDL_FRAMEBUFFER_ACCELERATION": "opengl", **_GPU}),
         "Alone GLES": ((), {"SDL_FRAMEBUFFER_ACCELERATION": "opengles2", **_GPU}), "X alone": (("x",), {})}
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


def toggle_compositor():
    _run(["pkill", "-x", "picom"] if compositor_on() else ["purple-start-compositor"])
    boot_log.heartbeat(f"admin: compositor {'on' if compositor_on() else 'off'}")


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
    os.sync()   # a restart right after, or the power button, must not lose it


def _alone(g, args, env: dict) -> dict:
    out = _run([sys.executable, "-m", "purplecomputer.screen_test", str(g.w), str(g.h), *args],
               cwd=Path(screen_test.__file__).parents[1], env={**os.environ, **env})
    try:     # Mesa may print notes after it
        return json.loads(next(line for line in reversed(out.splitlines()) if line.startswith("{")))
    except (ValueError, StopIteration):
        return {"error": out[-500:]}


def _watched(fn, tasks: list):
    """(fn(), where X's threads were meanwhile): each "thread state wchan" sampled every 2ms, as % of samples."""
    seen, rounds, done = Counter(), [0], threading.Event()

    def sample():
        while not done.wait(0.002):
            rounds[0] += 1
            for t in tasks:
                try:
                    with open(f"{t}/comm") as c, open(f"{t}/stat") as st, open(f"{t}/wchan") as w:
                        seen[f"{c.read().strip()} {st.read().rsplit(')', 1)[1].split()[0]} {w.read() or '-'}"] += 1
                except OSError:
                    pass
    watcher = threading.Thread(target=sample, daemon=True, name="x-waits")
    watcher.start()
    try:
        return fn(), {k: round(100 * n / max(1, rounds[0])) for k, n in seen.most_common(8)}
    finally:
        done.set()
        watcher.join()


def speed_test(app) -> list:
    """Times the screen inside Purple and alone; its lines to show. Blocks the UI for several seconds:
    nothing else should draw while it times the screen."""
    g = app.g
    xorg = _run(["pgrep", "-xo", "Xorg"]).strip()
    tasks = glob.glob(f"/proc/{xorg}/task/*") if xorg.isdigit() else []
    runs = {"Inside": lambda: screen_test.time_presents(g.surface, g.present)} | {
        name: (lambda way=way: _alone(g, *way)) for name, way in ALONE.items()}
    watched = {name: _watched(run, tasks) for name, run in runs.items()}
    tests = {name: r for name, (r, _) in watched.items()}
    result = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), **app_info(app), "tests": tests,
              "xorg_waits": {name: w for name, (_, w) in watched.items()}}
    perf_trace.DIR.mkdir(parents=True, exist_ok=True)
    with open(perf_trace.DIR / "screen-tests.jsonl", "a") as f:
        f.write(json.dumps(result) + "\n")
    boot_log.heartbeat(f"admin: screen test {json.dumps(result)}")
    app.invalidate()
    return [f"{name}: failed" if "error" in r else
            f"{name}: 1px {r['1px']['wall']['p50']:.1f}, full {r['full']['wall']['p50']:.1f} ms (cpu {r['1px']['cpu']['p50']:.1f}, {r['full']['cpu']['p50']:.1f})"
            + (f", sync {r['sync']['wall']['p50']:.1f}, batch {r['batch']:.1f}" if "sync" in r else "")
            for name, r in tests.items()]


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
                            + "".join(f"\n{label} is {'off' if s in now else 'on'} this start." for s, label in SWITCHES.items()))
        return ([("auto", "Run All Tests"),
                 ("record", "Stop Recording" if perf_trace.active() else "Record Performance"),
                 ("speed", "Screen Speed Test"),
                 ("compositor", f"Compositor: {'On' if compositor_on() else 'Off'}")]
                + [(s, f"Next Start: {label} {'Off' if s in nxt else 'On'}") for s, label in SWITCHES.items()]
                + [("copy", "Copy Logs to USB")])

    def _on_confirm(self, value):
        if value == "auto" or (value == "record" and not perf_trace.active()):
            from .admin_autorun import AutoRun
            self.close("leave")
            return self.app.push(AutoRun(self.app)) if value == "auto" else perf_trace.start(app_info(self.app))
        actions = {"record": perf_trace.stop, "speed": self._speed_test, "compositor": toggle_compositor,
                   "copy": lambda: self.app.push(LogExportScreen(self.app))}
        actions.get(value, lambda: _set_next_start(_switches(NEXT_START) ^ {value}))()
        self.options = self._rows()
        self.app.invalidate()

    def _speed_test(self):
        self.app.push(Notice(self.app, "Screen Speed Test", "\n".join(speed_test(self.app))))


class LogExportScreen(UsbCopyScreen):
    title = "Copy Logs to USB"
    working = "Copying logs..."

    def __init__(self, app, summary=()):
        super().__init__(app)
        self._info, self.lead = app_info(app), (*summary, "") if summary else ()
        self.width_pct = 85 if summary else self.width_pct

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
        size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
        return (f'Copied to "{FOLDER}/{out.name}" ({size:.1f} MB).', "", "You can unplug the USB drive now.")
