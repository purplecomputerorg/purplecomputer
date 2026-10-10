"""A family room: a pack's content/rooms/<name>.py, run as a guest in its own
process (roomkit/runner.py, as the purple-room user on the ISO) and drawn by
Purple from the messages it sends. It opens over the current room, so Esc
lands the kid back where they were. Protocol and safety: guides/family-rooms.md."""

import json
import pwd
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pygame

from ... import palette as P
from ... import tts
from ...audio import play_safe
from ...keyboard import CharacterAction, ControlAction, NavigationAction
from ...music_constants import instruments, pitch_filename
from ...roomkit.purple import H, W
from ..sounds import SoundBank
from ..ui import Overlay, TextField

ICON_FAMILY = "\U000F0827"  # nf-md-home_heart
RUNNER = Path(__file__).parents[2] / "roomkit" / "runner.py"
ROOM_USER = "purple-room"
START_TIMEOUT_S = 8.0       # python3 startup on the slowest laptops, plus the room's top level
STEP_TIMEOUT_S = 3.0
MAX_MESSAGES_PER_STEP = 2000
MAX_LINE_CHARS = 4096
MAX_TIMERS = 32
BACKGROUND_MIN_GAP_S = 0.3
IDLE_PAUSE_S = 180
LINES_KEPT = 5
QUEUE_MAX = 8
_NOTE = re.compile(r"^([A-Ga-g])(#?)(\d)$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def command() -> list:
    """The ISO has a purple-room user and a sudoers rule for exactly this line; a dev machine runs the room as itself."""
    try:
        pwd.getpwnam(ROOM_USER)
    except KeyError:
        return [sys.executable, "-I", "-S", str(RUNNER)]
    return ["sudo", "-n", "-u", ROOM_USER, "/usr/bin/python3", "-I", "-S", str(RUNNER)]


def _text(msg: dict, field: str = "text") -> str:
    return str(msg.get(field, ""))[:200]


class FamilyRoom(Overlay):
    scrim = False

    def __init__(self, app, room):
        super().__init__(app)
        self.room = room
        self.sounds = SoundBank()
        self.field = TextField()
        self._proc = None
        self._timers: dict = {}
        self._watchdog = None
        self._bg_timer = None
        self._last_key = time.monotonic()
        self._resting = False
        self._reset()

    def _reset(self):
        self.bg = self._bg_wanted = P.SURFACE
        self.big, self.lines, self.cells = "", [], {}
        self.prompt = None          # set while the room waits in ask()
        self.over = None            # game_over text
        self.fault = None           # why the room was stopped
        self._busy, self._queue, self._count = True, [], 0

    # ---------------------------------------------------------------- process
    def on_open(self):
        self._start()

    def on_close(self):
        self._stop()

    def _start(self):
        self._stop()
        self._reset()
        try:
            source = self.room.path.read_text(encoding="utf-8")
            self._proc = subprocess.Popen(command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, text=True, encoding="utf-8", cwd="/",
                                          start_new_session=True)
        except (OSError, UnicodeDecodeError) as e:
            return self._broken(f"could not start: {e}")
        threading.Thread(target=self._read, args=(self._proc, source), daemon=True, name=f"room-{self.room.name}").start()
        self._arm(START_TIMEOUT_S)
        self.app.invalidate()

    def _stop(self):
        for t in [*self._timers.values(), self._watchdog, self._bg_timer]:
            if t:
                t.stop()
        self._timers.clear()
        self._watchdog = self._bg_timer = None
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            proc.kill()

    def _read(self, proc, source: str):
        """Reader thread: hands over the source (a big file can't stall the UI on a full pipe),
        then passes each message line to the UI thread."""
        self._write({"source": source}, proc)
        for line in iter(lambda: proc.stdout.readline(MAX_LINE_CHARS), ""):
            if proc is not self._proc:
                return
            try:
                msg = json.loads(line) if line.endswith("\n") else {"cmd": "error", "text": "a message was too long"}
            except ValueError:
                msg = {"cmd": "error", "text": "a message was garbled"}
            self.app.call_from_thread(self._receive, proc, msg if isinstance(msg, dict) else {})
        if proc is self._proc:
            self.app.call_from_thread(self._receive, proc, {"cmd": "exit"})

    def _write(self, msg: dict, proc=None):
        try:
            (proc or self._proc).stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            (proc or self._proc).stdin.flush()
        except (AttributeError, OSError, ValueError):
            pass

    def _arm(self, seconds: float):
        if self._watchdog:
            self._watchdog.stop()
        self._watchdog = self.app.timers.after(seconds, lambda: self._broken("it took too long to answer"))

    def _broken(self, why: str, line=None):
        self._stop()
        self.fault = f"{why} (line {line})" if isinstance(line, int) else why
        self.prompt = None
        self.app.invalidate()

    # ---------------------------------------------------------------- events in
    def _send(self, event: dict):
        if self._proc is None:
            return
        if self._busy or self.prompt is not None:
            if event["ev"] == "key" and len(self._queue) < QUEUE_MAX:
                self._queue.append(event)
            return
        self._busy, self._count = True, 0
        self._arm(STEP_TIMEOUT_S)
        self._write(event)

    def _tick(self, n: int):
        covered = self.app.top is not self
        idle = time.monotonic() - self._last_key > IDLE_PAUSE_S
        if idle and not self._resting:
            self._resting = True
            self.app.invalidate()
        if not (covered or idle or self._busy or self.prompt is not None):
            self._send({"ev": "tick", "id": n})

    # ---------------------------------------------------------------- messages out
    def _receive(self, proc, msg: dict):
        if proc is not self._proc:
            return
        self._count += 1
        if self._count > MAX_MESSAGES_PER_STEP:
            return self._broken("it sent too many messages at once")
        handler = self._HANDLERS.get(msg.get("cmd"))
        if handler:
            handler(self, msg)
            self.app.invalidate()

    def _on_show(self, msg):
        self.big = _text(msg)

    def _on_write(self, msg):
        self.lines = (self.lines + [_text(msg)])[-LINES_KEPT:]

    def _on_clear(self, msg):
        self.big, self.lines, self.cells = "", [], {}

    def _on_background(self, msg):
        if isinstance(msg.get("color"), str) and _HEX.match(msg["color"]):
            self._bg_wanted = msg["color"]
            if self._bg_timer is None:
                self._apply_background()

    def _apply_background(self):
        """At most one color change per BACKGROUND_MIN_GAP_S, so no room can strobe."""
        self._bg_timer = None
        if self._bg_wanted != self.bg:
            self.bg = self._bg_wanted
            self._bg_timer = self.app.timers.after(BACKGROUND_MIN_GAP_S, self._apply_background)
            self.app.invalidate()

    def _audible(self) -> bool:
        return self.app._effective_volume() > 0

    def _on_say(self, msg):
        if self._audible():
            tts.speak(_text(msg))

    def _on_play(self, msg):
        m = _NOTE.match(str(msg.get("note", "")))
        wanted = str(msg.get("instrument", "")).lower()
        inst = next((i for i, n in instruments() if wanted in (i.lower(), n.lower())), instruments()[0][0])
        sound = m and self.sounds.instrument(inst).get(pitch_filename(m[1].upper() + m[2], int(m[3])))
        if sound and self._audible():
            play_safe(sound)

    def _on_drum(self, msg):
        sound = self.sounds.drum(str(msg.get("name", "")))
        if sound and self._audible():
            play_safe(sound)

    def _on_cell(self, msg):
        x, y, thing = msg.get("x"), msg.get("y"), msg.get("thing")
        if isinstance(x, int) and isinstance(y, int) and 0 <= x < W and 0 <= y < H:
            if thing is None:
                self.cells.pop((x, y), None)
            else:
                self.cells[(x, y)] = str(thing)[:8]

    def _on_grid_clear(self, msg):
        self.cells = {}

    def _on_timer(self, msg):
        n, seconds = msg.get("id"), msg.get("seconds")
        if not isinstance(n, int) or not isinstance(seconds, (int, float)) or len(self._timers) >= MAX_TIMERS:
            return
        self._on_stop(msg)
        start = self.app.timers.after if msg["cmd"] == "after" else self.app.timers.every
        self._timers[n] = start(min(max(0.1, seconds), 3600), lambda: self._tick(n))

    def _on_stop(self, msg):
        if t := self._timers.pop(msg.get("id"), None):
            t.stop()

    def _on_ask(self, msg):
        self.prompt = _text(msg, "prompt")
        self.field.clear()
        self._busy = False
        if self._watchdog:
            self._watchdog.stop()

    def _on_game_over(self, msg):
        self._stop()
        self.over = _text(msg) or "Press a key to play again"

    def _on_done(self, msg):
        self._busy = False
        if self._watchdog:
            self._watchdog.stop()
        if self._queue:
            self._send(self._queue.pop(0))

    def _on_error(self, msg):
        self._broken(_text(msg), msg.get("line"))

    def _on_exit(self, msg):
        if self.over is None and self.fault is None:
            self._broken("it stopped")

    _HANDLERS = {"show": _on_show, "write": _on_write, "clear": _on_clear, "background": _on_background,
                 "say": _on_say, "play": _on_play, "drum": _on_drum, "cell": _on_cell, "grid_clear": _on_grid_clear,
                 "every": _on_timer, "after": _on_timer, "stop": _on_stop, "ask": _on_ask,
                 "game_over": _on_game_over, "done": _on_done, "error": _on_error, "exit": _on_exit}

    # ---------------------------------------------------------------- keys
    @staticmethod
    def _key_name(action):
        if getattr(action, "is_repeat", False):
            return None
        if isinstance(action, CharacterAction) and len(action.char) == 1:
            return action.char.lower()
        if isinstance(action, NavigationAction):
            return action.direction
        if isinstance(action, ControlAction) and action.is_down and action.action in ("space", "enter", "backspace"):
            return action.action
        return None

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.action == "escape":
            if not action.is_down:
                self.close()  # on release, so a hold still reaches the parent menu
            return
        key = self._key_name(action)
        if key is None or self.fault:
            return
        self._last_key = time.monotonic()
        self._resting = False
        if self.over is not None:
            return self._start()
        if self.prompt is not None:
            return self._type(action, key)
        self._send({"ev": "key", "key": key})

    def _type(self, action, key: str):
        if key == "enter":
            text, self.prompt = self.field.value, None
            self._busy, self._count = True, 0
            self._arm(STEP_TIMEOUT_S)
            self._write({"ev": "answer", "text": text[:200]})
        elif key == "backspace":
            self.field.backspace()
        elif key == "space":
            self.field.insert(" ")
        elif isinstance(action, CharacterAction):
            self.field.insert(action.char)
        self.app.invalidate()

    # ---------------------------------------------------------------- drawing
    def draw(self, g):
        app = self.app
        g.fill(P.BG)
        vp = app._viewport_rect()
        frame = app._frame_rect(vp)
        app._draw_title(frame, f"{ICON_FAMILY} {self.room.title}")
        g.rect(self.bg, frame, radius=g.em(0.6))
        g.rect(P.LINE, frame, width=1, radius=g.em(0.6))
        g.surface.set_clip(frame.inflate(-4, -4))
        if self.fault:
            self._draw_fault(g, vp)
        else:
            (self._draw_grid if self.cells else self._draw_words)(g, vp)
            self._draw_footer(g, vp)
        g.surface.set_clip(None)
        app._draw_status(frame, right="Esc leaves", tabs=False)

    def _draw_grid(self, g, vp):
        cell = min(vp.w // W, vp.h // H)
        ox, oy = vp.centerx - cell * W // 2, vp.centery - cell * H // 2
        for (x, y), thing in self.cells.items():
            r = pygame.Rect(ox + x * cell, oy + y * cell, cell, cell)
            if _HEX.match(thing):
                g.rect(thing, r.inflate(-2, -2), radius=max(2, cell // 8))
            else:
                g.draw_text(thing, int(cell * 0.78), r.centerx, r.centery, "sans", P.TEXT, anchor="center")

    def _draw_words(self, g, vp):
        y = vp.y + vp.h * 0.36
        if self.big:
            px = int(vp.h * 0.24)
            while px > 16 and g.measure(self.big, px)[0] > vp.w * 0.9:
                px = int(px * 0.85)
            g.draw_text(self.big, px, vp.centerx, y, "sans", P.TEXT, anchor="center")
        px = int(vp.h * 0.055)
        for i, line in enumerate(self.lines):
            g.draw_text(line, px, vp.centerx, vp.y + vp.h * 0.6 + i * px * 1.35, "sans", P.TEXT, anchor="midtop")

    def _draw_footer(self, g, vp):
        px = int(vp.h * 0.05)
        y = vp.bottom - px * 2.2
        if self.prompt is not None:
            if self.prompt:
                g.draw_text(self.prompt, px, vp.x + px, y - px * 1.5, "sans", P.MUTED, anchor="topleft")
            self.field.draw(g, vp.x + px, y, vp.w - 2 * px, px, label="Answer")
        elif self.over is not None:
            g.draw_text(self.over, px, vp.centerx, y, "mono-bold", P.ACCENT, anchor="midtop")
        elif self._resting:
            g.draw_text("Resting. Press a key to keep going", px, vp.centerx, y, "mono", P.MUTED, anchor="midtop")

    def _draw_fault(self, g, vp):
        px = int(vp.h * 0.06)
        g.draw_text("This room needs fixing", int(px * 1.4), vp.centerx, vp.centery - px * 2, "mono-bold", P.TEXT, anchor="center")
        g.draw_text("A grown-up can fix it in Purple Studio.  Esc goes back.", px, vp.centerx, vp.centery,
                    "sans", P.MUTED, anchor="center")
        g.draw_text(f"(Technical: {self.fault})", int(px * 0.7), vp.centerx, vp.centery + px * 1.8,
                    "mono", P.DIM, anchor="center")
