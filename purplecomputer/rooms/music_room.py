"""Music room: a 10x4 grid that mirrors the keyboard. Letters play notes,
digits play percussion, Tab says letters, arrows change key, Enter cycles the
instrument (in Letters: names or sounds), hold Enter records a loop, and the code line opens from the Esc menu.
In Letters, a real word typed shows under the grid and Space says it."""

import asyncio
import math
import time

import pygame

from .. import palette as P
from ..audio import play_safe
from ..code_runner import MusicCodeRunner
from ..content import get_content
from ..constants import ICON_KEYBOARD, ICON_MUSIC
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from ..loop_station import IDLE, LOOPING, LoopStation
from ..mixer import warm_mixer
from ..speech_filter import is_clean
from ..music_constants import (
    ALL_KEYS, COLOR_KEYCAP, COLORS, DEFAULT_ROOT_INDEX, FRIENDLY_KEY_NAMES, FRIENDLY_KEYS, GRID_KEYS,
    INSTRUMENT_ALIASES, PERCUSSION, instruments, pitch_filename, pitch_for,
)
from ..palette import KEY_COLORS, text_color_for
from .. import paper
from ..gfx import is_one_emoji, mix, rgb
from ..panels import FOOTER_EM, CodePanel, Echo, LoopPanel
from ..sounds import SoundBank
from ..ui import (ABC_PICTURE, CODE_HINT, LOOP, KID_MATH_KEYS, KID_MATH_REMAP, LEFT, RIGHT, draw_key_hint, key_hint_width, draw_label,
                  draw_mode_switch, draw_status_row, HeldKey, hold_status, status_row_h)
from .base import Room

MODE_MUSIC, MODE_LETTERS = "music", "letters"
PAPER_OUTLINE = "#d0d0d0"
_KEY_TO_RC = {key: (r - 1, c) for r, row in enumerate(GRID_KEYS) if r >= 1 for c, key in enumerate(row)}


def drum_picture(key: str) -> str:
    return f"drums/{PERCUSSION[key].replace('-', '_')}.png"

PITCH_TRANSITION_DURATION = 0.25
LETTER_PICTURES = ("letters/names.png", "letters/sounds.png")
KEY_WORD = 0.75               # sizes the grid's side margin; changing it moves the grid
NOTE_STRIP = 0.45             # height of the tape's row under the grid, in keys
NOTE_FAINT = 0.72             # how far a key's note name sinks into the key until it sounds
LETTERS_MASH_S = 0.06         # letters closer than this are one hand landing at once
LETTER_FADE = (1, 1, 0.6, 0.35, 0.15)  # the same letter again and again; past the end it's silent
LETTER_FADE_REST_S = 1.0      # a rest this long, or another letter, brings it back to full
LETTER_AFTER_GAP_S = 0.15     # between Purple saying a key and the family's recording after it
ECHO_PAUSE_S = 2.0            # a rest this long starts a new line of echoed notes, and a new phrase on the tape
TAPE_MAX = 100                # notes kept on the music tape
ERASE_MORE_S = 1.0            # seconds of holding Backspace before it takes whole phrases (whole words in Letters)
ERASE_EVERY_S = (0.15, 0.6)   # a held Backspace takes a note, or later a phrase, this often, not at key repeat
ERASE_HINT = "{Backspace} erase"
TAPE_FADE = 0.9               # how far the tape has faded into the background by the time it clears
TAPE_REST_FADE = 0.65         # how far back the Notes tape sits, except while it plays back or loops
REPLAY_LIGHT_S = 0.25         # how long a key the tape or loop plays lights in its color
REST_STEPS = 20               # the tape fades and its clock empties in this many steps over its quiet rest
NOTE_ROW = 2                  # Shift plays a note by name on this grid row, the middle octave
SONG_REST_S = 20.0            # this long without a sound, and the Notes tape clears (still in Time Travel)
TAPE_HINT = "{Space} play it"
LAST_SONG_HINT = "{Space} last song"
NOTE_NAMES_HINT = "{hold Shift} + a letter plays its note"
TUNE_GAP_MAX_S = 1.5          # a longer rest in a tune plays back this long, so a pause to think isn't silence
WORD_REST_S = 10.0            # a rest this long starts a new word; slow spellers pause between letters
WORD_GAP_S = 1.5              # a two-letter word counts only after a rest this long
SPELL_MAX = 12                # letters kept toward a word
WORD_HINT = "{Space} say it"
NOSCREEN_TEXT = "No-screen music mode\nPress keys to play sounds\n\nHold Esc to exit"
FLAT_KEYS = {5, 10}           # F and B flat name their black keys as flats
SHARP_TO_FLAT = {"C#": "D♭", "D#": "E♭", "F#": "G♭", "G#": "A♭", "A#": "B♭"}


def key_label(root_index: int) -> str:
    return f"Key of {FRIENDLY_KEY_NAMES[root_index]}"


def note_name(col: int, root_index: int) -> str:
    """A column's note as a reader expects it in that key: F♯ in G and D, B♭ in F and B♭."""
    root = FRIENDLY_KEYS[root_index]
    note = pitch_for(0, col, root, 0)[0]
    return SHARP_TO_FLAT.get(note, note) if root in FLAT_KEYS else note.replace("#", "♯")


def note_label(note: str) -> str:
    return f"♪ {note}"


