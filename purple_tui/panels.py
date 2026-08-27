"""Panels that borrow the bottom of the viewport: the code line, the loop
station, and the Time Travel bar. Plus the Space hold-or-tap policy the
Music and Art rooms share.
"""

import re
import time

from . import palette as P
from .constants import HOLD_OR_TAP_THRESHOLD
from .content import get_content
from .keyboard import CharacterAction, ControlAction, HoldOrTap, NavigationAction
from .loop_station import LOOPING, RECORDING
from .ui import HintRotator, TextField, draw_bar

ROOM_KEYWORDS = {
    'music': ['choose', 'select', 'use', 'play', 'instrument', 'fast', 'slow', 'letters', 'repeat',
              'marimba', 'accordion', 'ukulele', 'uke', 'glockenspiel', 'piano', 'electric'],
    'art': ['left', 'right', 'up', 'down', 'forward', 'go', 'move', 'walk', 'step', 'turn', 'color',
            'paint', 'write', 'lift', 'pen', 'penup', 'pendown', 'repeat'],
}
ROOM_HINTS = {
    'music': [
        "Try: abcdefg  •  cdefgagf",
        "Try: choose ukulele  •  choose piano",
        "Try: slow asdf  •  fast cdefga  •  letters on",
        "Try: fast abcdefg slow asdf",
        "Try: repeat 3 abcdefg  •  repeat 4 cdefgagf",
    ],
    'art': [
        "Try: red forward 10  •  blue up 6",
        "Try: green down 5 right 5  •  pink turn left forward 8",
        "Try: yellow forward 8 spin forward 8  •  paint hello",
        "Try: purple repeat 4 forward 8 spin",
        "Try: orange repeat 4 right 4 down 4",
        "Try: repeat 36 forward 5 spin",
    ],
}
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


class SpaceHold:
    """Space in Music and Art: a tap does the room thing, a hold (0.8s) toggles
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
    """The 'Code →' line with autocomplete, recall, and rotating hints."""

    kind = "code"

    def __init__(self, app, room: str):
        self.app = app
        self.room = room
        keywords = set(ROOM_KEYWORDS[room])
        self.field = TextField(keyword_autocomplete(room), validator=lambda w: w.lower() in keywords, context_autocomplete=True)
        self.hints = HintRotator(ROOM_HINTS[room])

    def height(self, g) -> int:
        return 3 * self.app.unit    # the Art header and hint rows it replaces, so the grid keeps its size

    def set_correction(self, original: str, corrected: str):
        self.field.set_correction(original, corrected)

    async def handle(self, action):
        """Returns 'tab_fallthrough' when Tab had nothing to accept, 'close' on `exit`."""
        f = self.field
        if isinstance(action, NavigationAction):
            if action.direction == "left":
                f.move(-1)
            elif action.direction == "right":
                f.move(1)
            return None
        if isinstance(action, ControlAction):
            if not action.is_down:
                return None
            if action.action == "tab":
                return None if f.accept_autocomplete() else "tab_fallthrough"
            if action.action == "enter":
                if action.is_repeat:
                    return None
                text = f.value.strip()
                self.hints.advance()
                if not text:
                    f.set(f.last_command)
                    return None
                f.clear()
                f.remember(text)
                if text.lower() == "exit":
                    return "close"
                self.app.run_code(self.room, [text])
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

    def draw(self, g, rect):
        """Two lines: the code line, then autocomplete, the recall hint, or a
        'Try:' idea, whichever applies."""
        px, sub_px = g.vh(2.8), g.vh(1.9)
        y = rect.y + (rect.h - g.line_height(px, "mono") - g.line_height(sub_px, "mono")) // 2
        self.field.draw(g, rect.x + g.vw(1), y, rect.w - g.vw(2), px, "Code")
        y += g.line_height(px, "mono")
        sub = self.field.autocomplete_markup or f"[dim]{self.field.recall_text() or self.hints.current}[/]"
        g.draw_markup(sub, sub_px, self.field.text_x(g, rect.x + g.vw(1), px, "Code"), y, "mono", P.MUTED, rect.w - g.vw(26), dim_to=P.SURFACE)
        g.draw_text("🤖 Hold Space: close code", sub_px, rect.right - g.vw(1), y + g.line_height(sub_px, "mono") // 2, "mono", P.DIM, anchor="midright")


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
            head = "🔁 Looping and recording"
            frac = self.loop.loop_progress()
            action = "Play on top    Esc: exit"
        else:
            return
        g.draw_text(head, g.vh(2.6), cx, y, "sans-heavy", P.DANGER, anchor="midtop")
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
        g.draw_text("⏪ Time Travel", g.vh(2.6), cx, rect.y + g.vh(1.5), "sans-heavy", P.TEXT, anchor="midtop")
        px = g.vh(2.4)
        markup = self.dots_markup()
        w = g.markup_size(markup, px)[0]
        g.draw_markup(markup, px, cx - w // 2, rect.y + g.vh(5.5), "sans-bold", P.PRIMARY, dim_to=P.SURFACE)
        g.draw_text("Enter: keep this    Esc: never mind", g.vh(1.9), cx, rect.bottom - g.vh(1.4), "mono", P.MUTED, anchor="midbottom")
