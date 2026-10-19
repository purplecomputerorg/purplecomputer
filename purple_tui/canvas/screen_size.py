"""Run X at no more than 1920x1200. Every frame is drawn in software, so a
2880x1800 Retina panel costs 2.5x a 1080p frame and looks no different at a
kid's distance; the panel or monitor scales the smaller mode up for free."""

import re
import subprocess

MAX_W, MAX_H = 1920, 1200
ASPECT_SLACK = 0.03

_OUTPUT = re.compile(r"^(\S+) connected")
_MODE = re.compile(r"^\s+(\d+)x(\d+)(\S*)\s*(.*)$")


def fits(w: int, h: int) -> bool:
    return w <= MAX_W and h <= MAX_H


def outputs(query: str) -> dict:
    """{output: [(w, h, mode name, rate flags)]} for each connected output in `xrandr --query`."""
    found, modes = {}, None
    for line in query.splitlines():
        if not line.startswith(" "):
            m = _OUTPUT.match(line)
            modes = found.setdefault(m[1], []) if m else None
        elif modes is not None and (m := _MODE.match(line)):
            modes.append((int(m[1]), int(m[2]), f"{m[1]}x{m[2]}{m[3]}", m[4]))
    return found


def _native(modes: list):
    return next((m for m in modes if "+" in m[3]), modes[0])


def current(modes: list):
    return next((m for m in modes if "*" in m[3]), _native(modes))


def pick(modes: list):
    """The largest progressive mode under the cap with the panel's shape, or None."""
    w, h = _native(modes)[:2]
    same_shape = [m for m in modes if fits(*m[:2]) and not m[2].endswith("i") and abs(m[0] / m[1] - w / h) < ASPECT_SLACK]
    return max(same_shape, key=lambda m: m[0] * m[1], default=(None,) * 3)[2]


def _in_vm() -> bool:
    try:
        with open("/proc/cpuinfo") as f:
            return any(line.startswith("flags") and " hypervisor" in line for line in f)
    except OSError:
        return False


def cap(width: int, height: int, log) -> bool:
    """Switch every connected output over the cap to a smaller mode. True when
    one changed, so the caller reopens the display at the new size."""
    if fits(width, height) or _in_vm():   # a VM's screen follows its window
        return False
    try:
        query = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError) as e:
        log(f"screen size: xrandr failed: {e}")
        return False
    changed = False
    for output, modes in outputs(query).items():
        if not modes or fits(*current(modes)[:2]):
            continue
        name = pick(modes)
        if name is None:
            log(f"screen size: {output} keeps {current(modes)[2]}, no smaller mode with its shape")
            continue
        ok = subprocess.run(["xrandr", "--output", output, "--mode", name], capture_output=True, timeout=10).returncode == 0
        log(f"screen size: {output} {current(modes)[2]} -> {name}{'' if ok else ' FAILED'}")
        changed |= ok
    return changed
