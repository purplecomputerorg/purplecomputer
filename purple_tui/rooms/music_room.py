"""Music room: a 10x4 grid that mirrors the keyboard. Letters play notes,
digits play percussion, Tab says letters, arrows change key, Enter cycles the
instrument, hold Enter records a loop, hold Space opens the code line."""

import asyncio
import time
from pathlib import Path

import pygame

from .. import palette as P
from ..audio import play_safe
from ..code_runner import MusicCodeRunner
from ..constants import HOLD_OR_TAP_THRESHOLD
from ..keyboard import CharacterAction, ControlAction, HoldOrTap, NavigationAction
from ..loop_station import IDLE, LOOPING, RECORDING, LoopStation
from ..mixer import mixer_generation, mixer_ready_for_play, warm_mixer
from ..music_constants import (
    ALL_KEYS, COLOR_KEYCAP, COLORS, DEFAULT_ROOT_INDEX, FRIENDLY_KEY_NAMES, FRIENDLY_KEYS, GRID_KEYS,
    INSTRUMENT_ALIASES, INSTRUMENTS, PERCUSSION_NAMES, pitch_filename, pitch_for,
)
from ..palette import KEY_COLORS, text_color_for
from ..panels import CodePanel, LoopPanel, SpaceHold
from ..ui import TRACK, draw_keycap, draw_label

MODE_MUSIC, MODE_LETTERS = "music", "letters"
_KEY_TO_RC = {key: (r - 1, c) for r, row in enumerate(GRID_KEYS) if r >= 1 for c, key in enumerate(row)}
_SPEAKABLE_KEYS = {k for k in ALL_KEYS if k.isalpha() or k.isdigit()}
_KID_MATH_UNREMAP = {"÷": "/", "×": "*"}
_KID_MATH_DISPLAY = {"/": "÷", "*": "×"}
WAVEFRONT_COLOR = "#5a3875"
PITCH_TRANSITION_DURATION = 0.25
LETTERS_SAME_KEY_DEBOUNCE_S = 0.40
LETTERS_CROSS_KEY_DEBOUNCE_S = 0.20
NOSCREEN_TEXT = "No-screen music mode\nPress keys to play sounds\n\nHold Esc to exit"


def _sounds_path() -> Path:
    paths = [Path(__file__).parent.parent.parent / "packs" / "core-sounds" / "content",
             Path.home() / ".purple" / "packs" / "core-sounds" / "content"]
    return next((p for p in paths if p.exists()), paths[0])


def _find_sound(base: Path, name: str):
    return next((p for ext in (".ogg", ".wav") if (p := base / f"{name}{ext}").exists()), None)


def _load(path) -> pygame.mixer.Sound | None:
    try:
        s = pygame.mixer.Sound(str(path))
        s.set_volume(0.4)
        return s
    except pygame.error:
        return None


