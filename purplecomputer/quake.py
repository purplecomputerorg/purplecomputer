"""Type "earthquake" in Play: the screen rumbles, everything on it falls into a pile, then hops home."""

import math
import random
import time

import pygame

from . import palette as P
from .gfx import rgb
from .ui import Overlay

WORD = "earthquake"
SHAKE_S, FALL_S, REST_S, BACK_S = 1.6, 1.6, 1.0, 0.9
TOTAL_S = SHAKE_S + FALL_S + REST_S + BACK_S
STEP = 1 / 60
COL = 8            # heightmap column width, px
MIN_BITS = 12      # specks smaller than this stay put
MAX_PIECES = 160


def is_quake(text: str) -> bool:
    return text.strip(" !.").lower() == WORD


def _rumble(t: float, amp: float) -> tuple:
    """A few summed sines, so the screen rolls instead of jumping frame to frame."""
    return (amp * (0.6 * math.sin(t * 71) + 0.4 * math.sin(t * 113 + 1.3)),
            amp * 0.5 * (0.6 * math.sin(t * 89 + 0.7) + 0.4 * math.sin(t * 131 + 2.1)))


def _envelope(t: float) -> float:
    rise, hold = 0.25, 0.6
    if t < rise:
        return t / rise
    return 1.0 if t < rise + hold else max(0.0, 1 - (t - rise - hold) / (SHAKE_S - rise - hold)) ** 2


def _sized(w: int, h: int) -> pygame.Mask:
    return pygame.Mask((w, h), fill=True)


def _crop(mask: pygame.Mask, r: pygame.Rect) -> pygame.Mask:
    out = pygame.Mask(r.size)
    out.draw(mask, (-r.x, -r.y))
    return out


class Piece:
    def __init__(self, surf, rect, inside, rng):
        self.surf, self.home, self.inside = surf, rect, inside
        self.x, self.y, self.vx, self.vy = float(rect.x), float(rect.y), 0.0, 0.0
        self.spin, self.delay, self.drift = rng.uniform(-14, 14), rng.uniform(0, 0.35), rng.uniform(-1, 1)
        self.resting, self.bounced, self.angle = False, False, 0.0
        self._turned = {}

    def turned(self, angle: float):
        a = round(angle)
        if a not in self._turned:
            self._turned[a] = pygame.transform.rotate(self.surf, a)
        return self._turned[a]


