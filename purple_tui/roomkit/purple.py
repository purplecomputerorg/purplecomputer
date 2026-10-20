"""What a family room imports: `from purple import *`.

A room is a Python file. Its top level runs once when the kid enters; after
that Purple calls on_key(key) for each key and fires the timers it set up.
This module is the room's whole idea of a screen: it keeps the text, the
grid, the timers, and ask(), and after every event answers Purple with one
reply holding the scene to draw. Purple only draws shapes and plays sounds,
so this file can change in any pack without changing Purple. Studio ships
its copy beside a pack's rooms as content/rooms/purple.py; a pack without
one gets the copy Purple was built with. Protocol: guides/family-rooms.md.
"""

import json as _json
import re as _re
import traceback as _traceback

__all__ = ["grid", "keep", "images", "sounds", "show", "write", "status", "clear", "background", "say", "play", "drum", "sound",
           "picture", "pixels", "held", "ask", "every", "after", "game_over", "state"]

W, H = 24, 12
CELL = 10
LINES_KEPT = 5
KEEP_MAX_BYTES = 4096
_HEX = _re.compile(r"^#[0-9a-fA-F]{6}$")
_NOTE = _re.compile(r"^[A-Ga-g]#?\d$")
DRUMS = ("kick", "snare", "hi-hat", "clap", "cowbell", "woodblock", "triangle", "tambourine", "bongo", "gong")
# The theme's colors by name: Purple paints them in the family's theme.
ROLES = ("bg", "surface", "tile", "field", "hair", "line", "primary", "on_primary", "accent", "text", "muted", "dim")


def _is_color(thing) -> bool:
    return isinstance(thing, str) and bool(_HEX.match(thing) or thing in ROLES)

_send = None   # the host's: send(reply: dict)
_recv = None   # the host's: blocking recv() -> event dict

keep = {}      # remembered for next time, up to 4 KB of JSON
images = {}    # the pack's pictures this room can draw: name -> (width, height)
sounds = set() # the pack's own sounds this room can play
_held = set()


def _text(value) -> str:
    return str(value)[:200]


class _Screen:
    def __init__(self):
        self.background = "surface"
        self.big = ""        # text, or a picture
        self.lines = []
        self.status = ""
        self.cells = {}
        self.floor = {}
        self.cursor = None
        self.timers = {}
        self.sounds = []
        self.asking = None   # [prompt, typed so far] while ask() waits
        self.over = None     # game_over text


_s = _Screen()
_size = [240, 120]
_now = [0.0]


def show(thing):
    """Big in the middle of the screen, replacing what was there: text, or a picture."""
    _s.big = thing if isinstance(thing, _Picture) else _text(thing)


def write(text):
    """A line of text under the middle, for stories and questions."""
    _s.lines = (_s.lines + [_text(text)])[-LINES_KEPT:]


def status(text=""):
    """A line along the top, for a score or what to do; status() takes it away."""
    _s.status = _text(text)


def clear():
    """Empty the screen: the middle, the lines, the top line, and the grid."""
    _s.big, _s.lines, _s.status = "", [], ""
    grid.clear()


def background(color):
    if not _is_color(color):
        raise ValueError(f"background needs a color like '#2a1845' or 'tile', not {color!r}")
    _s.background = color


def say(text):
    _s.sounds.append(["say", _text(text)])


def play(note, instrument="marimba"):
    """A note like 'C4' or 'F#3' on one of Purple's instruments."""
    if not _NOTE.match(str(note)):
        raise ValueError(f"a note looks like 'C4' or 'F#3', not {note!r}")
    _s.sounds.append(["note", str(note), str(instrument)])


def drum(name):
    """kick, snare, hi-hat, clap, cowbell, woodblock, triangle, tambourine, bongo, or gong."""
    if name not in DRUMS:
        raise ValueError(f"there's no drum called {name!r}; try {', '.join(DRUMS)}")
    _s.sounds.append(["drum", name])


