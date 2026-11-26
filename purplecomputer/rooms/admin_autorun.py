"""Admin menu's Run All Tests: screen speed tests with the compositor on and off, then a recording
of Blocks turning and looking around builds of several sizes, then of the animations (a hold, a
Music key change, Art's pen and fade, a family room) drawn as kids get them and with partial
redraws, each on a copy of the room so the kid's own is never touched, then everything is copied
to a USB drive. guides/admin-menu.md"""

import asyncio
import json
import statistics
import time
from contextlib import asynccontextmanager

from .. import boot_log, perf_trace
from ..constants import HOLD_OR_TAP_THRESHOLD
from ..palette import KEY_COLORS
from ..ui import Overlay, draw_label
from .art_room import COLS, LINE_FADE_S, ROWS
from .blocks_view import DEPTH, HEIGHT, WIDTH
from .music_room import FRIENDLY_KEYS, PITCH_TRANSITION_DURATION

BUILDS = (100, 400, 850)    # blocks
KEY_REPEAT_S = 1 / 30       # a held arrow's repeats, as the kernel sends them
FAMILY_S = 5                # seconds a family room runs, each way
SUMMARY = "autorun.txt"


def city(n: int) -> dict:
    """A Blocks timeline state of n blocks: towers of mixed heights, standing from the middle out."""
    cells = sorted(((x, z) for x in range(WIDTH) for z in range(DEPTH)),
                   key=lambda c: (abs(c[0] - WIDTH / 2 + 0.5) + abs(c[1] - DEPTH / 2 + 0.5), c))
    colors = list(KEY_COLORS.values())
    spots = [(x, z, y) for x, z in cells for y in range(HEIGHT) if y < 2 + (x * 7 + z * 13) % (HEIGHT - 2)]
    return {"floor": [WIDTH, DEPTH]} | {f"b:{x},{z},{y}": colors[(x + z + y) % len(colors)] for x, z, y in spots[:n]}


def painting(rows: int = 4) -> dict:
    """An Art timeline state of `rows` lines painted across, the cursor at the end of the last."""
    colors = list(KEY_COLORS.values())
    return {f"c:{x},{y}": [" ", colors[(x + y) % len(colors)], colors[(x + y) % len(colors)], 1]
            for x in range(COLS) for y in range(rows)} | {"cursor": [COLS - 1, rows - 1], "paint": True, "grid": [COLS, ROWS]}


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


async def _enter_hold(room):
    for _ in range(2):
        room.enter_hold.down()
        await asyncio.sleep(HOLD_OR_TAP_THRESHOLD + 0.3)
        room.enter_hold.up()
        await asyncio.sleep(0.5)


async def _key_changes(room):
    for _ in range(4):
        room.set_key((room.root_index + 1) % len(FRIENDLY_KEYS))
        await asyncio.sleep(PITCH_TRANSITION_DURATION + 0.4)


async def _pen_and_fade(room):
    for down in (True, False, True, False):
        room._set_pen(down)
        await asyncio.sleep(0.5)
    room._fade_next_line()
    await asyncio.sleep(LINE_FADE_S + 0.5)


# name: (room, its timeline state, what to do in it)
ANIMATIONS = {"hold": ("blocks", city(100), _enter_hold), "music key": ("music", {}, _key_changes),
              "art pen and fade": ("art", painting(), _pen_and_fade)}


def _fps(frames):    # from the typical gap, not the span: the pauses between moves draw nothing
    return 1000 / max(1e-3, statistics.median(f["gap"] for f in frames if f.get("gap") is not None))


def _med(key, frames):
    return round(statistics.median(f[key] for f in frames), 1)


