"""Small UI primitives shared by every screen: timers, a text field with
autocomplete, dialogs, pickers, toasts, and the hold bar.

Nothing here knows about rooms. Screens compose these and draw with Gfx.
"""

import asyncio
import re
import time

import pygame

from . import palette as P
from .constants import ICON_VOLUME_HIGH, ICON_VOLUME_OFF
from .gfx import Gfx, rgb
from .keyboard import CharacterAction, ControlAction, NavigationAction

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


def volume_badge(vol: int):
    """(icon, bar, label) for a volume level; Play, the picker and toasts share it."""
    steps = [(0, "Sound Off"), (15, "Whisper"), (35, "Quiet"), (60, "Medium"), (85, "Loud"), (100, "Full")]
    label = next(lbl for lvl, lbl in steps if vol <= lvl)
    filled = 0 if vol <= 0 else next(i for i, (lvl, _) in enumerate(steps) if vol <= lvl) * 2
    return (ICON_VOLUME_OFF if vol == 0 else ICON_VOLUME_HIGH), "█" * filled + "░" * (10 - filled), label


class TextField:
    """One-line editable text with a cursor, word underlining, and
    autocomplete suggestions of (word, color_hex, emoji)."""

    def __init__(self, autocomplete_fn=None, validator=None, context_autocomplete=False):
        self.value = ""
        self.cursor = 0
        self._autocomplete_fn = autocomplete_fn
        self._validator = validator
        self._context = context_autocomplete
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

    def recall_text(self) -> str:
        """Dim hint under an empty field; a correction shows once."""
        if self.value or not self.last_command:
            return ""
        if self._correction:
            orig, corr = self._correction
            self._correction = None
            return _truncate(f"{orig} → {corr}")
        return f"Enter to try again: {_truncate(self.last_command)}"

    # --- autocomplete (logic unchanged from CodeInput) ---
    def _check_autocomplete(self):
        self.matches, self.match_index, self.exact_display = [], 0, ""
        if not self._autocomplete_fn:
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
        if self.exact_display:
            return self.exact_display
        if not self.matches:
            return ""
        parts = []
        for word, color_hex, emoji in self.matches:
            s = f"[dim]{word}[/]"
            if emoji:
                s += f" {emoji}"
            if color_hex:
                s += f" [{color_hex}]██[/]"
            parts.append(s)
        return "   ".join(parts) + "   [dim]⇥ Tab[/]"

    # --- drawing ---
    def text_x(self, g: Gfx, x: int, px: int, label: str = "Ask", label_px: int | None = None,
               gap: int | None = None) -> int:
        """Where typed text starts, so hints under the field can line up with it."""
        return x + g.measure(f"{label} →", label_px or px, "mono-heavy")[0] + (gap if gap is not None else px // 2)

    def draw(self, g: Gfx, x: int, y: int, width: int, px: int, label: str = "Ask", label_px: int | None = None,
             gap: int | None = None) -> pygame.Rect:
        """'Label →  text▌' in the mono face; returns the rect used.
        label_px lets the label sit a step larger than the typed text; gap
        sets the space between label and text (a boxed field needs more)."""
        mid = y + g.line_height(px, "mono") // 2
        g.draw_text(f"{label} →", label_px or px, x, mid, "mono-heavy", P.ACCENT, anchor="midleft")
        tx = self.text_x(g, x, px, label, label_px, gap)
        shown, start = self._visible_slice(g, px, width - (tx - x) - px)
        before = shown[:self.cursor - start]
        g.draw_text(shown, px, tx, y, "mono", P.TEXT)
        if self._validator:
            self._underline(g, shown, px, tx, y)
        cx = tx + g.measure(before, px, "mono")[0] if before else tx
        g.rect(P.CARET, (cx, y + px // 8, max(2, int(px * 0.55)), int(px * 1.05)))
        return pygame.Rect(x, y, width, g.line_height(px, "mono"))

    def _visible_slice(self, g, px, avail):
        """Keep the cursor on screen for long lines by scrolling the start."""
        if g.measure(self.value, px, "mono")[0] <= avail or not self.value:
            return self.value, 0
        cw = g.measure("M", px, "mono")[0] or 1
        fit = max(8, avail // cw)
        start = max(0, self.cursor - fit + 1)
        return self.value[start:start + fit], start

    def _underline(self, g, shown, px, tx, y):
        lh = g.line_height(px, "mono")
        for m in re.finditer(r'[a-z]+', shown.lower()):
            if self._validator(m.group()):
                x0 = tx + g.measure(shown[:m.start()], px, "mono")[0]
                x1 = tx + g.measure(shown[:m.end()], px, "mono")[0]
                g.rect(P.MUTED, (x0, y + lh - 2, x1 - x0, 2))


def _truncate(text: str) -> str:
    return text[:MAX_RECALL_LEN - 1] + "…" if len(text) > MAX_RECALL_LEN else text


class HintRotator:
    """The 'Try: ...' line that advances on Enter and every minute."""

    CYCLE_SECONDS = 60

    def __init__(self, hints: list):
        self.hints = hints
        self.index = 0
        self._stamp = time.monotonic()

    @property
    def current(self) -> str:
        if not self.hints:
            return ""
        if time.monotonic() - self._stamp > self.CYCLE_SECONDS:
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
        px = g.vh(2.4)
        return sum(g.markup_size(line or " ", px, max_width=self.box_width(g) - 2 * g.vw(3))[1] for line in self.body_lines)

    def box_width(self, g: Gfx) -> int:
        return g.vw(self.width_pct)

    def draw(self, g: Gfx):
        if self.scrim:
            draw_scrim(g)
        pad = g.vh(3)
        hint_h = g.line_height(g.vh(2.0), "mono") if self.hint else 0
        body_h = self.body_height(g)
        w = self.box_width(g)
        h = window_title_height(g, self.title) + pad + body_h + (pad // 2 if self.hint else 0) + hint_h + pad
        box = pygame.Rect(0, 0, w, h)
        box.center = (g.w // 2, g.h // 2)
        y = draw_window(g, box, self.title) + pad
        inner = pygame.Rect(box.x + g.vw(3), y, w - 2 * g.vw(3), body_h)
        self.draw_body(g, inner)
        if self.hint:
            g.draw_markup(self.hint, g.vh(2.0), inner.x, box.bottom - pad - hint_h, "mono", P.MUTED, inner.w, "center", P.SURFACE)
        self.box = box

    def draw_body(self, g: Gfx, rect: pygame.Rect):
        px = g.vh(2.4)
        y = rect.y
        for line in self.body_lines:
            y += g.draw_markup(line or " ", px, rect.x, y, "sans", P.TEXT, rect.w, "center", P.SURFACE)


class Picker(Dialog):
    """Vertical option list: up/down wrap, Enter confirms, Esc cancels.
    Options are (value, label) or (value, label, description)."""

    hint = "▲ ▼ choose   Enter confirm   Esc cancel"
    width_pct = 44
    OPTIONS: list = []
    DESCRIPTION = ""
    default_selected = 0
    escape_value = None

    def __init__(self, app, options=None):
        super().__init__(app)
        self.options = list(options if options is not None else self.OPTIONS)
        self.selected = self.default_selected

    def option_height(self, g: Gfx) -> int:
        return g.vh(7.5)

    def body_height(self, g: Gfx) -> int:
        desc = g.markup_size(self.DESCRIPTION, g.vh(2.2), max_width=self.box_width(g))[1] + g.vh(1) if self.DESCRIPTION else 0
        return desc + len(self.options) * (self.option_height(g) + g.vh(1))

    def draw_body(self, g: Gfx, rect: pygame.Rect):
        y = rect.y
        if self.DESCRIPTION:
            y += g.draw_markup(self.DESCRIPTION, g.vh(2.2), rect.x, y, "sans", P.MUTED, rect.w, "center", P.SURFACE) + g.vh(1)
        oh = self.option_height(g)
        for i, opt in enumerate(self.options):
            box = pygame.Rect(rect.x, y, rect.w, oh)
            on = i == self.selected
            g.rect(P.PRIMARY if on else P.TILE, box, radius=g.em(0.35))
            label = opt[1]
            color = P.ON_PRIMARY if on else P.TEXT
            if len(opt) == 3:
                g.draw_text(label, g.vh(2.6), box.centerx, box.centery - g.vh(1.2), "mono-heavy" if on else "mono-bold", color, anchor="center")
                g.draw_text(opt[2], g.vh(1.9), box.centerx, box.centery + g.vh(1.4), "sans", color if on else P.MUTED, anchor="center")
            else:
                g.draw_text(label, g.vh(2.6), box.centerx, box.centery, "mono-heavy" if on else "mono-bold", color, anchor="center")
            y += oh + g.vh(1)

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
    return g.vh(4.4) if title else 0


def draw_window(g: Gfx, box: pygame.Rect, title: str = "") -> int:
    """A dialog box: rounded frame and a title strip across the top.
    Returns the y where the body starts."""
    radius = g.em(0.6)
    g.rect(P.SURFACE, box, radius=radius)
    g.rect(P.LINE, box, width=1, radius=radius)
    if not title:
        return box.y
    strip = pygame.Rect(box.x, box.y, box.w, window_title_height(g, title))
    pygame.draw.rect(g.surface, rgb(P.TILE), strip, border_top_left_radius=radius, border_top_right_radius=radius)
    g.rect(P.HAIR, (box.x, strip.bottom - 1, box.w, 1))
    g.draw_text(title, g.vh(2.0), strip.centerx, strip.centery, "mono-bold", P.TEXT, anchor="center")
    return strip.bottom


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


def draw_bar(g: Gfx, x: int, y: int, w: int, h: int, fraction: float, color=P.PRIMARY, track=P.LINE):
    g.rect(track, (x, y, w, h))
    if fraction > 0:
        g.rect(color, (x, y, max(h, int(w * min(1.0, fraction))), h))


def draw_hold_bar(g: Gfx, rect: pygame.Rect, progress: float, label: str):
    """Progress for a hold gesture, drawn over the hint strip at the bottom of
    the viewport: a label and a segmented bar that fills left to right."""
    g.rect(P.SURFACE, rect)
    px = g.vh(2.0)
    seg_w, seg_h, n = g.vw(1.1), g.vh(1.4), 12
    lab = g.text(label, px, "mono-bold", P.PRIMARY)
    total = lab.get_width() + px + n * seg_w + (n - 1) * (seg_w // 3)
    x = rect.centerx - total // 2
    g.surface.blit(lab, lab.get_rect(midleft=(x, rect.centery)))
    x += lab.get_width() + px
    for i in range(n):
        g.rect(P.PRIMARY if i < round(progress * n) else P.LINE, (x, rect.centery - seg_h // 2, seg_w, seg_h))
        x += seg_w + seg_w // 3


def is_char(action, ch: str | None = None) -> bool:
    return isinstance(action, CharacterAction) and (ch is None or action.char.lower() == ch)


def is_control(action, name: str, down: bool = True) -> bool:
    return isinstance(action, ControlAction) and action.action == name and action.is_down == down


async def sleep(seconds: float):
    await asyncio.sleep(seconds)