def instrument_icon(instrument_id: str) -> str:
    """Its picture, or a pack's emoji; anything that isn't one emoji gets the music glyph, as rooms do."""
    icon = get_content().instrument_icon(instrument_id)
    return icon if is_one_emoji(icon) else ICON_MUSIC


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
        self.say_sounds = False
        self._note_labels: set = set()
        self._note_timers: dict = {}
        self._transition = None
        self._transition_timer = None
        self.sounds = SoundBank()
        self.loop = LoopStation()
        self._loop_task = None
        self._loop_timer = None
        self._last_letter_press_t = float("-inf")
        self._letter_playing = None
        self._letter_next = None
        self._letter_streak = (None, float("-inf"), 0)   # (key, last press, presses in a row)
        self._spelled = ""
        self._typed_at: list = []  # when each letter of _spelled was typed
        self.word = None          # the real word the letters just typed end with
        self._tape: list = []     # (key, mode, when) of the song played in Notes, on whichever instrument is set
        self._tape_origin = 0.0   # when the song began, and how many notes have dropped off its front,
        self._tape_base = 0       # so each note keeps its timeline key while the song grows
        self._last_song = None    # (tape, origin, base) of the song quiet cleared, which Space or hold Enter brings back
        self._erasing_since = None
        self._erased_at = 0.0
        self._tape_task = None
        self._tape_at = None      # the tape note playing back now, or looping
        self._loop_tape: dict = {}
        self._lit: dict = {}      # keys the tape or loop just played: their timers
        self._rest_timers: list = []
        self._active_at = 0.0     # the last sound, play back or erase: the tape clears once it's quiet this long
        self.echo = Echo(pause=ECHO_PAUSE_S)
        self.enter_hold = HeldKey(app, self._enter_hold_fired)
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
        self.stop_sound()
        self.code_panel = None

    def stop_sound(self):
        self._stop_loop()
        self._stop_letter()
        self._stop_tape()

    def on_littles_change(self):
        self.app.invalidate()

    @property
    def _is_noscreen(self) -> bool:
        return self.app._littles_mode == "music_noscreen"

    def _current_mode(self) -> str:
        return MODE_LETTERS if self.letters_mode else MODE_MUSIC

    @property
    def keys_word(self):
        return "music" if self.letters_mode else None

    # ---------------------------------------------------------------- timeline
    def timeline_state(self) -> dict:
        state = {f"k:{k}": v for k, v in self.color_state.items() if v != -1}
        state.update(instrument=self.instrument_index, root=self.root_index, letters=self.letters_mode, sounds=self.say_sounds)
        return state | self._tape_state()

    def _tape_state(self) -> dict:
        """The song a note per key, numbered from its start, so a Time Travel step adds only the notes new in it."""
        return {f"t:{self._tape_base + i}": [k, round((t - self._tape_origin) * 1000)] for i, (k, _, t) in enumerate(self._tape)}

    def _restore_tape(self, state: dict) -> list:
        """The song in a state, as a tune to load, numbered on from where it was."""
        notes = sorted((int(k[2:]), v) for k, v in state.items()
                       if k.startswith("t:") and k[2:].isdigit() and isinstance(v, list) and len(v) == 2)
        self._tape_base = notes[0][0] if notes else 0
        return [[k, MODE_MUSIC, ms] for _, (k, ms) in notes]

    def restore_timeline_state(self, state: dict):
        self._stop_loop()
        self.instrument_index = int(state.get("instrument", 0))
        self.root_index = int(state.get("root", DEFAULT_ROOT_INDEX))
        self.letters_mode = bool(state.get("letters", False))
        self.say_sounds = bool(state.get("sounds", False))
        self.color_state = {k: -1 for k in ALL_KEYS}
        for key, val in state.items():
            if key.startswith("k:") and key[2:] in self.color_state:
                self.color_state[key[2:]] = int(val)
        self._transition = None
        self._forget_word()
        self._stop_tape()
        self._tape = []
        old = state.get("replay")   # saves from before the tape kept the last minute of playing; it plays as their tune
        self._load_tune(self._restore_tape(state) or (old.get("notes") if isinstance(old, dict) else None) or [])
        self._load_tune(state.get("tune") or [])
        self._busy()
        self.echo.reset()
        self.app.invalidate()

    def clear(self):
        self._last_song = None
        self.restore_timeline_state({})

    # ---------------------------------------------------------------- saved music
    def save_extras(self) -> dict:
        """In Letters, the letters on the tape, which the save says when it opens (the song is in the state)."""
        tune = self._tune() if self.letters_mode else []
        return {"tune": [[k, m, round((t - tune[0][2]) * 1000)] for k, m, t in tune]} if tune else {}

    def _load_tune(self, notes: list):
        """A tune of [key, mode, ms] onto the tape, ending a phrase's rest ago so the next note starts a new
        phrase. Older saves' notes also name an instrument, before the ms; the room's own plays them."""
        notes = [n for n in notes if isinstance(n, list) and len(n) in (3, 4)][-TAPE_MAX:]
        if not notes:
            return
        end = time.monotonic() - ECHO_PAUSE_S
        tune = [(n[0], n[1], end + (n[-1] - notes[-1][-1]) / 1000) for n in notes]
        letters = [(k, t) for k, m, t in tune if m == MODE_LETTERS and k.isalpha()][-SPELL_MAX:]
        if self.letters_mode and letters:
            self._spelled, self._typed_at = "".join(k.lower() for k, _ in letters), [t for _, t in letters]
            self.word = self._word_at_end()
        if any(n[1] == MODE_MUSIC for n in tune):
            self._tape = [n for n in tune if n[1] == MODE_MUSIC]
            self._tape_origin = end - notes[-1][-1] / 1000

    def on_open_save(self):
        """The saved picture as it was, and its tune played once."""
        if self._tune():
            self._play_tape()

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
        volume = self._letter_volume(key, time.monotonic())
        self._stop_letter()
        if volume and (clips := self.sounds.letters(self.say_sounds).get(key)):
            self._play_clips(clips, volume)

    def _play_clips(self, clips: list, volume: float):
        """The first now and each next once it ends; the next letter cuts them all off."""
        first, *rest = clips
        self._letter_playing, self._letter_next = first, None
        if (ch := play_safe(first)) is not None:
            ch.set_volume(volume)
        if rest:
            self._letter_next = self.app.timers.after(first.get_length() + LETTER_AFTER_GAP_S, lambda: self._play_clips(rest, volume))

    def _stop_letter(self):
        if self._letter_next is not None:
            self._letter_next.stop()
        try:
            if self._letter_playing is not None:
                self._letter_playing.stop()
        except pygame.error:  # the mixer was released while idle
            pass
        self._letter_playing = self._letter_next = None

    def _letter_volume(self, key: str, now: float) -> float:
        last, at, n = self._letter_streak
        n = n + 1 if key == last and now - at < LETTER_FADE_REST_S else 0
        self._letter_streak = (key, now, n)
        return LETTER_FADE[n] if n < len(LETTER_FADE) else 0

    @staticmethod
    def _instrument(index: int) -> tuple:
        """(id, name); an index saved before a pack was removed wraps instead of failing."""
        available = instruments()
        return available[index % len(available)]

    @classmethod
    def _instrument_label(cls, index: int) -> str:
        inst_id, name = cls._instrument(index)
        return f"{instrument_icon(inst_id)} {name}"

    def cleanup_sounds(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except pygame.error:
            pass
        self._stop_letter()
        self.sounds.clear()
        for t in self._note_timers.values():
            t.stop()
        self._note_timers.clear()
        self._note_labels.clear()

    def _play_key(self, key: str, mode: str):
        if mode == MODE_LETTERS and key in self.sounds.letters():
            self.play_letter(key)
        else:
            self.play_sound_with_instrument(key, self.instrument_index)

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

    def _tile_color(self, key: str, on_paper=False) -> str:
        """Its color, or lit brighter than any it takes while the tape or a loop plays it."""
        if key in self._lit and not on_paper:
            return mix(KEY_COLORS.get(key.lower(), P.ACCENT), "#ffffff", 0.35)
        return self.get_color(key)

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
        if root_index != self.root_index:
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
    def _loop_tune(self):
        """Hold Enter: the song plays over and over, its rests as played back, and notes played along join in."""
        if not self._loopable() or not self._bring_back():
            return
        tune = list(self._tape)
        offsets = self._tune_offsets(tune)
        gaps = [b - a for a, b in zip(offsets, offsets[1:])]
        tail = min(max(sum(gaps) / len(gaps), 0.25), TUNE_GAP_MAX_S) if gaps else 0.6
        self._stop_tape()
        events = [(k, m, o - offsets[0]) for (k, m, _), o in zip(tune, offsets)]
        self._loop_tape = {e: i for i, e in enumerate(events)}   # the tape's own notes, which the dot follows
        self.loop.play(events, offsets[-1] - offsets[0] + tail)
        self._start_loop_playback()
        self._sync_panels()

    def _stop_loop(self):
        looped = self.loop.state != IDLE
        self.loop.stop()
        if self._loop_timer:
            self._loop_timer.stop()
            self._loop_timer = None
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        self._loop_task = None
        self._tape_at = None
        if looped:   # the quiet starts when the loop does
            self._busy()
        self._sync_panels()

    def _start_loop_timer(self):
        if self._loop_timer is None:
            self._loop_timer = self.app.timers.every(0.15, self._loop_tick)

    def _loop_tick(self):
        if self.loop.state == IDLE and self._loop_timer:
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
                for event in sorted(events, key=lambda e: e[2]):
                    if self.loop.state != LOOPING:
                        return
                    wait = event[2] - (asyncio.get_event_loop().time() - cycle_start)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    if self.loop.state != LOOPING:
                        return
                    self._tape_at = self._loop_tape.get(event, self._tape_at)
                    self._replay(event[0], event[1])
                remaining = duration - (asyncio.get_event_loop().time() - cycle_start)
                if remaining > 0:
                    await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            pass

    def _hit(self, key: str, mode: str):
        """A key played: its color moves on."""
        if mode == MODE_LETTERS:
            self._spell(key, time.monotonic())
        self.next_color(key)
        self._sound(key, mode)

    def _replay(self, key: str, mode: str):
        """A key the tape or a loop plays: it lights a moment in its color, and the colors the kid made stay put."""
        if key in self._lit:
            self._lit[key].stop()

        def _off():
            self._lit.pop(key, None)
            self.app.invalidate()
        self._lit[key] = self.app.timers.after(REPLAY_LIGHT_S, _off)
        self._sound(key, mode)

    def _sound(self, key: str, mode: str):
        self._play_key(key, mode)
        if self.app.active_room == self.name:
            self.app.set_legend(KEY_COLORS.get(key.lower()), fade=True)
        if mode == MODE_MUSIC:
            self.flash_note(key)
        if self._is_noscreen:
            self._noscreen_flash(self.get_color(key))

    def _sync_panels(self):
        """The loop panel shows while the loop station isn't idle."""
        if self.app.active_room != "music" or self.code_panel is not None:
            return
        panel = self.app._panel
        if self.loop.state != IDLE:
            if not isinstance(panel, LoopPanel):
                self.app.set_panel(LoopPanel(self.app, self.loop))
        elif isinstance(panel, LoopPanel):
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

    def _space_tap(self):
        if self.app._littles_mode:
            return
        if self.loop.state == LOOPING:
            self._start_loop_playback()  # from the top: the sound and the bar start over together
        elif self.letters_mode and self.word:
            from ..tts import speak_many
            speak_many([self.word], family=False)
            self._busy()
        elif not self.letters_mode and self._bring_back():
            self._play_tape()
        self.app.invalidate()

    def _bring_back(self) -> bool:
        """The song on the tape, the one quiet cleared if the tape is empty: whether there is one."""
        if not self._tape and self._last_song:
            self._tape, self._tape_origin, self._tape_base = self._last_song
            self._last_song = None
        return bool(self._tape)

    # ---------------------------------------------------------------- tape
    def _tape_add(self, key: str, now: float):
        """The song grows; a long enough rest before a note marks a new phrase in it."""
        if not self._tape:
            self._tape_origin, self._tape_base = now, 0
        tape = self._tape + [(key, MODE_MUSIC, now)]
        self._tape_base += max(0, len(tape) - TAPE_MAX)
        self._tape = tape[-TAPE_MAX:]
        self._busy()

    def _tune(self) -> list:
        """What the tape holds, as (key, mode, when): the song in Notes, the letters in Letters."""
        if self.letters_mode:
            return [(c.upper(), MODE_LETTERS, t) for c, t in zip(self._spelled, self._typed_at)]
        return list(self._tape)

    @staticmethod
    def _tune_offsets(tune: list) -> list:
        """When each note plays back, from the first: its rests as played, a long one cut short."""
        offsets = [0.0]
        for a, b in zip(tune, tune[1:]):
            offsets.append(offsets[-1] + min(b[2] - a[2], TUNE_GAP_MAX_S))
        return offsets

    def _play_tape(self):
        self._stop_tape()
        self._tape_task = asyncio.create_task(self._tape_playback(self._tune()))

    async def _tape_playback(self, tune: list):
        """The tape again as it was played, its keys lit, nothing joining the loop or the code."""
        try:
            played = 0.0
            for i, ((key, mode, _), at) in enumerate(zip(tune, self._tune_offsets(tune))):
                await asyncio.sleep(at - played)
                played, self._tape_at = at, i
                self._replay(key, mode)
            await asyncio.sleep(0.3)
        finally:
            self._tape_at = None
            self._busy()
            self.app.invalidate()

    def _stop_tape(self):
        if self._tape_task is not None and not self._tape_task.done():
            self._tape_task.cancel()
        self._tape_task, self._tape_at = None, None

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
                set_letter_sounds_fn=lambda on: setattr(self, "say_sounds", on),
                set_key_fn=self.set_key,
                note_key_fn=lambda letter: self._note_key(letter) if self.app._music_note_names_enabled else None,
            )
            await self.run_shown(runner, lines, self._current_mode())
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        self.app.invalidate()

    # ---------------------------------------------------------------- input
    def _toggle_letters(self):
        self._stop_loop()
        self.letters_mode = not self.letters_mode
        self._forget_word()
        self._schedule_quiet()   # switching isn't a sound: the song's quiet goes on
        self._announce_voice()
        self.app.invalidate()

    def _announce_voice(self):
        """What the keys play now, shown in a toast and heard on one sample, for kids who can't read the header."""
        if self.letters_mode:
            self.announce(f"Letter {'sounds' if self.say_sounds else 'names'}", LETTER_PICTURES[self.say_sounds])
            self.play_letter("A")
        else:
            self.announce(self._instrument_label(self.instrument_index))
            self.play_sound_with_instrument("A", self.instrument_index)

    def _spell(self, key: str, now: float):
        """Letters typed without a long rest build words; anything else starts over."""
        if not key.isalpha() or (self._typed_at and now - self._typed_at[-1] >= WORD_REST_S):
            self._forget_word()
        if key.isalpha():
            self._spelled = (self._spelled + key.lower())[-SPELL_MAX:]
            self._typed_at = (self._typed_at + [now])[-SPELL_MAX:]
            self.word = self._word_at_end()
            self._busy()

    def _rest(self) -> tuple:
        """(how long the quiet runs before the tape clears, clock steps, when it began)."""
        held = self._typed_at if self.letters_mode else self._tape
        return (WORD_REST_S if self.letters_mode else SONG_REST_S), REST_STEPS, self._active_at if held else None

    def _sounding(self) -> bool:
        return (self._tape_task is not None and not self._tape_task.done()) or self.loop.state != IDLE

    def _busy(self):
        """Something just sounded or changed on the tape: its clock starts over."""
        self._active_at = time.monotonic()
        self._schedule_quiet()

    def _schedule_quiet(self):
        """The clock's steps and the clear for the tape showing now, from where its quiet already is: a song
        left quiet past its rest while Letters was on clears as soon as it shows again."""
        for timer in self._rest_timers:
            timer.stop()
        rest, steps, began = self._rest()
        now = time.monotonic()
        if began is not None and now - began >= rest:
            self._rest_timers = []
            return self._quiet()
        start = now if began is None else began
        self._rest_timers = [self.app.timers.after(start + rest * i / steps - now, self.app.invalidate)
                             for i in range(1, steps) if start + rest * i / steps > now]
        self._rest_timers.append(self.app.timers.after(start + rest - now, self._quiet))

    def _rest_left(self) -> float:
        """How much of the quiet is left, in whole clock steps; all of it while the tape or a loop plays."""
        rest, steps, began = self._rest()
        if self._sounding():
            return 1.0
        passed = steps if began is None else int((time.monotonic() - began) * steps / rest)
        return max(0, steps - passed) / steps

    def _quiet(self):
        """Quiet long enough: the tape clears, the letters or the song. Not while it plays or in Time Travel."""
        if self._sounding() or self.app._time_travel is not None:
            return self._busy()
        if self.letters_mode:
            self._forget_word()
        elif self._tape:
            self._last_song, self._tape = (self._tape, self._tape_origin, self._tape_base), []
            self.app.timeline_capture_now(self.name)
        self.app.invalidate()

    def _word_at_end(self):
        """The longest real word the letters end with: three letters or more, or two typed after a rest. One typed
        since the last rest comes first, as the tape's gap promises; a slow speller's word spans rests when
        nothing since the last one is a word."""
        run, at = self._spelled, self._typed_at
        two = len(run) == 2 or (len(run) > 2 and at[-2] - at[-3] >= WORD_GAP_S)
        since = len(run) - next((i for i in range(len(run) - 1, 0, -1) if at[i] - at[i - 1] >= WORD_GAP_S), 0)
        ends = (run[-n:] for n in (*range(since, 1, -1), *range(len(run), since, -1)) if n >= 3 or two)
        return next((w for w in ends if get_content().is_known_word(w) and is_clean(w)), None)

    def _forget_word(self):
        self._spelled, self._typed_at, self.word = "", [], None

    def _letters_mash_drop(self, now: float) -> bool:
        """A new letter cuts off the one still speaking, so only a whole hand landing at once needs dropping."""
        if now - self._last_letter_press_t < LETTERS_MASH_S:
            return True
        self._last_letter_press_t = now
        return False

    async def handle(self, action):
        if self._tape_task is not None and getattr(action, "is_down", True) and not getattr(action, "is_repeat", False):
            self._stop_tape()   # Space starts it over; any other key just stops it
        if self.code_panel is not None:
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
            if action.action == "backspace":
                self._handle_backspace(action)
                return
            if action.is_down:
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
            if action.is_repeat or self.app._littles_mode:
                return
            self._flush_enter()
            if action.direction in ("left", "right") and not self.letters_mode:   # Letters has no key to change
                step = 1 if action.direction == "right" else -1
                self.shift_root((self.root_index + step) % len(FRIENDLY_KEYS), step)
                self.announce(f"{ICON_MUSIC}  {key_label(self.root_index)}")
            return
        if isinstance(action, CharacterAction):
            if action.is_repeat or not action.char:
                return
            char = action.char
            lookup = char.upper() if char.isalpha() else KID_MATH_KEYS.get(char, char)
            by_name = action.shift_held and self._shift_notes(held=False)
            named = by_name and self._note_key(lookup)
            echo = ("notes", lookup.lower()) if named else ("", None)
            lookup = named or lookup
            if lookup not in ALL_KEYS or (by_name and not named):   # with Shift, only the note names play
                return
            if self.letters_mode and self._letters_mash_drop(time.monotonic()):
                return
            mode = self._current_mode()
            self.loop.record_event(lookup, mode)
            self._hit(lookup, mode)
            if mode == MODE_MUSIC and self.loop.state == IDLE:
                self._tape_add(lookup, time.monotonic())
            self._echo_key(echo[0], echo[1] or lookup.lower())

    def _echo_key(self, way: str, ch: str):
        """Code for a key played: `notes c` for one played by name, which `notes` keeps to the end of its
        line, so a switch between names and keys starts a new line."""
        last = self.echo.parts[-1][0] if self.echo.parts else None
        if last is not None and "notes" in (way, last) and last != way:
            self.echo.flush()
        self.echo.letter(way, ch)

    @property
    def uses_sticky_shift(self) -> bool:
        """Only its code takes a tap of Shift; the grid plays the same either way and Shift notes need it held."""
        return self.code_panel is not None

    def _shift_notes(self, held: bool = True) -> bool:
        """Held Shift plays notes by name (not a tap, so a stray one can't): in Notes, when a parent left it on;
        `held` asks whether Shift is down now."""
        on = self.app._music_note_names_enabled and not self.letters_mode and not self.app._littles_mode
        return on and (not held or self.app._keyboard_state_machine.shift_held)

    def _note_key(self, letter: str):
        """The middle row's key that plays the note named `letter` (F plays F♯ in G): its one octave from the root."""
        col = next((c for c in range(7) if note_name(c, self.root_index)[0] == letter), None)
        return None if col is None else GRID_KEYS[NOTE_ROW][col]

    def _handle_backspace(self, action):
        """Erases from the end of the tape a note (in Letters, a letter) at a time, held after a while whole
        phrases (words), as Backspace does in Write and Art."""
        if not action.is_down:
            self._erasing_since = None
            return
        if self.app._littles_mode or self.loop.state != IDLE:
            return
        now = time.monotonic()
        if not action.is_repeat or self._erasing_since is None:
            self._erasing_since = self._erased_at = now
            self._erase(whole=False)
        else:
            whole = now - self._erasing_since >= ERASE_MORE_S
            if now - self._erased_at >= ERASE_EVERY_S[whole]:
                self._erased_at = now
                self._erase(whole)
        self.app.invalidate()

    def _erase(self, whole: bool):
        """The last note or letter, or with `whole` back to the start of its phrase or word."""
        tune = self._tune()
        if not tune:
            return
        gap = WORD_GAP_S if self.letters_mode else ECHO_PAUSE_S
        n = 1
        while whole and n < len(tune) and tune[-n][2] - tune[-n - 1][2] < gap:
            n += 1
        if self.letters_mode:
            self._spelled, self._typed_at = self._spelled[:-n], self._typed_at[:-n]
            self.word = self._word_at_end() if self._spelled else None
        else:
            self._tape = self._tape[:-n]
        self._busy()

    def _handle_enter(self, action):
        if self.enter_hold.fired:
            if not action.is_down:
                self.enter_hold.up()
            return
        if action.is_down and not action.is_repeat:
            self.enter_hold.down()
        elif not action.is_down:
            if self.enter_hold.up():
                self._next_voice()
                self.app.invalidate()

    def _next_voice(self):
        """Enter's tap: the next instrument, or in Letters, names or sounds."""
        if self.letters_mode:
            self.say_sounds = not self.say_sounds
        else:
            self.instrument_index = (self.instrument_index + 1) % len(instruments())
            self.echo.flush()
            self.echo.word(f"choose {self._instrument(self.instrument_index)[0]}")
        self._announce_voice()

    def _flush_enter(self):
        self.enter_hold.other_key()

    def _enter_hold_fired(self):
        if self.app._littles_mode or self.code_panel is not None:
            return
        if self.loop.state != IDLE:
            self._stop_loop()
        elif self._loopable():
            self._loop_tune()
        elif self.letters_mode:   # Letters has nothing to loop, so a hold is a tap
            self._next_voice()
            self.app.invalidate()

    def _loopable(self) -> bool:
        """Only a Notes song loops: Letters has Space to say its word, and its letters clear."""
        return self.app._music_looping_enabled and not self.letters_mode and bool(self._tape or self._last_song)

    def hold_progress(self):
        held = self.enter_hold.progress()
        looping = self.loop.state != IDLE
        if held is not None and (looping or self._loopable()):
            return hold_status(held, "Enter", LOOP, "stop the loop" if looping else "loop it")
        return None

    def footer_h(self, g) -> int:
        return g.em(FOOTER_EM)

    def cursor_fraction(self, vp):
        return None

    # ---------------------------------------------------------------- drawing
    def draw(self, g, rect):
        if self._is_noscreen:
            return self._draw_noscreen(g, rect)
        em = g.em
        panel = self.app.viewport_panel()
        hint_h = em(FOOTER_EM) if panel is None else 0 if isinstance(panel, LoopPanel) else em(1.0)
        pad = em(1.6)
        self.header_row = None
        if self.code_panel is None:
            head_h = em(4.3)
            self._draw_header(g, rect)
        else:
            head_h = status_row_h(g) + em(1.2)
            draw_status_row(g, pygame.Rect(rect.x, rect.y + em(0.4), rect.w, status_row_h(g)), self._code_status(g))
        side = em(0.6)
        grid = pygame.Rect(rect.x + side, rect.y + head_h, rect.w - 2 * side, rect.h - head_h - hint_h)
        self._draw_grid(g, grid)
        if self.app._panel is None:
            cy = rect.bottom - em(1.4) - g.line_height(em(0.92), "mono") // 2
            right_edge = rect.right - pad
            if self.app._code_panel_enabled:
                right_edge = draw_key_hint(g, CODE_HINT, em(0.86), right_edge, cy, anchor="midright").left - em(2)
            self._draw_hints(g, rect.x + pad, right_edge, cy)

    def _draw_hints(self, g, left, right, cy):
        """The hint row, centered: what Space and holding Enter do with the tape now, the same in both modes."""
        px = g.em(0.92)
        if self.app._littles_mode:
            draw_key_hint(g, "{Enter} sound", px, (left + right) // 2, cy, anchor="center")
            return
        tune = self._tune()
        space = "" if self.letters_mode else TAPE_HINT if tune else LAST_SONG_HINT if self._last_song else ""
        hint = "   ".join(h for h in (space, self._hint_text(), ERASE_HINT if tune else "") if h)
        if hint:
            draw_key_hint(g, hint, px, (left + right) // 2, cy, anchor="center")

    def _tape_parts(self) -> tuple:
        """(texts, keys over them, rest before each, face, lead, underline from) for what the tape shows now: the
        letters in Letters; in Notes each note's name, with the key that played it over it in its color. A rest
        before each is 1 where a new word or phrase starts, drawn as a space."""
        if self.letters_mode:
            run, at = self._spelled.upper(), self._typed_at
            rests = [int(i > 0 and at[i] - at[i - 1] >= WORD_GAP_S) for i in range(len(run))]
            return list(run), None, rests, "mono-heavy", "", len(run) - len(self.word) if self.word else None
        names = [drum_picture(key) if key not in _KEY_TO_RC else note_name(_KEY_TO_RC[key][1], self.root_index)
                 for key, *_ in self._tape]
        keys = [(KID_MATH_REMAP.get(key, key), KEY_COLORS.get(key.lower(), P.MUTED)) for key, *_ in self._tape]
        rests = [0] + [int(b[2] - a[2] >= ECHO_PAUSE_S) for a, b in zip(self._tape, self._tape[1:])]
        return names, keys, rests, "note", "♪", None

    def _tape_ink(self, color=P.TEXT) -> str:
        """The Notes tape sits back but for while it plays, and fades a little each clock step as the quiet grows,
        nearly gone when it clears."""
        fade = (1 - self._rest_left()) * TAPE_FADE
        sits_back = not self.letters_mode and not self._sounding()
        return mix(color, P.SURFACE, max(fade, TAPE_REST_FADE) if sits_back else fade)

    def _draw_note_names(self, g, xs, ys, letter_px):
        """Shift's seven notes in a row of their own, centered in the grid's place so they don't read as keys, each
        lit in its key's color while it sounds, with a few words on what they are under them."""
        tw, th = xs[1] - xs[0], ys[1] - ys[0]
        row = pygame.Rect(0, 0, tw * 7, th)
        row.center = ((xs[0] + xs[10]) // 2, (ys[0] + ys[4]) // 2 - th // 4)
        for col, key in enumerate(GRID_KEYS[NOTE_ROW][:7]):
            tile = pygame.Rect(row.x + col * tw, row.y, tw, th).inflate(-max(4, tw // 12), -max(4, tw // 12))
            bg = self._tile_color(key)
            g.rect(bg, tile, radius=tw // 8) if bg != P.TILE else g.rect(P.LINE, tile, width=2, radius=tw // 8)
            ink = P.TEXT if bg == P.TILE else text_color_for(bg)
            self._draw_big_note(g, note_name(col, self.root_index), round(letter_px * 1.3), tile.center, ink)
        draw_key_hint(g, NOTE_NAMES_HINT, g.em(0.92), row.centerx, row.bottom + th // 2, anchor="center")

    @staticmethod
    def _draw_big_note(g, note: str, px: int, center: tuple, ink):
        """A note's name big, with a small ♪ before it, centered together."""
        sym_px = round(px * 0.55)
        sym_w = g.measure("♪", sym_px, "mono-bold", tr=False)[0] + px // 8
        note_w = g.measure(note, px, "note", tr=False)[0]
        x = center[0] - (sym_w + note_w) // 2
        g.draw_text("♪", sym_px, x, center[1] + px // 8, "mono-bold", ink, anchor="midleft", tr=False)
        g.draw_text(note, px, x + sym_w, center[1], "note", ink, anchor="midleft", tr=False)

    def _draw_tape(self, g, row: pygame.Rect, size: float):
        """What was just played or typed, left to right under the grid, a rest as a gap; the word the letters end
        with is underlined. Too long for the row, it shows its end, or follows the note playing back, with …
        where it goes on. Laid out on the face's cell width, and the timer pinned while it overflows, so nothing
        moves with which notes it holds."""
        texts, keys, rests, face, lead, word_at = self._tape_parts()
        if not texts:
            return
        px = max(12, int(size * 0.2))
        key_px = round(px * 0.7)
        cell = g.measure("M", px, face, tr=False)[0]
        step, rest_w, clock_r = px // 3, px, round(px * 0.32)
        pic_h = round(px * 0.87)   # drums a little taller than the notes, on their baseline

        def drum(t):   # just its ink, so drums side by side sit as close as letters
            return (pic := g.image(t, pic_h)).subsurface(pic.get_bounding_rect()) if t.endswith(".png") else None

        def width(t):
            return d.get_width() if (d := drum(t)) else cell * len(t)

        def after(t):
            return max(2, px // 8) if t.endswith(".png") else step
        x, cy = row.x, row.centery + (key_px // 2 if keys else 0)
        lead_w = cell + px // 2 if lead else 0
        room = row.right - x - lead_w - (2 * clock_r + px)
        spans = [width(t) + after(t) + rest_w * r for t, r in zip(texts, rests)]
        first, last = self._tape_window(spans, room, cell + step)
        clipped = first > 0 or last < len(texts) - 1
        end = x + lead_w + room
        ink = self._tape_ink()
        if lead:
            g.draw_text(lead, px, x, cy, face, self._tape_ink(P.MUTED), anchor="midleft", tr=False)
            x += lead_w
        if first > 0:
            g.draw_text("…", px, x, cy, face, self._tape_ink(P.MUTED), anchor="midleft", tr=False)
            x += cell + step
        under = None
        for i in range(first, last + 1):
            x += rest_w * rests[i] if i > first else 0
            w = width(texts[i])
            lead_in = word_at is not None and i < word_at   # letters before the word step back
            playing = i == self._tape_at
            lit = (keys[i][1] if keys else KEY_COLORS.get(texts[i].lower(), P.ACCENT)) if playing else None
            color = lit or (mix(ink, P.SURFACE, 0.5) if lead_in else ink)
            if pic := drum(texts[i]):
                pic = g.image(texts[i], pic_h, color).subsurface(pic.get_offset(), pic.get_size())
                g.surface.blit(pic, pic.get_rect(bottomleft=(x, cy + round(px * 0.37))))
            else:
                g.draw_text(texts[i], px, x, cy, face, color, anchor="midleft", tr=False)
            if lit:   # a dot under what's sounding, in its key's color, below the word's underline in Letters
                dot_y = cy + round(px * (1.1 if word_at is not None else 0.85))
                pygame.draw.circle(g.surface, rgb(lit), (x + w // 2, dot_y), max(3, px // 4))
            if keys:
                g.draw_text(keys[i][0], key_px, x + w // 2, cy - round(px * 0.85), "mono-bold", self._tape_ink(keys[i][1]),
                            anchor="center", tr=False)
            if word_at is not None and i >= word_at:
                slot = pygame.Rect(x, cy, w, round(px * 0.6))
                under = slot if under is None else under.union(slot)
            x += w + after(texts[i])
        if last < len(texts) - 1:
            g.draw_text("…", px, x, cy, face, self._tape_ink(P.MUTED), anchor="midleft", tr=False)
            x += cell + step
        if under is not None:
            line = pygame.Rect(under.x, under.bottom + max(2, px // 10), under.w, max(2, px // 8))
            g.rect(self._tape_ink(P.ACCENT), line, radius=line.h // 2)
        x = self._draw_rest_mark(g, (end if clipped else x) + px // 4 + clock_r, cy, clock_r)
        if self.letters_mode:
            if self.word:   # centered on the row, unless the letters reach past where it would start
                word_w = self._draw_word(g, None, cy, round(px * 1.15))
                self._draw_word(g, max(x + px, row.centerx - word_w // 2), cy, round(px * 1.15))

    def _draw_word(self, g, x, cy, px) -> int:
        """The word the letters found, with its picture, and what Space does with it; returns its width, and
        with x None only measures it."""
        picture = get_content().exact_emoji(self.word)
        text = f"{self.word} {picture}" if picture else self.word
        hint_px = g.em(0.92)
        w = g.measure(text, px, "mono-heavy", tr=False)[0] + px
        if x is not None:
            g.draw_text(text, px, x, cy, "mono-heavy", P.TEXT, anchor="midleft", tr=False)
            draw_key_hint(g, WORD_HINT, hint_px, x + w, cy)
        return w + key_hint_width(g, WORD_HINT, hint_px)

    def _tape_window(self, spans: list, room: int, ellipsis: int) -> tuple:
        """(first, last) of the tape that fit in `room`: its end, or from the note playing back once that has
        scrolled off; each cut side gives up an ellipsis' worth."""
        n = len(spans)

        def fits(a, b):
            return sum(spans[a:b + 1]) + ellipsis * ((a > 0) + (b < n - 1)) <= room
        first, last = 0, n - 1
        while first < last and not fits(first, last):
            first += 1
        if self._tape_at is not None and self._tape_at < first:
            first = last = self._tape_at
            while last + 1 < n and fits(first, last + 1):
                last += 1
        return first, last

    def _draw_rest_mark(self, g, cx, cy, r) -> int:
        """A small pie that empties while it's quiet, till the tape clears. Returns its right edge."""
        left = self._rest_left()
        pygame.draw.circle(g.surface, rgb(P.LINE), (cx, cy), r, width=max(1, r // 6))
        if left > 0:
            arc = [(cx + r * math.sin(2 * math.pi * left * k / 24), cy - r * math.cos(2 * math.pi * left * k / 24))
                   for k in range(25)]
            pygame.draw.polygon(g.surface, rgb(P.MUTED), [(cx, cy), *arc])
        return cx + r

    def _hint_text(self) -> str:
        """Hold Enter loops the tape, so this shows beside one."""
        return f"{{hold Enter}} {LOOP} to loop" if self._loopable() else ""

    def _draw_header(self, g, rect):
        """The same header as Art and Blocks: the Enter chip beside the Notes / Letters switch."""
        if self.app._littles_mode:
            plate = f"{ICON_KEYBOARD} Saying Letters" if self.letters_mode else self._instrument_label(self.instrument_index)
            draw_label(g, plate, g.em(1.0), rect.centerx, rect.y + g.em(1.9), P.TEXT, anchor="center", on=True)
            return
        draw_mode_switch(g, self.header_band(g, rect), ("modes/notes.png", ABC_PICTURE), 1 if self.letters_mode else 0,
                         chips=self._header_chips(),
                         also=(self._header_chips(not self.letters_mode),), reserve=self.header_reserve(g))

    def _header_chips(self, letters: bool | None = None) -> tuple:
        """Enter steps through instruments, shown by their pictures, or in Letters, names and sounds."""
        if self.letters_mode if letters is None else letters:
            return ("Enter", int(self.say_sounds), LETTER_PICTURES),
        available = instruments()
        return ("Enter", self.instrument_index % len(available), tuple(instrument_icon(inst_id) for inst_id, _ in available)),

    def _code_status(self, g) -> tuple:
        """What code can change, in its own words: choose, letters, key."""
        inst_id, name = self._instrument(self.instrument_index)
        return ((instrument_icon(inst_id), name),
                (ICON_KEYBOARD, f"Letter {'sounds' if self.say_sounds else 'names'}" if self.letters_mode else "Letters off"),
                (None, key_label(self.root_index)))

    def arrow_hint(self) -> str:
        if self.app._littles_mode:
            return key_label(DEFAULT_ROOT_INDEX)
        if self.letters_mode:
            return ""
        return f"{LEFT} {RIGHT} key: {FRIENDLY_KEY_NAMES[self.root_index]}"

    def paper(self, g, size, on_screen=False):
        """The kid's colors on the keyboard grid; quiet keys print as outlined letters."""
        if all(self.get_color(k) == P.TILE for row in GRID_KEYS for k in row):
            return None
        s = paper.blank(size, on_screen)
        with g.drawing_on(s):
            self._draw_grid(g, s.get_rect(), on_paper=not on_screen)
        return s

    def _draw_grid(self, g, r, on_paper=False):
        """Ten by four gapless blocks, as wide as fit with a margin either side, the tape's row under them: a quiet
        key is its letter over its note's name, faint until it sounds; a sounding key fills its block with color."""
        rows_h = r.h / (4 + NOTE_STRIP)
        tab_w = self._key_tab_width(g, rows_h)
        w = (r.w - 2 * tab_w) / 10
        size = min(rows_h, w)
        top = r.centery - (4 + NOTE_STRIP) * size / 2
        xs = [round(r.x + tab_w + i * w) for i in range(11)]
        ys = [round(top + i * size) for i in range(5)]
        letter_px = max(12, int(size * 0.3))
        named = not on_paper and self._shift_notes()   # Shift down: just the notes it plays, apart from the keys
        if named:
            self._draw_note_names(g, xs, ys, letter_px)
        for row_idx, row in enumerate(() if named else GRID_KEYS):
            melodic = row_idx >= 1
            for col_idx, key in enumerate(row):
                bg = self._tile_color(key, on_paper)
                note = note_name(col_idx, self._transition_state_for_col(col_idx)[0]) if melodic else None
                tile = pygame.Rect(xs[col_idx], ys[row_idx], xs[col_idx + 1] - xs[col_idx], ys[row_idx + 1] - ys[row_idx])
                quiet = bg == P.TILE
                if not quiet:
                    g.rect(bg, tile)
                elif on_paper:
                    g.rect(PAPER_OUTLINE, tile, width=2)
                fg = (paper.INK_MUTED if on_paper else P.MUTED) if quiet else text_color_for(bg)
                letter = KID_MATH_REMAP.get(key, key)
                g.draw_text(letter, letter_px, tile.centerx, tile.centery,
                            "mono-bold" if quiet else "mono-heavy", fg, anchor="center")
                sounding = key in self._note_labels
                label = (note_label(note) if not self.letters_mode else None) if melodic \
                    else drum_picture(key) if sounding else None
                if label and not on_paper:
                    sweeping = melodic and self._transition_state_for_col(col_idx)[1]
                    ink = P.ACCENT if sweeping else mix(fg, bg, 0.3 if sounding else NOTE_FAINT)
                    label_px, at = max(10, int(size * 0.15)), (tile.centerx, tile.bottom - int(size * 0.17))
                    if melodic:
                        g.draw_text(label, label_px, *at, "note", ink,
                                    anchor="center", tr=False)
                    else:
                        pic = g.image(label, round(label_px * 1.1), ink)
                        g.surface.blit(pic, pic.get_rect(center=at))
        if not on_paper and self.code_panel is None:   # the code is its own composition
            gap = round(size * 0.06)
            self._draw_tape(g, pygame.Rect(xs[0], ys[4] + gap, xs[10] - xs[0], round(size * NOTE_STRIP) - gap), size)

    @staticmethod
    def _strip_px(size) -> int:
        return max(10, int(size * 0.17))

    @staticmethod
    def _bar_h(size) -> int:
        return round(size * NOTE_STRIP * 0.62)

    def _key_tab_width(self, g, size) -> int:
        """The margin either side of the grid, the same in every key so the grid holds still."""
        px = self._strip_px(size)
        labels = [(name, px) for name in FRIENDLY_KEY_NAMES] + [("Key", round(px * KEY_WORD))]
        return max(g.measure(text, text_px, "note", tr=False)[0] for text, text_px in labels) + self._bar_h(size)

    def _draw_noscreen(self, g, rect):
        cy = rect.centery
        if self._noscreen_dot:
            g.draw_text("●", g.vh(6), rect.centerx, cy - g.vh(10), "sans-heavy", self._noscreen_dot, anchor="center")
        g.draw_markup(NOSCREEN_TEXT, g.vh(1.9), rect.x, cy - g.vh(3), "mono", P.MUTED, rect.w, "center", P.SURFACE, g.vh(0.5))
