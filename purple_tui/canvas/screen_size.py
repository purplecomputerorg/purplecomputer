"""Run X at no more than 1920x1200. Every frame is drawn in software, so a
2880x1800 Retina panel costs 2.5x a 1080p frame and looks no different at a
kid's distance; the panel or monitor scales the smaller mode up for free.

Only a lone screen is switched, only to a mode of its own shape, and a laptop
panel is told to fill itself so no driver leaves a small centered picture."""

import os
import re
import subprocess

MAX_LONG, MAX_SHORT = 1920, 1200
ASPECT_SLACK = 0.03
NATIVE_FLAG = "/opt/purple/native-resolution"   # touch to keep every screen at its own size
FILL = "Full aspect"

_OUTPUT = re.compile(r"^(\S+) connected")
_MODE = re.compile(r"^\s+(\d+)x(\d+)(\S*)\s*(.*)$")
_SCALING = re.compile(r"^\s+scaling mode:")
_SUPPORTED = re.compile(r"^\s+supported:(.*)$")


def fits(w: int, h: int) -> bool:
    return max(w, h) <= MAX_LONG and min(w, h) <= MAX_SHORT


def outputs(query: str) -> dict:
    """{output: {"modes": [(w, h, name, rate flags)], "fill": bool}} for each
    connected output in `xrandr --query --prop`; fill when its driver can scale to fill."""
    found, out, scaling = {}, None, False
    for line in query.splitlines():
        if not line[:1].isspace():
            m = _OUTPUT.match(line)
            out = found.setdefault(m[1], {"modes": [], "fill": False}) if m else None
            scaling = False
        elif out is None:
            continue
        elif _SCALING.match(line):
            scaling = True
        elif scaling and (m := _SUPPORTED.match(line)):
            out["fill"] = FILL in [v.strip() for v in m[1].split(",")]
            scaling = False
        elif m := _MODE.match(line):
            out["modes"].append((int(m[1]), int(m[2]), f"{m[1]}x{m[2]}{m[3]}", m[4]))
    return found


def _native(modes: list):
    return next((m for m in modes if "+" in m[3]), modes[0])


def current(modes: list):
    return next((m for m in modes if "*" in m[3]), _native(modes))


def pick(modes: list):
    """The largest progressive mode under the cap with the screen's shape, or None."""
    w, h = _native(modes)[:2]
    same_shape = [m for m in modes if fits(*m[:2]) and not m[2].endswith("i") and abs(m[0] / m[1] - w / h) < ASPECT_SLACK]
    return max(same_shape, key=lambda m: m[0] * m[1], default=(None,) * 3)[2]


def _in_vm() -> bool:
    try:
        with open("/proc/cpuinfo") as f:
            return any(line.startswith("flags") and " hypervisor" in line for line in f)
    except OSError:
        return False


def _plan(query: str):
    """(xrandr arguments, log line) for the switch, or (None, why not)."""
    found = {name: o for name, o in outputs(query).items() if o["modes"]}
    if len(found) != 1:
        return None, f"{len(found)} screens connected, each keeps its size"
    (name, out), = found.items()
    mode = pick(out["modes"])
    if mode is None:
        return None, f"{name} keeps {current(out['modes'])[2]}, no smaller mode with its shape"
    fill = ["--set", "scaling mode", FILL] if out["fill"] else []
    return ["--output", name, *fill, "--mode", mode], f"{name} {current(out['modes'])[2]} -> {mode}"


def cap(width: int, height: int, log) -> bool:
    """Switch a lone screen over the cap to a smaller mode. True when xrandr
    ran, so the caller reopens the display at whatever size it left."""
    if fits(width, height) or _in_vm() or os.path.exists(NATIVE_FLAG):
        return False
    try:
        query = subprocess.run(["xrandr", "--query", "--prop"], capture_output=True, text=True, timeout=5).stdout
        args, line = _plan(query)
        if args:
            ok = subprocess.run(["xrandr", *args], capture_output=True, timeout=10).returncode == 0
            line += "" if ok else " FAILED"
        log(f"screen size: {line}")
        return bool(args)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"screen size: xrandr failed: {e}")
        return True
