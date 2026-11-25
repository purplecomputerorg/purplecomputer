"""Admin menu's Run All Tests: screen speed tests with the compositor on and off, then a recording
of Blocks turning and looking around builds of several sizes, on a copy of the room so the kid's
build is never touched, then everything is copied to a USB drive. guides/admin-menu.md"""

import asyncio
import json
import statistics
import time

from .. import boot_log, perf_trace
from ..palette import KEY_COLORS
from ..ui import Overlay, draw_label
from .blocks_view import DEPTH, HEIGHT, WIDTH

BUILDS = (100, 400, 850)    # blocks
KEY_REPEAT_S = 1 / 30       # a held arrow's repeats, as the kernel sends them
SUMMARY = "autorun.txt"


def city(n: int) -> dict:
    """A Blocks timeline state of n blocks: towers of mixed heights, standing from the middle out."""
    cells = sorted(((x, z) for x in range(WIDTH) for z in range(DEPTH)),
                   key=lambda c: (abs(c[0] - WIDTH / 2 + 0.5) + abs(c[1] - DEPTH / 2 + 0.5), c))
    colors = list(KEY_COLORS.values())
    spots = [(x, z, y) for x, z in cells for y in range(HEIGHT) if y < 2 + (x * 7 + z * 13) % (HEIGHT - 2)]
    return {"floor": [WIDTH, DEPTH]} | {f"b:{x},{z},{y}": colors[(x + z + y) % len(colors)] for x, z, y in spots[:n]}


async def _settle(room, timeout=6.0):
    end = time.monotonic() + timeout
    while room._moving() is not None and time.monotonic() < end:
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.5)


async def _turns(room):
    for _ in range(4):
        room.turn()
        await _settle(room)


async def _hold(room, direction, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        room.look_around(direction, held=True)
        await asyncio.sleep(KEY_REPEAT_S)
    await _settle(room)


async def _looks(room):
    await _hold(room, "left", 4)


async def _tilts(room):
    await _hold(room, "up", 2)
    await _hold(room, "down", 2)


MOVES = {"turn": _turns, "look": _looks, "tilt": _tilts}


def summarize(path) -> list:
    """A line per build: frames a second while each move goes, and its frames' median draw and present."""
    runs: dict = {}
    for rec in map(json.loads, path.read_text().splitlines()):
        if "step" in rec and "blocks" in rec:
            runs.setdefault(rec["blocks"], {}).setdefault(rec["step"], []).append(rec)

    def fps(fr):    # from the typical gap, not the span: the pauses between moves draw nothing
        return 1000 / max(1e-3, statistics.median(f["gap"] for f in fr if f.get("gap") is not None))

    def med(key, steps):
        return round(statistics.median(f[key] for fr in steps.values() for f in fr))
    return [f"{n} blocks: " + ", ".join(f"{step} {fps(fr):.1f}" for step, fr in steps.items()) +
            f" fps (draw {med('draw', steps)}, present {med('present', steps)} ms)" for n, steps in runs.items()]


class AutoRun(Overlay):
    """Over the screen while the run goes: says what it's doing, between the parts it times. Escape stops it."""

    scrim = False

    def __init__(self, app):
        super().__init__(app)
        self.status = "starting"
        self.task = None

    def on_open(self):
        self.task = asyncio.get_running_loop().create_task(self._run())

    def draw(self, g):
        if self.status:
            draw_label(g, f"Run All Tests: {self.status}. Esc stops.", g.em(0.9), g.stage.x + g.em(1), g.stage.y + g.em(1), on=True)

    async def handle(self, action):
        if getattr(action, "action", None) == "escape" and getattr(action, "is_down", True):
            self.task.cancel()

    async def _say(self, status):
        self.status = status
        self.app.invalidate()
        await asyncio.sleep(0.2)    # a frame to show it before the UI blocks

    async def _run(self):
        from .admin_menu import LogExportScreen, app_info, compositor_on, speed_test, toggle_compositor
        lines, compositor = [], compositor_on()
        try:
            for _ in range(2):
                await self._say(f"timing the screen, compositor {'on' if compositor_on() else 'off'}")
                lines += [f"Compositor {'on' if compositor_on() else 'off'}:"] + speed_test(self.app)
                toggle_compositor()
                await asyncio.sleep(1)
            perf_trace.start({**app_info(self.app), "autorun": True})
            for n in BUILDS:
                await self._blocks(n)
            perf_trace.stop()
            lines += summarize(perf_trace.FRAMES)
        except asyncio.CancelledError:
            lines.append("Stopped.")
        except Exception as e:     # whatever got done still goes to the drive
            lines.append(f"Failed: {e!r}")
        finally:
            perf_trace.stop()
            if compositor_on() != compositor:
                toggle_compositor()
            perf_trace.DIR.mkdir(parents=True, exist_ok=True)
            (perf_trace.DIR / SUMMARY).write_text("\n".join(lines) + "\n")
            boot_log.heartbeat(f"admin: run all tests {lines}")
            self.close()
        self.app.push(LogExportScreen(self.app, lines))

    async def _blocks(self, n):
        """Swaps a copy of Blocks holding n blocks in for the room, then puts everything back as it was."""
        await self._say(f"building {n} blocks")
        app, real, was, panel = self.app, self.app.rooms["blocks"], self.app.active_room, self.app._panel
        if app._time_travel is not None:
            app._cancel_time_travel()
        app._timeline_flush()
        if was != "blocks":
            app.room.on_leave()
        room = app.rooms["blocks"] = type(real)(app)
        room.restore_timeline_state(city(n))
        app.active_room, app._panel = "blocks", None
        room.on_enter()
        try:
            await self._say("")
            for name, move in MOVES.items():
                perf_trace.step(step=name)
                await move(room)
            perf_trace.step()
        finally:
            if room._look_timer is not None:
                room._look_timer.stop()
            app._timeline_pending.pop("blocks", None)
            app.rooms["blocks"], app.active_room, app._panel = real, was, panel
            app.room.on_enter()
            app.invalidate()
