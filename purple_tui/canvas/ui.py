"""Small UI primitives shared by every screen: timers, a text field with
autocomplete, dialogs, pickers, toasts, and the hold bar.

Nothing here knows about rooms. Screens compose these and draw with Gfx.
"""

import asyncio
import functools
import re
import time

import pygame

from .. import palette as P
from ..constants import ICON_ROBOT
from .gfx import Gfx, mix, rgb
from ..keyboard import CharacterAction, ControlAction, NavigationAction

# Heavy arrows: Plex's ← → ↑ ↓ are too thin to read at hint size.
LEFT, UP, DOWN, RIGHT = "⬅⬆⬇➡"

# ----------------------------------------------------------------------------
# Timers (asyncio-backed; HoldOrTap needs an object with .stop())
# ----------------------------------------------------------------------------


class Handle:
    def __init__(self, timers, delay, fn, repeat):
        self._timers, self._delay, self._fn, self._repeat = timers, delay, fn, repeat
        self._h = None
        self._arm()

    def _arm(self):
        self._h = self._timers.loop.call_later(self._delay, self._fire)
        self._timers.active.add(self)

    def _fire(self):
        self._h = None
        if self._repeat:
            self._arm()
        else:
            self._timers.active.discard(self)
        self._fn()

    def stop(self):
        if self._h:
            self._h.cancel()
            self._h = None
        self._timers.active.discard(self)

    def reset(self):
        self.stop()
        self._arm()

    @property
    def active(self) -> bool:
        return self._h is not None


class Timers:
    def __init__(self):
        self.loop = None
        self.active: set = set()

    def bind(self, loop):
        self.loop = loop

    def after(self, delay: float, fn) -> Handle:
        return Handle(self, max(0.0, delay), fn, repeat=False)

    def every(self, period: float, fn) -> Handle:
        return Handle(self, period, fn, repeat=True)

    def intervals(self) -> list:
        """(period, callback name) for every repeating timer that is armed."""
        return [(h._delay, getattr(h._fn, "__qualname__", repr(h._fn))) for h in self.active if h._repeat]

    def call_from_thread(self, fn, *args):
        self.loop.call_soon_threadsafe(fn, *args)


# ----------------------------------------------------------------------------
# Text field with pluggable autocomplete (was CodeInput / InlineInput)
# ----------------------------------------------------------------------------

