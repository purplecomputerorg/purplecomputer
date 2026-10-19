"""Write room: a quiet page for stories, letters and reports. Typing inserts at
the caret, words wrap whole, Enter starts a new line, and the page scrolls to
keep the caret in view. Plain text only: it prints every page, and a copy to a
USB drive brings a .txt along with the picture."""

import time
from bisect import bisect_right

import pygame

from ... import palette as P
from ...constants import ICON_PENCIL
from ...keyboard import CharacterAction, ControlAction, NavigationAction
from .. import paper
from ..ui import MOVE_HINT, TextField, draw_key_hint, draw_text_caret, hint_row_h
from .base import Room
from .play_room import scroll_thumb

COLS = 60           # wraps the same on every screen, page and save
MAX_CHARS = 40_000  # about 7,000 words: far past a school report, still a small save
LEADING = 1.3       # line pitch over the font's own, so a page of text breathes
HINT = "Type to write! {Enter} for a new line."
WORDS_AFTER = 1.0   # seconds of holding Backspace before it takes whole words
WORD_EVERY = 0.15


def wrap(text: str, cols: int = COLS) -> list:
    """Visual lines as (start, end, soft): text[start:end] is the line, soft when it
    wrapped rather than ended at Enter or the end. A wrapped line keeps its space,
    so the next one starts on a letter; only a word longer than a line breaks."""
    lines, start = [], 0
    for para in text.split("\n"):
        s, end = start, start + len(para)
        while end - s > cols:
            space = text.rfind(" ", s, s + cols + 1)
            cut = space + 1 if space > s else s + cols
            lines.append((s, cut, True))
            s = cut
        lines.append((s, end, False))
        start = end + 1
    return lines


def line_of(lines: list, i: int) -> int:
    """The visual line the caret at i sits on; at a wrap it starts the next line."""
    return bisect_right([s for s, _, _ in lines], i) - 1


def keep_in_view(top: int, k: int, rows: int, n: int) -> int:
    """The first of n lines to show so line k is in view, moving as little as
    possible and leaving no empty rows under the text."""
    return max(k - rows + 1, min(top, k, max(0, n - rows)))


def text_px(g, width: int, most: int) -> int:
    """The biggest mono size up to `most` that fits a line and the caret after it in width."""
    per_px = g.measure("M" * 50, 100, "mono", tr=False)[0] / 5000
    return max(6, min(most, int(width / ((COLS + 1) * per_px))))


def line_pitch(g, px: int) -> int:
    return round(g.line_height(px, "mono") * LEADING)


