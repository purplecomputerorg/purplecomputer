"""A family room: a pack's content/rooms/<name>.py, run as a guest in a sealed
process of its own and drawn by Purple from its replies. Purple sends one event
at a time (start, key, tick) and the room answers each with one reply: the
whole scene as shapes, sounds, when to tick next, and what to remember. All
the room ideas (text, the grid, ask, timers) live in the guest library,
roomkit/purple.py, which the pack carries, so this side never needs to grow.
It opens over the built-in room, which waits as it was; Esc opens the room picker, as in any room.
Protocol and safety: guides/family-rooms.md."""

import json
import math
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
from ...content import png_size
from ...keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction
from ...music_constants import instruments, pitch_filename
from ...timeline import state_dir
from ...roomkit.limits import (KEEP_MAX_BYTES, MAX_REPLY_CHARS, MAX_SHAPES, MAX_SOUNDS, MAX_WAKE_S, MIN_WAKE_S,
                               START_TIMEOUT_S, STEP_TIMEOUT_S, sealed)
from ..gfx import is_one_emoji
from ..sounds import SoundBank
from ..theme import ROLES
from ..ui import KEY_RE, KID_MATH_KEYS, Overlay, auto_ink, draw_key, keycap_size

ICON_FAMILY = "\U000F0827"  # nf-md-home_heart
API = 3                     # 3: a text's how.keys draws {Key} as a keycap
SIZE = (240, 120)           # the room's surface; the viewport is 2:1 on every machine
RUNNER = Path(__file__).parents[2] / "roomkit" / "runner.py"
BUILTIN_LIB = RUNNER.parent / "purple.py"
MAX_PIXELS = 64             # an inline picture's rows, and characters per row
PICTURE_CACHE = 512
TEXT_MAX = 200
FAULT_SHOWN = 400           # characters of a fault the card shows, so it fits the frame
PAUSED_RECHECK_S = 0.5
IDLE_PAUSE_S = 180
READY_HINT_S = 0.3        # a room still silent this long shows it's coming, so a fast one never flashes it
QUEUE_MAX = 8
# Flashes: the scene shrunk to these tiles; a change that moves at least FLASH_AREA of them by
# FLASH_DELTA in luminance shows at most once per FLASH_GAP_S (WCAG 2.3.1's three per second).
FLASH_TILES = (16, 8)
FLASH_DELTA = 0.1
FLASH_AREA = 0.25
FLASH_GAP_S = 1 / 3
# A text shape's anchor: which point of its block sits at (x, y), as a pygame.Rect attribute.
ANCHORS = {"center": "center", "left": "midleft", "right": "midright", "top": "midtop", "bottom": "midbottom",
           "topleft": "topleft", "topright": "topright", "bottomleft": "bottomleft", "bottomright": "bottomright"}
_NOTE = re.compile(r"^([A-Ga-g])(#?)(\d)$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ram_keeps: dict = {}


def room_icon(room) -> str:
    """The room's own emoji, or the family glyph when it has none."""
    return room.icon if is_one_emoji(room.icon) else ICON_FAMILY


def command() -> list:
    """The ISO seals the room with purple-room-run; a dev machine runs it as itself."""
    return sealed() or [sys.executable, "-I", "-S", str(RUNNER)]


class ProcessGuest:
    """The room's process. Writes the start line, then hands each reply line to on_line on its
    reader thread, and None when the process ends."""

    def __init__(self, start: str, on_line):
        self._stopped = False
        self._proc = subprocess.Popen(command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, encoding="utf-8", cwd="/",
                                      start_new_session=True)
        threading.Thread(target=self._read, args=(start, on_line), daemon=True, name="family-room").start()

    def _read(self, start, on_line):
        self.send(start)  # here, so a big room can't stall the screen on a full pipe
        for line in iter(lambda: self._proc.stdout.readline(MAX_REPLY_CHARS), ""):
            if self._stopped:
                return
            on_line(line)
        if not self._stopped:
            on_line(None)

    def send(self, line: str):
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def stop(self):
        """Closing stdin is what ends a sealed room (runner._watch); the kill covers the rest."""
        self._stopped = True
        try:
            self._proc.stdin.close()
        except (OSError, ValueError):
            pass
        if self._proc.poll() is None:
            self._proc.kill()


Guest = ProcessGuest  # Studio swaps in its Web Worker (studio/src/live/browser.py)


def _keep_path(room) -> Path | None:
    base = state_dir("rooms", "PURPLE_ROOMS_DIR")
    return base / room.pack / f"{room.name}.json" if base else None


def load_keep(room) -> dict:
    path = _keep_path(room)
    try:
        data = json.loads(path.read_text()) if path else _ram_keeps.get(room.key, {})
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save_keep(room, keep: dict):
    path = _keep_path(room)
    if path is None:
        _ram_keeps[room.key] = keep
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(keep))
        tmp.replace(path)
    except OSError:
        pass


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _color(v) -> str | None:
    return v if isinstance(v, str) and (_HEX.match(v) or v in ROLES) else None


