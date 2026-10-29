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

import colorsys
import json as _json
import math
import re as _re
import traceback as _traceback

__all__ = ["grid", "keep", "images", "sounds", "show", "write", "status", "clear", "background", "say", "play", "drum", "sound",
           "picture", "pixels", "mix", "held", "ask", "every", "after", "game_over", "state",
           "ARROWS", "KEY_COLORS", "KEY_ROWS"]

W, H = 26, 12
CELL = 8.75
TOP = 11       # the strip above the grid, where status() goes
LINES_KEPT = 5
KEEP_MAX_BYTES = 4096
OVER_PAUSE_S = 1.0  # so the key that ended the game, or the tap right after it, doesn't start the next one
_HEX = _re.compile(r"^#[0-9a-fA-F]{6}$")
_KEY_NAMES = _re.compile(r"(?<!\{)\b(Space|Enter|Tab|Backspace)\b(?!\})")
_NOTE = _re.compile(r"^[A-Ga-g]#?\d$")
# Each arrow key's step on the grid, as (across, down).
ARROWS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
# The keys the Music room plays, a row at a time, top to bottom.
KEY_ROWS = ("1234567890", "qwertyuiop", "asdfghjkl;", "zxcvbnm,./")
DRUMS = ("kick", "snare", "hi-hat", "clap", "cowbell", "woodblock", "triangle", "tambourine", "bongo", "gong")
# The theme's colors by name: Purple paints them in the family's theme.
ROLES = ("bg", "surface", "tile", "field", "hair", "line", "primary", "on_primary", "accent", "text", "muted", "dim")


def _is_color(thing) -> bool:
    return isinstance(thing, str) and bool(_HEX.match(thing) or thing in ROLES)


def _shades(hue, keys):
    return {k: "#%02X%02X%02X" % tuple(int(c * 255) for c in colorsys.hls_to_rgb(hue / 360, 0.80 - (i / (len(keys) - 1)) * 0.60, 0.75))
            for i, k in enumerate(keys)}


# Each key's color, as on its sticker: the number row grays, then a row each of reds, yellows, and blues, light to dark.
KEY_COLORS = {
    **dict(zip("1234567890-=", ("#FFFFFF", "#E8E8E8", "#D0D0D0", "#B8B8B8", "#A0A0A0", "#888888",
                                "#707070", "#585858", "#404040", "#282828", "#101010", "#000000"))),
    **_shades(0, "qwertyuiop[]"), **_shades(50, "asdfghjkl;'"), **_shades(220, "zxcvbnm,./"),
}

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
        self.over_at = 0.0
        self.stale = set()   # keys already down at game_over; they don't start the room over


_s = _Screen()
_size = [240, 120]
_api = [0]
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
    """kick, snare, hi-hat, clap, cowbell, woodblock, triangle, tambourine, bongo, gong, or one of the pack's own sounds."""
    if name in sounds:
        return sound(name)
    if name not in DRUMS:
        raise ValueError(f"there's no drum called {name!r}; try {', '.join([*DRUMS, *sorted(sounds)])}")
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
    """w by h squares; h left out keeps the picture's shape. Both left out (w is None), it fits where an
    emoji would go, keeping its shape."""

    def __init__(self, source, shape, w, h):
        self.source, self.shape = source, shape
        self.w = self.h = None
        if w is not None or h is not None:
            self.w = max(1, min(W, int(w or 1)))
            self.h = max(1, min(H, int(h))) if h is not None else max(1, min(H, round(self.w * shape[1] / shape[0])))

    def __str__(self):
        return self.source if isinstance(self.source, str) else "picture"


def picture(name, w=None, h=None):
    """One of the pack's pictures, content/images/<name>.png: where an emoji would go, or w squares wide."""
    if name not in images:
        raise ValueError(f"the pack has no picture called {name!r}")
    return _Picture(name, images[name], w, h)


