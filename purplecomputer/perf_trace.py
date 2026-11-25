"""A performance recording, started from the admin menu: every frame as a line of JSON with what the
room noted while drawing it, beside log-performance's once a second machine samples. Off, a frame
costs one check."""

import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

DIR = Path(os.environ.get("PURPLE_PERF_DIR", "/tmp/purple-perf"))
FRAMES = DIR / "frames.jsonl"
SECONDS = 600   # a forgotten recording stops itself: /tmp is RAM
THREADS_EVERY = 1.0   # seconds between samples of each thread's CPU time and where it is
_HERE = Path(__file__).resolve().parents[1]
SAMPLER = next((p for p in (_HERE / "scripts" / "log-performance.py", _HERE / "scripts" / "on-device" / "log-performance.py")
                if p.exists()), None)

_out = None
_until = 0.0
_last = None    # when the frame before reached the screen
_threads_at = 0.0
_note: dict = {}


def ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


def active() -> bool:
    return _out is not None


def sampler(cmd: str) -> subprocess.CompletedProcess | None:
    if SAMPLER is None:
        return None
    env = {**os.environ, "PURPLE_PERF_DIR": str(DIR), "PURPLE_PERF_SECONDS": str(SECONDS)}
    try:
        return subprocess.run([sys.executable, str(SAMPLER), cmd], env=env, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None


def start(info: dict):
    global _out, _until, _last
    stop()
    DIR.mkdir(parents=True, exist_ok=True)
    sampler("start")    # it clears the folder's old samples, then returns while its sampler runs on
    _out, _until, _last = open(FRAMES, "w"), time.monotonic() + SECONDS, None
    _write({"started": time.strftime("%Y-%m-%d %H:%M:%S"), "ticks_per_s": os.sysconf("SC_CLK_TCK"), **info})


def stop():
    global _out
    if _out is not None:
        _out.close()
        _out = None
        sampler("stop")


def flush():
    if _out is not None:
        _out.flush()


def _write(rec: dict):
    _out.write(json.dumps(rec, separators=(",", ":")) + "\n")


def note(**fields):
    """Fields for the frame being drawn now."""
    if _out is not None:
        _note.update(fields)


def _skip(name: str):
    pass


def laps():
    """lap(name) records the time since the last lap, or since laps(), under the frame's phases."""
    if _out is None:
        return _skip
    phases, last = _note.setdefault("phases", {}), [time.monotonic()]

    def lap(name: str):
        now = time.monotonic()
        phases[name] = ms(now - last[0])
        last[0] = now
    return lap


def threads() -> dict:
    """Each of this process's threads, as "name#id": [CPU ticks so far, its innermost Python frames]."""
    live, frames = threading.enumerate(), sys._current_frames()
    py = {t.native_id: (t.name, frames.get(t.ident)) for t in live}
    out = {}
    for task in os.scandir("/proc/self/task"):
        try:
            with open(f"{task.path}/stat") as f:
                stat = f.read()
        except OSError:
            continue
        tid, fields = int(task.name), stat[stat.rindex(")") + 2:].split()
        name, where = py.get(tid, (stat[stat.index("(") + 1:stat.rindex(")")], None))
        stack = [f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno} {f.name}" for f in traceback.extract_stack(where)[-3:]] if where else []
        out[f"{name}#{tid}"] = [int(fields[11]) + int(fields[12]), stack]
    return out


def frame(start: float, drawn: float, presented: float, room: str):
    global _last, _threads_at
    if _out is None:
        return
    gap = ms(presented - _last) if _last is not None else None
    _write({"t": round(presented, 4), "room": room, "draw": ms(drawn - start), "present": ms(presented - drawn), "gap": gap, **_note})
    _note.clear()
    _last = presented
    if presented - _threads_at >= THREADS_EVERY:
        _threads_at = presented
        _write({"t": round(presented, 4), "threads": threads()})
    if presented > _until:
        stop()
