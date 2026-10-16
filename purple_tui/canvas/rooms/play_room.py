"""Play room: type a word, a sum, a color, and it comes to life. History
scrolls up; the line you're typing shows a rotating set of ideas to try."""

import re

import pygame

from ... import palette as P
from ...constants import ICON_VOLUME_HIGH, ICON_VOLUME_OFF
from ...content import get_content
from .. import paper
from ..gfx import is_emoji, mix, strip_markup
from ...keyboard import CharacterAction, ControlAction, NavigationAction
from ...palette import get_key_color
from ...play_eval import SimpleEvaluator, pair_speakables, parse_speech_trigger
from ..ui import MATH_OPERATORS, HintRotator, TextField

PAPER_ZOOM = 1.6
PLAY_IDEAS = [
    ("cat", "2 + 2", "trex!"),
    ("say hi", "red sun"),
    ("red + blue!", "5 dinos"),
    ("asdfghjkl", "say yellow"),
    ("three cats!", "pink fish"),
    ("say 4 + 3 cats", "red + yellow!"),
    ("I love trex", "blue frog!"),
    ("4 birds + 2 owls", "say purple"),
    ("cat times 5", "light pink unicorn!"),
    ("I have 5 dinos!", "say 5 x 5 ducks"),
    ("pink + purple", "dark green trex!"),
    ("say wow!", "2 red, 3 blue"),
    ("orange + white", "rainbow mermaid!"),
    ("20 19 18 17...", "bright blue dinosaur!"),
    ("dinos ... 5", "2 4 6 8..."),
]
TIMELINE_MAX_ENTRIES = 100
MAX_HISTORY = 60
SPEECH_ICONS = {"generating": "··", "playing": ICON_VOLUME_HIGH, "filtered": ICON_VOLUME_OFF}
ABACUS_MARK = "\x1e"
ABACUS_RE = re.compile(r"\x1e(\d+) (.*?)\x1e")
ABACUS_SLOTS = 12  # 9 beads plus the gap they slide across


class PlayEvaluator(SimpleEvaluator):
    """Hands big counts to the room as a marked abacus to draw; the text rows
    only line up in a terminal's fixed cells."""

    def _format_number_with_dots(self, num, show_label=True, expression="", bead="●"):
        n = int(num) if float(num).is_integer() else 0
        if not self.INLINE_MAX < n < 10 ** len(self.ABACUS_COLORS):
            return super()._format_number_with_dots(num, show_label, expression, bead)
        rods = f"{ABACUS_MARK}{n} {bead}{ABACUS_MARK}"
        return f"{self._format_number(num)}\n{rods}" if show_label else rods


def answer_parts(markup: str) -> list:
    """An answer's markup runs, with each abacus as an (n, bead) tuple."""
    parts = ABACUS_RE.split(markup)
    out = []
    for i in range(0, len(parts), 3):
        if text := parts[i].strip("\n"):
            out.append(text)
        if i + 1 < len(parts):
            out.append((int(parts[i + 1]), parts[i + 2]))
    return out


def abacus_rows(n: int) -> list:
    """(place name, digit, color) per rod, the biggest place on top."""
    digits = str(n)
    places = range(len(digits) - 1, -1, -1)
    return [(SimpleEvaluator.PLACE_NAMES[10 ** p], int(d), SimpleEvaluator.ABACUS_COLORS[p])
            for p, d in zip(places, digits)]


def abacus_size(g, n: int) -> tuple:
    slot, bar = g.em(1.8), g.em(0.45)
    return slot, bar, len(str(n)) * slot + 2 * bar