def _pixels(src) -> tuple | None:
    """{"rows": ["..X.", ...], "palette": {"X": color}}: a character not in the palette is see-through."""
    rows, palette = src.get("rows"), src.get("palette")
    if not (isinstance(rows, list) and 0 < len(rows) <= MAX_PIXELS and isinstance(palette, dict)):
        return None
    if not all(isinstance(r, str) and len(r) <= MAX_PIXELS for r in rows):
        return None
    if not all(isinstance(c, str) and len(c) == 1 and _color(v) for c, v in palette.items()):
        return None
    return ("pixels", tuple(rows), tuple(sorted(palette.items())))


def _picture_source(src, images) -> str | tuple | None:
    if isinstance(src, str):
        return src if src in images else None
    return _pixels(src) if isinstance(src, dict) else None


def _size_or_0(v) -> float:
    return float(v) if _num(v) and v > 0 else 0.0


def _text_shape(a) -> tuple:
    """("text", x, y, size, text, color, anchor, width, height, box, pad, radius, keys): see guides/family-rooms.md."""
    how = a[5] if len(a) > 5 and isinstance(a[5], dict) else {}
    return ("text", *map(float, a[:3]), str(a[3])[:TEXT_MAX], (_color(a[4]) if len(a) > 4 else None) or "text",
            how.get("anchor") if how.get("anchor") in ANCHORS else "center",
            *(_size_or_0(how.get(k)) for k in ("width", "height")), _color(how.get("box")),
            *(_size_or_0(how.get(k)) for k in ("pad", "radius")), how.get("keys") is True)


def _shape(s, images=()) -> tuple | None:
    """A shape from a reply, checked; None for anything malformed or unknown, which is skipped."""
    if not isinstance(s, list) or not s:
        return None
    kind, a = s[0], s[1:]
    if kind == "image" and len(a) >= 5 and all(map(_num, a[:4])) and (src := _picture_source(a[4], images)):
        return ("image", *map(float, a[:4]), src)
    if kind == "rect" and len(a) >= 5 and all(map(_num, a[:4])) and _color(a[4]):
        return ("rect", *map(float, a[:4]), a[4], *(_size_or_0(a[i]) if len(a) > i else 0.0 for i in (5, 6)))
    if kind == "text" and len(a) >= 4 and all(map(_num, a[:3])):
        return _text_shape(a)
    return None


def _paint(color: str) -> str:
    return getattr(P, color.upper()) if color in ROLES else color


def _luminance(c) -> float:
    lin = [(v / 255 / 12.92) if v <= 10 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c[:3]]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _thumb(surface) -> list:
    small = pygame.transform.smoothscale(surface, FLASH_TILES)
    return [_luminance(small.get_at((x, y))) for y in range(FLASH_TILES[1]) for x in range(FLASH_TILES[0])]


def _flashes(a: list, b: list) -> bool:
    return sum(abs(x - y) > FLASH_DELTA for x, y in zip(a, b)) >= FLASH_AREA * len(a)


