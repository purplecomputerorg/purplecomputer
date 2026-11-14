"""Frame timing in the boot log: draw, present, and keypress-to-screen time,
summarized every 30s while frames are drawn (an idle screen logs nothing)."""

import time

from .. import boot_log

INTERVAL = 30.0


def _ms(values: list) -> str:
    s = sorted(values)
    pick = lambda q: s[min(len(s) - 1, int(q * len(s)))] * 1000  # noqa: E731
    return f"p50 {pick(0.5):.0f} p95 {pick(0.95):.0f} max {s[-1] * 1000:.0f}ms" if s else "-"


class FrameStats:
    def __init__(self, g):
        self._g = g  # read at log time: the screen can change size under us
        self._reset(time.monotonic())

    def _reset(self, now: float):
        self._since = now
        self._key_at = None
        self._draw, self._present, self._key = [], [], []

    def key(self):
        if self._key_at is None:
            self._key_at = time.monotonic()

    def frame(self, start: float, drawn: float, presented: float):
        self._draw.append(drawn - start)
        self._present.append(presented - drawn)
        if self._key_at is not None:
            self._key.append(presented - self._key_at)
            self._key_at = None
        if presented - self._since >= INTERVAL:
            boot_log.heartbeat(f"frames {len(self._draw)} at {self._g.w}x{self._g.h}: "
                               f"draw {_ms(self._draw)}, present {_ms(self._present)}, key to screen {_ms(self._key)}")
            self._reset(presented)