class WriteRoom(Room):
    name, label, icon = "write", "Write", ICON_PENCIL
    STARTS_OFF = True
    about = "a quiet page for stories and letters"
    shows_legend = False

    def __init__(self, app):
        super().__init__(app)
        self.field = TextField()
        self.top = 0        # the first visual line on screen
        self._goal = None   # the column a run of up and down keeps aiming for
        self._held = self._last_word = 0.0

    def arrow_hint(self) -> str:
        return MOVE_HINT

    # ---------------------------------------------------------------- state
    def timeline_state(self) -> dict:
        return {"text": self.field.value, "caret": self.field.cursor}

    def restore_timeline_state(self, state: dict):
        self.field.set(state.get("text", "")[:MAX_CHARS], state.get("caret"))
        self.top, self._goal = 0, None
        self.app.invalidate()

    def plain_text(self) -> str:
        return self.field.value

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        goal = None
        if isinstance(action, NavigationAction):
            goal = self._move(action.direction)
        elif isinstance(action, ControlAction) and action.is_down:
            if action.action == "backspace":
                self._backspace(action.is_repeat)
            elif action.action in ("space", "enter") and not action.is_repeat:
                self._type(" " if action.action == "space" else "\n")
            else:
                return
        elif isinstance(action, CharacterAction) and not action.is_repeat:
            self._type(action.char)
        else:
            return
        self._goal = goal
        self.app.invalidate()

    def _type(self, s: str):
        if len(self.field.value) + len(s) <= MAX_CHARS:
            self.field.insert(s)

    def _backspace(self, repeat: bool):
        """A letter at a time, then whole words once Backspace has been held a while."""
        now = time.monotonic()
        if not repeat:
            self._held = now
        if now - self._held < WORDS_AFTER:
            self.field.backspace()
        elif now - self._last_word >= WORD_EVERY:
            self._last_word = now
            self._delete_word()

    def _delete_word(self):
        """Back over the spaces before the caret and the word before them, or one Enter."""
        f = self.field
        t, i = f.value, f.cursor
        j = len(t[:i].rstrip(" "))
        while j and t[j - 1] not in " \n":
            j -= 1
        j = min(j, i - 1) if i and j == i else j
        f.set(t[:j] + t[i:], j)

    def _move(self, direction: str):
        """Left and right step a letter; up and down a visual line, keeping the column. Returns that column."""
        f = self.field
        if direction in ("left", "right"):
            f.move(-1 if direction == "left" else 1)
            return None
        lines = wrap(f.value)
        k = line_of(lines, f.cursor)
        col = f.cursor - lines[k][0] if self._goal is None else self._goal
        k += 1 if direction == "down" else -1
        if k < 0:
            f.cursor = 0
        elif k >= len(lines):
            f.cursor = len(f.value)
        else:
            s, e, soft = lines[k]
            f.cursor = s + min(col, e - s - soft)
        return col

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        """The text in a centered column on faint ruled lines, the hint under it as in Art."""
        em, pad = g.em, g.em(0.7)
        inner = rect.inflate(-2 * pad, -2 * pad)
        foot_h = hint_row_h(g)
        page = pygame.Rect(inner.x, inner.y + em(0.5), inner.w, inner.h - foot_h - em(1.0))
        px = text_px(g, page.w - 2 * em(2), em(1.45))
        lh = line_pitch(g, px)
        col_w = (COLS + 1) * g.measure("M", px, "mono", tr=False)[0]
        x = page.centerx - col_w // 2
        rows = max(1, page.h // lh)
        for i in range(rows):
            y = page.y + i * lh + round(px * 1.25)
            g.rect(P.FIELD, pygame.Rect(x, y, col_w, max(1, px // 14)))
        text, cursor = self.field.value, self.field.cursor
        lines = wrap(text)
        k = line_of(lines, cursor)
        self.top = keep_in_view(self.top, k, rows, len(lines))
        for i, (s, e, _) in enumerate(lines[self.top:self.top + rows]):
            g.draw_text(text[s:e], px, x, page.y + i * lh, "mono", P.TEXT, tr=False)
        before = text[lines[k][0]:cursor]
        draw_text_caret(g, x + (g.measure(before, px, "mono", tr=False)[0] if before else 0),
                        page.y + (k - self.top) * lh, px, bar=True)
        if len(lines) > rows:
            w = em(0.7)
            track = pygame.Rect(rect.right - em(0.5) - w, page.y, w, rows * lh)
            g.rect(P.BG, track, radius=w // 2)
            hidden = (len(lines) - self.top - rows) * lh
            g.rect(P.FIELD, scroll_thumb(track, rows * lh, len(lines) * lh, hidden, em(1.5)), radius=w // 2)
        foot = pygame.Rect(x, inner.bottom - foot_h, inner.w, foot_h)
        draw_key_hint(g, HINT, g.vh(1.9), foot.x, foot.centery)

    def paper_pages(self, g, size, on_screen=False, limit=None) -> list:
        """Every page of the text, a line as long as on screen, in ink on white (screen colors on_screen)."""
        text = self.field.value.rstrip()
        if not text.strip():
            return []
        px = text_px(g, size[0], size[0])
        lh = line_pitch(g, px)
        rows = max(1, size[1] // lh)
        lines = wrap(text)
        out = []
        for top in range(0, len(lines), rows)[:limit]:
            s = paper.blank(size, on_screen)
            with g.drawing_on(s):
                for i, (a, b, _) in enumerate(lines[top:top + rows]):
                    g.draw_text(text[a:b], px, 0, i * lh, "mono", P.TEXT if on_screen else paper.INK, tr=False)
            out.append(s)
        return out

    def paper(self, g, size, on_screen=False):
        return next(iter(self.paper_pages(g, size, on_screen, limit=1)), None)
