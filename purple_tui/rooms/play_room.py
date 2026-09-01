"""Play room: type a word, a sum, a color, and it comes to life. History
scrolls up; the line you're typing sits above the rotating 'Try:' hint."""

import pygame

from .. import palette as P
from ..constants import ICON_SPARK, ICON_VOLUME_HIGH, ICON_VOLUME_OFF
from ..content import get_content
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from ..palette import get_key_color
from ..play_eval import SimpleEvaluator, pair_speakables, parse_speech_trigger
from ..ui import MATH_OPERATORS, HintRotator, TextField

PLAY_HINTS = [
    "Try: cat  •  2 + 2  •  trex!",
    "Try: say hi  (or hello!, both speak aloud)  •  red sun",
    "Try: red + blue!  •  5 dinos",
    "Try: asdfghjkl  •  say yellow",
    "Try: three cats!  •  pink fish",
    "Try: say 4 + 3 cats  •  red + yellow!",
    "Try: I love trex  •  blue frog!",
    "Try: 4 birds + 2 owls  •  say purple  (speaks out loud)",
    "Try: cat times 5  •  light pink unicorn!",
    "Try: I have 5 dinos!  •  say 5 x 5 ducks",
    "Try: pink + purple  •  dark green trex!",
    "Try: say wow!  •  2 red, 3 blue",
    "Try: orange + white  •  rainbow mermaid!  (end with ! to speak it)",
    "Try: 20 19 18 17...  •  bright blue dinosaur!",
    "Try: dinos ... 5  •  2 4 6 8...",
]
TIMELINE_MAX_ENTRIES = 100
MAX_HISTORY = 60
SPEECH_ICONS = {"generating": "··", "playing": ICON_VOLUME_HIGH, "filtered": ICON_VOLUME_OFF}


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


class Entry:
    """One history line: what was asked, or an answer in markup."""

    def __init__(self, kind: str, markup: str):
        self.kind = kind          # "ask" | "answer"
        self.markup = markup
        self.speech = ""          # "", generating, playing, filtered


class PlayRoom:
    name = "play"

    def __init__(self, app):
        self.app = app
        self.evaluator = SimpleEvaluator()
        self.field = TextField(_play_autocomplete, validator=_play_validator)
        self.hints = HintRotator(PLAY_HINTS)
        self.history: list = []
        self.scroll = 0                  # entries hidden below the bottom (scrolled up)
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
        hex_color, color_name, components = data
        other = " ".join(filter(None, [before, after]))
        is_modified = len(components) == 1 and components[0].upper() != hex_color.upper()
        box = f"[on {hex_color}]   [/]"
        if len(components) <= 1 and not is_modified:
            return self._add("answer", " ".join(filter(None, [before, box, after])))
        comps = " ".join(f"[on {c}]   [/]" for c in components)
        if is_modified and not other:
            return self._add("answer", f"{comps} → {box}  {color_name}")
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
        from ..code_runner import PlayCodeRunner, is_repeat_line
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
        from ..tts import _dbg
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
        from ..tts import _dbg, speak
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
        from ..tts import speak_many
        spoken = dict(pair_speakables(self.evaluator, pairs))
        items = [(spoken[i], e) for i, e in enumerate(entries) if i in spoken]
        if not items:
            return

        def on_playing(i):
            self.app.call_from_thread(self._set_speech, items[i][1], "playing")
            if i:
                self.app.call_from_thread(self._set_speech, items[i - 1][1], "")

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
                self.scroll = min(self.scroll + 1, max(0, len(self.history) - 1))
            elif action.direction == "down":
                self.scroll = max(0, self.scroll - 1)
            elif action.direction == "left":
                f.move(-1)
            elif action.direction == "right":
                f.move(1)
            return
        if isinstance(action, ControlAction):
            if not action.is_down:
                return
            a = action.action
            if a == "tab":
                f.accept_autocomplete()
            elif a == "space":
                if not action.is_repeat:
                    f.insert(" ")
            elif a == "enter":
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
        line_px = em(1.05)
        bottom = rect.bottom - em(1.4)
        g.draw_text(f"{ICON_SPARK}  {self.hints.current}", em(0.95), x, bottom, "mono", P.DIM, anchor="bottomleft")
        bottom -= g.line_height(em(0.95), "mono") + em(1.1)
        sub = self.field.autocomplete_markup or \
            f"[dim]{self.field.recall_text() or 'Type a word, then press Enter'}[/]"
        sub_h = g.line_height(em(0.92), "mono")
        sub_x = self.field.text_x(g, x, line_px, label_px=em(1.2))
        g.draw_markup(sub, em(0.92), sub_x, bottom - sub_h, "mono", P.MUTED, rect.right - pad - sub_x, dim_to=P.SURFACE)
        bottom -= sub_h + em(0.4)
        box = pygame.Rect(sub_x - em(0.6), bottom - em(2.0), 0, em(2.0))
        box.w = min(rect.right - pad - box.x, em(21))
        g.rect(P.FIELD, box, radius=em(0.42))
        g.rect(P.LINE, box, width=1, radius=em(0.42))
        line_h = g.line_height(line_px, "mono")
        self.field.draw(g, x, box.centery - line_h // 2, box.right - x, line_px, label_px=em(1.2))
        top_limit = rect.y + em(1)
        y = box.y - em(1)
        g.surface.set_clip(pygame.Rect(rect.x, rect.y, rect.w, y - rect.y + em(0.5)))
        for e in reversed(self.history[:len(self.history) - self.scroll] if self.scroll else self.history):
            h = self._entry_height(g, e, width)
            y -= h
            if y + h < top_limit:
                break
            self._draw_entry(g, e, x, y, width)
            y -= em(0.3) if e.kind == "answer" else em(0.1)
        g.surface.set_clip(None)

    def _answer_px(self, g, e) -> int:
        return g.em(2.2)

    def _entry_height(self, g, e, width) -> int:
        if e.kind == "ask":
            return g.line_height(g.em(1.05), "mono")
        return g.markup_size(e.markup, self._answer_px(g, e), max_width=width)[1]

    def _draw_entry(self, g, e, x, y, width):
        if e.kind == "ask":
            px = g.em(1.05)
            r = g.draw_text("Ask → ", px, x, y, "mono-bold", P.MUTED)
            g.draw_text(e.markup, px, r.right, y, "mono", P.MUTED)
            return
        ax = x + g.em(0.1)
        icon = SPEECH_ICONS.get(e.speech, "")
        if icon:
            ax = g.draw_text(icon, g.em(1.05), ax, y, "mono-bold", P.TEXT).right + g.em(0.5)
        g.draw_markup(e.markup, self._answer_px(g, e), ax, y, "sans-bold", P.TEXT, width - (ax - x), dim_to=P.SURFACE)
