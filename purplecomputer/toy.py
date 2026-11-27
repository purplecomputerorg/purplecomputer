"""Play's code panel makes a toy: a Play line with a key in front runs when that key is pressed.
A toy is read from Play's code lines, so saves and Time Travel keep it. docs/plans/play-toy-builder.md"""

import asyncio
import re

from . import palette as P
from .audio import play_safe
from .content import get_content
from .keyboard import ControlAction
from .music_constants import PERCUSSION, PERCUSSION_NAMES
from .ui import Overlay, draw_key_hint, key_hint_width

STEP_S = 0.45   # between one step and the next, so a line plays out in order
KEYS = set("abcdefghijklmnopqrstuvwxyz0123456789") | {"space", "enter", "up", "down", "left", "right"}
DRUMS = {**{n: n for n in PERCUSSION.values()}, **{short: PERCUSSION[d] for d, short in PERCUSSION_NAMES.items()}}
DEFAULT_DRUM = "bongo"
_LEAD = re.compile(r"\s*(?:when|press|on)\s+", re.I)
_MARKED = re.compile(r"(\w+)\s*(?::|->|=)\s*(.*)", re.S)
_STEP_START = re.compile(r"\s+(?=(?:say|drum)\b)", re.I)


def _bare_key_ok(word: str) -> bool:
    """A key needs no colon when Play wouldn't read the word: not a, i, a number, an emoji or a color."""
    content = get_content()
    return word not in ("a", "i") and not word.isdigit() and not content.exact_emoji(word) and not content.exact_color(word)


def label(line: str) -> tuple:
    """(key, the rest) for a line that waits for a key, else (None, line)."""
    led = _LEAD.match(line)
    text = line[led.end():].strip() if led else line.strip()
    if (m := _MARKED.fullmatch(text)) and m[1].lower() in KEYS and m[2].strip():
        return m[1].lower(), m[2].strip()
    word, _, rest = text.partition(" ")
    word = word.lower()
    if word in KEYS and rest.strip() and (led or _bare_key_ok(word)):
        return word, rest.strip()
    return None, line


def steps(text: str) -> list:
    """(kind, text) for each step: ("play", a Play line) or ("drum", a drum name).
    Commas split steps, and so does say or drum partway through: `cow say moo drum cowbell`."""
    return [step for clause in re.split(r"[,;]", text)
            for part in _STEP_START.split(clause.strip()) for step in _step(part.strip())]


def _step(part: str) -> list:
    word, _, rest = part.partition(" ")
    if not part:
        return []
    if word.lower() != "drum":
        return [("play", part)]
    name, _, after = rest.strip().partition(" ")
    if name.lower() in DRUMS:
        return [("drum", DRUMS[name.lower()])] + _step(after.strip())
    return [("drum", DEFAULT_DRUM)] + _step(rest.strip())


def toy_from(lines: list) -> dict:
    """key -> what it does, from code lines: a key typed again keeps its place and takes the newer line."""
    toy = {}
    for line in lines:
        key, rest = label(line)
        if key:
            toy[key] = rest
    return toy


def keycap(key: str) -> str:
    return f"{{{key.upper() if len(key) == 1 else key.title()}}}"


def is_play_word(line: str) -> bool:
    return line.strip().lower().rstrip("!") == "play"


async def run_steps(todo: list, show, sounds):
    """Each step in turn: a drum plays, then show(kind, text) puts it on screen."""
    for i, (kind, text) in enumerate(todo):
        if i:
            await asyncio.sleep(STEP_S)
        if kind == "drum" and (clip := sounds.drum(text)):
            play_safe(clip)
        show(kind, text)


class ToyScreen(Overlay):
    """The toy, playing: a key shows what Play shows for its line, big. Esc goes back to the code."""

    scrim = False

    def __init__(self, app, room):
        super().__init__(app)
        self.room = room
        self.toy = toy_from(app.code_lines(room.name))
        self.entries: list = []
        self._task = None

    def on_close(self):
        self._stop()

    def _stop(self):
        if self._task and not self._task.done():
            self._task.cancel()

    async def handle(self, action):
        from .rooms.family_room import FamilyRoom
        if isinstance(action, ControlAction) and action.action == "escape":
            if not action.is_down and self.app._escape_pressed_on is self:
                self.close()
            return
        key = ((FamilyRoom._key_event(action) or {}).get("key") or "").lower()
        if key not in self.toy:
            return
        self._stop()
        self.entries = []
        self._task = asyncio.create_task(run_steps(steps(self.toy[key]), self._show, self.room.sounds))

    def _show(self, kind: str, text: str):
        self.entries += self.room.step_entries(kind, text)
        self.app.invalidate()

    def draw(self, g):
        app = self.app
        g.fill(P.BG)
        vp = app._viewport_rect()
        frame = app._frame_rect(vp)
        app._draw_title(frame, f"{self.room.icon} My toy")
        g.rect(P.SURFACE, frame, radius=g.em(0.6))
        g.rect(P.LINE, frame, width=1, radius=g.em(0.6))
        keys_y = vp.bottom - g.em(2.2)
        self._draw_keys(g, vp, keys_y)
        stage = vp.inflate(-g.em(3), 0)
        stage.height = keys_y - g.em(1.5) - vp.y
        if self.entries:
            with g.drawing_on(g.surface, em=g.em(1.8)):
                self.room.draw_centered(g, self.entries, stage)
        else:
            words = "Press a key" if self.toy else "No keys yet. Esc, then type  a: cat"
            g.draw_text(words, g.em(1.6), stage.centerx, stage.centery, "mono", P.MUTED, anchor="center")
        app._draw_footer(frame)

    def _draw_keys(self, g, vp, y):
        """The toy's keys along the bottom, each with the start of what it does, as many as fit."""
        px, room = g.em(0.95), vp.w - g.em(3)
        back = "{Esc} back to code"
        shown = [f"{keycap(k)} {re.sub('[{}]', '', self.toy[k])[:14]}" for k in self.toy]
        while shown and key_hint_width(g, "   ".join(shown + [back]), px) > room:
            shown = [s.split(" ", 1)[0] for s in shown] if " " in "".join(shown) else shown[:-1]
        draw_key_hint(g, "   ".join(shown + [back]), px, vp.centerx, y, color=P.MUTED, anchor="center")