_COMMON_2CHAR = {'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is', 'it', 'me', 'my',
                 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we', 'hi', 'oh', 'ok'}
MATH_OPERATORS = {'+', '-', '×', '÷'}
MAX_RECALL_LEN = 40
CANCELLED = object()  # a picker closed with Esc, distinct from choosing None


class TextField:
    """One-line editable text with a cursor, word underlining, and
    autocomplete suggestions of (word, color_hex, emoji)."""

    def __init__(self, autocomplete_fn=None, validator=None, context_autocomplete=False, marks=None):
        self.value = ""
        self.cursor = 0
        self._autocomplete_fn = autocomplete_fn
        self._validator = validator
        self._context = context_autocomplete
        self._marks = marks  # value -> [(start, end)] spans drawn as accent pills
        self.matches: list = []
        self.match_index = 0
        self.exact_display = ""
        self.last_command = ""
        self._correction = None

    # --- editing ---
    def set(self, value: str, cursor: int | None = None):
        self.value = value
        self.cursor = len(value) if cursor is None else max(0, min(cursor, len(value)))
        self._check_autocomplete()

    def insert(self, text: str):
        self.set(self.value[:self.cursor] + text + self.value[self.cursor:], self.cursor + len(text))

    def insert_operator(self, ch: str):
        """Math operators get spaces around them unless one is already there."""
        before = self.value[:self.cursor]
        if before and before[-1] not in " +-×÷(":
            self.insert(f" {ch} ")
        else:
            self.insert(ch)

    def backspace(self):
        if self.cursor > 0:
            self.set(self.value[:self.cursor - 1] + self.value[self.cursor:], self.cursor - 1)

    def move(self, delta: int):
        self.cursor = max(0, min(self.cursor + delta, len(self.value)))

    def clear(self):
        self.set("")

    def take(self) -> str:
        """Return the value and clear the field (Enter)."""
        v = self.value
        self.clear()
        return v

    # --- recall hint (was RecallHint) ---
    def remember(self, command: str):
        self.last_command = command

    def set_correction(self, original: str, corrected: str):
        self._correction = (original, corrected)
        self.last_command = corrected

    def recall_text(self, keycap: bool = False) -> str:
        """Dim hint under an empty field; a correction shows once. keycap
        writes Enter as {Enter} for draw_key_hint."""
        if self.value or not self.last_command:
            return ""
        if self._correction:
            orig, corr = self._correction
            self._correction = None
            return _truncate(f"{orig} → {corr}")
        return f"{'{Enter}' if keycap else 'Enter to'} try again: {_truncate(self.last_command)}"

    # --- autocomplete (logic unchanged from CodeInput) ---
    def _check_autocomplete(self):
        self.matches, self.match_index, self.exact_display = [], 0, ""
        if not self._autocomplete_fn or not self.value.strip():
            return
        text = self.value.lower()
        m = re.search(r'([a-z]+)$', text)
        last_word = m.group(1) if m else ""
        if len(last_word) < 2 or last_word in _COMMON_2CHAR:
            results = self._autocomplete_fn(last_word, text) if self._context else []
            if not results:
                return
        else:
            results = self._autocomplete_fn(last_word, text)
        exact = [r for r in results if r[0] == last_word]
        if exact:
            _, color_hex, emoji = exact[0]
            parts = ([emoji] if emoji else []) + ([f"[{color_hex}]██[/]"] if color_hex else [])
            self.exact_display = " ".join(parts)
            return
        self.matches = [r for r in results if r[0] != last_word][:5]

    def accept_autocomplete(self) -> bool:
        if not self.matches:
            return False
        selected = self.matches[self.match_index][0]
        if self.value.endswith(" "):
            value = self.value + selected + " "
        else:
            words = self.value.split()
            words[-1] = selected
            value = " ".join(words) + " "
        self.set(value)
        self.matches, self.exact_display = [], ""
        return True

    @property
    def autocomplete_markup(self) -> str:
        if self.exact_display or not self.matches:
            return self.exact_display
        return self.match_words + "   [dim]⇥ Tab[/]"

    @property
    def match_words(self) -> str:
        parts = []
        for word, color_hex, emoji in self.matches:
            s = f"[dim]{word}[/]"
            if emoji:
                s += f" {emoji}"
            if color_hex:
                s += f" [{color_hex}]██[/]"
            parts.append(s)
        return "   ".join(parts)

    # --- drawing ---
    def text_x(self, g: Gfx, x: int, px: int, label: str = "Type", label_px: int | None = None,
               gap: int | None = None) -> int:
        """Where typed text starts, so hints under the field can line up with it."""
        return x + g.measure(f"{label} →", label_px or px, "mono-heavy")[0] + (gap if gap is not None else px // 2)

    def draw(self, g: Gfx, x: int, y: int, width: int, px: int, label: str = "Type", label_px: int | None = None,
             gap: int | None = None, arrow: str = "→") -> pygame.Rect:
        """'Label →  text▌' in the mono face; returns the rect used.
        label_px lets the label sit a step larger than the typed text; gap
        sets the space between label and text (a boxed field needs more)."""
        mid = y + g.line_height(px, "mono") // 2
        lpx = label_px or px
        head = g.draw_text(f"{label} ", lpx, x, mid, "mono-bold", P.ACCENT, anchor="midleft").right
        cell = g.measure("→", lpx, "mono-bold")[0]
        apx = min(lpx, lpx * cell * 3 // 2 // max(1, g.measure(arrow, lpx, "mono-bold")[0]))
        g.draw_text(arrow, apx, head + cell // 2, mid, "mono-bold", P.ACCENT, anchor="center")
        tx = self.text_x(g, x, px, label, label_px, gap)
        shown, start = self._visible_slice(g, px, width - (tx - x) - px)
        before = shown[:self.cursor - start]
        g.draw_text(shown, px, tx, y, "mono", P.TEXT)
        if self._validator:
            self._underline(g, shown, px, tx, y)
        if self._marks:
            self._draw_marks(g, shown, start, px, tx, y)
        cx = tx + g.measure(before, px, "mono")[0] if before else tx
        caret = (cx, y + px // 8, max(2, int(px * 0.55)), int(px * 1.05))
        g.draw_caret(caret, lambda: g.rect(P.CARET, caret))
        return pygame.Rect(x, y, width, g.line_height(px, "mono"))

    def traced(self, ideas) -> str:
        """The first idea the text so far starts, if any."""
        v = self.value
        if not v or self.cursor != len(v):
            return ""
        return next((i for i in ideas if i.lower().startswith(v.lower())), "")

    def draw_boxed(self, g: Gfx, x: int, y: int, width: int, px: int, label: str, placeholder: str = "",
                   ideas: tuple = (), arrow: str = "→") -> pygame.Rect:
        """The label, then a box out to `width` holding the text, with
        `placeholder` faint inside while it is empty and `ideas` as chips on
        its right until the text reaches them; the chip being typed lights
        up as it is. Returns the box."""
        label_px, gap, pad = round(px * 1.15), round(px * 1.1), round(px * 0.55)
        tx = self.text_x(g, x, px, label, label_px, gap)
        box = pygame.Rect(tx - pad, y, x + width - tx + pad, round(px * 1.9))
        g.rect(P.FIELD, box, radius=round(px * 0.4))
        g.rect(P.LINE, box, width=1, radius=round(px * 0.4))
        ty = box.centery - g.line_height(px, "mono") // 2
        right = box.right - pad
        if placeholder and not self.value:
            hx = tx + px
            g.draw_text(_fit(g, placeholder, px, right - hx), px, hx, ty, "mono", P.DIM)
        self.draw(g, x, ty, right - x, px, label, label_px, gap, arrow)
        if ideas:
            self._draw_ideas(g, ideas, tx + g.measure(self.value, px, "mono")[0] + px, box, right, px)
        return box

    def _draw_ideas(self, g: Gfx, ideas, left: int, box: pygame.Rect, right: int, px: int):
        """'Try' then the ideas as chips, flush against `right`; the first
        ones drop out as the text grows toward them, the one being typed last."""
        cpx = round(px * 0.75)
        cpad, gap = round(cpx * 0.7), round(cpx * 0.5)
        try_w = g.measure("Try", cpx, "mono-bold")[0]
        typing = self.traced(ideas)
        chips = [(i, g.measure(i, cpx, "mono")[0] + 2 * cpad) for i in sorted(ideas, key=lambda i: i == typing)]
        while chips and right - try_w - sum(w + gap for _, w in chips) < left:
            chips.pop(0)
        if not chips:
            return
        x = right - try_w - sum(w + gap for _, w in chips)
        g.draw_text("Try", cpx, x, box.centery, "mono-bold", P.DIM, anchor="midleft")
        x += try_w + gap
        h = round(cpx * 1.6)
        for idea, w in chips:
            chip = pygame.Rect(x, box.centery - h // 2, w, h)
            g.rect(P.SURFACE, chip, radius=h // 2)
            done = len(self.value) if idea == typing else 0
            tx = g.draw_text(idea[:done], cpx, chip.x + cpad, chip.centery, "mono", P.CARET, anchor="midleft").right if done else chip.x + cpad
            g.draw_text(idea[done:], cpx, tx, chip.centery, "mono", P.MUTED, anchor="midleft")
            x += w + gap

    def _visible_slice(self, g, px, avail):
        """Keep the cursor on screen for long lines by scrolling the start."""
        if g.measure(self.value, px, "mono")[0] <= avail or not self.value:
            return self.value, 0
        cw = g.measure("M", px, "mono")[0] or 1
        fit = max(8, avail // cw)
        start = max(0, self.cursor - fit + 1)
        return self.value[start:start + fit], start

    def _draw_marks(self, g, shown, start, px, tx, y):
        lh = g.line_height(px, "mono")
        for a, b in self._marks(self.value):
            a, b = max(a - start, 0), min(b - start, len(shown))
            if a < b:
                x0 = tx + g.measure(shown[:a], px, "mono")[0]
                w = g.measure(shown[a:b], px, "mono")[0]
                g.rect(mix(P.FIELD, P.PRIMARY, 0.35), (x0 - px // 12, y + lh // 10, w + px // 6, lh - lh // 5), radius=px // 6)
                g.draw_text(shown[a:b], px, x0, y, "mono", P.ACCENT)

    def _underline(self, g, shown, px, tx, y):
        lh = g.line_height(px, "mono")
        for m in re.finditer(r'[a-z]+', shown.lower()):
            if self._validator(m.group()):
                x0 = tx + g.measure(shown[:m.start()], px, "mono")[0]
                x1 = tx + g.measure(shown[:m.end()], px, "mono")[0]
                g.rect(P.MUTED, (x0, y + lh - 2, x1 - x0, 2))


def _truncate(text: str) -> str:
    return text[:MAX_RECALL_LEN - 1] + "…" if len(text) > MAX_RECALL_LEN else text


def _fit(g: Gfx, text: str, px: int, avail: int) -> str:
    """`text` cut with an ellipsis to fit `avail` pixels of the mono face."""
    while text and g.measure(text, px, "mono")[0] > avail:
        text = text[:-2] + "…"
    return text


class HintRotator:
    """The suggestion that advances on Enter and every minute, unless held."""

    CYCLE_SECONDS = 60

    def __init__(self, hints: list):
        self.hints = hints
        self.index = 0
        self._stamp = time.monotonic()

    def current(self, hold: bool = False):
        if not self.hints:
            return ""
        if not hold and time.monotonic() - self._stamp > self.CYCLE_SECONDS:
            self.advance()
        return self.hints[self.index]

    def advance(self):
        if self.hints:
            self.index = (self.index + 1) % len(self.hints)
        self._stamp = time.monotonic()


# ----------------------------------------------------------------------------
# Overlays: anything that takes the keyboard away from the room
# ----------------------------------------------------------------------------


class Overlay:
    """A screen stacked over the rooms. The top overlay owns every key."""

    scrim = True

    def __init__(self, app):
        self.app = app
        self._on_close = None
        self.closed = False

    def close(self, result=None):
        if self.closed:
            return
        self.closed = True
        self.app.pop(self, result)

    def on_open(self):
        pass

    def on_close(self):
        pass

    async def handle(self, action):
        pass

    def draw(self, g: Gfx):
        pass

    def selected_item_label(self):
        return None


class Dialog(Overlay):
    """Centered box with a title, a body drawn by the subclass, and a hint."""

    title = ""
    hint = ""
    width_pct = 60          # of screen width
    body_lines: list = []   # markup lines when draw_body isn't overridden

    def body_height(self, g: Gfx) -> int:
        px = g.em(0.98)
        return sum(g.markup_size(line or " ", px, "mono", self.box_width(g) - 2 * g.vw(3))[1] for line in self.body_lines)

    def box_width(self, g: Gfx) -> int:
        return g.vw(self.width_pct)

    def draw(self, g: Gfx):
        if self.scrim:
            draw_scrim(g)
        pad = g.em(1.2)
        hint_h = g.line_height(g.em(0.85), "mono") if self.hint else 0
        body_h = self.body_height(g)
        w = self.box_width(g)
        h = window_title_height(g, self.title) + pad + body_h + (pad // 2 if self.hint else 0) + hint_h + pad
        box = pygame.Rect(0, 0, w, h)
        box.center = (g.w // 2, g.h // 2)
        y = draw_window(g, box, self.title) + pad
        inner = pygame.Rect(box.x + g.vw(3), y, w - 2 * g.vw(3), body_h)
        self.draw_body(g, inner)
        if self.hint:
            g.draw_markup(self.hint, g.em(0.85), inner.x, box.bottom - pad - hint_h, "mono", P.MUTED, inner.w, "center", P.SURFACE)
        self.box = box

    def draw_body(self, g: Gfx, rect: pygame.Rect):
        px = g.em(0.98)
        y = rect.y
        for line in self.body_lines:
            y += g.draw_markup(line or " ", px, rect.x, y, "mono", P.TEXT, rect.w, "center", P.SURFACE)


class Picker(Dialog):
    """Vertical option list: up/down wrap, Enter confirms, Esc cancels.
    Options are (value, label) or (value, label, description)."""

    hint = f"{UP} {DOWN} choose   Enter confirm   Esc cancel"
    width_pct = 44
    OPTIONS: list = []
    DESCRIPTION = ""
    default_selected = 0
    escape_value = None
    dim_values: set = set()  # options drawn quietly until selected (a destructive alternative)

    def __init__(self, app, options=None):
        super().__init__(app)
        self.options = list(options if options is not None else self.OPTIONS)
        self.selected = self.default_selected

    def option_height(self, g: Gfx) -> int:
        return g.em(3.2) if any(len(o) == 3 for o in self.options) else g.em(1.9)

    def body_height(self, g: Gfx) -> int:
        desc = g.markup_size(self.DESCRIPTION, g.em(0.92), "mono", self.box_width(g))[1] + g.em(0.8) if self.DESCRIPTION else 0
        return desc + len(self.options) * (self.option_height(g) + g.em(0.3))

    def draw_body(self, g: Gfx, rect: pygame.Rect):
        """Rows in the Parent Menu's idiom: plain mono, the chosen one on
        the selection plate."""
        y = rect.y
        px = g.em(0.98)
        if self.DESCRIPTION:
            y += g.draw_markup(self.DESCRIPTION, g.em(0.92), rect.x, y, "mono", P.MUTED, rect.w, "center", P.SURFACE) + g.em(0.8)
        oh = self.option_height(g)
        for i, opt in enumerate(self.options):
            box = pygame.Rect(rect.x, y, rect.w, oh)
            on = i == self.selected
            if on:
                g.rect(P.PRIMARY, box, radius=g.em(0.35))
            color = P.ON_PRIMARY if on else (P.DIM if opt[0] in self.dim_values else P.TEXT)
            if len(opt) == 3:
                g.draw_text(opt[1], px, box.centerx, box.centery - g.em(0.6), "mono-bold" if on else "mono", color, anchor="center")
                g.draw_text(opt[2], g.em(0.85), box.centerx, box.centery + g.em(0.65), "mono", color if on else P.MUTED, anchor="center")
            else:
                g.draw_text(opt[1], px, box.centerx, box.centery, "mono-bold" if on else "mono", color, anchor="center")
            y += oh + g.em(0.3)

    def selected_item_label(self):
        return self.options[self.selected][1] if self.options else None

    async def handle(self, action):
        if isinstance(action, NavigationAction):
            if action.is_repeat:
                return
            if action.direction == "up":
                self.selected = (self.selected - 1) % len(self.options)
            elif action.direction == "down":
                self.selected = (self.selected + 1) % len(self.options)
            self.app.invalidate()
        elif isinstance(action, ControlAction) and action.is_down and not action.is_repeat:
            if action.action == "enter":
                self._on_confirm(self.options[self.selected][0])
            elif action.action == "escape":
                self.close(self.escape_value)

    def _on_confirm(self, value):
        self.close(value)


class Confirm(Picker):
    """Two-choice dialog; value True/False."""

    def __init__(self, app, title, body="", yes="Yes", no="No", default_no=True, danger=False):
        super().__init__(app, [(True, yes), (False, no)])
        self.title = title
        self.DESCRIPTION = body
        self.selected = 1 if default_no else 0
        self.escape_value = False


class Toast:
    def __init__(self, text: str, timeout: float):
        self.text = text
        self.expires = time.monotonic() + timeout


# ----------------------------------------------------------------------------
# Drawing helpers
# ----------------------------------------------------------------------------


def draw_scrim(g: Gfx, alpha: int = 225):
    s = pygame.Surface((g.w, g.h), pygame.SRCALPHA)
    s.fill((*rgb(P.BG), alpha))
    g.surface.blit(s, (0, 0))


def window_title_height(g: Gfx, title: str) -> int:
    return g.em(3.0) if title else 0


def draw_window(g: Gfx, box: pygame.Rect, title: str = "") -> int:
    """A dialog box: rounded frame with the title inside it, in the accent,
    the way the Parent Menu is headed. Returns the y where the body starts."""
    radius = g.em(0.6)
    g.rect(P.SURFACE, box, radius=radius)
    g.rect(P.LINE, box, width=1, radius=radius)
    if not title:
        return box.y
    head = window_title_height(g, title)
    g.draw_text(title, g.em(1.05), box.centerx, box.y + head // 2 + g.em(0.3), "mono-bold", P.ACCENT, anchor="center", track=0.1)
    return box.y + head


def draw_label(g: Gfx, text: str, px: int, x: int, y: int, color=P.MUTED, anchor="midleft", on=False) -> pygame.Rect:
    """Mono label; on = the selection plate (filled rounded pill, dark ink):
    the one selection idiom everywhere."""
    if not on:
        return g.draw_text(text, px, x, y, "mono", color, anchor=anchor)
    w, h = g.measure(text, px, "mono-bold")
    plate = pygame.Rect(0, 0, w + round(px * 1.4), h + round(px * 0.56))
    setattr(plate, anchor, (x, y))
    g.rect(P.PRIMARY, plate, radius=round(px * 0.5))
    g.draw_text(text, px, plate.centerx, plate.centery, "mono-bold", P.ON_PRIMARY, anchor="center")
    return plate


def draw_keycap(g: Gfx, text: str, px: int, x: int, y: int, anchor="midleft", color=P.MUTED) -> pygame.Rect:
    """A key name in a quiet rounded outline pill: Esc, Tab."""
    r = g.draw_text(text, px, x, y, "mono", color, anchor=anchor)
    box = r.inflate(round(px * 1.4), round(px * 0.56))
    g.rect(P.HAIR, box, width=1, radius=round(px * 0.5))
    return box


def arrow_key_metrics(g: Gfx, px: int) -> tuple:
    w, h = g.measure(DOWN, px, "mono")
    return w + round(px * 1.4), h + round(px * 0.56), round(px * 0.2)


def arrow_keys_size(g: Gfx, px: int) -> tuple:
    key_w, key_h, space = arrow_key_metrics(g, px)
    return 3 * key_w + 2 * space, 2 * key_h + space


def draw_arrow_keys(g: Gfx, px: int, x: int, y: int, color=P.MUTED) -> pygame.Rect:
    """Inverted-T keycaps, up floating over down; (x, y) is the bottom row's
    midleft. Returns the cluster's rect."""
    key_w, key_h, space = arrow_key_metrics(g, px)
    mid = x + key_w // 2 + key_w + space
    for i, glyph in enumerate((LEFT, DOWN, RIGHT)):
        draw_keycap(g, glyph, px, mid + (i - 1) * (key_w + space), y, anchor="center", color=color)
    draw_keycap(g, UP, px, mid, y - key_h - space, anchor="center", color=color)
    w, h = arrow_keys_size(g, px)
    return pygame.Rect(x, y + key_h // 2 - h, w, h)


@functools.lru_cache(maxsize=8)
def _swatch_dot(color: str, d: int) -> pygame.Surface:
    """A color dot drawn 4x and smoothed down so the edge stays clean."""
    s = 4
    big = pygame.Surface((d * s, d * s), pygame.SRCALPHA)
    pygame.draw.circle(big, rgb(color), (d * s / 2, d * s / 2), d * s / 2)
    return pygame.transform.smoothscale(big, (d, d))


HOLD = "hold "


def keycap_size(g: Gfx, text: str, px: int) -> tuple:
    w, h = g.measure(text.removeprefix(HOLD), px, "mono-bold")
    if text.startswith(HOLD):
        w += g.measure(HOLD, px, "mono")[0]
    return w + round(px * 1.4), h + round(px * 0.56)


def draw_key(g: Gfx, text: str, px: int, x: int, y: int, anchor="midleft", fill=P.TEXT, ink=P.SURFACE) -> pygame.Rect:
    """A solid keycap: the one look for a key the kid can press inside a room.
    'hold Space' puts the verb on the cap, so the hold reads as part of the key."""
    key = pygame.Rect((0, 0), keycap_size(g, text, px))
    setattr(key, anchor, (x, y))
    g.rect(fill, key, radius=round(px * 0.5))
    name = text.removeprefix(HOLD)
    left = key.x + round(px * 0.7)
    if name != text:
        left = g.draw_text(HOLD, px, left, key.centery, "mono", mix(ink, fill, 0.25), anchor="midleft").right
    g.draw_text(name, px, left, key.centery, "mono-bold", ink, anchor="midleft")
    return key


_KEY_RE = re.compile(r"\{([^}]+)\}")


def key_hint_width(g: Gfx, text: str, px: int) -> int:
    parts = _KEY_RE.split(text)
    return sum(keycap_size(g, t, px)[0] if i % 2 else g.measure(t, px, "mono")[0] for i, t in enumerate(parts) if t)


def draw_key_hint(g: Gfx, text: str, px: int, x: int, y: int, color=P.DIM, anchor="midleft") -> pygame.Rect:
    """A dim hint line where {Key} draws as a solid keycap: '{hold Space} write code'."""
    box = pygame.Rect(0, 0, key_hint_width(g, text, px), keycap_size(g, "X", px)[1])
    setattr(box, anchor, (x, y))
    x = box.x
    for i, t in enumerate(_KEY_RE.split(text)):
        if t:
            x = (draw_key(g, t, px, x, box.centery, fill=color) if i % 2 else
                 g.draw_text(t, px, x, box.centery, "mono", color, anchor="midleft")).right
    return box


CODE_HINT = f"{ICON_ROBOT} {{hold Space}} write code"


def _pill(g: Gfx, px: int, content_w: int, right: int, cy: int, on: bool) -> tuple:
    """The rounded plate a header control sits in; returns (pill, pad)."""
    pad = round(px * 0.35)
    pill = pygame.Rect(0, 0, content_w + 2 * pad, keycap_size(g, "X", px)[1] + 2 * pad)
    pill.midright = (right, cy)
    g.rect(P.PRIMARY if on else P.FIELD, pill, radius=round(px * 0.5) + pad)
    if not on:
        g.rect(P.LINE, pill, width=1, radius=round(px * 0.5) + pad)
    return pill, pad


def _draw_key_chip(g: Gfx, px: int, right: int, cy: int, key_name: str, mark, label: str, on: bool,
                   noun: str = "") -> pygame.Rect:
    """'[key] noun mark label' in one pill: noun says what the key changes, label
    is what it's on now; mark is a surface, an icon glyph or None; on = lit."""
    gap = px // 2
    key_w = keycap_size(g, key_name, px)[0]
    noun_w = g.measure(noun, px, "mono")[0] + gap if noun else 0
    mark_w = (mark.get_width() if isinstance(mark, pygame.Surface) else g.measure(mark, px, "mono")[0]) + gap if mark else 0
    label_w = g.measure(label, px, "mono-bold" if on else "mono")[0]
    pill, pad = _pill(g, px, key_w + gap + noun_w + mark_w + label_w + px - round(px * 0.35), right, cy, on)
    ink, cap = (P.ON_PRIMARY, P.PRIMARY) if on else (P.TEXT, P.SURFACE)
    x = draw_key(g, key_name, px, pill.x + pad, cy, fill=ink, ink=cap).right + gap
    if noun:
        x = g.draw_text(noun, px, x, cy, "mono", ink if on else P.MUTED, anchor="midleft").right + gap
    if isinstance(mark, pygame.Surface):
        x = g.surface.blit(mark, mark.get_rect(midleft=(x, cy))).right + gap
    elif mark:
        x = g.draw_text(mark, px, x, cy, "mono", ink, anchor="midleft").right + gap
    g.draw_text(label, px, x, cy, "mono-bold" if on else "mono", ink, anchor="midleft")
    return pill


def _draw_tab_switch(g: Gfx, px: int, left: int, cy: int, labels: tuple, active: int) -> pygame.Rect:
    """'[Tab] One Two' in one pill, the active label on the selection plate."""
    gap = px // 2
    key_w = keycap_size(g, "Tab", px)[0]
    widths = [g.measure(t, px, "mono-bold")[0] + round(px * 1.4) for t in labels]
    content = key_w + gap + sum(widths) + gap * (len(labels) - 1)
    pill, pad = _pill(g, px, content, left + content + 2 * round(px * 0.35), cy, False)
    x = draw_key(g, "Tab", px, pill.x + pad, cy).right + gap
    for i, (label, w) in enumerate(zip(labels, widths)):
        draw_label(g, label, px, x + w // 2, cy, anchor="center", on=i == active)
        x += w + gap
    return pill


def draw_mode_switch(g: Gfx, r: pygame.Rect, labels: tuple, active: int, swatch: str | None = None,
                     icon=None, wheel: str | None = None, chips: tuple = ()):
    """The room's header: the Tab switch starting at the middle, the brush
    swatch (or an icon standing in for it) left of it, then key chips further
    left: '[\\] Colors' when wheel (from color_wheel.chip) is set, and each of
    chips = (key, mark, label, on, noun)."""
    px = g.vh(1.9)
    cy = r.centery
    sw = _draw_tab_switch(g, px, r.centerx - keycap_size(g, "Tab", px)[0], cy, labels, active)
    left = sw.x - round(px * 1.2)
    if icon:
        left = g.surface.blit(icon, icon.get_rect(midright=(left, cy))).x - round(px * 1.2)
    elif swatch:
        dot = _swatch_dot(swatch, round(px * 2.1))
        left = g.surface.blit(dot, dot.get_rect(midright=(left, cy))).x - round(px * 1.2)
    if wheel:
        from .color_wheel import OPEN_KEY, disc
        chips = ((OPEN_KEY, disc(round(px * 1.3)), "Colors", wheel == "open"), *chips)
    for chip in reversed(chips):
        left = _draw_key_chip(g, px, left, cy, *chip).x - round(px * 1.2)


def draw_bar(g: Gfx, x: int, y: int, w: int, h: int, fraction: float, color=P.PRIMARY, track=P.LINE):
    g.rect(track, (x, y, w, h))
    if fraction > 0:
        g.rect(color, (x, y, max(h, int(w * min(1.0, fraction))), h))


HOLD_QUIET = 0.35   # of a hold: before this, nothing shows, so a tap never flashes the bar


def draw_hold_bar(g: Gfx, rect: pygame.Rect, progress: float, label: str):
    """A hold gesture under way, over the bottom of the viewport: a pill that
    fills as the hold goes on, saying what a full one does. The words turn
    dark where the fill has reached them."""
    g.rect(P.SURFACE, rect)
    g.rect(P.LINE, (rect.x + g.em(1), rect.y, rect.w - g.em(2), 1))
    px = g.em(0.95)
    pill = pygame.Rect(0, 0, g.measure(label, px, "mono-bold")[0] + g.em(3), round(px * 2.4))
    pill.center = rect.center
    r = pill.h // 2
    g.rect(P.FIELD, pill, radius=r)
    fill = pygame.Rect(pill.x, pill.y, round(pill.w * progress), pill.h)
    if fill.w:
        g.rect(P.PRIMARY, (pill.x, pill.y, max(fill.w, pill.h), pill.h), radius=r)
    g.rect(P.LINE, pill, width=1, radius=r)
    clip = g.surface.get_clip()
    for ink, area in ((P.TEXT, pill), (P.BG, fill.clip(clip))):
        g.surface.set_clip(area.clip(clip))
        g.draw_text(label, px, pill.centerx, pill.centery, "mono-bold", ink, anchor="center")
    g.surface.set_clip(clip)


def is_char(action, ch: str | None = None) -> bool:
    return isinstance(action, CharacterAction) and (ch is None or action.char.lower() == ch)


def is_control(action, name: str, down: bool = True) -> bool:
    return isinstance(action, ControlAction) and action.action == name and action.is_down == down


async def sleep(seconds: float):
    await asyncio.sleep(seconds)