class Quake(Overlay):
    scrim = False

    def __init__(self, app):
        super().__init__(app)
        self.pieces = None
        self.t, self.sim_t, self.start = 0.0, 0.0, 0.0
        self._tick_handle = None

    def on_open(self):
        self._tick_handle = self.app.timers.every(STEP, self._tick)

    def on_close(self):
        if self._tick_handle:
            self._tick_handle.stop()

    async def handle(self, action):
        pass

    def _tick(self):
        self.advance(time.monotonic() - self.start if self.pieces else 0.0)
        if self.t >= TOTAL_S:
            self.close()
        else:
            self.app.invalidate()

    # ------------------------------------------------------------ cutting the screen into pieces
    def _cut(self, snap: pygame.Surface):
        """Every word, emoji or button whose pixels stand out from the two grounds becomes a piece;
        the ground underneath is painted over where each one was."""
        frame = self.app._frame_rect(self.app._viewport_rect())
        thr = (10, 10, 10, 255)
        fg = pygame.mask.from_threshold(snap, rgb(P.BG), thr)
        fg.draw(pygame.mask.from_threshold(snap, rgb(P.SURFACE), thr), (0, 0))
        fg.invert()
        ring = _sized(*frame.size)
        ring.erase(_sized(frame.w - 10, frame.h - 10), (5, 5))
        fg.erase(ring, frame.topleft)   # the frame's own border stays: it is the floor and walls
        edges = fg.convolve(_sized(3, 3), None, (-1, -1))
        words = fg.convolve(_sized(9, 3), None, (-4, -1))
        comps = sorted(words.connected_components(MIN_BITS), key=lambda m: -m.count())[:MAX_PIECES]
        self.ground = snap.copy()
        self.inner = frame.inflate(-10, -10)
        rng = random.Random(len(comps))
        self.pieces = []
        for comp in comps:
            r = comp.get_bounding_rects()[0].clip(snap.get_rect())
            shape = _crop(edges, r).overlap_mask(_crop(comp, r), (0, 0))
            inside = self.inner.collidepoint(r.center)
            surf = pygame.Surface(r.size, pygame.SRCALPHA)
            surf.blit(snap, (0, 0), r)
            shape.to_surface(surf, setcolor=None, unsetcolor=(0, 0, 0, 0))
            shape.to_surface(self.ground, setcolor=rgb(P.SURFACE if inside else P.BG), unsetcolor=None, dest=r.topleft)
            self.pieces.append(Piece(surf, r, inside, rng))
        w, h = snap.get_size()
        self.floors = {True: [float(self.inner.bottom)] * (w // COL + 1), False: [float(h)] * (w // COL + 1)}
        self.size = (w, h)
        self.start = time.monotonic()   # after the cut, so a slow machine still shows the whole rumble

    # ------------------------------------------------------------ motion
    def advance(self, t: float):
        self.t = t
        if self.pieces is None:
            return
        while self.sim_t + STEP <= min(max(0.0, t - SHAKE_S), FALL_S):
            self.sim_t += STEP
            for p in self.pieces:
                self._fall(p)

    def _fall(self, p: Piece):
        if p.resting or self.sim_t < p.delay:
            return
        w, h = self.size
        lo, hi = (self.inner.left, self.inner.right) if p.inside else (0, w)
        p.vy += 3.4 * h * STEP
        p.y += p.vy * STEP
        p.x = min(max(p.x + p.drift * 0.08 * w * STEP, lo), hi - p.home.w)
        cols = self.floors[p.inside]
        a, b = int(p.x) // COL, (int(p.x) + p.home.w) // COL + 1
        floor = min(cols[a:b])
        p.angle = p.spin * min(1.0, (p.y - p.home.y) / (h * 0.25))
        if p.y + p.home.h < floor:
            return
        p.y = floor - p.home.h
        if not p.bounced and p.vy > 0.6 * h:
            p.vy, p.bounced = -p.vy * 0.28, True
        else:
            p.resting = True
            cols[a:b] = [p.y] * (b - a)

    def _pose(self, p: Piece, k: int) -> tuple:
        """Where piece k sits right now: (x, y, angle)."""
        t = self.t
        if t < SHAKE_S:
            a = self.size[1] * 0.004 * _envelope(t)
            return (p.home.x + a * math.sin(t * 83 + k * 3), p.home.y + a * 1.2 * math.sin(t * 97 + k),
                    a * 0.6 * math.sin(t * 61 + k * 2))
        back = t - SHAKE_S - FALL_S - REST_S
        if back <= 0:
            return p.x, p.y, p.angle
        v = min(1.0, max(0.0, (back / BACK_S - p.delay * 0.6) / 0.79))
        e = 1 - (1 - v) ** 3
        hop = -self.size[1] * 0.12 * math.sin(math.pi * v) * (1 - e)
        return p.x + (p.home.x - p.x) * e, p.y + (p.home.y - p.y) * e + hop, p.angle * (1 - e)

    # ------------------------------------------------------------ drawing
    def draw(self, g):
        g.caret = None
        if self.pieces is None:
            self._cut(g.surface)
        dx, dy = _rumble(self.t, self.size[1] * 0.02 * _envelope(self.t)) if self.t < SHAKE_S else (0, 0)
        g.surface.fill(rgb(P.BG))
        g.surface.blit(self.ground, (dx, dy))
        for k, p in enumerate(self.pieces):
            x, y, angle = self._pose(p, k)
            surf = p.turned(angle) if abs(angle) >= 0.5 else p.surf
            cx, cy = x + p.home.w / 2 + dx, y + p.home.h / 2 + dy
            g.surface.blit(surf, (round(cx - surf.get_width() / 2), round(cy - surf.get_height() / 2)))