def summarize(path) -> list:
    """A line per build: frames a second while each move goes, and its frames' median draw and present. Then
    a line per animation: its frames' median draw and present, as kids get them and with partial redraws."""
    builds, anims = {}, {}
    for rec in map(json.loads, path.read_text().splitlines()):
        if rec.get("step") in MOVES and "blocks" in rec:
            builds.setdefault(rec["blocks"], {}).setdefault(rec["step"], []).append(rec)
        elif "step" in rec and "partial" in rec:
            anims.setdefault(rec["step"], {}).setdefault(rec["partial"], []).append(rec)
    lines = [f"{n} blocks: " + ", ".join(f"{step} {_fps(fr):.1f}" for step, fr in steps.items()) +
             f" fps (draw {_med('draw', sum(steps.values(), [])):.0f}, present {_med('present', sum(steps.values(), [])):.0f} ms)"
             for n, steps in builds.items()]
    return lines + [f"{name}: " + ", ".join(f"{'partial' if on else 'whole'} {_med('draw', fr)} + {_med('present', fr)} ms"
                                             for on, fr in sorted(ways.items())) for name, ways in anims.items()]


class AutoRun(Overlay):
    """Over the screen while the run goes: says what it's doing, between the parts it times. Escape stops it."""

    scrim = False

    def __init__(self, app):
        super().__init__(app)
        self.status = "starting"
        self.task = None

    @property
    def covers_room(self):
        return bool(self.status)

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
            await self._animations()
            perf_trace.stop()
            lines += summarize(perf_trace.FRAMES)
        except asyncio.CancelledError:
            lines.append("Stopped.")
        except Exception as e:     # whatever got done still goes to the drive
            lines.append(f"Failed: {e!r}")
        finally:
            perf_trace.stop()
            self.app.partial_redraws = False
            if compositor_on() != compositor:
                toggle_compositor()
            perf_trace.DIR.mkdir(parents=True, exist_ok=True)
            (perf_trace.DIR / SUMMARY).write_text("\n".join(lines) + "\n")
            boot_log.heartbeat(f"admin: run all tests {lines}")
            self.close()
        self.app.push(LogExportScreen(self.app, lines))

    async def _blocks(self, n):
        await self._say(f"building {n} blocks")
        async with self._room("blocks", city(n)) as room:
            await self._say("")
            for name, move in MOVES.items():
                perf_trace.step(step=name)
                await move(room)
            perf_trace.step()

    async def _animations(self):
        """Each animation as kids get it, then with partial redraws."""
        from ..room_picker import family_rooms
        for name, (room_name, state, play) in ANIMATIONS.items():
            await self._say(name)
            async with self._room(room_name, state) as room:
                await self._say("")
                for partial in (False, True):
                    self.app.partial_redraws = partial
                    perf_trace.step(step=name, partial=partial)
                    await play(room)
                    perf_trace.step()
        for family in family_rooms()[:1]:
            await self._say(f"family room {family.title}")
            for partial in (False, True):
                self.app.partial_redraws = partial
                self.app.open_family_room(family.name)
                await self._say("")
                perf_trace.step(step="family room", partial=partial)
                await asyncio.sleep(FAMILY_S)
                perf_trace.step()
                if self.app.family_room:
                    self.app.family_room.close()
        self.app.partial_redraws = False

    @asynccontextmanager
    async def _room(self, name, state):
        """A copy of the room `name` holding `state` in its place, then everything put back as it was."""
        app, real, was, panel = self.app, self.app.rooms[name], self.app.active_room, self.app._panel
        if app._time_travel is not None:
            app._cancel_time_travel()
        app._timeline_flush()
        if was != name:
            app.room.on_leave()
        room = app.rooms[name] = type(real)(app)
        room.restore_timeline_state(state)
        app.active_room, app._panel = name, None
        room.on_enter()
        try:
            yield room
        finally:
            room.on_leave()
            for timer in ("_look_timer", "_transition_timer", "_lift_timer"):
                if getattr(room, timer, None) is not None:
                    getattr(room, timer).stop()
            app._timeline_pending.pop(name, None)
            app.rooms[name], app.active_room, app._panel = real, was, panel
            app.room.on_enter()
            app.invalidate()
