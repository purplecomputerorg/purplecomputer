#!/usr/bin/env python3
"""Stop a process group once the X11 screen has gone visually idle.

Used by record-demo.sh manual mode. There is no usable input-idle signal:
Purple EVIOCGRABs the keyboard, so X never sees keystrokes and xprintidle
would report idle the whole time. Instead we sample the framebuffer and stop
when nothing meaningful has changed for a while. A small per-pixel + fraction
threshold ignores a blinking cursor while still resetting on real activity.
"""
import argparse
import os
import signal
import subprocess
import sys
import time
from io import BytesIO

import numpy as np
from PIL import Image


def grab(display, size):
    cmd = [
        "ffmpeg", "-loglevel", "quiet", "-f", "x11grab",
        "-video_size", size, "-i", display,
        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-",
    ]
    out = subprocess.run(cmd, capture_output=True).stdout
    if not out:
        return None
    return np.asarray(Image.open(BytesIO(out)).convert("L"), dtype=np.int16)


def alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except OSError:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--display", required=True)
    p.add_argument("--size", required=True)
    p.add_argument("--pid", type=int, required=True, help="process group id to stop")
    p.add_argument("--idle", type=float, default=60.0, help="idle seconds before stopping")
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--pixel-thresh", type=int, default=24)
    p.add_argument("--frac-thresh", type=float, default=0.002)
    a = p.parse_args()

    prev = grab(a.display, a.size)
    last_change = time.monotonic()

    while alive(a.pid):
        time.sleep(a.interval)
        cur = grab(a.display, a.size)
        if cur is None:
            continue
        if prev is None or cur.shape != prev.shape:
            prev = cur
            last_change = time.monotonic()
            continue
        changed = (np.abs(cur - prev) > a.pixel_thresh).mean() > a.frac_thresh
        prev = cur
        now = time.monotonic()
        if changed:
            last_change = now
        elif now - last_change >= a.idle:
            print(f"Idle for {a.idle:.0f}s, stopping recording.", file=sys.stderr)
            try:
                os.killpg(a.pid, signal.SIGTERM)
            except OSError:
                pass
            return


if __name__ == "__main__":
    main()
