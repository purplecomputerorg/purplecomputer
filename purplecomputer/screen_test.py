"""How long one frame takes to reach the screen, a 1-pixel update and a full one, from the admin menu.
Timed inside Purple, beside its other threads, and run as `python -m purplecomputer.screen_test W H`:
a process of its own with nothing else in it, in the same kind of fullscreen window. If only the
first is slow, Purple's own threads hold it up; if both are, the X server or the GPU does. `cpu` is
the calling thread's own CPU time: far under `wall`, the call is waiting, not working."""

import ctypes
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


def x_fills(w: int, h: int) -> dict:
    """X drawing alone, no SDL: a window's rectangles filled by the X server, each waited for, a bare round
    trip (`sync`), and `batch`: ms per fill when 60 go before one wait. Slow fills but a quick `sync`: X's
    drawing is slow. A quick `batch`: the time is a wait per round trip, which drawing the next frame
    meanwhile would hide."""
    x = ctypes.CDLL("libX11.so.6")
    P, U = ctypes.c_void_p, ctypes.c_ulong
    for name, res, args in (("XOpenDisplay", P, [P]), ("XDefaultScreen", ctypes.c_int, [P]), ("XRootWindow", U, [P, ctypes.c_int]),
                            ("XCreateSimpleWindow", U, [P, U, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, U, U]),
                            ("XMapRaised", ctypes.c_int, [P, U]), ("XSync", ctypes.c_int, [P, ctypes.c_int]),
                            ("XDefaultGC", P, [P, ctypes.c_int]), ("XSetForeground", ctypes.c_int, [P, P, U]),
                            ("XFillRectangle", ctypes.c_int, [P, U, P, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint])):
        getattr(x, name).restype, getattr(x, name).argtypes = res, args
    d = x.XOpenDisplay(None)
    screen = x.XDefaultScreen(d)
    win, gc = x.XCreateSimpleWindow(d, x.XRootWindow(d, screen), 0, 0, w, h, 0, 0, 0), x.XDefaultGC(d, screen)
    x.XMapRaised(d, win)
    x.XSync(d, 0)
    time.sleep(0.5)

    def timed(fill):
        wall, cpu = [], []
        for i in range(FRAMES):
            c, t = time.thread_time(), time.perf_counter()
            fill(i)
            x.XSync(d, 0)
            wall.append(time.perf_counter() - t)
            cpu.append(time.thread_time() - c)
        return {"wall": _ms(wall), "cpu": _ms(cpu)}

    def fill(rw, rh):
        return lambda i: (x.XSetForeground(d, gc, i * 0x040404), x.XFillRectangle(d, win, gc, 0, 0, rw, rh))
    start = time.perf_counter()
    for i in range(FRAMES):
        fill(1, 1)(i)
    x.XSync(d, 0)
    batch = (time.perf_counter() - start) / FRAMES     # each fill when only the last is waited for
    return {"1px": timed(fill(1, 1)), "full": timed(fill(w, h)), "sync": timed(lambda i: None), "batch": round(batch * 1000, 2)}


def main():
    w, h = int(sys.argv[1]), int(sys.argv[2])
    if sys.argv[3:] == ["x"]:
        return print(json.dumps(x_fills(w, h)))
    pygame.display.init()
    screen = pygame.display.set_mode((w, h), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    print(json.dumps(time_presents(screen, lambda r: pygame.display.update(r) if r else pygame.display.flip())))


if __name__ == "__main__":
    main()
