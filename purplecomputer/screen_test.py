"""How long one frame takes to reach the screen, a 1-pixel update and a full one, from the admin menu.
Timed inside Purple, beside its other threads, and run as `python -m purplecomputer.screen_test W H`:
a process of its own with nothing else in it, in the same kind of fullscreen window. If only the
first is slow, Purple's own threads hold it up; if both are, the X server or the GPU does. `cpu` is
the calling thread's own CPU time: far under `wall`, the call is waiting, not working."""

import json
import sys
import time

import pygame

FRAMES = 60


def _ms(values: list) -> dict:
    s = sorted(values)
    return {q: round(s[min(len(s) - 1, int(f * len(s)))] * 1000, 2) for q, f in (("p50", 0.5), ("p90", 0.9), ("max", 1.0))}


def time_presents(surface, present) -> dict:
    """present(rect or None) FRAMES times each way, every frame changed, as a real one is."""
    out = {}
    for name, rect in (("1px", pygame.Rect(0, 0, 1, 1)), ("full", None)):
        wall, cpu = [], []
        for i in range(FRAMES):
            surface.fill((i * 4 % 256, 0, 80), rect)
            w, c = time.perf_counter(), time.thread_time()
            present(rect)
            wall.append(time.perf_counter() - w)
            cpu.append(time.thread_time() - c)
        out[name] = {"wall": _ms(wall), "cpu": _ms(cpu)}
    return out


def main():
    pygame.display.init()
    screen = pygame.display.set_mode((int(sys.argv[1]), int(sys.argv[2])), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    print(json.dumps(time_presents(screen, lambda r: pygame.display.update(r) if r else pygame.display.flip())))


if __name__ == "__main__":
    main()