def sound(name):
    """One of the pack's own sounds, content/sounds/<name>.wav."""
    if name not in sounds:
        raise ValueError(f"the pack has no sound called {name!r}")
    _s.sounds.append(["clip", name])


def held(key):
    """Whether a key is down right now: 'left', 'space', 'a'."""
    return key in _held


class _Picture:
    """w by h squares; h left out keeps the picture's shape."""

    def __init__(self, source, shape, w, h):
        self.source = source
        self.w = max(1, min(W, int(w)))
        self.h = max(1, min(H, int(h))) if h is not None else max(1, min(H, round(self.w * shape[1] / shape[0])))


def picture(name, w=1, h=None):
    """One of the pack's pictures, content/images/<name>.png, w squares wide."""
    if name not in images:
        raise ValueError(f"the pack has no picture called {name!r}")
    return _Picture(name, images[name], w, h)


def pixels(rows, palette, w=1, h=None):
    """A small picture made of characters: pixels([".X.", "XXX"], {"X": "#ffcc00"}).
    A character not in the palette is see-through."""
    rows = list(rows)
    return _Picture({"rows": rows, "palette": dict(palette)}, (max(map(len, rows), default=1) or 1, len(rows) or 1), w, h)


def ask(prompt=""):
    """Wait for the kid to type an answer and press Enter. Returns what they typed."""
    _s.asking = [_text(prompt), ""]
    while True:
        ev = _exchange()
        key = ev.get("key") if ev.get("ev") == "key" else None
        if key == "enter":
            answer, _s.asking = _s.asking[1], None
            return answer
        if key == "backspace":
            _s.asking[1] = _s.asking[1][:-1]
        elif key:
            _s.asking[1] = _text(_s.asking[1] + (" " if key == "space" else ev.get("char", key) if len(key) == 1 else ""))


class state:
    """What a room changes as it plays: game = state(turn=0), then game.turn = 1 in any function, no global needed."""

    def __init__(self, **values):
        self.__dict__.update(values)


def game_over(text="Press a key to play again"):
    """Stop the timers and show text; the next key starts the room over."""
    _s.timers.clear()
    _s.over = _text(text)


def _pos(args):
    x, y = args if len(args) == 2 else args[0]
    return int(x) % W, int(y) % H


class _Layer:
    """W x H squares, (0, 0) top left. A square holds an emoji, a letter, a color ('#rrggbb' or a theme color like 'tile'), or a picture.
    Every call takes x, y or one (x, y)."""

    w, h = W, H

    def __init__(self, name):
        self._name = name

    @property
    def _cells(self) -> dict:
        return getattr(_s, self._name)

    def set(self, *args, size=1):
        """size: an emoji, letter, or color as big as size by size squares, from this one right and down."""
        *where, thing = args
        self._cells[_pos(where)] = (thing if isinstance(thing, _Picture) else _text(thing), max(1, min(H, int(size))))

    def get(self, *where):
        return self._cells.get(_pos(where), (None,))[0]

    def erase(self, *where):
        self._cells.pop(_pos(where), None)

    def clear(self):
        self._cells.clear()

    def random_empty(self):
        """An (x, y) with nothing in it, or None when every square is full."""
        import random
        free = [(x, y) for x in range(W) for y in range(H) if (x, y) not in self._cells]
        return random.choice(free) if free else None


class _Grid(_Layer):
    """The grid kids see. grid.floor is a layer under it, so a hero can stand on grass."""

    def __init__(self):
        super().__init__("cells")
        self.floor = _Layer("floor")

    def clear(self):
        """Empties the grid, its floor, and the cursor."""
        _s.cells.clear()
        _s.floor.clear()
        _s.cursor = None

    def cursor(self, *where):
        """A ring around one square, or around a bigger thing in it, to show what's picked; grid.cursor() takes it away."""
        _s.cursor = _pos(where) if where and where[0] is not None else None


