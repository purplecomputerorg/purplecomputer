"""Panels that borrow the bottom of the viewport: the code line, the loop
station, and the Time Travel bar. Plus the Space hold-or-tap policy the
Music, Art and Blocks rooms share, and the echo that writes code for what a
kid does by hand.
"""

import colorsys
import math
import random
import re
import time
from datetime import date
from functools import cache

import pygame

from .. import palette as P
from ..constants import HOLD_OR_TAP_THRESHOLD, ICON_LOOP, ICON_ROBOT, ICON_TIME_TRAVEL
from ..content import get_content
from ..keyboard import CharacterAction, ControlAction, HoldOrTap, NavigationAction
from ..loop_station import LOOPING, RECORDING
from ..music_constants import GRID_KEYS
from ..palette import get_key_color
from ..timeline import SESSION_GAP_S
from . import color_wheel
from .gfx import rgb
from .ui import AUTO, DOWN, LEFT, RIGHT, TURN, UP, TextField, draw_bar, draw_key_hint, hold_status, keycap_size

ROOM_KEYWORDS = {
    'music': ['choose', 'select', 'use', 'play', 'instrument', 'fast', 'slow', 'letters', 'repeat', 'key',
              'marimba', 'accordion', 'ukulele', 'uke', 'glockenspiel', 'piano', 'electric'],
    'art': ['left', 'right', 'up', 'down', 'forward', 'go', 'move', 'walk', 'step', 'turn', 'color',
            'paint', 'write', 'lift', 'brush', 'pen', 'penup', 'pendown', 'repeat', 'colors', 'wheel'],
    'blocks': ['left', 'right', 'up', 'down', 'back', 'front', 'forward', 'go', 'repeat', 'color', 'colors', 'wheel'],
}
# Enter on a line ending in one of these opens the color wheel, which writes the color picked in its place.
WHEEL_WORDS = ('color', 'colors', 'wheel')


def _keys(notes: str) -> list:
    """Music's picture: the four rows of the grid, the tune's keys lit."""
    return ["".join(k.lower() if k.lower() in notes else "-" for k in row) for row in GRID_KEYS]


FOOTER_EM = 3.9   # the strip under Music's grid: its key hints, or the loop panel in their place

