"""Music room: a 10x4 grid that mirrors the keyboard. Letters play notes,
digits play percussion, Tab says letters, arrows change key, Enter cycles the
instrument, hold Enter records a loop, hold Space opens the code line."""

import asyncio
import time

import pygame

from ... import palette as P
from ...audio import play_safe
from ...code_runner import MusicCodeRunner
from ...constants import HOLD_OR_TAP_THRESHOLD, ICON_KEYBOARD, ICON_LOOP, ICON_MUSIC
from ...keyboard import CharacterAction, ControlAction, HoldOrTap, NavigationAction
from ...loop_station import IDLE, LOOPING, RECORDING, LoopStation
from ...mixer import warm_mixer
from ...music_constants import (
    ALL_KEYS, COLOR_KEYCAP, COLORS, DEFAULT_ROOT_INDEX, FRIENDLY_KEY_NAMES, FRIENDLY_KEYS, GRID_KEYS,
    INSTRUMENT_ALIASES, PERCUSSION_NAMES, instruments, pitch_filename, pitch_for,
)
from ...palette import KEY_COLORS, text_color_for
from .. import paper
from ..music_replay import Recording
from ..panels import FOOTER_EM, CodePanel, Echo, LoopPanel, ReplayPanel, SpaceHold
from ..sounds import SoundBank
from ..ui import (CODE_HINT, KID_MATH_KEYS, KID_MATH_REMAP, LEFT, RIGHT, draw_key_hint, draw_label, draw_mode_switch,
                  draw_status_row, hint_row_h, hold_status, status_row_h)
from .base import Room

MODE_MUSIC, MODE_LETTERS = "music", "letters"
PAPER_OUTLINE = "#d0d0d0"
_KEY_TO_RC = {key: (r - 1, c) for r, row in enumerate(GRID_KEYS) if r >= 1 for c, key in enumerate(row)}
PITCH_TRANSITION_DURATION = 0.25
LETTERS_SAME_KEY_DEBOUNCE_S = 0.40
LETTERS_CROSS_KEY_DEBOUNCE_S = 0.20
ECHO_PAUSE_S = 2.0            # a rest this long starts a new line of echoed notes
NOSCREEN_TEXT = "No-screen music mode\nPress keys to play sounds\n\nHold Esc to exit"


