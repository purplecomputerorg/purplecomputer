"""What a family room imports: `from purple import *`.

A room is a Python file. Its top level runs once when the kid enters; after
that Purple calls on_key(key) for each key and fires the timers it set up.
Everything a room shows or plays is a request to Purple, sent as one JSON
message, so a room never touches the screen, speakers, or disk itself. The
same file runs on the laptop (purple_tui/roomkit/runner.py, in its own
process) and in Studio (Pyodide in a Web Worker); each sets _send and _recv.
Protocol and rules: guides/family-rooms.md.
"""

import re as _re
import traceback as _traceback

__all__ = ["grid", "show", "write", "clear", "background", "say", "play", "drum",
           "ask", "every", "after", "game_over"]

W, H = 24, 12
_HEX = _re.compile(r"^#[0-9a-fA-F]{6}$")

_send = None   # the host's: send(message: dict)
_recv = None   # the host's: blocking recv() -> dict


def _text(value) -> str:
    return str(value)[:200]


def show(text):
    """Big in the middle of the screen, replacing what was there."""
    _send({"cmd": "show", "text": _text(text)})


def write(text):
    """A line of text under the middle, for stories and questions."""
    _send({"cmd": "write", "text": _text(text)})


def clear():
    """Empty the screen: the middle, the lines, and the grid."""
    grid._cells.clear()
    _send({"cmd": "clear"})


def background(color):
    if not (isinstance(color, str) and _HEX.match(color)):
        raise ValueError(f"background needs a color like '#2a1845', not {color!r}")
    _send({"cmd": "background", "color": color})


def say(text):
    _send({"cmd": "say", "text": _text(text)})


def play(note, instrument="marimba"):
    """A note like 'C4' or 'F#3' on one of Purple's instruments."""
    _send({"cmd": "play", "note": str(note), "instrument": str(instrument)})


def drum(name):
    """kick, snare, hi-hat, clap, cowbell, woodblock, triangle, tambourine, bongo, or gong."""
    _send({"cmd": "drum", "name": str(name)})


def ask(prompt=""):
    """Wait for the kid to type an answer and press Enter. Returns what they typed."""
    _send({"cmd": "ask", "prompt": _text(prompt)})
    while (msg := _recv())["ev"] != "answer":
        pass
    return msg["text"]


def game_over(text="Press a key to play again"):
    """Stop the timers and show text; the next key starts the room over."""
    _send({"cmd": "game_over", "text": _text(text)})


class _Grid:
    """W x H squares, (0, 0) top left. A square holds an emoji, a letter, or a '#rrggbb' color."""

    w, h = W, H

    def __init__(self):
        self._cells = {}

    @staticmethod
    def _pos(args):
        x, y = args if len(args) == 2 else args[0]
        return int(x) % W, int(y) % H

    def set(self, *args):
        """grid.set(x, y, thing) or grid.set((x, y), thing)."""
        *where, thing = args
        x, y = self._pos(where)
        self._cells[(x, y)] = _text(thing)
        _send({"cmd": "cell", "x": x, "y": y, "thing": self._cells[(x, y)]})

    def get(self, *where):
        return self._cells.get(self._pos(where))

    def erase(self, *where):
        x, y = self._pos(where)
        if self._cells.pop((x, y), None) is not None:
            _send({"cmd": "cell", "x": x, "y": y, "thing": None})

    def clear(self):
        self._cells.clear()
        _send({"cmd": "grid_clear"})

    def random_empty(self):
        import random
        free = [(x, y) for x in range(W) for y in range(H) if (x, y) not in self._cells]
        return random.choice(free) if free else (0, 0)


grid = _Grid()


class _Timer:
    def __init__(self, n, fn, once):
        self.n, self.fn, self.once = n, fn, once

    def stop(self):
        if _timers.pop(self.n, None):
            _send({"cmd": "stop", "id": self.n})


_timers = {}
_next_timer = [0]


def _timer(seconds, fn, once):
    _next_timer[0] += 1
    t = _timers[_next_timer[0]] = _Timer(_next_timer[0], fn, once)
    _send({"cmd": "after" if once else "every", "id": t.n, "seconds": max(0.1, float(seconds))})
    return t


def every(seconds, fn):
    """Call fn every so many seconds (at least 0.1). Returns a timer with .stop()."""
    return _timer(seconds, fn, False)


def after(seconds, fn):
    """Call fn once, after so many seconds."""
    return _timer(seconds, fn, True)


def _dispatch(room, msg):
    if msg["ev"] == "key" and callable(room.get("on_key")):
        room["on_key"](msg["key"])
    elif msg["ev"] == "tick" and (t := _timers.get(msg["id"])):
        if t.once:
            _timers.pop(t.n)
        t.fn()


def _error(exc) -> dict:
    if isinstance(exc, SyntaxError):
        return {"cmd": "error", "text": f"SyntaxError: {exc.msg}", "line": exc.lineno}
    frames = [f for f in _traceback.extract_tb(exc.__traceback__) if f.filename == "room.py"]
    return {"cmd": "error", "text": f"{type(exc).__name__}: {exc}"[:300], "line": frames[-1].lineno if frames else None}


def run(source: str):
    """Run a room: its top level, then one event at a time, saying "done" after each."""
    room = {"__name__": "__main__"}
    try:
        exec(compile(source, "room.py", "exec"), room)
        _send({"cmd": "done"})
        while True:
            _dispatch(room, _recv())
            _send({"cmd": "done"})
    except Exception as exc:
        _send(_error(exc))
