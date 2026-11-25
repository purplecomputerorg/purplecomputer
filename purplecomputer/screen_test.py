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


P, U, I = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int
_XLIB = (("XOpenDisplay", P, [P]), ("XDefaultScreen", I, [P]), ("XRootWindow", U, [P, I]),
         ("XCreateSimpleWindow", U, [P, U, I, I, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, U, U]),
         ("XMapRaised", I, [P, U]), ("XSync", I, [P, I]), ("XDefaultGC", P, [P, I]), ("XSetForeground", I, [P, P, U]),
         ("XFillRectangle", I, [P, U, P, I, I, ctypes.c_uint, ctypes.c_uint]),
         ("XDefaultVisual", P, [P, I]), ("XDefaultDepth", I, [P, I]))
_XSHM = (("XShmCreateImage", P, [P, P, ctypes.c_uint, I, P, P, ctypes.c_uint, ctypes.c_uint]), ("XShmAttach", I, [P, P]),
         ("XShmPutImage", I, [P, U, P, P, I, I, I, I, ctypes.c_uint, ctypes.c_uint, I]))


def _bind(lib: str, table) -> ctypes.CDLL:
    so = ctypes.CDLL(lib)
    for name, res, args in table:
        getattr(so, name).restype, getattr(so, name).argtypes = res, args
    return so


class _X:
    """A plain window of our own, mapped over everything, and a way to time a request that is waited for."""

    def __init__(self, w, h):
        self.x = x = _bind("libX11.so.6", _XLIB)
        self.d = x.XOpenDisplay(None)
        self.screen = x.XDefaultScreen(self.d)
        self.win = x.XCreateSimpleWindow(self.d, x.XRootWindow(self.d, self.screen), 0, 0, w, h, 0, 0, 0)
        self.gc = x.XDefaultGC(self.d, self.screen)
        x.XMapRaised(self.d, self.win)
        x.XSync(self.d, 0)
        time.sleep(0.5)

    def timed(self, send):
        wall, cpu = [], []
        for i in range(FRAMES):
            c, t = time.thread_time(), time.perf_counter()
            send(i)
            self.x.XSync(self.d, 0)
            wall.append(time.perf_counter() - t)
            cpu.append(time.thread_time() - c)
        return {"wall": _ms(wall), "cpu": _ms(cpu)}


def x_fills(w: int, h: int) -> dict:
    """X drawing alone, no SDL: a window's rectangles filled by the X server, each waited for, a bare round
    trip (`sync`), and `batch`: ms per fill when 60 go before one wait. Slow fills but a quick `sync`: X's
    drawing is slow. A quick `batch`: the time is a wait per round trip, which drawing the next frame
    meanwhile would hide."""
    xw = _X(w, h)
    x, d = xw.x, xw.d

    def fill(rw, rh):
        return lambda i: (x.XSetForeground(d, xw.gc, i * 0x040404), x.XFillRectangle(d, xw.win, xw.gc, 0, 0, rw, rh))
    start = time.perf_counter()
    for i in range(FRAMES):
        fill(1, 1)(i)
    x.XSync(d, 0)
    batch = (time.perf_counter() - start) / FRAMES     # each fill when only the last is waited for
    return {"1px": xw.timed(fill(1, 1)), "full": xw.timed(fill(w, h)), "sync": xw.timed(lambda i: None), "batch": round(batch * 1000, 2)}


class _ShmInfo(ctypes.Structure):
    _fields_ = [("shmseg", U), ("shmid", I), ("shmaddr", P), ("readOnly", I)]


def x_shm(w: int, h: int) -> dict:
    """Pixels from our own memory, shared with the X server (MIT-SHM), as SDL is meant to send them but
    without SDL: what Purple would gain by sending its frames itself."""
    xw = _X(w, h)
    x, d = xw.x, xw.d
    xext = _bind("libXext.so.6", _XSHM)
    libc = _bind("libc.so.6", (("shmget", I, [I, ctypes.c_size_t, I]), ("shmat", P, [I, P, I]), ("shmctl", I, [I, I, P])))
    info = _ShmInfo()
    img = xext.XShmCreateImage(d, x.XDefaultVisual(d, xw.screen), x.XDefaultDepth(d, xw.screen), 2, None, ctypes.byref(info), w, h)
    stride = ctypes.cast(img + 44, ctypes.POINTER(I))[0]       # XImage.bytes_per_line
    info.shmid = libc.shmget(0, stride * h, 0o1600)            # IPC_PRIVATE, IPC_CREAT | 0600
    info.shmaddr = libc.shmat(info.shmid, None, 0)
    ctypes.cast(img + 16, ctypes.POINTER(P))[0] = info.shmaddr   # XImage.data
    xext.XShmAttach(d, ctypes.byref(info))
    x.XSync(d, 0)
    libc.shmctl(info.shmid, 0, None)                           # IPC_RMID: gone once both let go

    def put(rw, rh):
        def send(i):
            ctypes.memset(info.shmaddr, i * 4 % 256, stride * rh)
            xext.XShmPutImage(d, xw.win, xw.gc, img, 0, 0, 0, 0, rw, rh, 0)
        return send
    return {"1px": xw.timed(put(1, 1)), "full": xw.timed(put(w, h))}


def main():
    w, h = int(sys.argv[1]), int(sys.argv[2])
    if sys.argv[3:]:
        return print(json.dumps({"x": x_fills, "shm": x_shm}[sys.argv[3]](w, h)))
    pygame.display.init()
    screen = pygame.display.set_mode((w, h), pygame.FULLSCREEN)
    pygame.mouse.set_visible(False)
    print(json.dumps(time_presents(screen, lambda r: pygame.display.update(r) if r else pygame.display.flip())))


if __name__ == "__main__":
    main()
