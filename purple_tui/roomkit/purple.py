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

__all__ = ["grid", "keep", "images", "show", "write", "clear", "background", "say", "play", "drum", "sound",
           "picture", "pixels", "held", "ask", "every", "after", "game_over"]

W, H = 24, 12
CELL = 10
LINES_KEPT = 5
KEEP_MAX_BYTES = 4096
_HEX = _re.compile(r"^#[0-9a-fA-F]{6}$")

_send = None   # the host's: send(reply: dict)
_recv = None   # the host's: blocking recv() -> event dict

keep = {}      # remembered for next time, up to 4 KB of JSON
images = {}    # the pack's pictures this room can draw: name -> (width, height)
_held = set()


def _text(value) -> str:
    return str(value)[:200]


class _Screen:
    def __init__(self):
        self.background = "surface"
        self.big = ""
        self.lines = []
        self.cells = {}
        self.timers = {}
        self.sounds = []
        self.asking = None   # [prompt, typed so far] while ask() waits
        self.over = None     # game_over text


_s = _Screen()
_size = [240, 120]
_now = [0.0]


def show(text):
    """Big in the middle of the screen, replacing what was there."""
    _s.big = _text(text)


def write(text):
    """A line of text under the middle, for stories and questions."""
    _s.lines = (_s.lines + [_text(text)])[-LINES_KEPT:]


def clear():
    """Empty the screen: the middle, the lines, and the grid."""
    _s.big, _s.lines = "", []
    _s.cells.clear()


def background(color):
    if not (isinstance(color, str) and _HEX.match(color)):
        raise ValueError(f"background needs a color like '#2a1845', not {color!r}")
    _s.background = color


def say(text):
    _s.sounds.append(["say", _text(text)])


def play(note, instrument="marimba"):
    """A note like 'C4' or 'F#3' on one of Purple's instruments."""
    _s.sounds.append(["note", str(note), str(instrument)])


def drum(name):
    """kick, snare, hi-hat, clap, cowbell, woodblock, triangle, tambourine, bongo, or gong."""
    _s.sounds.append(["drum", str(name)])


def sound(name):
    """One of the pack's own sounds, content/sounds/<name>.wav."""
    _s.sounds.append(["clip", str(name)])


def held(key):
    """Whether a key is down right now: 'left', 'space', 'a'."""
    return key in _held


class _Picture:
    def __init__(self, source):
        self.source = source


def picture(name):
    """One of the pack's pictures, content/images/<name>.png, for a grid square."""
    if name not in images:
        raise ValueError(f"the pack has no picture called {name!r}")
    return _Picture(name)


def pixels(rows, palette):
    """A small picture made of characters, for a grid square: pixels([".X.", "XXX"], {"X": "#ffcc00"}).
    A character not in the palette is see-through."""
    return _Picture({"rows": list(rows), "palette": dict(palette)})


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


def game_over(text="Press a key to play again"):
    """Stop the timers and show text; the next key starts the room over."""
    _s.timers.clear()
    _s.over = _text(text)


class _Grid:
    """W x H squares, (0, 0) top left. A square holds an emoji, a letter, or a '#rrggbb' color."""

    w, h = W, H

    @staticmethod
    def _pos(args):
        x, y = args if len(args) == 2 else args[0]
        return int(x) % W, int(y) % H

    def set(self, *args):
        """grid.set(x, y, thing) or grid.set((x, y), thing)."""
        *where, thing = args
        _s.cells[self._pos(where)] = thing if isinstance(thing, _Picture) else _text(thing)

    def get(self, *where):
        return _s.cells.get(self._pos(where))

    def erase(self, *where):
        _s.cells.pop(self._pos(where), None)

    def clear(self):
        _s.cells.clear()

    def random_empty(self):
        import random
        free = [(x, y) for x in range(W) for y in range(H) if (x, y) not in _s.cells]
        return random.choice(free) if free else (0, 0)


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

def _label(x, y, size, text, color="text", align="center"):
    return ["text", round(x, 1), round(y, 1), round(size, 1), text, color, align]


def _scene() -> list:
    sw, sh = _size
    shapes = [["rect", 0, 0, sw, sh, _s.background, 0]]
    if _s.cells:
        ox, oy = (sw - W * CELL) / 2, (sh - H * CELL) / 2
        for (x, y), thing in _s.cells.items():
            cx, cy = ox + x * CELL, oy + y * CELL
            if isinstance(thing, _Picture):
                shapes.append(["image", cx, cy, CELL, CELL, thing.source])
            elif _HEX.match(thing):
                shapes.append(["rect", cx + 0.5, cy + 0.5, CELL - 1, CELL - 1, thing, CELL / 8])
            else:
                shapes.append(_label(cx + CELL / 2, cy + CELL / 2, CELL * 0.78, thing))
    else:
        if _s.big:
            shapes.append(_label(sw / 2, sh * 0.36, sh * 0.24, _s.big))
        px = sh * 0.055
        shapes += [_label(sw / 2, sh * 0.6 + i * px * 1.35 + px / 2, px, line) for i, line in enumerate(_s.lines)]
    px = sh * 0.05
    y = sh - px * 1.7
    if _s.asking:
        prompt, typed = _s.asking
        if prompt:
            shapes.append(_label(px, y - px * 1.5, px, prompt, "muted", "left"))
        shapes.append(_label(px, y, px, f"Answer → {typed}_", "accent", "left"))
    elif _s.over is not None:
        shapes.append(_label(sw / 2, y, px, _s.over, "accent"))
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