# Finished programs to pick with ↓, each with a picture of what it makes:
# rows of cells, '#' in the recipe's color, a letter in that key's color, '-' an unlit key.
RECIPES = {
    'art': [
        ("asdfghjkl", "", ["asdfghjkl"]),
        ("red repeat 4 forward 6 turn", "#ED1C24", ["#######", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#######"]),
        ("blue repeat 4 right 2 down 2", "#1F75FE", ["###......", "..#......", "..###....", "....#....", "....###..", "......#..", "......###", "........#"]),
        ("green repeat 3 up 3 right 2 down 3 right 2", "#48D370", ["###.###.###.", "#.#.#.#.#.#.", "#.#.#.#.#.#.", "#.###.###.##"]),
    ],
    'music': [
        ("asdfghjkl", "", _keys("asdfghjkl")),
        ("fast qwertyuiop", "", _keys("qwertyuiop")),
        ("repeat 3 asdf", "", _keys("asdf")),
        ("choose ukulele zxcvbnm", "", _keys("zxcvbnm")),
    ],
    'blocks': [
        ("red up 5", "#ED1C24", ["#", "#", "#", "#", "#"]),
        ("blue right 6", "#1F75FE", ["######"]),
        ("green repeat 4 right 1 up 1", "#48D370", ["...##", "..##.", ".##..", "##..."]),
        ("right hello", "", ["hello"]),
    ],
}
# The side column: words to use, a section at a time, each an example and a
# few words on what it does. COLORS lists the color words in their colors,
# ALL_COLORS every one of the extras too.
COLORS, ALL_COLORS = "colors", "all colors"
GUIDE = {
    'art': [
        ("Colors", [(COLORS, "")]),
        ("Move", [("right 5", RIGHT), ("up 3", UP)]),
        ("Turn", [("turn", TURN), ("forward 6", "where it points")]),
        ("Again", [("repeat 4 right 2 up 2", "")]),
        ("Letters", [("write hi", "")]),
    ],
    'music': [
        ("Notes", [("asdf", "play those keys"), ("1234", "drums")]),
        ("Speed", [("fast asdf", "quick"), ("slow asdf", "slow")]),
        ("Sound", [("choose ukulele", "or marimba, accordion, glockenspiel")]),
        ("Key", [("key g", "same keys, new notes")]),
        ("Again", [("repeat 3 asdf", "three times")]),
        ("Say", [("letters on", "keys say letters")]),
    ],
    'blocks': [
        ("Colors", [(COLORS, "")]),
        ("Build", [("right 5", f"a row {RIGHT}"), ("up 4", f"a tower {UP}"), ("back 3", "away from you"), ("front 3", "toward you")]),
        ("Letters", [("right hi", "a block per letter")]),
        ("Again", [("repeat 4 right 1 up 1", "stairs")]),
    ],
}
# What the side column shows instead while the code holds one of a topic's
# words: (words, heading, rows). COLORS stands for any color word.
_COLOR_TOPIC = ("Colors", [(ALL_COLORS, ""), ("color mint", "switch colors"), ("dark blue", "or light, bright, pale, neon")])
_AGAIN_ROWS = [("repeat 3 right 2, up 1", "commas: both, each time"), ("repeat right 1", "with no number: twice")]
TOPICS = {
    'art': [
        ("right left up down", "Move", [("right 5", f"{RIGHT} five steps"), ("left 5", f"{LEFT} five steps"), ("up 3", f"{UP} three steps"),
                                        ("down 3", f"{DOWN} three steps"), ("right", "one step"), ("red right 5 blue down 3", "")]),
        ("turn spin rotate face forward go move walk step back backward around", "Turn and go",
         [("forward 6", "the way it points"), ("turn left", ""), ("turn right", ""), ("turn around", ""), ("turn", "a turn to the right"),
          ("face up", "point up"), ("back 3", "go backwards"), ("go 4", "same as forward")]),
        ("brush pen lift penup pendown", "Brush", [("brush up", "move without painting"), ("brush down", "paint again"),
                                                   ("lift", "brush up, or down again"), ("right 2 brush up right 3", "leaves a gap")]),
        ("repeat", "Again", [("repeat 4 forward 6 turn", "a square")] + _AGAIN_ROWS),
        ("paint write", "Letters", [("asdf", "a color per key"), ("paint hi", "the same"), ("write hi", "real letters"),
                                    ("write on", "keep typing letters"), ("paint on", "back to colors")]),
        (COLORS, *_COLOR_TOPIC),
    ],
    'music': [
        ("choose select use instrument play marimba ukulele uke accordion glockenspiel", "Sound",
         [("choose marimba", ""), ("choose ukulele", ""), ("choose accordion", ""), ("choose glockenspiel", ""),
          ("play uke", "same as choose"), ("choose ukulele zxcv", "then play")]),
        ("fast slow", "Speed", [("fast asdf", "quick"), ("slow asdf", "slow"), ("fast 1234", "quick drums")]),
        ("key", "Key", [("key c", "where you start"), ("key g", "brighter"), ("key d", "brighter still"),
                        ("key f", "warmer"), ("key b flat", "warmer still")]),
        ("repeat", "Again", [("repeat 3 asdf", "three times"), ("repeat 2 asdf, jkl", "commas: both, each time"), ("repeat asdf", "with no number: twice")]),
        ("letters", "Say", [("letters on", "keys say letters"), ("letters off", "keys play notes")]),
    ],
    'blocks': [
        ("right left up down back front forward go", "Build",
         [("right 5", f"a row {RIGHT}"), ("left 5", f"a row {LEFT}"), ("up 4", f"a tower {UP}"), ("down 2", f"{DOWN} again"),
          ("back 3", "away from you"), ("front 3", "toward you"), ("forward 3", "keep going that way"), ("red up 3 blue right 2", "")]),
        ("repeat", "Again", [("repeat 4 right 1 up 1", "stairs")] + _AGAIN_ROWS),
        (COLORS, "Colors", [(ALL_COLORS, ""), ("red up 5", "a red tower"), ("dark blue", "or light, bright, pale, neon")]),
    ],
}
_TAKES_A_WAY = {"turn", "face", "brush", "pen"}


def guide_topic(room: str, text: str):
    """(heading, rows, word) for the last word in `text` that has a topic, else None.
    The way after turn, face or brush belongs to that word: "brush up" is Brush."""
    from ..color_mixing import COLOR_ADJECTIVES
    words = text.lower().split()
    for i, word in reversed(list(enumerate(words))):
        if i and words[i - 1] in _TAKES_A_WAY:
            continue
        is_color = word in COLOR_ADJECTIVES or get_content().exact_color(word)
        for triggers, heading, rows in TOPICS[room]:
            if word in triggers.split() or (is_color and triggers == COLORS):
                return heading, rows, word
    return None


PLACEHOLDER = f"Type code, or press {DOWN} to try one"
HUES = ['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'brown']
# A few of these show under the plain hues, different ones each time code opens.
MORE_COLORS = ['periwinkle', 'mint', 'gold', 'coral', 'sky', 'lime', 'turquoise', 'lavender', 'peach',
               'bubblegum', 'lemon', 'tangerine', 'silver', 'orchid', 'lilac', 'ruby', 'emerald', 'aqua']
SEPARATORS = ",.;|"           # they split a code line, so an echo leaves them out
ECHO_MAX = 40
_INSTRUMENT_NAMES = ['marimba', 'accordion', 'ukulele', 'uke', 'glockenspiel', 'piano']
_INSTRUMENT_PREFIX = re.compile(r'.*\b(?:choose|select|use|play|instrument)\s+\S*$', re.IGNORECASE)
_DEFAULT_COLORS = ['red', 'green', 'blue', 'yellow', 'purple']
_MAX_CONTEXT_RESULTS = 7
ICON_STAR = "\U000F04CE"  # nf-md-star
MAX_STRETCHES = 7
SCRUB_HOLD_S = 0.35       # an arrow held this long in Time Travel starts rewinding (or fast-forwarding)
SCRUB_SLOW = 6.0          # steps a second when a hold starts,
SCRUB_DOUBLE_S = 0.4      # doubling this often,
SCRUB_CROSS_S = 1.0       # up to crossing a whole session in this long
SCRUB_REST_S = 0.6        # a held arrow rests this long on each landmark


def keyword_autocomplete(room: str):
    keywords = set(ROOM_KEYWORDS[room])
    color_aware, instrument_aware = room == 'art', room == 'music'

    def fn(last_word: str, full_text: str = "") -> list:
        if color_aware and re.match(r'.*\bcolor\s+\S*$', full_text, re.IGNORECASE):
            content = get_content()
            if content.get_color(last_word):
                return [(last_word, content.get_color(last_word), "")]
            if not last_word:
                return [(w, content.get_color(w) or "", "") for w in _DEFAULT_COLORS]
            colors = [(w, c or "", "") for w, c, _e in content.search_words(last_word) if c]
            if not colors and len(last_word) == 1:
                colors = sorted((n, h, "") for n, h in content.colors.items() if n.startswith(last_word))
            return colors[:_MAX_CONTEXT_RESULTS]
        if instrument_aware and _INSTRUMENT_PREFIX.match(full_text):
            if last_word in _INSTRUMENT_NAMES:
                return [(last_word, "", "")]
            return [(n, "", "") for n in sorted(n for n in _INSTRUMENT_NAMES if n.startswith(last_word))[:_MAX_CONTEXT_RESULTS]]
        if last_word in keywords:
            return [(last_word, "", "")]
        return [(kw, "", "") for kw in sorted(kw for kw in keywords if kw.startswith(last_word))[:_MAX_CONTEXT_RESULTS]]
    return fn


@cache
def _named_colors(every: bool = False) -> dict:
    """name -> (hex, hls): the plain words echo writes, or with `every`, each named color too."""
    content = get_content()
    names = {n: content.get_color(n) for n in HUES + ['black', 'white', 'gray']}
    for adj in ("light", "dark"):
        names.update({f"{adj} {n}": m[0] for n in HUES if (m := content.get_modified_color(f"{adj} {n}"))})
    if every:
        names.update({n: h for n, h in content.colors.items() if n not in names})
    return {n: (h, _hls(h)) for n, h in names.items() if h}


def _hls(hex_color: str) -> tuple:
    return colorsys.rgb_to_hls(*(v / 255 for v in rgb(hex_color)[:3]))


def color_name(hex_color: str, every: bool = False) -> str:
    """The color word nearest a brush color, so code can say it. Hue counts
    most, but only as far as both colors have any. Ties go to plain words."""
    h, l, s = _hls(hex_color)
    names = _named_colors(every)

    def far(n):
        h2, l2, s2 = names[n][1]
        dh = min(abs(h - h2), 1 - abs(h - h2)) * min(s, s2)
        return (3 * dh) ** 2 + (l - l2) ** 2 + (0.5 * (s - s2)) ** 2
    return min(names, key=far)


class Echo:
    """Writes the code for what a kid just did by hand, a stroke at a time:
    `red right 5 down 2`, `right hello`, `qwerty`. The newest stroke waits in
    the line when code opens; it joins the room's code only once it runs.
    `pause` (seconds) ends a stroke on its own, for Music, where notes have
    no other edge."""

    def __init__(self, pause: float | None = None):
        self.pause = pause
        self.parts: list = []        # [word, tail]: tail a count, letters, or None for a lone word
        self.fresh = ""
        self._color = None
        self._at = 0.0

    def color(self, hex_color: str):
        self._touch()
        name = color_name(hex_color)
        if name != self._color:
            self._color = name
            self.parts.append([name, None])

    def step(self, way: str):
        """One block or cell laid going `way`."""
        self._touch()
        if self.parts and self.parts[-1][0] == way and isinstance(self.parts[-1][1], int):
            self.parts[-1][1] += 1
        else:
            self.parts.append([way, 1])

    def letter(self, way: str, ch: str):
        """A typed letter going `way`; '' for a bare run of letters (notes)."""
        self._touch()
        if ch in SEPARATORS:
            return
        if self.parts and self.parts[-1][0] == way and isinstance(self.parts[-1][1], str):
            self.parts[-1][1] += ch
        else:
            self.parts.append([way, ch])

    def word(self, text: str):
        self._touch()
        self.parts.append([text, None])

    def _touch(self):
        now = time.monotonic()
        if (self.pause and now - self._at > self.pause) or len(self.line()) > ECHO_MAX:
            self.flush()
        self._at = now

    def line(self) -> str:
        return " ".join(" ".join(str(p) for p in part if p not in (None, "")) for part in self.parts).strip()

    def flush(self):
        line, self.parts, self._color = self.line(), [], None
        if line:
            self.fresh = line

    def take(self) -> str:
        """The newest stroke, once: what the code line opens holding."""
        self.flush()
        line, self.fresh = self.fresh, ""
        return line

    def reset(self):
        self.parts, self.fresh, self._color = [], "", None


class SpaceHold:
    """Space in Music, Art and Blocks: a tap does the room thing, a hold (0.8s) toggles
    the code panel. A pending tap is flushed before any other key so fast
    typing like 'left 10' keeps its space."""

    def __init__(self, app, on_tap, on_hold):
        self.app = app
        self.on_tap, self.on_hold = on_tap, on_hold
        self.hold = HoldOrTap(HOLD_OR_TAP_THRESHOLD)
        self._down_at = None

    def route(self, action: ControlAction) -> bool:
        """True when consumed here; False when the room should treat Space normally."""
        if not self.app._code_panel_enabled:
            return False
        if action.is_down and not action.is_repeat:
            if action.arrow_held:
                return False
            self._down_at = time.monotonic()
            self.hold.on_down(self.app.timers.after, self._fire)
            self._ring = self.app.timers.every(1 / 30, self.app.invalidate)
            return True
        if action.is_down:
            return self.hold.is_pending or self.hold.fired
        self._stop_ring()
        if self.hold.on_up():
            self.on_tap()
        return True

    def other_key(self, flush: bool = True):
        """flush False drops the pending tap: Space was held as a modifier."""
        if self.hold.on_other_key():
            self._stop_ring()
            if flush:
                self.on_tap()

    def _fire(self):
        self._stop_ring()
        self.on_hold()

    def _stop_ring(self):
        self._down_at = None
        if getattr(self, "_ring", None):
            self._ring.stop()
            self._ring = None
        self.app.invalidate()

    def status(self, panel_open: bool):
        """ui.hold_status while Space is held, else None."""
        p = self.progress()
        return None if p is None else hold_status(p, "Space", ICON_ROBOT, f"{'close' if panel_open else 'write'} code")

    def progress(self):
        if self._down_at is None or not self.hold.is_pending:
            return None
        return min(1.0, (time.monotonic() - self._down_at) / HOLD_OR_TAP_THRESHOLD)


class CodePanel:
    """The 'Code →' line with autocomplete and recall, over a row of recipe
    cards that ↓ steps into, with a Close button left of them. It opens holding
    the code for the newest thing done by hand, if any."""

    kind = "code"
    CLOSE = -1   # self.card on the Close button

    def __init__(self, app, room: str, prefill: str = ""):
        self.app = app
        self.room = room
        keywords = set(ROOM_KEYWORDS[room])
        self.field = TextField(keyword_autocomplete(room), validator=lambda w: w.lower() in keywords, context_autocomplete=True)
        if prefill:
            self.field.set(prefill)
        self.note = (prefill, "Your code!  {Enter} again")
        self._replace = bool(prefill)   # the first letter typed starts fresh, like selected text
        self.recipes = RECIPES[room]
        self.card = None   # index of the picked recipe card while ↓ is in the cards
        self._back = 0     # how far up the room's code lines ↑ has stepped
        self.colors = _colors_markup(random.sample(MORE_COLORS, 2))
        self.all_colors = _colors_markup(MORE_COLORS)

    def _layout(self, g) -> tuple:
        """(margin, input px, box height, sub px, sub row height, gap, cards height),
        sized to the viewport like the rooms are. The sub row fits a keycap, not
        just a text line, so a lit Tab never crowds the box or the cards."""
        px, sub_px = g.em(1.2), g.em(0.85)
        return g.em(0.6), px, round(px * 1.9), sub_px, keycap_size(g, "X", sub_px)[1], g.em(0.45), g.em(4.2)

    def side_width(self, g) -> int:
        return g.em(16)

    def height(self, g) -> int:
        m, _, box_h, _, sub_h, gap, cards_h = self._layout(g)
        return 2 * m + box_h + gap + sub_h + gap + cards_h

    def set_correction(self, original: str, corrected: str):
        self.field.set_correction(original, corrected)

    async def handle(self, action):
        """Returns 'tab_fallthrough' when Tab had nothing to accept, 'close' on `exit`."""
        f = self.field
        if self._replace and isinstance(action, CharacterAction):
            f.clear()
        self._replace = False
        if isinstance(action, NavigationAction):
            if self.card is not None:
                self._pick(action.direction)
            elif action.direction == "left":
                f.move(-1)
            elif action.direction == "right":
                f.move(1)
            elif action.direction == "down" and not self._back and self.recipes:
                self._choose(0)
            else:
                self._recall(1 if action.direction == "up" else -1)
            return None
        closing, from_card, self.card = self.card == self.CLOSE, self.card is not None, None
        if isinstance(action, ControlAction):
            if not action.is_down:
                return None
            if action.action == "tab":
                return None if f.accept_autocomplete() else "tab_fallthrough"
            if action.action == "enter":
                if action.is_repeat:
                    return None
                if closing:
                    return "close"
                text = f.value.strip()
                if not text:
                    f.set(f.last_command)
                    return None
                if self._open_wheel(text):
                    return None
                f.clear()
                f.remember(text)
                self._back = 0
                if text.lower() == "exit":
                    return "close"
                self.app.run_code(self.room, [text])
                if from_card:
                    f.set(text)     # a recipe stays in the line, to change a number and run again
                    self.note = (text, "Change a number, then {Enter}")
            elif action.action == "backspace":
                f.backspace()
            elif action.action == "space":
                f.insert(" ")
            elif action.action == "escape" and not action.is_repeat:
                f.clear()
            return None
        if isinstance(action, CharacterAction) and not action.is_repeat:
            f.insert(action.char)
        return None

    def _open_wheel(self, text: str) -> bool:
        *head, last = text.split()
        if last.lower() not in WHEEL_WORDS:
            return False
        return color_wheel.open_on(self.app.room, on_close=lambda kept: self._took_color(text, head, kept))

    def _took_color(self, text: str, head: list, kept):
        """The wheel's color goes in as the nearest color word, and the brush takes
        that word's color so running the line paints what the wheel showed."""
        if kept is None:
            self.field.set(text)
            return
        if kept != AUTO:
            name = color_name(kept, every=True)
            self.app.room.set_brush_color(_named_colors(True)[name][0])
            head = [*head, name]
        self.field.set(" ".join(head) + " " if head else "")

    def arrow_hint(self) -> str:
        if self.card is not None:
            return f"Arrows pick  {LEFT} {RIGHT}   Back  {UP}"
        return f"Your code  {UP}   Examples  {DOWN}"

    def _choose(self, i: int):
        self.card = i
        self.field.set(self.recipes[i][0])

    def _pick(self, direction: str):
        """In the cards: ← → pick one or Close, ↑ goes back to the line with it."""
        if direction == "up":
            self.card = None
        elif direction in ("left", "right"):
            i = max(self.CLOSE, min(len(self.recipes) - 1, self.card + (1 if direction == "right" else -1)))
            if i == self.CLOSE:
                self.card = i
            else:
                self._choose(i)

    def _recall(self, step: int):
        """↑/↓ through the code typed in this room, which a save or Time Travel brings back with it."""
        lines = self.app.code_lines(self.room)
        self._back = max(0, min(len(lines), self._back + step))
        self.field.set(lines[-self._back] if self._back else "")

    def _sub(self) -> str | None:
        """The key hint under the line when the cards or a note own it, else None."""
        if self.card == self.CLOSE:
            return "{Enter} close"
        if self.card is not None:
            return "{Enter} run it"
        if self.note[0] and self.field.value == self.note[0]:
            return self.note[1]
        return None

    def draw(self, g, rect):
        m, px, box_h, sub_px, sub_h, gap, cards_h = self._layout(g)
        x, w = rect.x + g.em(0.8), rect.w - g.em(1.6)
        box = self.field.draw_boxed(g, x, rect.y + m, w, px, "Code", PLACEHOLDER)
        y = box.bottom + gap
        sub = self._sub()
        text_y = y + (sub_h - g.line_height(sub_px, "mono")) // 2
        self.field.draw_sub(g, box.x + round(px * 0.55), text_y, sub_px, hint=sub and ("", sub))
        y += sub_h + gap
        self._draw_cards(g, pygame.Rect(box.x, y, x + w - box.x, cards_h))
        self._draw_close_hint(g, pygame.Rect(x, y, box.x - x - g.em(0.4), cards_h))

    def _draw_close_hint(self, g, rect):
        """Under the label, beside the cards: a Close button the arrows reach, with Space's hold under it."""
        picked = self.card == self.CLOSE
        g.rect(P.FIELD, rect, radius=g.em(0.4))
        g.rect(P.ACCENT if picked else P.LINE, rect, width=3 if picked else 1, radius=g.em(0.4))
        px, key_px = g.em(0.78), g.em(0.6)
        key_px = min(key_px, key_px * (rect.w - g.em(1.1)) // keycap_size(g, "hold Space", key_px)[0])
        ink = P.TEXT if picked else P.MUTED
        g.draw_text("Close", px, rect.centerx, rect.centery - g.em(0.5), "mono-bold", ink, anchor="center")
        draw_key_hint(g, "{hold Space}", key_px, rect.centerx, rect.centery + g.em(0.55), color=P.MUTED, anchor="center")

    def _draw_cards(self, g, area):
        n = len(self.recipes)
        if not n:
            return
        gap = g.em(0.6)
        cw = (area.w - (n - 1) * gap) // n
        for i, (code, color, rows) in enumerate(self.recipes):
            card = pygame.Rect(area.x + i * (cw + gap), area.y, cw, area.h)
            picked = i == self.card
            g.rect(P.FIELD, card, radius=g.em(0.4))
            g.rect(P.ACCENT if picked else P.LINE, card, width=3 if picked else 1, radius=g.em(0.4))
            pad, px = g.em(0.55), g.em(0.78)
            side = card.h - 2 * pad
            wide = min(cw * 2 // 5, side * max(map(len, rows)) // len(rows))
            pic = pygame.Rect(card.x + pad, card.y + pad, max(side, wide), side)
            draw_picture(g, rows, color, pic)
            tx = pic.right + pad
            text_h = g.markup_size(code, px, "mono", card.right - pad - tx)[1]
            g.draw_markup(code, px, tx, card.centery - text_h // 2, "mono", P.TEXT if picked else P.MUTED, card.right - pad - tx)

    def draw_side(self, g, rect):
        """The word guide, top down until it runs out of room: all about the
        last code word typed, else a bit of everything. Each example is boxed
        like the code line, so it reads as something to type; its note sits
        beside it, or under it when it won't fit."""
        g.rect(P.LINE, (rect.x, rect.y + g.em(0.9), 1, rect.h - g.em(1.8)))
        topic = guide_topic(self.room, self.field.value)
        x, w = rect.x + g.em(0.95), rect.w - g.em(1.7)
        head_px, px = g.em(0.9), g.em(0.82)
        bottom = rect.bottom - g.em(0.45)
        y = rect.y + g.em(0.9)
        word = topic[2] if topic else None
        for heading, rows in [topic[:2]] if topic else GUIDE[self.room]:
            code, gloss = rows[0]
            first_h = g.line_height(px, "mono") if code in (COLORS, ALL_COLORS) else _example_height(g, code, gloss, px, w)
            if y + g.line_height(head_px, "mono-heavy") + g.em(0.35) + first_h > bottom:
                break
            y += g.draw_text(heading, head_px, x, y, "mono-heavy", P.ACCENT).h + g.em(0.35)
            for code, gloss in rows:
                if code in (COLORS, ALL_COLORS):
                    h = g.draw_markup(self.colors if code == COLORS else self.all_colors, px, x, y, "mono", P.TEXT, w, dim_to=P.SURFACE)
                elif y + (h := _example_height(g, code, gloss, px, w)) > bottom:
                    break
                else:
                    _draw_example(g, code, gloss, px, x, y, w, word)
                y += h + g.em(0.12)
            y += g.em(0.6)


def _example_layout(g, code: str, gloss: str, px: int, w: int) -> tuple:
    """(chip size, gloss px, gloss beside the chip?) for one guide example."""
    tw, th = g.measure(code, px, "mono")
    chip = (tw + round(px * 0.8), th + round(px * 0.1))
    gpx = px
    beside = not gloss or chip[0] + g.em(0.5) + g.markup_size(gloss, gpx, "sans")[0] <= w
    return chip, gpx, beside


def _example_height(g, code, gloss, px, w) -> int:
    chip, gpx, beside = _example_layout(g, code, gloss, px, w)
    return chip[1] if beside else chip[1] + g.em(0.1) + g.markup_size(gloss, gpx, "sans", w)[1]


def _draw_example(g, code, gloss, px, x, y, w, word=None):
    """`word`, the one being typed, is lit wherever the example uses it."""
    chip, gpx, beside = _example_layout(g, code, gloss, px, w)
    box = pygame.Rect((x, y), chip)
    words = code.split(" ")
    lit = word in words
    g.rect(P.FIELD, box, radius=g.em(0.25))
    g.rect(P.ACCENT if lit else P.HAIR, box, width=2 if lit else 1, radius=g.em(0.25))
    markup = " ".join(f"[bold {P.ACCENT}]{c}[/]" if c == word else c for c in words)
    tw, th = g.markup_size(markup, px, "mono")
    g.draw_markup(markup, px, box.centerx - tw // 2, box.centery - th // 2, "mono", P.TEXT)
    if gloss:
        gx, gy = (box.right + g.em(0.5), box.centery - g.line_height(gpx, "sans") // 2) if beside else (x + g.em(0.2), box.bottom + g.em(0.1))
        g.draw_markup(gloss, gpx, gx, gy, "sans", P.MUTED, x + w - gx)


def _colors_markup(more: list) -> str:
    """The plain hues, then `more` and a light one, each in its own color."""
    content = get_content()
    hues = [f"[{content.get_color(n)}]{n}[/]" for n in HUES + ['white'] + more if n != 'brown']
    light = f"[{content.get_modified_color('light blue')[0]}]light blue[/]"
    return " ".join(hues + [light, "[dim]...[/]"])


def draw_picture(g, rows: list, color: str, rect: pygame.Rect):
    """A recipe's picture, centered in `rect`: '#' cells in `color`, '-' a quiet key, letters in their key colors."""
    cell = max(1, min(rect.w // max(len(r) for r in rows), rect.h // len(rows)))
    ox = rect.x + (rect.w - cell * max(len(r) for r in rows)) // 2
    oy = rect.y + (rect.h - cell * len(rows)) // 2
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                g.rect({"#": color, "-": P.SURFACE}.get(ch) or get_key_color(ch), (ox + i * cell, oy + j * cell, cell, cell))


class LoopPanel:
    """One row in the footer Music already keeps under its grid, so the keys
    never shrink: a status pill, the time bar, then the keys that matter."""
    kind = "loop"

    def __init__(self, app, loop):
        self.app = app
        self.loop = loop

    def height(self, g) -> int:
        return g.em(FOOTER_EM)

    def draw(self, g, rect):
        st = self.loop.state
        if st not in (RECORDING, LOOPING):
            return
        recording = st == RECORDING
        px, pad, gap = g.em(0.92), g.em(1.6), g.em(1.4)
        cy = rect.bottom - g.em(1.4) - g.line_height(px, "mono") // 2
        color = P.DANGER if recording else P.PRIMARY
        label = "● Recording" if recording else f"{ICON_LOOP} Looping"
        w, h = g.measure(label, px, "mono-bold")
        pill = pygame.Rect(0, 0, w + round(px * 1.6), h + round(px * 0.7))
        pill.midleft = (rect.x + pad, cy)
        g.rect(color, pill, radius=pill.h // 2)
        g.draw_text(label, px, pill.centerx, pill.centery, "mono-bold", P.ON_PRIMARY, anchor="center")
        keys = "{Space} play it back   {Esc} stop" if recording else "keys play on top   {Esc} stop"
        right = draw_key_hint(g, keys, px, rect.right - pad, cy, color=P.MUTED, anchor="midright").x - gap
        if recording:
            right = g.draw_text(f"{int(self.loop.recording_remaining())}s", px, right, cy,
                                "mono-bold", P.DANGER, anchor="midright").x - g.em(0.8)
        bar_h = g.em(0.55)
        frac = self.loop.recording_progress() if recording else self.loop.loop_progress()
        draw_bar(g, pill.right + gap, cy - bar_h // 2, max(0, right - pill.right - gap), bar_h, frac, color, P.FIELD, bar_h // 2)


class TimeTravelBar:
    """Every step on one track, split into stretches where the kid took a
    break. A stretch is as wide as the log of its steps (today's twice that),
    so months of old history never crowd out today; the words say how long
    ago it really was. A star marks each moment the kid saved. The track only
    shows where you are: the arrows travel (see PurpleApp._press_time_travel)."""
    kind = "time"

    def __init__(self, app):
        self.app = app

    def height(self, g) -> int:
        return g.vh(11)

    def arrow_hint(self) -> str:
        return f"Hold to go fast  {LEFT} {RIGHT}"

    def draw(self, g, rect):
        index, times, saved = self.app.time_travel_position()
        if not times:
            return
        now = time.time()
        pad, cy = g.em(2), rect.y + g.vh(3)
        when = "Now" if index == len(times) - 1 else time_ago(times[index], now)
        if index in saved:
            when = f"{ICON_STAR}  Saved" + ("" if when == "Now" else f" {when.lower()}")
        g.draw_text(f"{ICON_TIME_TRAVEL}  Time Travel", g.vh(2.1), rect.x + pad, cy, "mono-heavy", P.ACCENT, anchor="midleft")
        g.draw_text(when, g.vh(2.6), rect.centerx, cy, "mono-heavy", P.TEXT, anchor="center")
        g.draw_text("Enter: keep this    Esc: never mind", g.vh(1.8), rect.right - pad, cy, "mono", P.MUTED, anchor="midright")
        track = pygame.Rect(rect.x + pad, rect.y + g.vh(5.2), rect.w - 2 * pad, g.vh(3))
        labels = self._draw_track(g, track, index, times, saved, stretches(times, now))
        last_left = track.right
        for label, left, right, here in reversed(labels):   # newest first, so Today always fits
            r = g.text(label, g.vh(1.7), "mono").get_rect(midtop=((left + right) // 2, track.bottom + g.vh(0.4)))
            if r.right < last_left - g.em(1) and r.x >= track.x:
                g.draw_text(label, g.vh(1.7), r.x, r.y, "mono-bold" if here else "mono", P.MUTED if here else P.DIM)
                last_left = r.x

    def _draw_track(self, g, track, index, times, saved, runs) -> list:
        """The arrows, stretches, stars and knob, drawn big and scaled down smooth.
        Returns each day's (label, left, right, holds the knob) span."""
        k = 3
        surf = pygame.Surface((track.w * k, track.h * k), pygame.SRCALPHA)
        cy, a, bar, knob = track.h * k // 2, g.vh(1) * k, g.vh(0.9) * k, g.vh(1.25) * k
        live = (index > 0, index < len(times) - 1)
        for d, x, on in ((-1, a, live[0]), (1, track.w * k - a, live[1])):
            pygame.draw.polygon(surf, rgb(P.ACCENT if on else P.FIELD), [(x + d * a, cy), (x - d * a * 0.7, cy - a), (x - d * a * 0.7, cy + a)])
        x0, x1 = 2 * a + g.em(1.5) * k, track.w * k - 2 * a - g.em(1.5) * k
        gap = g.em(1.2) * k
        weights = [(1 + math.log2(end - begin)) * (2 if label == "Today" else 1) for begin, end, label in runs]
        unit = (x1 - x0 - gap * (len(runs) - 1)) / sum(weights)
        x, knob_x, days, stars = x0, x0, [], []
        for (begin, end, label), w in zip(runs, weights):
            span = pygame.Rect(round(x), cy - bar // 2, round(w * unit), bar)
            steps = end - begin
            at = lambda i: span.centerx if steps == 1 else span.x + bar // 2 + (span.w - bar) * (i - begin) // (steps - 1)
            if begin <= index < end:
                knob_x = at(index)
            stars += [at(i) for i in saved if begin <= i < end]
            pygame.draw.rect(surf, rgb(P.FIELD), span, border_radius=bar // 2)
            past = span.w if index >= end - 1 else knob_x - span.x if index >= begin else 0
            if past:
                pygame.draw.rect(surf, rgb(P.LINE), (span.x, span.y, max(bar, past), bar), border_radius=bar // 2)
            here = begin <= index < end
            if days and days[-1][0] == label:
                days[-1] = (label, days[-1][1], span.right // k, days[-1][3] or here)
            else:
                days.append((label, span.x // k, span.right // k, here))
            x += w * unit + gap
        for sx in stars:
            _star(surf, sx, cy, knob * 1.15, P.ACCENT, P.ON_PRIMARY, k * 2)
        pygame.draw.circle(surf, rgb(P.ON_PRIMARY), (knob_x, cy), knob + k * 2)
        pygame.draw.circle(surf, rgb(P.TEXT), (knob_x, cy), knob)
        g.surface.blit(pygame.transform.smoothscale(surf, track.size), track)
        return [(label, track.x + left, track.x + right, here) for label, left, right, here in days]


def _star(surf, x, y, r, fill, edge, edge_w):
    """Five points, drawn over a slightly larger copy in edge so it stands off the bar."""
    for color, radius in ((edge, r + edge_w), (fill, r)):
        points = [(x + radius * (1 if j % 2 == 0 else 0.45) * math.sin(j * math.pi / 5),
                   y - radius * (1 if j % 2 == 0 else 0.45) * math.cos(j * math.pi / 5)) for j in range(10)]
        pygame.draw.polygon(surf, rgb(color), points)


def _ago(n: int, unit: str) -> str:
    return f"{n} {unit}{'' if n == 1 else 's'} ago"


def day_label(t, now) -> str:
    if t is None:
        return "Earlier"
    days = (date.fromtimestamp(now) - date.fromtimestamp(t)).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    for limit, unit, size in ((7, "day", 1), (60, "week", 7), (365, "month", 30)):
        if days < limit:
            return _ago(days // size, unit)
    return _ago(days // 365, "year")


def time_ago(t, now) -> str:
    day = day_label(t, now)
    if day != "Today":
        return day
    secs = now - t
    if secs < 60:
        return "Just now"
    return _ago(int(secs // 60), "minute") if secs < 3600 else _ago(int(secs // 3600), "hour")


def sessions(times, now) -> list:
    """[begin, end, day label] runs of steps, split at long pauses and new days."""
    runs = []
    for i, t in enumerate(times):
        label, prev = day_label(t, now), times[i - 1] if i else None
        if runs and runs[-1][2] == label and (t is None or prev is None or t - prev < SESSION_GAP_S):
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1, label])
    return runs


def stretches(times, now) -> list:
    """The sessions the track draws: the oldest merged into one "Earlier" until there are at most MAX_STRETCHES."""
    runs = sessions(times, now)
    while len(runs) > MAX_STRETCHES:
        oldest = runs.pop(0)
        runs[0][0], runs[0][2] = oldest[0], "Earlier"
    return runs


def landmarks(runs, more=()) -> list:
    """Where a held arrow rests: the very start, how each of the sessions `runs` ended, and `more`."""
    return sorted({0, *more, *(end - 1 for _, end, _ in runs)})


def scrub_rate(held_s: float, session_steps: int) -> float:
    """Steps a second for an arrow held this long: slow at first so a short hold is precise,
    doubling until it would cross the whole session in SCRUB_CROSS_S."""
    top = max(SCRUB_SLOW, session_steps / SCRUB_CROSS_S)
    return min(top, SCRUB_SLOW * 2 ** (held_s / SCRUB_DOUBLE_S))