class MusicRoom(Room):
    name, label, icon = "music", "Music", ICON_MUSIC
    LANDSCAPE = True
    has_code_panel = True
    keeps_audio_awake = True

    def __init__(self, app):
        super().__init__(app)
        self.color_state = {k: -1 for k in ALL_KEYS}
        self.instrument_index = 0
        self.root_index = DEFAULT_ROOT_INDEX
        self.letters_mode = False
        self.show_labels = False
        self._note_labels: set = set()
        self._note_timers: dict = {}
        self._transition = None
        self._transition_timer = None
        self.sounds = SoundBank()
        self.loop = LoopStation()
        self._loop_task = None
        self._loop_timer = None
        self.recording = Recording(self.color_state)
        self._replay = None       # (task, colors it ends on, when it started) while a save plays back
        self._saved_loop = None
        self._last_letter_key = None
        self._last_letter_press_t = float("-inf")
        self.space = SpaceHold(app, self._space_tap, self._space_hold_fired)
        self.echo = Echo(pause=ECHO_PAUSE_S)
        self.enter_hold = HoldOrTap(HOLD_OR_TAP_THRESHOLD)
        self._enter_down_at = None
        self._enter_ring = None
        self.code_panel = None
        self._noscreen_dot = None
        self._noscreen_timer = None
        self._warmed = False

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self):
        if not self._warmed:
            self._warmed = True
            import threading
            threading.Thread(target=warm_mixer, daemon=True, name="mixer-warm").start()
        self._sync_panels()

    def on_leave(self):
        self._stop_loop()
        self.code_panel = None

    def stop_sound(self):
        self._stop_loop()

    def on_littles_change(self):
        self.app.invalidate()

    @property
    def _is_noscreen(self) -> bool:
        return self.app._littles_mode == "music_noscreen"

    def _current_mode(self) -> str:
        return MODE_LETTERS if self.letters_mode else MODE_MUSIC

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        colors = self._replay[1] if self._replay else self.color_state
        state = {f"k:{k}": v for k, v in colors.items() if v != -1}
        state.update(instrument=self.instrument_index, root=self.root_index, letters=self.letters_mode, labels=self.show_labels)
        return state

    def restore_timeline_state(self, state: dict):
        self._stop_loop()
        self.instrument_index = int(state.get("instrument", 0))
        self.root_index = int(state.get("root", DEFAULT_ROOT_INDEX))
        self.letters_mode = bool(state.get("letters", False))
        self.show_labels = bool(state.get("labels", False))
        self.color_state = {k: -1 for k in ALL_KEYS}
        for key, val in state.items():
            if key.startswith("k:") and key[2:] in self.color_state:
                self.color_state[key[2:]] = int(val)
        self.recording = Recording.load(state.get("replay"), self.color_state)
        self._saved_loop = state.get("loop")
        self._transition = None
        self.echo.reset()
        self.app.invalidate()

    def clear(self):
        self.restore_timeline_state({})

    # ---------------------------------------------------------------- saved music
    def save_extras(self) -> dict:
        """The last minute of playing, and the loop if one is going."""
        loop = self._saved_loop if self._replay else self._loop_data()
        extras = {"replay": self.recording.data()} if self.recording.notes else {}
        return extras | ({"loop": loop} if loop else {})

    def _loop_data(self):
        if self.loop.state != LOOPING:
            return None
        return {"ms": round(self.loop.loop_duration * 1000),
                "notes": [[k, m, self._instrument(i)[0], round(o * 1000)] for k, m, o, i in self.loop.loop_events]}

    def on_open_save(self):
        """Play the save's music from the colors it started on up to the saved ones."""
        if not self.recording.notes:
            return self._carry_on()
        self._replay = (asyncio.create_task(self._replay_notes()), dict(self.color_state), time.monotonic())
        self.color_state = dict(self.recording.start)
        self._sync_panels()

    async def _replay_notes(self):
        played = self.recording.notes[0][3]
        for key, mode, instrument, ms in self.recording.notes:
            await asyncio.sleep((ms - played) / 1000)
            played = ms
            self._hit(key, mode, self._instrument_index(instrument))
        self._end_replay()

    def replay_progress(self) -> float:
        total = self.recording.seconds
        return min(1.0, (time.monotonic() - self._replay[2]) / total) if self._replay and total else 1.0

    def _end_replay(self, carry_on: bool = True):
        """The saved colors come back, and a saved loop carries on unless the music is stopping."""
        if self._replay is None:
            return
        task, self.color_state, _ = self._replay
        self._replay = None
        if task is not asyncio.current_task():
            task.cancel()
        if carry_on:
            self._carry_on()
        self._saved_loop = None
        self._sync_panels()
        self.app.invalidate()

    def _carry_on(self):
        loop, self._saved_loop = self._saved_loop, None
        if loop:
            self.loop.play([(k, m, ms / 1000, self._instrument_index(i)) for k, m, i, ms in loop["notes"]], loop["ms"] / 1000)
            self._start_loop_playback()
            self._sync_panels()

    # ---------------------------------------------------------------- sounds
    def _pitch_stem_for_key(self, key: str):
        rc = _KEY_TO_RC.get(key)
        if rc is None:
            return None
        note, octave = pitch_for(rc[0], rc[1], FRIENDLY_KEYS[self.root_index], 0)
        return pitch_filename(note, octave)

    def play_sound_with_instrument(self, key: str, instrument_index: int, volume_scale: float = 1.0):
        if self.app._effective_volume() == 0:
            return
        if key.isdigit():
            sound = self.sounds.percussion().get(key)
        else:
            stem = self._pitch_stem_for_key(key)
            sound = self.sounds.instrument(self._instrument(instrument_index)[0]).get(stem) if stem else None
        if sound is not None:
            ch = play_safe(sound)
            if ch is not None and volume_scale != 1.0:
                ch.set_volume(volume_scale)

    def play_letter(self, key: str):
        if self.app._effective_volume() == 0:
            return
        if sound := self.sounds.letters().get(key):
            play_safe(sound)

    @staticmethod
    def _instrument(index: int) -> tuple:
        """(id, name); an index saved before a pack was removed wraps instead of failing."""
        available = instruments()
        return available[index % len(available)]

    @staticmethod
    def _instrument_index(instrument_id: str) -> int:
        """A saved instrument whose pack was removed plays as the first one."""
        ids = [i for i, _ in instruments()]
        return ids.index(instrument_id) if instrument_id in ids else 0

    def reset_letter_sounds(self):
        self.sounds.clear()

    def cleanup_sounds(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except pygame.error:
            pass
        self.sounds.clear()
        for t in self._note_timers.values():
            t.stop()
        self._note_timers.clear()
        self._note_labels.clear()

    def _play_key(self, key: str, mode: str, instrument: int | None = None):
        instrument = self.instrument_index if instrument is None else instrument
        if self._replay is None:
            self.recording.add(key, mode, self._instrument(instrument)[0], time.monotonic())
        is_letters_layer = mode == MODE_LETTERS and key in self.sounds.letters()
        scale = 0.2 if is_letters_layer else 1.0
        self.play_sound_with_instrument(key, instrument, scale)
        if is_letters_layer:
            self.play_letter(key)

    # ---------------------------------------------------------------- grid state
    def next_color(self, key: str):
        self.color_state[key] = (self.color_state[key] + 1) % len(COLORS)
        self.app.invalidate()

    def set_color_index(self, key: str, index: int):
        if key in self.color_state:
            self.color_state[key] = index
            self.recording = Recording(self.color_state)
            self.app.invalidate()

    def get_color(self, key: str) -> str:
        idx = self.color_state[key]
        state = COLORS[idx] if idx >= 0 else None
        if state is None:
            return P.TILE
        return KEY_COLORS.get(key.lower(), P.TILE) if state == COLOR_KEYCAP else state

    def flash_note(self, key: str):
        if key in self._note_timers:
            self._note_timers[key].stop()
        self._note_labels.add(key)

        def _clear():
            self._note_labels.discard(key)
            self._note_timers.pop(key, None)
            self.app.invalidate()
        self._note_timers[key] = self.app.timers.after(1.0, _clear)
        self.app.invalidate()

    def shift_root(self, new_root_index: int, direction: int):
        self._transition = {"start": time.monotonic(), "direction": direction, "prev": self.root_index}
        self.root_index = new_root_index
        if self._transition_timer is None:
            self._transition_timer = self.app.timers.every(0.03, self._transition_tick)
        self.app.invalidate()

    def set_key(self, root_index: int):
        if self.app._music_key_switching_enabled and root_index != self.root_index:
            self.shift_root(root_index, 1 if root_index > self.root_index else -1)

    def _transition_tick(self):
        if self._transition and time.monotonic() - self._transition["start"] >= PITCH_TRANSITION_DURATION:
            self._transition = None
        if self._transition is None and self._transition_timer:
            self._transition_timer.stop()
            self._transition_timer = None
        self.app.invalidate()

    def _transition_state_for_col(self, col: int):
        t = self._transition
        if t is None:
            return self.root_index, False
        progress = max(0.0, min(1.0, (time.monotonic() - t["start"]) / PITCH_TRANSITION_DURATION))
        wavefront = progress * 10.0
        if t["direction"] >= 0:
            passed, at_front = col < wavefront, abs(col - wavefront) < 0.6
        else:
            passed, at_front = col > (9 - wavefront), abs((9 - col) - wavefront) < 0.6
        return (self.root_index if passed else t["prev"]), at_front

    # ---------------------------------------------------------------- loop station
    def _advance_loop_state(self):
        state = self.loop.state
        if state == IDLE:
            self.loop.start_recording()
            self._start_loop_timer()
        elif state == RECORDING:
            events, _ = self.loop.finish_recording()
            if events:
                self._start_loop_playback()
            else:
                self.loop.stop()
        elif state == LOOPING:
            self._stop_loop()
        self._sync_panels()

    def _stop_loop(self):
        self._end_replay(carry_on=False)
        self.loop.stop()
        if self._loop_timer:
            self._loop_timer.stop()
            self._loop_timer = None
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = None
        self._sync_panels()

    def _start_loop_timer(self):
        if self._loop_timer is None:
            self._loop_timer = self.app.timers.every(0.15, self._loop_tick)

    def _loop_tick(self):
        if self.loop.state == RECORDING and self.loop.is_at_max_duration():
            events, _ = self.loop.finish_recording()
            if events:
                self._start_loop_playback()
            else:
                self.loop.stop()
            self._sync_panels()
        elif self.loop.state == IDLE and self._loop_timer:
            self._loop_timer.stop()
            self._loop_timer = None
        self.app.invalidate()

    def _start_loop_playback(self):
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = asyncio.create_task(self._loop_playback())
        self._start_loop_timer()

    async def _loop_playback(self):
        try:
            while self.loop.state == LOOPING:
                events, duration = self.loop.loop_events, self.loop.loop_duration
                if not events or duration <= 0:
                    break
                cycle_start = asyncio.get_event_loop().time()
                self.loop.start_new_cycle()
                for key, mode, offset, instrument in sorted(events, key=lambda e: e[2]):
                    if self.loop.state != LOOPING:
                        return
                    wait = offset - (asyncio.get_event_loop().time() - cycle_start)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    if self.loop.state != LOOPING:
                        return
                    self._hit(key, mode, instrument)
                remaining = duration - (asyncio.get_event_loop().time() - cycle_start)
                if remaining > 0:
                    await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            pass

    def _hit(self, key: str, mode: str, instrument: int | None = None):
        self.next_color(key)
        self._play_key(key, mode, instrument)
        if self.app.active_room == self.name:
            self.app.set_legend(KEY_COLORS.get(key.lower()), fade=True)
        if mode == MODE_MUSIC:
            self.flash_note(key)
        if self._is_noscreen:
            self._noscreen_flash(self.get_color(key))

    def _sync_panels(self):
        """The replay panel shows while a save plays back, the loop panel while the loop station isn't idle."""
        if self.app.active_room != "music" or self.code_panel is not None:
            return
        panel = self.app._panel
        if self._replay:
            if not isinstance(panel, ReplayPanel):
                self.app.set_panel(ReplayPanel(self.app, self))
        elif self.loop.state != IDLE:
            if not isinstance(panel, LoopPanel):
                self.app.set_panel(LoopPanel(self.app, self.loop))
        elif isinstance(panel, (LoopPanel, ReplayPanel)):
            self.app.set_panel(None)
        self.app.invalidate()

    # ---------------------------------------------------------------- no-screen mode
    def _noscreen_flash(self, color: str):
        self._noscreen_dot = color
        if self._noscreen_timer:
            self._noscreen_timer.stop()

        def _clear():
            self._noscreen_dot = None
            self._noscreen_timer = None
            self.app.invalidate()
        self._noscreen_timer = self.app.timers.after(0.4, _clear)
        self.app.invalidate()

    # ---------------------------------------------------------------- code panel
    def open_code_panel(self):
        if self.code_panel is None and self.app._code_panel_enabled:
            if self.loop.state != IDLE:
                self._stop_loop()
            self.cleanup_sounds()
            self.code_panel = CodePanel(self.app, "music", self.echo.take())
            self.app.set_panel(self.code_panel)

    def close_code_panel(self):
        if self.code_panel is not None:
            self.code_panel = None
            self.app.set_panel(None)

    def _space_hold_fired(self):
        if self.code_panel is None:
            self.open_code_panel()
        else:
            self.close_code_panel()

    def _space_tap(self):
        if self.code_panel is not None:
            self.code_panel.field.insert(" ")
            return
        if self.app._littles_mode:
            return
        if self.loop.state == RECORDING:
            self._advance_loop_state()
        elif self.loop.state == LOOPING:
            self.loop.start_new_cycle()
        else:
            self.show_labels = not self.show_labels
        self.app.invalidate()

    def set_instrument_by_name(self, name: str):
        name_lower = INSTRUMENT_ALIASES.get(name.lower(), name.lower())
        for match in (lambda a, b: a == b, lambda a, b: a.startswith(b)):
            for i, (inst_id, inst_name) in enumerate(instruments()):
                if match(inst_name.lower(), name_lower) or match(inst_id.lower(), name_lower):
                    self.instrument_index = i
                    self.app.invalidate()
                    return

    async def run_code(self, lines: list):
        try:
            runner = MusicCodeRunner(
                play_key_fn=self._play_key,
                set_instrument_fn=self.set_instrument_by_name,
                color_fn=self.next_color,
                flash_fn=self.flash_note,
                set_letters_fn=lambda on: setattr(self, "letters_mode", on),
                set_key_fn=self.set_key,
            )
            await runner.run(lines, self._current_mode())
            if runner.corrections and self.code_panel:
                self.code_panel.set_correction(*runner.corrections[-1])
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        self.app.invalidate()

    # ---------------------------------------------------------------- input
    def _toggle_letters(self):
        # The header shows the mode (instrument vs Say Letters) persistently,
        # so the switch needs no toast over the keys.
        self.letters_mode = not self.letters_mode
        self.app.invalidate()

    def _letters_debounce_drop(self, lookup: str, now: float) -> bool:
        threshold = LETTERS_SAME_KEY_DEBOUNCE_S if lookup == self._last_letter_key else LETTERS_CROSS_KEY_DEBOUNCE_S
        if now - self._last_letter_press_t < threshold:
            return True
        self._last_letter_key, self._last_letter_press_t = lookup, now
        return False

    async def handle(self, action):
        if self._replay and getattr(action, "is_down", True) and not getattr(action, "is_repeat", False):
            self._end_replay()   # the key that stops it plays as usual; Esc only stops
            if isinstance(action, ControlAction) and action.action == "escape":
                self.app._escape_consumed_by_mode = True
                return
        if isinstance(action, ControlAction) and action.action == "space" and self.space.route(action):
            return
        if self.code_panel is not None:
            self.space.other_key()
            result = await self.code_panel.handle(action)
            if result == "tab_fallthrough":
                self._toggle_letters()
            elif result == "close":
                self.close_code_panel()
            return
        if isinstance(action, ControlAction):
            if action.action == "space":
                if action.is_down and not action.is_repeat:
                    self._space_tap()
                return
            if action.action == "enter":
                self._handle_enter(action)
                return
            if action.is_down:
                self.space.other_key()
                self._flush_enter()
                if action.action == "escape" and self.loop.state != IDLE:
                    self._stop_loop()
                    self.app._escape_consumed_by_mode = True
                elif action.action == "tab":
                    self.echo.flush()
                    if self.loop.state != IDLE:
                        self._stop_loop()
                    else:
                        self._toggle_letters()
            return
        if isinstance(action, NavigationAction):
            if action.is_repeat or self.app._littles_mode or not self.app._music_key_switching_enabled:
                return
            self.space.other_key()
            self._flush_enter()
            if action.direction in ("left", "right"):
                step = 1 if action.direction == "right" else -1
                self.shift_root((self.root_index + step) % len(FRIENDLY_KEYS), step)
            return
        if isinstance(action, CharacterAction):
            if action.is_repeat or not action.char:
                return
            self.space.other_key()
            char = action.char
            lookup = char.upper() if char.isalpha() else KID_MATH_KEYS.get(char, char)
            if lookup not in ALL_KEYS:
                return
            if self.letters_mode and self._letters_debounce_drop(lookup, time.monotonic()):
                return
            mode = self._current_mode()
            self.loop.record_event(lookup, mode, instrument=self.instrument_index)
            self._hit(lookup, mode)
            self.echo.letter("", lookup.lower())

    def _handle_enter(self, action):
        if self.enter_hold.fired:
            if not action.is_down:
                self.enter_hold.on_up()
                self._enter_down_at = None
            return
        if action.is_down and not action.is_repeat:
            self.space.other_key()
            self._enter_down_at = time.monotonic()
            self.enter_hold.on_down(self.app.timers.after, self._enter_hold_fired)
            self._enter_ring = self.app.timers.every(1 / 30, self.app.invalidate)
        elif not action.is_down:
            self._stop_enter_ring()
            if self.enter_hold.on_up():
                self.instrument_index = (self.instrument_index + 1) % len(instruments())
                self.echo.flush()
                self.echo.word(f"choose {self._instrument(self.instrument_index)[0]}")
                self.app.invalidate()

    def _flush_enter(self):
        self.enter_hold.on_other_key()
        self._stop_enter_ring()

    def _stop_enter_ring(self):
        self._enter_down_at = None
        if self._enter_ring:
            self._enter_ring.stop()
            self._enter_ring = None
        self.app.invalidate()

    def _enter_hold_fired(self):
        self._stop_enter_ring()
        if self.app._littles_mode or self.code_panel is not None:
            return
        if self.loop.state == IDLE:
            if self.app._music_looping_enabled:
                self._advance_loop_state()
        else:
            self._stop_loop()

    def hold_progress(self):
        if self._enter_down_at is not None and self.enter_hold.is_pending and \
                (self.loop.state != IDLE or self.app._music_looping_enabled):
            doing = "record a loop" if self.loop.state == IDLE else "stop the loop"
            return hold_status(min(1.0, (time.monotonic() - self._enter_down_at) / HOLD_OR_TAP_THRESHOLD),
                               "Enter", ICON_LOOP, doing)
        return self.space.status(self.code_panel is not None)

    def footer_h(self, g) -> int:
        return g.em(FOOTER_EM)

    def cursor_fraction(self, vp):
        return None

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        if self._is_noscreen:
            return self._draw_noscreen(g, rect)
        em = g.em
        panel = self.app._panel
        hint_h = em(FOOTER_EM) if panel is None else 0 if isinstance(panel, (LoopPanel, ReplayPanel)) else em(1.0)
        pad = em(1.6)
        if self.code_panel is None:
            head_h = em(4.3)
            self._draw_header(g, rect)
        else:
            head_h = status_row_h(g) + em(0.4)
            draw_status_row(g, pygame.Rect(rect.x, rect.y + em(0.4), rect.w, status_row_h(g)), self._code_status(g))
        grid = pygame.Rect(rect.x + pad, rect.y + head_h, rect.w - 2 * pad, rect.h - head_h - hint_h)
        self._draw_grid(g, grid)
        if self.app._panel is None:
            cy = rect.bottom - em(1.4) - g.line_height(em(0.92), "mono") // 2
            right_edge = rect.right - pad
            if self.app._code_panel_enabled:
                right_edge = draw_key_hint(g, CODE_HINT, em(0.86), right_edge, cy, anchor="midright").left - em(2)
            draw_key_hint(g, self._hint_text(), em(0.92), (rect.x + right_edge) // 2, cy, anchor="center")

    def _hint_text(self) -> str:
        if self.app._littles_mode:
            return "{Enter} sound"
        return "{hold Enter} loop" if self.app._music_looping_enabled else ""

    def _draw_header(self, g, rect):
        """The same header as Art and Blocks: Enter and Space chips beside the
        Sounds / ABC switch."""
        instrument = self._instrument(self.instrument_index)[1]
        if self.app._littles_mode:
            plate = f"{ICON_KEYBOARD} Saying Letters" if self.letters_mode else f"{ICON_MUSIC} {instrument}"
            draw_label(g, plate, g.em(1.0), rect.centerx, rect.y + g.em(1.9), P.TEXT, anchor="center", on=True)
            return
        bar = rect.inflate(-2 * g.em(0.7), -2 * g.em(0.7))
        bar.h = hint_row_h(g)
        draw_mode_switch(g, bar, ("Sounds", "ABC"), 1 if self.letters_mode else 0,
                         chips=(("Enter", ICON_MUSIC, instrument, False, "sound"), ("Space", None, "notes", self.show_labels)))

    def _code_status(self, g) -> tuple:
        """What code can change, in its own words: choose, letters, key."""
        return ((ICON_MUSIC, self._instrument(self.instrument_index)[1]),
                (ICON_KEYBOARD, "Letters on" if self.letters_mode else "Letters off"),
                (None, f"Key of {FRIENDLY_KEY_NAMES[self.root_index]}"))

    def arrow_hint(self) -> str:
        if not self.app._music_key_switching_enabled:
            return f"Key of {FRIENDLY_KEY_NAMES[DEFAULT_ROOT_INDEX]}"
        return f"Arrows change key: {FRIENDLY_KEY_NAMES[self.root_index]}  {LEFT} {RIGHT}"

    def paper(self, g, size, on_screen=False):
        """The kid's colors on the keyboard grid; quiet keys print as outlined letters."""
        if all(self.get_color(k) == P.TILE for row in GRID_KEYS for k in row):
            return None
        s = paper.blank(size, on_screen)
        with g.drawing_on(s):
            self._draw_grid(g, s.get_rect(), on_paper=not on_screen)
        return s

    def _draw_grid(self, g, r, on_paper=False):
        """Ten by four gapless square blocks: a quiet key is just its letter,
        a sounding key fills its whole block with color."""
        size = min(r.w / 10, r.h / 4)
        xs = [round(r.centerx - 5 * size + i * size) for i in range(11)]
        ys = [round(r.centery - 2 * size + i * size) for i in range(5)]
        letter_px = max(12, int(size * 0.3))
        label_px = max(10, int(size * 0.15))
        for row_idx, row in enumerate(GRID_KEYS):
            melodic = row_idx >= 1
            for col_idx, key in enumerate(row):
                bg = self.get_color(key)
                note = None
                if melodic:
                    root_idx, at_front = self._transition_state_for_col(col_idx)
                    note, _ = pitch_for(row_idx - 1, col_idx, FRIENDLY_KEYS[root_idx], 0)
                    if at_front and not on_paper:
                        bg = P.LINE
                tile = pygame.Rect(xs[col_idx], ys[row_idx], xs[col_idx + 1] - xs[col_idx], ys[row_idx + 1] - ys[row_idx])
                quiet = bg == P.TILE
                if not quiet:
                    g.rect(bg, tile)
                elif on_paper:
                    g.rect(PAPER_OUTLINE, tile, width=2)
                fg = (paper.INK_MUTED if on_paper else P.MUTED) if quiet else text_color_for(bg)
                g.draw_text(KID_MATH_REMAP.get(key, key), letter_px, tile.centerx, tile.centery,
                            "mono-bold" if quiet else "mono-heavy", fg, anchor="center")
                flashing = key in self._note_labels or (melodic and self._transition is not None)
                show = (flashing and not on_paper) or (melodic and self.show_labels)
                label = PERCUSSION_NAMES.get(key, "") if key.isdigit() else (note or "")
                if show and label:
                    muted = "#6a5a7a" if fg == "#000000" else "#a898c0"
                    g.draw_text(f"♪ {label} ♪", label_px, tile.centerx, tile.y + label_px, "mono-bold", muted, anchor="center")

    def _draw_noscreen(self, g, rect):
        cy = rect.centery
        if self._noscreen_dot:
            g.draw_text("●", g.vh(6), rect.centerx, cy - g.vh(10), "sans-heavy", self._noscreen_dot, anchor="center")
        g.draw_markup(NOSCREEN_TEXT, g.vh(1.9), rect.x, cy - g.vh(3), "mono", P.DIM, rect.w, "center", P.SURFACE, g.vh(0.5))