class FamilyRoom(Overlay):
    scrim = False

    def __init__(self, app, room):
        super().__init__(app)
        self.room = room
        self.sounds = SoundBank()
        self._guest = self._token = None
        self._wake = self._watchdog = self._flash_timer = self._hint = None
        self._keep, self._keep_dirty = load_keep(room), False
        self._images, self._clips = {}, {}
        self._pictures: dict = {}    # source -> its picture, decoded once
        self._scaled: dict = {}      # (source, size) -> the picture at that size
        self._last_key = time.monotonic()
        self._resting = False
        self._saying = None          # the say()s still being spoken
        self._reset()

    def _reset(self):
        self.scene: list = []        # what's on screen, as checked shapes
        self.fault = None            # why the room was stopped
        self._why_shown = False
        self._surface = self._thumb = self._pending = None
        self._last_flash = -math.inf
        self._busy, self._queue = True, []
        self._held: set = set()      # keys the room was told went down and not yet up
        self._t0, self._paused, self._paused_at = time.monotonic(), 0.0, None

    @property
    def tab(self) -> str:
        from ..room_picker import short_title
        return f"{room_icon(self.room)} {short_title(self.room.title)}"

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
            lib = (self.room.lib or BUILTIN_LIB).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return self._broken(f"could not read it: {e}")
        self._images = {n: (p, size) for n, p in self.room.images.items() if (size := png_size(p))}
        self._clips = self.room.sounds
        start = {"ev": "start", "t": 0, "api": API, "size": list(SIZE), "keep": self._keep, "lib": lib, "source": source,
                 "images": {n: list(size) for n, (_, size) in self._images.items()}, "sounds": sorted(self._clips)}
        token = self._token = object()
        try:
            self._guest = Guest(json.dumps(start, ensure_ascii=False),
                                lambda line: self.app.call_from_thread(self._reply, token, line))
        except OSError as e:
            return self._broken(f"could not start: {e}")
        self._arm(START_TIMEOUT_S)
        self._hint = self.app.timers.after(READY_HINT_S, self.app.invalidate)
        self.app.invalidate()

    def _stop(self):
        for t in (self._wake, self._watchdog, self._flash_timer, self._hint):
            if t:
                t.stop()
        self._wake = self._watchdog = self._flash_timer = self._hint = None
        guest, self._guest, self._token = self._guest, None, None
        if guest:
            guest.stop()
        if self._keep_dirty:
            save_keep(self.room, self._keep)
            self._keep_dirty = False

    def _arm(self, seconds: float):
        if self._watchdog:
            self._watchdog.stop()
        self._watchdog = self.app.timers.after(seconds, lambda: self._broken("it took too long to answer"))

    def _broken(self, why: str, line=None):
        self._stop()
        self.fault = f"{why} (line {line})" if isinstance(line, int) else why
        self.app.invalidate()

    # ---------------------------------------------------------------- events in
    def _clock(self) -> float:
        return time.monotonic() - self._t0 - self._paused

    def _send(self, event: dict) -> bool:
        """False when the event was dropped. A keyup is never dropped, or the room would think its key still down."""
        if self._guest is None:
            return False
        if self._busy:
            if event["ev"] == "keyup" or (event["ev"] == "key" and sum(e["ev"] == "key" for e in self._queue) < QUEUE_MAX):
                self._queue.append(event)
                return True
            return False
        if self._paused_at is not None:
            self._paused += time.monotonic() - self._paused_at
            self._paused_at = None
        self._busy = True
        self._arm(STEP_TIMEOUT_S)
        self._guest.send(json.dumps({**event, "t": round(self._clock(), 3)}, ensure_ascii=False))
        return True

    def _tick(self):
        """The room's wake time came. Its clock stops while a menu covers it or the kid has
        stepped away; it looks again shortly, without drawing anything."""
        self._wake = None
        idle = time.monotonic() - self._last_key > IDLE_PAUSE_S
        if idle and not self._resting:
            self._resting = True
            self.app.invalidate()
        if idle or self.app.top is not self:
            self._release_all()  # its releases went to whatever covers it
            if self._paused_at is None:
                self._paused_at = time.monotonic()
            self._wake = self.app.timers.after(PAUSED_RECHECK_S, self._tick)
            return
        self._send({"ev": "tick"})

    # ---------------------------------------------------------------- replies
    def _reply(self, token, line):
        if token is not self._token:
            return
        if line is None:
            return self._broken("it stopped")
        if not self._busy:
            return self._broken("it spoke out of turn")
        if not line.endswith("\n"):
            return self._broken("its reply was too long")
        try:
            reply = json.loads(line)
        except ValueError:
            reply = None
        if not isinstance(reply, dict):
            return self._broken("its reply was garbled")
        if isinstance(reply.get("error"), dict):
            return self._broken(str(reply["error"].get("text", ""))[:300], reply["error"].get("line"))
        problem = self._apply(reply)
        if problem:
            return self._broken(problem)
        self._busy = False
        self._watchdog.stop()
        if self._hint:
            self._hint.stop()
            self._hint = None
        if self._queue:
            self._send(self._queue.pop(0))

    def _apply(self, reply: dict) -> str | None:
        """Unknown fields, shapes, and sounds are skipped, so a newer library still runs here."""
        scene = reply.get("scene")
        if "scene" in reply and (not isinstance(scene, list) or len(scene) > MAX_SHAPES):
            return "it drew too much at once"
        sounds = reply.get("sounds")
        self._play(sounds[:MAX_SOUNDS] if isinstance(sounds, list) else [])  # before drawing, so a note isn't late by a render
        if "scene" in reply:
            self._show([s for s in (_shape(s, self._images) for s in scene) if s])
        if "keep" in reply:
            keep = reply["keep"]
            if not isinstance(keep, dict) or len(json.dumps(keep).encode()) > KEEP_MAX_BYTES:
                return "it tried to remember too much"
            self._keep, self._keep_dirty = keep, True
        if self._wake:
            self._wake.stop()
            self._wake = None
        if _num(reply.get("wake")):
            self._wake = self.app.timers.after(min(max(MIN_WAKE_S, reply["wake"]), MAX_WAKE_S), self._tick)
        return None

    def _show(self, scene: list):
        if scene == (self._pending if self._pending is not None else self.scene):
            return
        self._pending = scene
        if self._flash_timer is None:
            self._present()

    def _present(self):
        """Puts the newest scene up, unless it would make a fourth flash this second; then it
        waits, and whatever is newest by then goes up."""
        self._flash_timer = None
        scene, self._pending = self._pending, None
        if scene is None:
            return
        surface = self._render(scene, self.app._viewport_rect().size)
        thumb = _thumb(surface)
        if self._thumb is not None and _flashes(self._thumb, thumb):
            wait = self._last_flash + FLASH_GAP_S - time.monotonic()
            if wait > 0:
                self._pending = scene
                self._flash_timer = self.app.timers.after(wait, self._present)
                return
            self._last_flash = time.monotonic()
        self.scene, self._surface, self._thumb = scene, surface, thumb
        self.app.invalidate()

    def _render(self, scene: list, size) -> pygame.Surface:
        """The scene drawn once, at the viewport's size; every frame after just copies it."""
        surface = pygame.Surface(size, depth=32)
        surface.fill(P.SURFACE)
        k = size[0] / SIZE[0]
        for kind, x, y, *rest in scene:
            if kind == "image":
                w, h, src = rest
                if img := self._picture(src, (max(1, round(w * k)), max(1, round(h * k)))):
                    surface.blit(img, (round(x * k), round(y * k)))
                continue
            if kind == "rect":
                w, h, color, radius, line = rest
                box = pygame.Rect(round(x * k), round(y * k), max(1, round(w * k)), max(1, round(h * k)))
                pygame.draw.rect(surface, _paint(color), box, max(0, round(line * k)) if line else 0,
                                 border_radius=max(0, round(radius * k)))
                continue
            self._text(surface, k, x * k, y * k, *rest)
        return surface

    def _text(self, surface, k, x, y, px, text, color, anchor, width, height, box, pad, radius, keys):
        side = ANCHORS[anchor]
        sw = surface.get_width()
        fits = sw - x if "left" in side else x if "right" in side else 2 * min(x, sw - x)
        keys = keys and bool(KEY_RE.search(text))
        if keys:    # a line with keycaps doesn't wrap; it shrinks into its width
            fits, width = min(fits, width * k or fits), 0
        lines = self._fit(text, max(6, round(px * k)), _paint(color), width * k, height * k, fits, keys)
        block = pygame.Rect(0, 0, max(w for w, _, _ in lines), sum(h for _, h, _ in lines))
        setattr(block, side, (round(x), round(y)))
        if box:
            pygame.draw.rect(surface, _paint(box), block.inflate(2 * pad * k, 2 * pad * k), border_radius=round(radius * k))
        top = block.y
        for w, h, pieces in lines:
            left = block.x + (0 if "left" in side else block.w - w if "right" in side else (block.w - w) // 2)
            for img, at, _ in pieces:
                surface.blit(img, (left + at, top + (h - img.get_height()) // 2))
            top += h

    def _lines(self, text, px, color, width, keys) -> list:
        """Gfx.layout's lines; a grid square's one short line skips layout, which costs three times as much."""
        g = self.app.g
        if keys:
            return self._keyed(text, px, color)
        if width or "\n" in text:
            return g.layout(text.replace("[", "\\["), px, "mono", color, max_width=width or None)
        img = g.text(text, px, "mono", color)
        return [(img.get_width(), img.get_height(), [(img, 0, None)])]

    def _keyed(self, text, px, color) -> list:
        """One line where {Key} is a keycap, as in Purple's own hints."""
        g, pieces, x = self.app.g, [], 0
        for i, part in enumerate(KEY_RE.split(text)):
            if part:
                img = self._keycap(part, px, color) if i % 2 else g.text(part, px, "mono", color)
                pieces.append((img, x, None))
                x += img.get_width()
        return [(x, max(img.get_height() for img, _, _ in pieces), pieces)]

    def _keycap(self, name, px, color) -> pygame.Surface:
        g = self.app.g
        cap = pygame.Surface(keycap_size(g, name, px), pygame.SRCALPHA)
        with g.drawing_on(cap):
            draw_key(g, name, px, 0, cap.get_height() // 2, fill=color, ink=auto_ink(color))
        return cap

    def _fit(self, text, px, color, width, height, fits, keys) -> list:
        """Lines at the biggest size up to px that fit: wrapped at width when there is one, else one
        line no wider than fits, and no taller than height when there is one."""
        while True:
            lines = self._lines(text, px, color, width, keys)
            w, h = max(w for w, _, _ in lines), sum(h for _, h, _ in lines)
            scale = min(1 if width or w <= fits or fits <= 0 else fits / w, h and height / h if height and h > height else 1)
            if scale >= 1 or px <= 6:
                return lines
            px = max(6, min(px - 1, int(px * (scale ** 0.5 if width else scale))))

    def _picture(self, src, size) -> pygame.Surface | None:
        """A pack image or inline pixels at a size: blocky when blown up at least twice, smooth otherwise."""
        if len(self._scaled) > PICTURE_CACHE:
            self._pictures.clear()
            self._scaled.clear()
        if (src, size) in self._scaled:
            return self._scaled[(src, size)]
        if src not in self._pictures:
            self._pictures[src] = self._decode(src)
        img = self._pictures[src]
        if img is not None:
            blocky = size[0] >= 2 * img.get_width() and size[1] >= 2 * img.get_height()
            img = (pygame.transform.scale if blocky else pygame.transform.smoothscale)(img, size)
        self._scaled[(src, size)] = img
        return img

    def _decode(self, src) -> pygame.Surface | None:
        if isinstance(src, str):
            try:
                loaded = pygame.image.load(str(self._images[src][0]))
            except (pygame.error, OSError):
                return None
            img = pygame.Surface(loaded.get_size(), pygame.SRCALPHA)
            img.blit(loaded, (0, 0))
            return img
        _, rows, palette = src
        colors = {c: pygame.Color(_paint(v)) for c, v in palette}
        img = pygame.Surface((max(map(len, rows)) or 1, len(rows)), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c in colors:
                    img.set_at((x, y), colors[c])
        return img

    def _audible(self) -> bool:
        return self.app._effective_volume() > 0

    def _play(self, sounds: list):
        """One reply's sounds; its say()s are spoken one after another, and cut off what's still being said."""
        sounds = [[str(a)[:TEXT_MAX] for a in s] for s in sounds if isinstance(s, list) and len(s) > 1]
        if not sounds or not self._audible():
            return
        if says := [s[1] for s in sounds if s[0] == "say"]:
            self._say(says)
        for s in sounds:
            self._sound(*s)

    def _say(self, says: list):
        """Cuts off what's still being said, unless it's these same words: a key pressed again
        mid-line would restart it and stutter."""
        if says == self._saying:
            return
        self._saying = says

        def done():
            if self._saying is says:
                self._saying = None
        if not tts.speak_many(says, gap=0.3, on_done=done, room_voice=self.room.voice):
            done()

    def _sound(self, kind, *args):
        if kind == "note" and (m := _NOTE.match(args[0])):
            wanted = args[1].lower() if len(args) > 1 else ""
            inst = next((i for i, n in instruments() if wanted in (i.lower(), n.lower())), instruments()[0][0])
            if clip := self.sounds.instrument(inst).get(pitch_filename(m[1].upper() + m[2], int(m[3]))):
                play_safe(clip)
        elif kind == "drum" and (clip := self.sounds.drum(args[0])):
            play_safe(clip)
        elif kind == "clip" and args[0] in self._clips and (clip := self.sounds.file(self._clips[args[0]])):
            play_safe(clip)

    # ---------------------------------------------------------------- keys
    @staticmethod
    def _key_event(action) -> dict | None:
        """`key` names the key itself (1 for !), so its keyup matches; `char` is what was typed."""
        if getattr(action, "is_repeat", False):
            return None
        if isinstance(action, CharacterAction) and len(action.char) == 1:
            key = KID_MATH_KEYS.get(action.char, action.char)
            return {"ev": "key", "key": UNSHIFT_MAP.get(key, key), "char": action.char}
        if isinstance(action, NavigationAction):
            return {"ev": "key", "key": action.direction}
        if isinstance(action, ControlAction) and action.is_down and action.action in ("space", "enter", "backspace"):
            return {"ev": "key", "key": action.action}
        return None

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.action == "escape":
            if not action.is_down and self.app._escape_pressed_on is self:
                self.app._show_room_picker()  # on release, so a hold still reaches the parent menu; not a press that closed one
            return
        if isinstance(action, ControlAction) and not action.is_down:
            return self.released(action.action)
        if self.fault:
            return self._toggle_why(action)
        event = self._key_event(action)
        if event is None:
            return
        self._last_key = time.monotonic()
        if self._resting:
            self._resting = False
            self.app.invalidate()
        if self._send(event):
            self._held.add(event["key"])

    def _toggle_why(self, action):
        if isinstance(action, ControlAction) and action.action == "enter":
            self._why_shown = not self._why_shown
            self.app.invalidate()

    def released(self, key: str):
        if key in self._held:
            self._held.discard(key)
            self._send({"ev": "keyup", "key": key})

    def _release_all(self):
        for key in list(self._held):
            self.released(key)

    # ---------------------------------------------------------------- drawing
    def draw(self, g):
        app = self.app
        g.fill(P.BG)
        vp = app._viewport_rect()
        frame = app._frame_rect(vp)
        app._draw_title(frame, f"{room_icon(self.room)} {self.room.title}")
        g.rect(P.SURFACE, frame, radius=g.em(0.6))
        g.rect(P.LINE, frame, width=1, radius=g.em(0.6))
        if self.fault:
            self._draw_fault(g, vp)
        elif self.scene:
            if self._surface is None or self._surface.get_size() != vp.size:
                self._surface = self._render(self.scene, vp.size)
            g.surface.blit(self._surface, vp.topleft)
        elif self._hint and not self._hint.active:
            g.draw_text("Getting ready...", int(vp.h * 0.06), vp.centerx, vp.centery, "mono", P.MUTED, anchor="center")
        if self._resting and not self.fault:
            px = int(vp.h * 0.05)
            g.draw_text("Resting. Press a key to keep going", px, vp.centerx, vp.bottom - px * 2.2, "mono", P.MUTED,
                        anchor="midtop", bg=P.SURFACE, pad=px // 3)
        app._draw_footer(frame)

    def _draw_fault(self, g, vp):
        px = int(vp.h * 0.06)
        g.draw_text("This room needs fixing", int(px * 1.4), vp.centerx, vp.centery - px * 2, "mono-bold", P.TEXT, anchor="center")
        g.draw_text("A grown-up can fix it in Purple Studio.  Esc picks a room.", px, vp.centerx, vp.centery,
                    "sans", P.MUTED, anchor="center")
        small, width = int(px * 0.7), int(vp.w * 0.8)
        x, y = vp.centerx - width // 2, vp.centery + px * 1.4
        if not self._why_shown:
            g.draw_text("Enter shows what went wrong", small, vp.centerx, y, "sans", P.DIM, anchor="midtop")
            return
        why = f"(Technical: {self.fault[:FAULT_SHOWN]})".replace("[", "\\[")
        y += g.draw_markup(why, small, x, y, "mono", P.DIM, max_width=width, align="center", tr=False) + small
        if Guest is ProcessGuest:  # Studio's preview has no Parent Menu terminal
            g.draw_markup("To see more: Parent Menu, Open Terminal, type check-room", small, x, y, "sans", P.DIM,
                          max_width=width, align="center")
