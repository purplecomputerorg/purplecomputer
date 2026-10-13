"""Panels that borrow the bottom of the viewport: the code line, the loop
station, and the Time Travel bar. Plus the Space hold-or-tap policy the
Music, Art and Blocks rooms share, and the echo that writes code for what a
kid does by hand.
"""

import colorsys
import re
import time
from functools import cache

import pygame

from .. import palette as P
from ..constants import HOLD_OR_TAP_THRESHOLD, ICON_LOOP, ICON_ROBOT, ICON_TIME_TRAVEL
from ..content import get_content
from ..keyboard import CharacterAction, ControlAction, HoldOrTap, NavigationAction
from ..loop_station import LOOPING, RECORDING
from ..palette import get_key_color
from .gfx import rgb
from .ui import TextField, draw_bar

ROOM_KEYWORDS = {
    'music': ['choose', 'select', 'use', 'play', 'instrument', 'fast', 'slow', 'letters', 'repeat',
              'marimba', 'accordion', 'ukulele', 'uke', 'glockenspiel', 'piano', 'electric'],
    'art': ['left', 'right', 'up', 'down', 'forward', 'go', 'move', 'walk', 'step', 'turn', 'color',
            'paint', 'write', 'lift', 'pen', 'penup', 'pendown', 'repeat'],
    'blocks': ['left', 'right', 'up', 'down', 'back', 'front', 'forward', 'go', 'repeat'],
}
# Finished programs to pick with ↓, each with a picture of what it makes:
# rows of cells, '#' in the recipe's color, a letter in that key's color
# (Music's notes, wrapped into a block).
RECIPES = {
    'art': [
        ("red repeat 4 forward 6 spin", "#ED1C24", ["#######", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#######"]),
        ("blue repeat 4 right 2 down 2", "#1F75FE", ["###......", "..#......", "..###....", "....#....", "....###..", "......#..", "......###", "........#"]),
        ("paint hello", "", ["hello"]),
        ("green repeat 3 up 3 right 2 down 3 right 2", "#48D370", ["###.###.###.", "#.#.#.#.#.#.", "#.#.#.#.#.#.", "#.###.###.##"]),
    ],
    'music': [
        ("asdfghjkl", "", ["asd", "fgh", "jkl"]),
        ("fast qwertyuiop", "", ["qwert", "yuiop"]),
        ("repeat 3 asdf", "", ["asdf", "asdf", "asdf"]),
        ("choose ukulele zxcvbnm", "", ["zxcv", "bnm."]),
    ],
    'blocks': [
        ("red up 5", "#ED1C24", ["#", "#", "#", "#", "#"]),
        ("blue right 6", "#1F75FE", ["######"]),
        ("green repeat 4 right 1 up 1", "#48D370", ["...##", "..##.", ".##..", "##..."]),
        ("right hello", "", ["hello"]),
    ],
}
# The side column: words to use, a section at a time, each an example and a
# few words on what it does. COLORS lists the color words in their colors.
COLORS = "colors"
GUIDE = {
    'art': [
        ("Colors", [(COLORS, "or dark blue")]),
        ("Move", [("right 5", "→ five steps"), ("up 3", "↑ three steps")]),
        ("Turn", [("forward 6", "the way it points"), ("spin", "turn to the right"), ("turn left", "")]),
        ("Again", [("repeat 4 ...", "do it four times")]),
        ("Letters", [("paint hi", "a color per letter"), ("write hi", "real letters")]),
    ],
    'music': [
        ("Notes", [("asdf", "play those keys"), ("1234", "drums")]),
        ("Speed", [("fast asdf", "quick"), ("slow asdf", "slow")]),
        ("Sound", [("choose ukulele", ""), ("choose accordion", ""), ("choose glockenspiel", "")]),
        ("Again", [("repeat 3 asdf", "three times")]),
        ("Say", [("letters on", "keys say letters")]),
    ],
    'blocks': [
        ("Colors", [(COLORS, "or dark blue")]),
        ("Build", [("right 5", "a row →"), ("up 4", "a tower ↑"), ("back 3", "away from you"), ("front 3", "toward you")]),
        ("Letters", [("right hi", "a block per letter")]),
        ("Again", [("repeat 4 right 1 up 1", "stairs")]),
    ],
}
PLACEHOLDER = "Type code, or press ↓ to try one"
HUES = ['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'brown']
SEPARATORS = ",.;|"           # they split a code line, so an echo leaves them out
ECHO_MAX = 40
_INSTRUMENT_NAMES = ['marimba', 'accordion', 'ukulele', 'uke', 'glockenspiel', 'piano']
_INSTRUMENT_PREFIX = re.compile(r'.*\b(?:choose|select|use|play|instrument)\s+\S*$', re.IGNORECASE)
_DEFAULT_COLORS = ['red', 'green', 'blue', 'yellow', 'purple']
_MAX_CONTEXT_RESULTS = 7
MAX_DOTS = 24


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
def _echo_colors() -> dict:
    content = get_content()
    names = {n: content.get_color(n) for n in HUES + ['black', 'white', 'gray']}
    for adj in ("light", "dark"):
        names.update({f"{adj} {n}": m[0] for n in HUES if (m := content.get_modified_color(f"{adj} {n}"))})
    return {n: _hls(h) for n, h in names.items() if h}


def _hls(hex_color: str) -> tuple:
    return colorsys.rgb_to_hls(*(v / 255 for v in rgb(hex_color)[:3]))


def color_name(hex_color: str) -> str:
    """The plain color word nearest a brush color, so code can say it. Hue
    counts most, but only as far as both colors have any."""
    h, l, s = _hls(hex_color)

    def far(n):
        h2, l2, s2 = _echo_colors()[n]
        dh = min(abs(h - h2), 1 - abs(h - h2)) * min(s, s2)
        return (3 * dh) ** 2 + (l - l2) ** 2 + (0.5 * (s - s2)) ** 2
    return min(_echo_colors(), key=far)


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

    def other_key(self):
        if self.hold.on_other_key():
            self._stop_ring()
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

    def progress(self):
        if self._down_at is None or not self.hold.is_pending:
            return None
        return min(1.0, (time.monotonic() - self._down_at) / HOLD_OR_TAP_THRESHOLD)


class CodePanel:
    """The 'Code →' line with autocomplete and recall, over a row of recipe
    cards that ↓ steps into. It opens holding the code for the newest thing
    done by hand, if any."""

    kind = "code"

    def __init__(self, app, room: str, prefill: str = ""):
        self.app = app
        self.room = room
        keywords = set(ROOM_KEYWORDS[room])
        self.field = TextField(keyword_autocomplete(room), validator=lambda w: w.lower() in keywords, context_autocomplete=True)
        if prefill:
            self.field.set(prefill)
        self.note = (prefill, "That's the code for what you just made! Enter does it again, or type something new.")
        self._replace = bool(prefill)   # the first letter typed starts fresh, like selected text
        self.recipes = RECIPES[room]
        self.card = None   # index of the picked recipe card while ↓ is in the cards
        self._back = 0     # how far up the room's code lines ↑ has stepped

    def _layout(self, g) -> tuple:
        """(margin, input px, box height, sub px, gap, cards height) in pixels."""
        px = g.vh(2.6)
        return g.vh(1.3), px, round(px * 1.9), g.vh(1.9), g.vh(0.7), g.vh(9)

    def side_width(self, g) -> int:
        return g.vw(21)

    def height(self, g) -> int:
        m, _, box_h, sub_px, gap, cards_h = self._layout(g)
        return 2 * m + box_h + gap + g.line_height(sub_px, "mono") + gap + cards_h

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
        from_card, self.card = self.card is not None, None
        if isinstance(action, ControlAction):
            if not action.is_down:
                return None
            if action.action == "tab":
                return None if f.accept_autocomplete() else "tab_fallthrough"
            if action.action == "enter":
                if action.is_repeat:
                    return None
                text = f.value.strip()
                if not text:
                    f.set(f.last_command)
                    return None
                f.clear()
                f.remember(text)
                self._back = 0
                if text.lower() == "exit":
                    return "close"
                self.app.run_code(self.room, [text])
                if from_card:
                    f.set(text)     # a recipe stays in the line, to change a number and run again
                    self.note = (text, "Now change a number and press Enter again!")
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

    def _choose(self, i: int):
        self.card = i
        self.field.set(self.recipes[i][0])

    def _pick(self, direction: str):
        """In the cards: ← → pick one, ↑ goes back to the line with it."""
        if direction == "up":
            self.card = None
        elif direction in ("left", "right"):
            self._choose(max(0, min(len(self.recipes) - 1, self.card + (1 if direction == "right" else -1))))

    def _recall(self, step: int):
        """↑/↓ through the code typed in this room, which a save or Time Travel brings back with it."""
        lines = self.app.code_lines(self.room)
        self._back = max(0, min(len(lines), self._back + step))
        self.field.set(lines[-self._back] if self._back else "")

    def _sub(self) -> str:
        if self.card is not None:
            return "[dim]← → pick one    Enter: run it    ↑ back to typing[/]"
        if self.note[0] and self.field.value == self.note[0]:
            return f"[dim]{self.note[1]}[/]"
        return self.field.autocomplete_markup or f"[dim]{self.field.recall_text()}[/]"

    def draw(self, g, rect):
        m, px, box_h, sub_px, gap, cards_h = self._layout(g)
        x, w = rect.x + g.vw(1), rect.w - g.vw(2)
        y = rect.y + m
        box = self.field.draw_boxed(g, x, y, w, px, "Code", PLACEHOLDER)
        y = box.bottom + gap
        sub_x = box.x + round(px * 0.55)
        note = g.draw_text(f"{ICON_ROBOT} Hold Space: close code", sub_px, x + w, y, "mono", P.DIM, anchor="topright")
        g.draw_markup(self._sub(), sub_px, sub_x, y, "mono", P.MUTED, note.x - g.vw(2) - sub_x, dim_to=P.SURFACE)
        y += g.line_height(sub_px, "mono") + gap
        self._draw_cards(g, pygame.Rect(box.x, y, x + w - box.x, cards_h))

    def _draw_cards(self, g, area):
        n = len(self.recipes)
        if not n:
            return
        gap = g.vw(1)
        cw = (area.w - (n - 1) * gap) // n
        for i, (code, color, rows) in enumerate(self.recipes):
            card = pygame.Rect(area.x + i * (cw + gap), area.y, cw, area.h)
            picked = i == self.card
            g.rect(P.FIELD, card, radius=g.em(0.4))
            g.rect(P.ACCENT if picked else P.LINE, card, width=3 if picked else 1, radius=g.em(0.4))
            pad, px = g.vh(1.2), g.vh(1.75)
            pic = pygame.Rect(card.x + pad, card.y + pad, card.h - 2 * pad, card.h - 2 * pad)
            draw_picture(g, rows, color, pic)
            tx = pic.right + pad
            text_h = g.markup_size(code, px, "mono", card.right - pad - tx)[1]
            g.draw_markup(code, px, tx, card.centery - text_h // 2, "mono", P.TEXT if picked else P.MUTED, card.right - pad - tx)


    def draw_side(self, g, rect):
        """The word guide, top down until it runs out of room. A line whose
        word is in the code being typed lights up."""
        g.rect(P.LINE, (rect.x, rect.y + g.vh(2), 1, rect.h - g.vh(4)))
        typed = set(self.field.value.lower().split())
        x, w = rect.x + g.vw(1.2), rect.w - g.vw(2.2)
        head_px, px = g.vh(1.6), g.vh(1.85)
        y = rect.y + g.vh(2)
        for heading, rows in GUIDE[self.room]:
            if y + g.line_height(head_px, "mono") + g.line_height(px, "mono") > rect.bottom - g.vh(1):
                break
            y += g.draw_text(heading, head_px, x, y, "mono-bold", P.ACCENT).h + g.vh(0.3)
            for code, gloss in rows:
                markup = (_colors_markup() if code == COLORS else code) + (f"  [dim]{gloss}[/]" if gloss else "")
                h = g.markup_size(markup, px, "mono", w)[1]
                if y + h > rect.bottom - g.vh(1):
                    break
                if code.split()[0] in typed:
                    g.rect(P.FIELD, (x - g.vw(0.4), y - 2, w + g.vw(0.8), h + 4), radius=g.vh(0.6))
                y += g.draw_markup(markup, px, x, y, "mono", P.TEXT, w, dim_to=P.SURFACE)
            y += g.vh(1.4)


@cache
def _colors_markup() -> str:
    content = get_content()
    return " ".join(f"[{content.get_color(n)}]{n}[/]" for n in HUES + ['white'] if n != 'brown')


def draw_picture(g, rows: list, color: str, rect: pygame.Rect):
    """A recipe's picture, centered in `rect`: '#' cells in `color`, letters in their key colors."""
    cell = max(1, min(rect.w // max(len(r) for r in rows), rect.h // len(rows)))
    ox = rect.x + (rect.w - cell * max(len(r) for r in rows)) // 2
    oy = rect.y + (rect.h - cell * len(rows)) // 2
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != ".":
                g.rect(color if ch == "#" else get_key_color(ch), (ox + i * cell, oy + j * cell, cell, cell))


class LoopPanel:
    kind = "loop"

    def __init__(self, app, loop):
        self.app = app
        self.loop = loop

    def height(self, g) -> int:
        return g.vh(12)

    def draw(self, g, rect):
        st = self.loop.state
        cx, y = rect.centerx, rect.y + g.vh(1.5)
        if st == RECORDING:
            head = f"● Recording, {int(self.loop.recording_remaining())}s left"
            frac = self.loop.recording_progress()
            action = "Play any keys    Space: play it back    Esc: exit"
        elif st == LOOPING:
            head = f"{ICON_LOOP} Looping and recording"
            frac = self.loop.loop_progress()
            action = "Play on top    Esc: exit"
        else:
            return
        g.draw_text(head, g.vh(2.6), cx, y, "mono-heavy", P.DANGER, anchor="midtop")
        bw = rect.w // 2
        by = y + g.vh(4)
        if st == RECORDING:
            draw_bar(g, cx - bw // 2, by, bw, g.vh(1.4), frac, P.DANGER)
        else:
            draw_bar(g, cx - bw // 2, by, bw, g.vh(1.4), 0)
            g.rect(P.TEXT, (cx - bw // 2 + int(bw * frac) - g.vw(0.3), by - 2, g.vw(0.6), g.vh(1.4) + 4))
        g.draw_text(action, g.vh(1.9), cx, by + g.vh(3.2), "mono", P.MUTED, anchor="midtop")


class TimeTravelBar:
    kind = "time"

    def __init__(self, app):
        self.app = app

    def height(self, g) -> int:
        return g.vh(13)

    def dots_markup(self) -> str:
        """One dot per step over a window of the newest MAX_DOTS steps."""
        index, total = self.app.time_travel_position()
        count = min(total, MAX_DOTS)
        start = min(max(0, total - count), index)
        filled = index - start + 1 if total else 0
        track = ("● " * filled + "○ " * (count - filled)).rstrip()
        if start > 0:
            track = f"[dim]⋯[/] {track}"
        if start + count < total:
            track = f"{track} [dim]⋯[/]"
        left = "[dim]◀ back in time[/]" if index <= 0 else "◀ back in time"
        right = "[dim]forward ▶[/]" if index >= total - 1 else "forward ▶"
        return f"{left}   {track}   {right}"

    def draw(self, g, rect):
        cx = rect.centerx
        g.draw_text(f"{ICON_TIME_TRAVEL} Time Travel", g.vh(2.6), cx, rect.y + g.vh(1.5), "mono-heavy", P.TEXT, anchor="midtop")
        px = g.vh(2.4)
        markup = self.dots_markup()
        w = g.markup_size(markup, px)[0]
        g.draw_markup(markup, px, cx - w // 2, rect.y + g.vh(5.5), "mono-bold", P.PRIMARY, dim_to=P.SURFACE)
        g.draw_text("Enter: keep this    Esc: never mind", g.vh(1.9), cx, rect.bottom - g.vh(1.4), "mono", P.MUTED, anchor="midbottom")