def pixels(rows, palette, w=None, h=None):
    """A small picture made of characters: pixels([".X.", "XXX"], {"X": "#ffcc00"}).
    A character not in the palette is see-through."""
    rows = list(rows)
    return _Picture({"rows": rows, "palette": dict(palette)}, (max(map(len, rows), default=1) or 1, len(rows) or 1), w, h)


def mix(*colors):
    """Colors mixed like paint: mix("#ffd400", "#1e5bd6") is green. Give a color twice to use more of it."""
    if not colors or not all(isinstance(c, str) and _HEX.match(c) for c in colors):
        raise ValueError(f"mix needs colors like '#ffd400', not {colors!r}")
    return _mix(colors)


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
    """Stop the timers and show text; a new key press, after a moment, starts the room over."""
    _s.timers.clear()
    _s.over, _s.over_at, _s.stale = _text(text), _now[0], set(_held)


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

    @property
    def here(self):
        """Where the ring is, as (x, y), or None when there's none."""
        return _s.cursor

    def move(self, key):
        """An arrow key moves the ring a square, around the edges, starting it in the middle if there's none; other keys do nothing."""
        if key in ARROWS:
            x, y = _s.cursor or (W // 2, H // 2)
            dx, dy = ARROWS[key]
            _s.cursor = _pos([(x + dx, y + dy)])

    def keyboard(self, rows=KEY_ROWS, size=2):
        """Each key's (x, y) with the rows laid out like the keyboard, size squares apart and centered on the grid."""
        left, top = (W - size * max(map(len, rows))) // 2, (H - size * len(rows)) // 2
        return {key: (left + c * size, top + r * size) for r, row in enumerate(rows) for c, key in enumerate(row)}


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


def _keyed(text) -> tuple:
    """Text and how, with key names drawn as keycaps where Purple can (api 3)."""
    if _api[0] < 3 or not _KEY_NAMES.search(text):
        return text, {}
    return _KEY_NAMES.sub(r"{\1}", text), {"keys": True}


def _span(thing, size) -> tuple:
    """How many squares across and down a thing in the grid covers."""
    return (thing.w, thing.h) if isinstance(thing, _Picture) and thing.w else (size, size)


def _fit(thing, size) -> tuple:
    """A picture's left and top inside its squares, and its width and height, all in squares."""
    if thing.w:
        return 0, 0, thing.w, thing.h
    k = size / max(thing.shape)
    w, h = thing.shape[0] * k, thing.shape[1] * k
    return (size - w) / 2, (size - h) / 2, w, h


def _thing(x, y, thing, size, corner=False) -> list:
    if isinstance(thing, _Picture):
        dx, dy, w, h = _fit(thing, size)
        return ["image", x + CELL * dx, y + CELL * dy, CELL * w, CELL * h, thing.source]
    side = CELL * size
    if _is_color(thing):
        return ["rect", x + 0.5, y + 0.5, side - 1, side - 1, thing, side / 8]
    if corner:
        return _label(x + side - 1, y + side - 1, side * 0.5, thing, anchor="bottomright", box="surface", pad=0.8, radius=1.5)
    return _label(x + side / 2, y + side / 2, side * 0.6, thing)


def _covered(cells) -> set:
    """The squares a bigger thing in the grid spreads over, past its own."""
    spans = {at: _span(*item) for at, item in cells.items()}
    return {(x + i, y + j) for (x, y), (w, h) in spans.items() for i in range(w) for j in range(h) if i or j}


def _big(sw, sh, thing, box) -> list:
    if not isinstance(thing, _Picture):
        return _label(sw / 2, sh * 0.34, sh * 0.24, thing, width=sw * 0.9, height=sh * 0.46, **box)
    _, _, w, h = _fit(thing, 1)
    k = min(sw * 0.8 / w, sh * 0.46 / h)
    w, h = w * k, h * k
    return ["image", (sw - w) / 2, sh * 0.34 - h / 2, w, h, thing.source]


def _scene() -> list:
    sw, sh = _size
    shapes = [["rect", 0, 0, sw, sh, _s.background, 0]]
    on_grid = bool(_s.cells or _s.floor or _s.cursor)
    box = {"box": "surface", "pad": 2, "radius": 2} if on_grid else {}
    if on_grid:
        ox, oy = (sw - W * CELL) / 2, TOP
        shapes += [_thing(ox + x * CELL, oy + y * CELL, *item) for (x, y), item in _s.floor.items()]
        # A letter on part of a bigger thing, like a key's letter on its picture, goes on top as a small corner badge.
        over = _covered(_s.cells)
        shapes += [_thing(ox + x * CELL, oy + y * CELL, *item, corner=(x, y) in over)
                   for (x, y), item in sorted(_s.cells.items(), key=lambda kv: kv[0] in over)]
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
        text, keys = _keyed(_s.status)
        shapes.append(_label(sw / 2, TOP / 2, px * 0.95, text, "muted", width=sw * 0.9, height=TOP - 3,
                             **keys, **(box and {**box, "pad": 1, "radius": 1.5})))
    if _s.asking:
        prompt, typed = _s.asking
        if prompt:
            shapes.append(_label(px, bottom - px * 1.6, px, prompt, "muted", anchor="bottomleft", **box))
        shapes.append(_label(px, bottom, px, f"Answer → {typed}_", "accent", anchor="bottomleft", **box))
    elif _s.over is not None:
        text, keys = _keyed(_s.over)
        shapes.append(_label(sw / 2, bottom, px, text, "accent", anchor="bottom", **keys, **box))
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
        _s.stale.discard(ev.get("key"))
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
    _api[0] = start.get("api") or 0
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
                if ev.get("key") not in _s.stale and _now[0] >= _s.over_at + OVER_PAUSE_S:
                    _begin(start["source"], room)
            elif ev.get("ev") == "key" and callable(room.get("on_key")):
                room["on_key"](ev.get("key"))
            elif ev.get("ev") == "keyup" and callable(room.get("on_key_up")):
                room["on_key_up"](ev.get("key"))
            elif ev.get("ev") == "tick":
                _fire_timers()
    except Exception as exc:
        _send(_error(exc))

# ---------------------------------------------------------------- mixing paint
# From spectral.js by Ronald van Wijnen (MIT License), https://github.com/rvanwijnen/spectral.js.
# Purple's Art room mixes with this same code (purple_tui/color_mixing.py imports it).

SIZE = 38  # Number of spectral samples

# Base spectral reflectance curves for primary pigments
# From spectral.js, based on Scott Burns' LHTSS method
BASE_SPECTRA = {
    "W": [
        1.0011607271876, 1.0011606515973, 1.0011603192275, 1.0011586727079, 1.0011525984455, 1.00113252529, 1.0010850066333, 1.0009968788945, 1.0008652515227,
        1.0006962900094, 1.0005049611489, 1.0003080818799, 1.0001196660201, 0.99995276596841, 0.9998218368993, 0.99973860955759, 0.99970955163961, 0.99973193021063,
        0.9997994363462, 0.99990033031667, 1.0000204065261, 1.0001447879366, 1.0002599790341, 1.0003557969709, 1.0004275378027, 1.0004762334489, 1.0005072096751,
        1.0005251915637, 1.000535096069, 1.0005402209748, 1.0005427281678, 1.0005438956909, 1.0005444821215, 1.0005447695999, 1.0005448988776, 1.0005449625469,
        1.0005449892706, 1.000544996993
    ],
    "C": [
        0.97058500132296, 0.97059249814343, 0.97062534872989, 0.97078680611902, 0.97136867322825, 0.97316323062125, 0.97674022315877, 0.98158760549138, 0.98628026565295,
        0.98994914768913, 0.99249270153842, 0.99414568040526, 0.99518397503321, 0.99575675011082, 0.99591281828671, 0.99560615783453, 0.99459760096185, 0.99221571549237,
        0.98623645278325, 0.96794333726454, 0.89128500424494, 0.53620247786205, 0.15410811900188, 0.057457509322893, 0.031534987310701, 0.022263392008634, 0.018202284149244,
        0.016299055973264, 0.015365623933461, 0.014911156873398, 0.014695433989824, 0.014596414671772, 0.014547015669966, 0.01452287718995, 0.014512034111897,
        0.014506694093983, 0.014504450731448, 0.014503800946464
    ],
    "M": [
        0.99067355731999, 0.99067152496198, 0.99066258235342, 0.9906181076448, 0.99045148087871, 0.9898710814002, 0.98828660875964, 0.9842906927975, 0.97393490562531,
        0.94181783846015, 0.81739032619516, 0.43247280506573, 0.13845397825887, 0.053734721694003, 0.029217499667323, 0.021313651750859, 0.020134953018114, 0.024132309628066,
        0.037223614522363, 0.07605065527066, 0.2053754719424, 0.54126890346044, 0.81584168508649, 0.91281770412398, 0.94633983016696, 0.95992769633199, 0.96626059523031,
        0.96932597005842, 0.9708545367214, 0.97160506652813, 0.97196276975739, 0.97212727227451, 0.97220941774581, 0.97224957767842, 0.97226762199874, 0.97227650946215,
        0.97228024330687, 0.97228132482656
    ],
    "Y": [
        0.021052337178931, 0.021056462751741, 0.021074617869504, 0.021164905844875, 0.02150279572725, 0.022673879904156, 0.025823564969363, 0.033487938563985,
        0.051906966374031, 0.10074901483347, 0.23912989970685, 0.53480431227275, 0.79780757864303, 0.91144989406738, 0.95379796300451, 0.97124161546543, 0.97930312380759,
        0.98338011950758, 0.98546124656776, 0.98643504697661, 0.98673825067014, 0.98661788244503, 0.98627777675864, 0.98586059244406, 0.98547492767621, 0.98517693476556,
        0.98497157401418, 0.98484630341571, 0.9847753518112, 0.98473806662527, 0.98471964831177, 0.98471102339194, 0.98470668330068, 0.98470455439309, 0.98470359630937,
        0.98470312407755, 0.98470292561509, 0.9847028681228
    ],
    "R": [
        0.031560573777721, 0.031552071833015, 0.031514821551366, 0.03133180449827, 0.030672985772553, 0.028648047698961, 0.024645040704571, 0.019296075366365,
        0.014206661222056, 0.010294260887861, 0.0076191460521811, 0.005898041083542, 0.0048233247781713, 0.0042298748350633, 0.0040599171299341, 0.0043533695594676,
        0.0053434425970201, 0.0076917201010463, 0.013596979573654, 0.031697544266112, 0.10786119635525, 0.4638126031687, 0.84705540527201, 0.94318540939392, 0.96886215069656,
        0.9780306674736, 0.98204364385431, 0.98392362371871, 0.98484548415438, 0.9852942758146, 0.98550729521983, 0.98560507153984, 0.98565384993358, 0.98567768503388,
        0.98568839180612, 0.98569366469003, 0.98569587984821, 0.98569652146376
    ],
    "G": [
        0.0095560747554212, 0.0095581580120851, 0.0095673245444588, 0.0096129126297349, 0.0097837090401843, 0.010378622705871, 0.012002645237857, 0.016097772147392,
        0.026706190223168, 0.059555544018588, 0.18603982653283, 0.57057982011616, 0.86146776840029, 0.94587908976766, 0.97046548647431, 0.97841363028445, 0.97958903141122,
        0.97553353690863, 0.96228875539781, 0.92312157451312, 0.79343401894311, 0.45927013590243, 0.1855741036663, 0.088177495995537, 0.05436302287667, 0.040628844706072,
        0.034221520431697, 0.031118579095697, 0.029570889833613, 0.028810873934893, 0.02844862713246, 0.028282030172473, 0.028198837649024, 0.028158165534204,
        0.028139891021639, 0.028130890166581, 0.028127108680582, 0.02812601336121
    ],
    "B": [
        0.97940475250201, 0.97940070684313, 0.97938290347026, 0.97929436494559, 0.97896301460857, 0.97781446669404, 0.97472432113384, 0.96719848234397, 0.94907965753058,
        0.90085012894098, 0.76315044546224, 0.46592217164932, 0.20126328045101, 0.087752441341962, 0.045717679329168, 0.028470605052184, 0.020527176756985, 0.016530279231021,
        0.014513510721286, 0.013600350863769, 0.013360425876957, 0.013548894314568, 0.013959435636699, 0.014443425575357, 0.014885444062141, 0.015225429699975,
        0.015459284818021, 0.015601802648596, 0.015682487128194, 0.015724876436062, 0.015745810878412, 0.015755612335023, 0.015760544396491, 0.015762963751528,
        0.015764052562911, 0.015764589232951, 0.015764814777265, 0.015764880114962
    ],
}

# CIE Color Matching Functions weighted by D65 (from spectral.js)
CIE_CMF_X = [
    0.0000646919989576, 0.0002194098998132, 0.0011205743509343, 0.0037666134117111, 0.011880553603799, 0.0232864424191771, 0.0345594181969747, 0.0372237901162006,
    0.0324183761091486, 0.021233205609381, 0.0104909907685421, 0.0032958375797931, 0.0005070351633801, 0.0009486742057141, 0.0062737180998318, 0.0168646241897775,
    0.028689649025981, 0.0426748124691731, 0.0562547481311377, 0.0694703972677158, 0.0830531516998291, 0.0861260963002257, 0.0904661376847769, 0.0850038650591277,
    0.0709066691074488, 0.0506288916373645, 0.035473961885264, 0.0214682102597065, 0.0125164567619117, 0.0068045816390165, 0.0034645657946526, 0.0014976097506959,
    0.000769700480928, 0.0004073680581315, 0.0001690104031614, 0.0000952245150365, 0.0000490309872958, 0.0000199961492222
]
CIE_CMF_Y = [
    0.000001844289444, 0.0000062053235865, 0.0000310096046799, 0.0001047483849269, 0.0003536405299538, 0.0009514714056444, 0.0022822631748318, 0.004207329043473,
    0.0066887983719014, 0.0098883960193565, 0.0152494514496311, 0.0214183109449723, 0.0334229301575068, 0.0513100134918512, 0.070402083939949, 0.0878387072603517,
    0.0942490536184085, 0.0979566702718931, 0.0941521856862608, 0.0867810237486753, 0.0788565338632013, 0.0635267026203555, 0.05374141675682, 0.042646064357412,
    0.0316173492792708, 0.020885205921391, 0.0138601101360152, 0.0081026402038399, 0.004630102258803, 0.0024913800051319, 0.0012593033677378, 0.000541646522168,
    0.0002779528920067, 0.0001471080673854, 0.0000610327472927, 0.0000343873229523, 0.0000177059860053, 0.000007220974913
]
CIE_CMF_Z = [
    0.000305017147638, 0.0010368066663574, 0.0053131363323992, 0.0179543925899536, 0.0570775815345485, 0.113651618936287, 0.17335872618355, 0.196206575558657,
    0.186082370706296, 0.139950475383207, 0.0891745294268649, 0.0478962113517075, 0.0281456253957952, 0.0161376622950514, 0.0077591019215214, 0.0042961483736618,
    0.0020055092122156, 0.0008614711098802, 0.0003690387177652, 0.0001914287288574, 0.0001495555858975, 0.0000923109285104, 0.0000681349182337, 0.0000288263655696,
    0.0000157671820553, 0.0000039406041027, 0.000001584012587, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
]

# XYZ to sRGB matrix
XYZ_TO_RGB = [
    [3.2409699419045226, -1.537383177570094, -0.4986107602930034],
    [-0.9692660305051868, 1.8760108454466942, 0.041556017530349834],
    [0.05563007969699366, -0.20397695888897652, 1.0569715142428786]
]


def _srgb_to_linear(c: int) -> float:
    """Convert sRGB (0-255) to linear RGB (0-1)."""
    c = c / 255
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> int:
    """Convert linear RGB (0-1) to sRGB (0-255)."""
    c = max(0, min(1, c))
    if c <= 0.0031308:
        c = 12.92 * c
    else:
        c = 1.055 * (c ** (1/2.4)) - 0.055
    return max(0, min(255, int(c * 255 + 0.5)))


def _linear_rgb_to_spectrum(lrgb: tuple) -> list[float]:
    """Convert linear RGB to spectral reflectance curve."""
    r, g, b = lrgb

    # Extract white component
    w = min(r, g, b)
    r, g, b = r - w, g - w, b - w

    # Decompose into CMY and RGB components
    c = min(g, b)
    m = min(r, b)
    y = min(r, g)
    # Calculate RGB remainder using original values (tuple assignment evaluates RHS first)
    r, g, b = (
        max(0, min(r - b, r - g)),
        max(0, min(g - b, g - r)),
        max(0, min(b - g, b - r)),
    )

    # Build spectrum from weighted base spectra
    spectrum = []
    for i in range(SIZE):
        val = (w * BASE_SPECTRA["W"][i] +
               c * BASE_SPECTRA["C"][i] +
               m * BASE_SPECTRA["M"][i] +
               y * BASE_SPECTRA["Y"][i] +
               r * BASE_SPECTRA["R"][i] +
               g * BASE_SPECTRA["G"][i] +
               b * BASE_SPECTRA["B"][i])
        # Real black paint reflects a little light; a near-zero floor made black absorb every mix.
        spectrum.append(max(0.003, val))
    return spectrum


def _spectrum_to_xyz(spectrum: list[float]) -> tuple:
    """Convert spectral reflectance to CIE XYZ."""
    x = sum(s * cmf for s, cmf in zip(spectrum, CIE_CMF_X))
    y = sum(s * cmf for s, cmf in zip(spectrum, CIE_CMF_Y))
    z = sum(s * cmf for s, cmf in zip(spectrum, CIE_CMF_Z))
    return x, y, z


def _xyz_to_linear_rgb(xyz: tuple) -> tuple:
    """Convert XYZ to linear RGB."""
    x, y, z = xyz
    r = XYZ_TO_RGB[0][0] * x + XYZ_TO_RGB[0][1] * y + XYZ_TO_RGB[0][2] * z
    g = XYZ_TO_RGB[1][0] * x + XYZ_TO_RGB[1][1] * y + XYZ_TO_RGB[1][2] * z
    b = XYZ_TO_RGB[2][0] * x + XYZ_TO_RGB[2][1] * y + XYZ_TO_RGB[2][2] * z
    return r, g, b


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex color string."""
    return f"#{r:02X}{g:02X}{b:02X}"


def _mix(colors) -> str:
    """Beer-Lambert spectral mixing: a weighted geometric mean of reflectance gives subtractive hues
    (yellow + blue = green). A color listed twice counts twice."""
    if not colors:
        return "#808080"
    if all(c.upper() == colors[0].upper() for c in colors):
        return colors[0]
    spectra = [_linear_rgb_to_spectrum(tuple(_srgb_to_linear(v) for v in hex_to_rgb(c))) for c in colors]
    mixed = [math.exp(sum(math.log(s[i]) for s in spectra) / len(spectra)) for i in range(SIZE)]
    r, g, b = (_linear_to_srgb(v) / 255 for v in _xyz_to_linear_rgb(_spectrum_to_xyz(mixed)))
    # Log-averaging desaturates; real pigment scatters light and keeps it, so double the saturation back.
    h, li, s = colorsys.rgb_to_hls(r, g, b)
    return rgb_to_hex(*(max(0, min(255, round(v * 255))) for v in colorsys.hls_to_rgb(h, li, min(1.0, s * 2.0))))