grid = _Grid()


class _Timer:
    def __init__(self, seconds, fn, once):
        self.seconds, self.fn, self.once = max(0.1, float(seconds)), fn, once
        self.due = _now[0] + self.seconds
        _s.timers[id(self)] = self

    def stop(self):
        _s.timers.pop(id(self), None)


def every(seconds, fn):
    """Call fn every so many seconds (at least 0.1). Returns a timer with .stop()."""
    return _Timer(seconds, fn, False)


def after(seconds, fn):
    """Call fn once, after so many seconds."""
    return _Timer(seconds, fn, True)


# ---------------------------------------------------------------- the scene

# Text straight on a room's own background color, light or dark, instead of the theme's roles.
_INKS = {True: {"text": "#2a1845", "muted": "#5b4a75", "accent": "#7a2fb8"},
         False: {"text": "#f4eefb", "muted": "#cbbfe0", "accent": "#e3b8ff"}}


def _ink(color):
    bg = _s.background
    if not _HEX.match(bg):
        return color
    light = sum(k * int(bg[i:i + 2], 16) for k, i in ((0.299, 1), (0.587, 3), (0.114, 5))) > 150
    return _INKS[light].get(color, color)


def _label(x, y, size, text, color="text", **how):
    """how: anchor (center, left, right, top, bottom, topleft, ...), width to wrap at, height to shrink into,
    box (a color behind), pad, radius."""
    shape = ["text", round(x, 1), round(y, 1), round(size, 1), text, color if "box" in how else _ink(color)]
    return shape + [how] if how else shape


def _span(thing, size) -> tuple:
    """How many squares across and down a thing in the grid covers."""
    return (thing.w, thing.h) if isinstance(thing, _Picture) else (size, size)


def _thing(x, y, thing, size) -> list:
    if isinstance(thing, _Picture):
        return ["image", x, y, CELL * thing.w, CELL * thing.h, thing.source]
    side = CELL * size
    if _is_color(thing):
        return ["rect", x + 0.5, y + 0.5, side - 1, side - 1, thing, side / 8]
    return _label(x + side / 2, y + side / 2, side * 0.78, thing)


def _big(sw, sh, thing, box) -> list:
    if not isinstance(thing, _Picture):
        return _label(sw / 2, sh * 0.34, sh * 0.24, thing, width=sw * 0.9, height=sh * 0.46, **box)
    k = min(sw * 0.8 / thing.w, sh * 0.46 / thing.h)
    w, h = thing.w * k, thing.h * k
    return ["image", (sw - w) / 2, sh * 0.34 - h / 2, w, h, thing.source]


def _scene() -> list:
    sw, sh = _size
    shapes = [["rect", 0, 0, sw, sh, _s.background, 0]]
    on_grid = bool(_s.cells or _s.floor or _s.cursor)
    box = {"box": "surface", "pad": 2, "radius": 2} if on_grid else {}
    if on_grid:
        ox, oy = (sw - W * CELL) / 2, (sh - H * CELL) / 2
        for layer in (_s.floor, _s.cells):
            shapes += [_thing(ox + x * CELL, oy + y * CELL, *item) for (x, y), item in layer.items()]
        if _s.cursor:
            x, y = _s.cursor
            w, h = _span(*_s.cells.get(_s.cursor, (None, 1)))
            shapes.append(["rect", ox + x * CELL, oy + y * CELL, w * CELL, h * CELL, "accent", CELL / 6, 1])
    if _s.big:
        shapes.append(_big(sw, sh, _s.big, box))
    px = sh * 0.05
    bottom = sh - px * 1.2
    if _s.lines:
        text = "\n".join(_s.lines)
        if on_grid:
            lift = px * 3.2 if _s.asking else px * 1.6 if _s.over is not None else 0
            shapes.append(_label(sw / 2, bottom - lift, px * 1.1, text, anchor="bottom", width=sw * 0.9, **box))
        else:
            shapes.append(_label(sw / 2, sh * 0.6, px * 1.1, text, anchor="top", width=sw * 0.9))
    if _s.status:
        shapes.append(_label(sw / 2, 1, px * 0.95, _s.status, anchor="top", width=sw * 0.9, height=CELL - 2,
                             **(box and {**box, "pad": 1, "radius": 1.5})))
    if _s.asking:
        prompt, typed = _s.asking
        if prompt:
            shapes.append(_label(px, bottom - px * 1.6, px, prompt, "muted", anchor="bottomleft", **box))
        shapes.append(_label(px, bottom, px, f"Answer → {typed}_", "accent", anchor="bottomleft", **box))
    elif _s.over is not None:
        shapes.append(_label(sw / 2, bottom, px, _s.over, "accent", anchor="bottom", **box))
    return shapes