def draw_abacus(g, n: int, bead: str, x: int, y: int, frame, ground):
    """A framed abacus: counted beads slid left, the rest waiting right,
    the place names before each rod and its digit after it."""
    rows = abacus_rows(n)
    slot, bar, h = abacus_size(g, n)
    px = g.em(1.3)
    label_w = max(g.measure(name, px, "mono-bold")[0] for name, _, _ in rows)
    box = pygame.Rect(x + label_w + g.em(0.9), y, ABACUS_SLOTS * slot + 2 * bar, h)
    rod_h, bead_h = max(2, g.em(0.15)), g.em(1.25)
    for i, (name, digit, color) in enumerate(rows):
        cy = y + bar + i * slot + slot // 2
        g.draw_text(name, px, box.x - g.em(0.9), cy, "mono-bold", color, anchor="midright")
        g.rect(mix(frame, ground, 0.35), (box.x, cy - rod_h // 2, box.w, rod_h))
        for k in range(9):
            at = k if k < digit else k + ABACUS_SLOTS - 9
            cell = pygame.Rect(box.x + bar + at * slot, cy - slot // 2, slot, slot)
            draw_bead(g, bead if k < digit else None, color, cell, bead_h, mix(frame, ground, 0.78))
        g.draw_text(str(digit), px, box.right + g.em(0.9), cy, "mono-bold", color, anchor="midleft")
    g.rect(frame, box, width=bar, radius=bar)


def draw_bead(g, bead, color, cell, h, idle):
    """bead None is one not yet counted; a color block becomes a bead of its color."""
    hexes = re.findall(r"\[on (#[0-9a-fA-F]{6})\]", bead or "")
    if bead and bead != "●" and strip_markup(bead).strip():
        w, bh = g.markup_size(bead, g.em(1.1), "mono-bold")
        g.draw_markup(bead, g.em(1.1), cell.centerx - w // 2, cell.centery - bh // 2, "mono-bold")
        return
    pill = pygame.Rect(0, 0, cell.w - g.em(0.2), h)
    pill.center = cell.center
    fill = idle if bead is None else hexes[0] if hexes else color
    g.rect(fill, pill, radius=h // 2)


def speech_marks(text: str) -> list:
    """Spans of what makes a line talk: each `!` and a say/talk/speak first word."""
    marks = [m.span() for m in re.finditer("!+", text)]
    m = re.match(r"\s*([A-Za-z]+)", text)
    if m and parse_speech_trigger(m.group(1))[0]:
        marks.append(m.span(1))
    return sorted(marks)


def toggled_say(value: str, cursor: int) -> tuple:
    """(value, cursor) with `say ` added to a quiet line, or every speech mark taken off a talking one."""
    marks = speech_marks(value)
    if not marks:
        return "say " + value, cursor + 4
    for a, b in reversed(marks):
        if value[a] != "!":
            b += len(value[b:]) - len(value[b:].lstrip())
        value = value[:a] + value[b:]
        cursor -= max(0, min(cursor, b) - a)
    return value, cursor


def _play_validator(word: str) -> bool:
    return get_content().is_valid_word(word)


def _play_autocomplete(last_word: str, full_text: str = "") -> list:
    content = get_content()
    r = content.resolve(last_word)
    if r.kind == "color":
        return [(last_word, r.value, "")]
    if r.kind == "emoji":
        return [(last_word, "", r.value)]
    return [(w, c, e) for w, c, e in content.search_words(last_word)]


def scroll_thumb(track, viewport: int, total: int, hidden: int, min_h: int) -> pygame.Rect:
    """Where the thumb sits on the track: content is `total` tall, the window
    shows `viewport` of it ending `hidden` px above the bottom."""
    h = min(track.h, max(min_h, round(track.h * viewport / total)))
    y = track.y + round(track.h * max(0, total - hidden - viewport) / total)
    return pygame.Rect(track.x, min(y, track.bottom - h), track.w, h)


class Entry:
    """One history line: what was asked, or an answer in markup."""

    def __init__(self, kind: str, markup: str):
        self.kind = kind          # "ask" | "answer"
        self.markup = markup
        self.speech = ""          # "", generating, playing, filtered


class PlayRoom:
    name = "play"
    LANDSCAPE = False

    def __init__(self, app):
        self.app = app
        self.evaluator = PlayEvaluator()
        self.field = TextField(_play_autocomplete, validator=_play_validator, marks=speech_marks)
        self.hints = HintRotator(PLAY_IDEAS)
        self.history: list = []
        self.scroll = 0                  # px of history hidden below the bottom (scrolled up)
        self._timeline_entries: list = []
        self._timeline_seq = 0
        self.code_panel = None

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        self.hints.advance()
        self.app.set_legend(None, visible=True)

    def on_leave(self):
        pass

    def stop_sound(self):
        pass

    def open_code_panel(self):
        pass

    def close_code_panel(self):
        pass

    def hold_progress(self):
        return None

    def cursor_fraction(self, vp):
        return (0.07, 0.9)

    async def run_code(self, lines):
        pass

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        return {f"e:{seq}": text for seq, text in self._timeline_entries}

    def restore_timeline_state(self, state: dict):
        self.clear()
        entries = sorted((int(k[2:]), v) for k, v in state.items() if k.startswith("e:"))
        self._timeline_entries = entries
        self._timeline_seq = entries[-1][0] + 1 if entries else self._timeline_seq
        for _, text in entries:
            self._submit_line(text, allow_speak=False)

    def clear(self):
        self._timeline_entries = []
        self.history = []
        self.scroll = 0
        self.field.last_command = ""
        self.app.invalidate()

    # ---------------------------------------------------------------- evaluation
    def _add(self, kind: str, markup: str) -> Entry:
        e = Entry(kind, markup)
        self.history.append(e)
        del self.history[:-MAX_HISTORY]
        self.scroll = 0
        return e

    def _display_result(self, result: str) -> Entry:
        if "COLOR_RESULT:" not in result:
            return self._add("answer", result)
        parts = result.split()
        i = next(i for i, p in enumerate(parts) if p.startswith("COLOR_RESULT:"))
        before, after = " ".join(parts[:i]) or None, " ".join(parts[i + 1:]) or None
        data = self.evaluator._parse_color_result(parts[i])
        if not data:
            return self._add("answer", result)
        hex_color, _, components = data
        is_modified = len(components) == 1 and components[0].upper() != hex_color.upper()
        box = f"[on {hex_color}]   [/]"
        if len(components) <= 1 and not is_modified:
            return self._add("answer", " ".join(filter(None, [before, box, after])))
        comps = " ".join(f"[on {c}]   [/]" for c in components)
        input_line = " ".join(filter(None, [before, comps, after]))
        result_line = " ".join(filter(None, [before, box, after]))
        combined = f"{input_line} → {result_line}"
        if self.evaluator._estimate_visual_width(combined) <= 80:
            return self._add("answer", combined)
        self._add("answer", input_line)
        return self._add("answer", result_line)

    def submit(self, text: str):
        self._submit_line(text)
        self._timeline_entries.append((self._timeline_seq, text))
        self._timeline_seq += 1
        self._timeline_entries = self._timeline_entries[-TIMELINE_MAX_ENTRIES:]
        self.app.timeline_capture_now("play")

    def _submit_line(self, input_text: str, allow_speak: bool = True):
        force_speak, eval_text = parse_speech_trigger(input_text)
        force_speak = force_speak and allow_speak
        if eval_text:
            self._add("ask", eval_text)
        from ...code_runner import PlayCodeRunner, is_repeat_line
        runner = PlayCodeRunner(self.evaluator)
        if is_repeat_line(eval_text):
            results = runner.run([eval_text])
            entries = [self._display_result(r) for r in results]
            if runner.corrections:
                self.field.set_correction(*runner.corrections[0])
            self.field.remember(input_text)
            if force_speak and results:
                self._speak_sequence(runner.pairs, entries)
            return
        result = self.evaluator.evaluate(eval_text)
        entry = self._display_result(result) if result else None
        self.field.remember(input_text)
        correction = self.evaluator._last_math_correction
        if not correction:
            c = self.evaluator.content.pop_correction()
            if c and c[0] in eval_text.lower():
                correction = c
        if correction:
            self.field.set_correction(correction[0], correction[1])
        from ...tts import _dbg
        _dbg(f"submit raw={input_text!r} force_speak={force_speak} result_len={len(result or '')}")
        if force_speak:
            self._speak(eval_text, result, entry)
        self.app.invalidate()

    # ---------------------------------------------------------------- speech
    def _set_speech(self, entry, state: str):
        if entry is not None:
            entry.speech = state
            self.app.invalidate()

    def _speak(self, input_text: str, result: str, entry):
        from ...tts import _dbg, speak
        speakable = self.evaluator._make_speakable(input_text, result)
        _dbg(f"speakable len={len(speakable)} head={speakable[:60]!r}")
        if not speakable:
            return
        started = speak(speakable,
                        on_playing=lambda: self.app.call_from_thread(self._set_speech, entry, "playing"),
                        on_done=lambda: self.app.call_from_thread(self._set_speech, entry, ""))
        _dbg(f"speak started={started}")
        if not started:
            self._set_speech(entry, "filtered")
            self.app.timers.after(1.5, lambda: self._set_speech(entry, ""))

    def _speak_sequence(self, pairs: list, entries: list):
        from ...tts import speak_many
        spoken = dict(pair_speakables(self.evaluator, pairs))
        items = [(spoken[i], e) for i, e in enumerate(entries) if i in spoken]
        if not items:
            return

        def on_playing(i):
            if i:
                self.app.call_from_thread(self._set_speech, items[i - 1][1], "")
            self.app.call_from_thread(self._set_speech, items[i][1], "playing")

        def on_done():
            for _, e in items:
                self.app.call_from_thread(self._set_speech, e, "")
        if not speak_many([s for s, _ in items], on_playing=on_playing, on_done=on_done):
            for _, e in items:
                self._set_speech(e, "filtered")
                self.app.timers.after(1.5, lambda e=e: self._set_speech(e, ""))

    # ---------------------------------------------------------------- input
    async def handle(self, action):
        f = self.field
        if isinstance(action, NavigationAction):
            if action.direction == "up":
                self.scroll += self.app.g.em(1.5)  # the next draw clamps it to the history's top
            elif action.direction == "down":
                self.scroll = max(0, self.scroll - self.app.g.em(1.5))
            elif action.direction == "left":
                f.move(-1)
            elif action.direction == "right":
                f.move(1)
            return
        if isinstance(action, ControlAction):
            if not action.is_down:
                return
            a = action.action
            if a == "tab" and not action.is_repeat:
                f.accept_autocomplete() or f.set(*toggled_say(f.value, f.cursor))
            elif a == "space":
                if not action.is_repeat:
                    f.insert(" ")
            elif a == "enter" and not action.is_repeat:
                text = f.value.strip()
                if text:
                    f.clear()
                    self.submit(text)
                elif f.last_command:
                    f.set(f.last_command)
                self.hints.advance()
            elif a == "backspace":
                f.backspace()
            elif a == "escape" and not action.is_repeat:
                f.clear()
            return
        if isinstance(action, CharacterAction) and not action.is_repeat:
            if action.char in MATH_OPERATORS:
                f.insert_operator(action.char)
            else:
                f.insert(action.char)
            self.app.set_legend(get_key_color(action.char))

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        em = g.em
        pad = em(1.6)
        x = rect.x + pad
        width = rect.w - 2 * pad
        line_px, sub_px = em(1.35), em(0.95)
        sub_h = g.line_height(sub_px, "mono")
        bottom = rect.bottom - em(1.2) - sub_h
        talks = bool(speech_marks(self.field.value))
        sub = self.field.autocomplete_markup if self.field.matches else self._say_hint(talks)
        ideas = self.hints.current(hold=bool(self.field.value))
        box = self.field.draw_boxed(g, x, bottom - em(0.4) - round(line_px * 1.9), width, line_px, "Type",
                                    ideas=ideas, arrow=ICON_VOLUME_HIGH if talks else "→")
        sub_x = box.x + round(line_px * 0.55)
        g.draw_markup(sub, sub_px, sub_x, bottom, "mono", P.MUTED, rect.right - pad - sub_x, dim_to=P.SURFACE)
        top_limit = rect.y + em(1)
        base = box.y - em(1)
        viewport = base - top_limit
        rows = [(e, self._entry_height(g, e, width), self._gap_above(g, e)) for e in self.history]
        total = sum(h + gap for _, h, gap in rows)
        self.scroll = min(self.scroll, max(0, total - viewport))
        clip_bottom = base + em(0.5)
        y = base + self.scroll
        g.surface.set_clip(pygame.Rect(rect.x, rect.y, rect.w, clip_bottom - rect.y))
        for e, h, gap in reversed(rows):
            y -= h
            if y + h < top_limit:
                break
            if y < clip_bottom:
                self._draw_entry(g, e, x, y, width)
            y -= gap
        g.surface.set_clip(None)
        if total > viewport:
            w = em(0.7)
            track = pygame.Rect(rect.right - em(0.5) - w, top_limit, w, viewport)
            g.rect(P.BG, track, radius=w // 2)
            g.rect(P.FIELD, scroll_thumb(track, viewport, total, self.scroll, em(1.5)), radius=w // 2)

    def _say_hint(self, talks: bool) -> str:
        f = self.field
        dim = [f"[dim]{t}[/]" for t in (f.recall_text(), "⇥ Tab: quiet" if talks else "⇥ Tab: say it") if t]
        return "   ".join(filter(None, [f.autocomplete_markup, *dim]))

    def _answer_px(self, g, e) -> int:
        """Only a small all-emoji answer earns the big size; text stays a
        step above the ask line so it reads as the computer's voice."""
        plain = strip_markup(e.markup).replace(" ", "")
        if is_emoji(plain) and len(plain) <= 12:
            return g.em(2.0)
        return g.em(1.3)

    def _row_gap(self, g) -> int:
        """The hairline between rows, so wrapped letter blocks never fuse."""
        return g.em(0.2)

    def _gap_above(self, g, e) -> int:
        """An answer hugs its ask; each new ask stands clear of the pair above."""
        return g.em(0.35) if e.kind == "answer" else g.em(1.0)

    def _answer_indent(self, g, e) -> int:
        icon = SPEECH_ICONS.get(e.speech, "")
        return g.em(0.1) + (g.measure(icon, g.em(1.05), "mono-bold")[0] + g.em(0.5) if icon else 0)

    def _part_height(self, g, e, part, width) -> int:
        if isinstance(part, tuple):
            return abacus_size(g, part[0])[2]
        return g.markup_size(part, self._answer_px(g, e), "mono-bold", width, self._row_gap(g))[1]

    def _entry_height(self, g, e, width) -> int:
        if e.kind == "ask":
            return g.line_height(g.em(1.05), "mono")
        width -= self._answer_indent(g, e)
        parts = answer_parts(e.markup)
        return sum(self._part_height(g, e, p, width) for p in parts) + self._row_gap(g) * (len(parts) - 1)

    def _first_row_height(self, g, e, width) -> int:
        """The answer's first row, so its speaker sits level with it."""
        part = next(iter(answer_parts(e.markup)), "")
        if isinstance(part, tuple):
            slot, bar, _ = abacus_size(g, part[0])
            return slot + 2 * bar
        lines = g.layout(part, self._answer_px(g, e), "mono-bold", P.TEXT, width)
        return lines[0][1] if lines else 0

    def _draw_entry(self, g, e, x, y, width, ink=None):
        """ink is (text, muted, ground); the screen's tokens unless printing."""
        text, muted, ground = ink or (P.TEXT, P.MUTED, P.SURFACE)
        if e.kind == "ask":
            px = g.em(1.05)
            r = g.draw_text("Type → ", px, x, y, "mono-bold", muted)
            g.draw_text(e.markup, px, r.right, y, "mono", muted)
            return
        icon = SPEECH_ICONS.get(e.speech, "")
        indent = self._answer_indent(g, e)
        if icon:
            mid = y + self._first_row_height(g, e, width - indent) // 2
            g.draw_text(icon, g.em(1.05), x + g.em(0.1), mid, "mono-bold", text, anchor="midleft")
        x, width = x + indent, width - indent
        for part in answer_parts(e.markup):
            if isinstance(part, tuple):
                draw_abacus(g, *part, x, y, muted, ground)
            else:
                g.draw_markup(part, self._answer_px(g, e), x, y, "mono-bold", text, width,
                              dim_to=ground, line_gap=self._row_gap(g))
            y += self._part_height(g, e, part, width) + self._row_gap(g)

    def paper(self, g, size):
        """The newest asks and answers that fit the page, oldest at the top,
        drawn at screen size and enlarged so they read from across a room."""
        w, h = (round(n / PAPER_ZOOM) for n in size)
        rows, used = [], 0
        for e in reversed(self.history):
            eh, gap = self._entry_height(g, e, w), self._gap_above(g, e)
            if used + eh > h:
                break
            rows.append((e, eh))
            used += eh + gap
        if not rows:
            return None
        s = paper.blank((w, h))
        y = 0
        with g.drawing_on(s):
            for e, eh in reversed(rows):
                self._draw_entry(g, e, 0, y, w, (paper.INK, paper.INK_MUTED, paper.WHITE))
                y += eh + self._gap_above(g, e)
        return pygame.transform.smoothscale(s, size)