class MusicRoom:
    name = "music"

    def __init__(self, app):
        self.app = app
        self.color_state = {k: -1 for k in ALL_KEYS}
        self.instrument_index = 0
        self.root_index = DEFAULT_ROOT_INDEX
        self.letters_mode = False
        self.show_labels = False
        self._note_labels: set = set()
        self._note_timers: dict = {}
        self._transition = None
        self._transition_timer = None
        self._instrument_sounds: dict = {}
        self._percussion_sounds: dict = {}
        self._percussion_loaded = False
        self._letter_sounds: dict = {}
        self._letter_sounds_loaded = False
        self._sounds_generation = mixer_generation()
        self.loop = LoopStation()
        self._loop_task = None
        self._loop_timer = None
        self._last_letter_key = None
        self._last_letter_press_t = float("-inf")
        self.space = SpaceHold(app, self._space_tap, self._space_hold_fired)
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
        state = {f"k:{k}": v for k, v in self.color_state.items() if v != -1}
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
        self._transition = None
        self.app.invalidate()

    def clear(self):
        self.restore_timeline_state({})

    # ---------------------------------------------------------------- sounds
    def _drop_stale_sounds(self):
        if self._sounds_generation != mixer_generation():
            self._clear_sound_caches()
            self._sounds_generation = mixer_generation()

    def _clear_sound_caches(self):
        self._instrument_sounds.clear()
        self._percussion_sounds.clear()
        self._percussion_loaded = False
        self._letter_sounds.clear()
        self._letter_sounds_loaded = False

    def _ensure_instrument_loaded(self, instrument_id: str):
        self._drop_stale_sounds()
        if instrument_id in self._instrument_sounds or not mixer_ready_for_play():
            return
        inst_path = _sounds_path() / instrument_id
        cache = {}
        if inst_path.exists():
            for path in inst_path.glob("*.ogg"):
                if (s := _load(path)) is not None:
                    cache[path.stem] = s
        self._instrument_sounds[instrument_id] = cache

    def _ensure_percussion_loaded(self):
        self._drop_stale_sounds()
        if self._percussion_loaded or not mixer_ready_for_play():
            return
        for key in ALL_KEYS:
            if key.isdigit() and (path := _find_sound(_sounds_path(), key)) and (s := _load(path)) is not None:
                self._percussion_sounds[key] = s
        self._percussion_loaded = True

    def _ensure_letter_sounds_loaded(self):
        self._drop_stale_sounds()
        if self._letter_sounds_loaded or not mixer_ready_for_play():
            return
        self._letter_sounds_loaded = True
        base = _sounds_path()
        letters_path = base / "letters"
        if not letters_path.exists():
            return
        dirs = [letters_path]
        from ..settings import get_kid_letters
        if get_kid_letters() and (base / "letters-kid").exists():
            dirs.insert(0, base / "letters-kid")
        for key in _SPEAKABLE_KEYS:
            path = next((p for d in dirs if (p := _find_sound(d, key.lower()))), None)
            if path and (s := _load(path)) is not None:
                self._letter_sounds[key] = s

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
            self._ensure_percussion_loaded()
            sound = self._percussion_sounds.get(key)
        else:
            stem = self._pitch_stem_for_key(key)
            inst_id = INSTRUMENTS[instrument_index][0]
            self._ensure_instrument_loaded(inst_id)
            sound = self._instrument_sounds.get(inst_id, {}).get(stem) if stem else None
        if sound is not None:
            ch = play_safe(sound)
            if ch is not None and volume_scale != 1.0:
                ch.set_volume(volume_scale)

    def play_letter(self, key: str):
        if self.app._effective_volume() == 0:
            return
        self._ensure_letter_sounds_loaded()
        if key in self._letter_sounds:
            play_safe(self._letter_sounds[key])

    def reset_letter_sounds(self):
        self._letter_sounds.clear()
        self._letter_sounds_loaded = False

    def cleanup_sounds(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except pygame.error:
            pass
        self._clear_sound_caches()
        for t in self._note_timers.values():
            t.stop()
        self._note_timers.clear()
        self._note_labels.clear()

    def _play_key(self, key: str, mode: str, instrument: int | None = None):
        is_letters_layer = mode == MODE_LETTERS and key in _SPEAKABLE_KEYS
        scale = 0.2 if is_letters_layer else 1.0
        self.play_sound_with_instrument(key, self.instrument_index if instrument is None else instrument, scale)
        if is_letters_layer:
            self.play_letter(key)

    # ---------------------------------------------------------------- grid state
    def next_color(self, key: str):
        self.color_state[key] = (self.color_state[key] + 1) % len(COLORS)
        self.app.invalidate()

    def set_color_index(self, key: str, index: int):
        if key in self.color_state:
            self.color_state[key] = index
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
        if mode == MODE_MUSIC:
            self.flash_note(key)
        if self._is_noscreen:
            self._noscreen_flash(self.get_color(key))

    def _sync_panels(self):
        """The loop panel shows exactly while the loop station isn't idle."""
        if self.app.active_room != "music" or self.code_panel is not None:
            return
        if self.loop.state == IDLE:
            if isinstance(self.app._panel, LoopPanel):
                self.app.set_panel(None)
        elif not isinstance(self.app._panel, LoopPanel):
            self.app.set_panel(LoopPanel(self.app, self.loop))
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
        if self.code_panel is None and self.app._code_panel_enabled and self.loop.state == IDLE:
            self.cleanup_sounds()
            self.code_panel = CodePanel(self.app, "music")
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
            for i, (inst_id, inst_name) in enumerate(INSTRUMENTS):
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
        self.letters_mode = not self.letters_mode
        label = "Say Letters" if self.letters_mode else f"🎵 {INSTRUMENTS[self.instrument_index][1]}"
        self.app.clear_notifications()
        self.app.notify(label)

    def _letters_debounce_drop(self, lookup: str, now: float) -> bool:
        threshold = LETTERS_SAME_KEY_DEBOUNCE_S if lookup == self._last_letter_key else LETTERS_CROSS_KEY_DEBOUNCE_S
        if now - self._last_letter_press_t < threshold:
            return True
        self._last_letter_key, self._last_letter_press_t = lookup, now
        return False

    async def handle(self, action):
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
                self.app.clear_notifications()
                self.app.notify(f"🎵 Key {FRIENDLY_KEY_NAMES[self.root_index]}")
            return
        if isinstance(action, CharacterAction):
            if action.is_repeat or not action.char:
                return
            self.space.other_key()
            char = action.char
            lookup = char.upper() if char.isalpha() else _KID_MATH_UNREMAP.get(char, char)
            if lookup not in ALL_KEYS:
                return
            if self.letters_mode and self._letters_debounce_drop(lookup, time.monotonic()):
                return
            mode = self._current_mode()
            self.loop.record_event(lookup, mode, instrument=self.instrument_index)
            self._hit(lookup, mode)

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
                self.instrument_index = (self.instrument_index + 1) % len(INSTRUMENTS)
                self.app.clear_notifications()
                self.app.notify(f"🎵 {INSTRUMENTS[self.instrument_index][1]}")

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
        p = self.space.progress()
        if p is not None:
            return p, "code"
        if self._enter_down_at is not None and self.enter_hold.is_pending:
            return min(1.0, (time.monotonic() - self._enter_down_at) / HOLD_OR_TAP_THRESHOLD), "loop"
        return None

    def cursor_fraction(self, vp):
        return None

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        if self._is_noscreen:
            return self._draw_noscreen(g, rect)
        head_h, hint_h = g.vh(5.5), g.vh(4.5)
        self._draw_header(g, pygame.Rect(rect.x, rect.y, rect.w, head_h))
        grid = pygame.Rect(rect.x + g.vw(1.5), rect.y + head_h, rect.w - g.vw(3), rect.h - head_h - hint_h)
        self._draw_grid(g, grid)
        if self.app._panel is None:
            px, cy = g.vh(1.9), rect.bottom - hint_h // 2
            g.draw_text(self._hint_text(), px, rect.x + g.vw(1.5), cy, "mono", P.DIM, anchor="midleft")
            if self.app._code_panel_enabled:
                g.draw_text("🤖 Hold Space: write code", px, rect.right - g.vw(1.5), cy, "mono", P.DIM, anchor="midright")

    def _hint_text(self) -> str:
        if self.app._littles_mode:
            return "Enter: instrument"
        parts = ["Space: hide notes" if self.show_labels else "Space: show notes"]
        if self.app._music_key_switching_enabled:
            parts.append("Arrows: key")
        parts.append("Enter: instrument")
        if self.app._music_looping_enabled:
            parts.append("Hold Enter: loop")
        return "   ".join(parts)

    def _draw_header(self, g, r):
        px = g.vh(1.9)
        cy = r.centery
        inst = f"🎵 {INSTRUMENTS[self.instrument_index][1]}"
        if self.app._littles_mode:
            draw_label(g, inst, px, r.centerx, cy, P.TEXT, anchor="center")
            return
        key = f"← Key {FRIENDLY_KEY_NAMES[self.root_index]} →" if self.app._music_key_switching_enabled else f"Key {FRIENDLY_KEY_NAMES[DEFAULT_ROOT_INDEX]}"
        draw_label(g, key, px, r.x + g.vw(1.5), cy)
        gap = g.vw(1.5)
        w_inst, w_say = g.measure(inst.upper(), px, "mono-bold", TRACK)[0] + px, g.measure("SAY LETTERS", px, "mono-bold", TRACK)[0] + px
        x = r.centerx - (w_inst + gap + w_say) // 2
        draw_label(g, inst, px, x + w_inst // 2, cy, anchor="center", on=not self.letters_mode)
        draw_label(g, "Say Letters", px, x + w_inst + gap + w_say // 2, cy, anchor="center", on=self.letters_mode)
        hint = "to stop saying letters" if self.letters_mode else "to say letters"
        g.draw_text(hint, px, r.right - g.vw(1.5), cy, "mono", P.MUTED, anchor="midright")
        draw_keycap(g, "Tab", px, r.right - g.vw(1.5) - g.measure(hint + " ", px, "mono")[0] - int(px * 0.5), cy, anchor="midright")

    def _draw_grid(self, g, r):
        gap_x, gap_y = g.vw(0.5), g.vh(0.9)
        cw = (r.w - 9 * gap_x) / 10
        ch = (r.h - 3 * gap_y) / 4
        letter_px = int(min(ch * 0.36, cw * 0.4))
        label_px = max(10, int(ch * 0.16))
        for row_idx, row in enumerate(GRID_KEYS):
            melodic = row_idx >= 1
            for col_idx, key in enumerate(row):
                bg = self.get_color(key)
                note = None
                if melodic:
                    root_idx, at_front = self._transition_state_for_col(col_idx)
                    note, _ = pitch_for(row_idx - 1, col_idx, FRIENDLY_KEYS[root_idx], 0)
                    if at_front:
                        bg = WAVEFRONT_COLOR
                tile = pygame.Rect(int(r.x + col_idx * (cw + gap_x)), int(r.y + row_idx * (ch + gap_y)), int(cw), int(ch))
                g.rect(bg, tile)
                fg = P.ACCENT if bg == P.TILE else text_color_for(bg)
                g.draw_text(_KID_MATH_DISPLAY.get(key, key), letter_px, tile.centerx, tile.centery, "sans-bold", fg, anchor="center")
                show = key in self._note_labels or (melodic and (self._transition is not None or self.show_labels))
                label = PERCUSSION_NAMES.get(key, "") if key.isdigit() else (note or "")
                if show and label:
                    muted = "#6a5a7a" if fg == "#000000" else "#a898c0"
                    g.draw_text(f"♪ {label} ♪", label_px, tile.centerx, tile.y + label_px, "sans-bold", muted, anchor="center")

    def _draw_noscreen(self, g, rect):
        cy = rect.centery
        if self._noscreen_dot:
            g.draw_text("●", g.vh(6), rect.centerx, cy - g.vh(10), "sans-heavy", self._noscreen_dot, anchor="center")
        g.draw_markup(NOSCREEN_TEXT, g.vh(2.8), rect.x, cy - g.vh(4), "sans-bold", P.MUTED, rect.w, "center", P.SURFACE, g.vh(0.6))