# ---------------------------------------------------------------- talking to Purple

_last = {"scene": None, "keep": "{}"}


def _wake():
    if _s.asking or _s.over is not None or not _s.timers:
        return None
    return max(0.0, min(t.due for t in _s.timers.values()) - _now[0])


def _reply() -> dict:
    reply = {"wake": _wake()}
    scene = _scene()
    if scene != _last["scene"]:
        reply["scene"] = _last["scene"] = scene
    if _s.sounds:
        reply["sounds"], _s.sounds = _s.sounds, []
    kept = _json.dumps(keep, sort_keys=True)
    if kept != _last["keep"]:
        if len(kept.encode()) > KEEP_MAX_BYTES:
            raise ValueError(f"keep holds at most {KEEP_MAX_BYTES // 1024} KB")
        reply["keep"], _last["keep"] = keep, kept
    return reply


def _exchange() -> dict:
    """Answer the event being handled, then wait for the next one."""
    _send(_reply())
    ev = _recv()
    if isinstance(ev.get("t"), (int, float)):
        _now[0] = float(ev["t"])
    if ev.get("ev") == "key":
        _held.add(ev.get("key"))
    elif ev.get("ev") == "keyup":
        _held.discard(ev.get("key"))
    return ev


def _begin(source, room):
    global _s
    _s = _Screen()
    room.clear()
    room["__name__"] = "__main__"
    exec(compile(source, "room.py", "exec"), room)


def _fire_timers():
    for t in sorted(_s.timers.values(), key=lambda t: t.due):
        if t.due > _now[0] or id(t) not in _s.timers:
            continue
        if t.once:
            t.stop()
        else:
            t.due = max(t.due + t.seconds, _now[0])
        t.fn()


def _error(exc) -> dict:
    if isinstance(exc, SyntaxError):
        return {"error": {"text": f"SyntaxError: {exc.msg}", "line": exc.lineno}}
    frames = [f for f in _traceback.extract_tb(exc.__traceback__) if f.filename == "room.py"]
    return {"error": {"text": f"{type(exc).__name__}: {exc}"[:300], "line": frames[-1].lineno if frames else None}}


def run(start: dict):
    """Run a room: its top level for the start event, then one event at a time."""
    _size[:] = start.get("size") or _size
    keep.update(start.get("keep") or {})
    images.update({n: tuple(size) for n, size in (start.get("images") or {}).items()})
    sounds.update(start.get("sounds") or ())
    _last["keep"] = _json.dumps(keep, sort_keys=True)
    room = {}
    try:
        _begin(start["source"], room)
        while True:
            ev = _exchange()
            if ev.get("ev") == "key" and _s.over is not None:
                _begin(start["source"], room)
            elif ev.get("ev") == "key" and callable(room.get("on_key")):
                room["on_key"](ev.get("key"))
            elif ev.get("ev") == "keyup" and callable(room.get("on_key_up")):
                room["on_key_up"](ev.get("key"))
            elif ev.get("ev") == "tick":
                _fire_timers()
    except Exception as exc:
        _send(_error(exc))
