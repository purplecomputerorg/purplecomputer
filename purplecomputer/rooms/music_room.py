"""Music room: a 10x4 grid that mirrors the keyboard. Letters play notes,
digits play percussion, Tab says letters, arrows change key, Enter cycles the
instrument (in Letters: names or sounds), hold Enter records a loop, and the code line opens from the Esc menu.
In Letters, a real word typed shows under the grid and Space says it."""

import asyncio
import math
import time
from functools import lru_cache

import pygame

from .. import dial_synth
from .. import palette as P
from ..audio import play_safe
from ..code_runner import MusicCodeRunner
from ..content import get_content
from ..constants import ICON_BROOM, ICON_KEYBOARD, ICON_MUSIC
from ..keyboard import CharacterAction, ControlAction, NavigationAction
from ..loop_station import IDLE, LOOPING, RECORDING, LoopStation
from ..mixer import warm_mixer
from ..speech_filter import is_clean
from ..music_constants import (
    ALL_KEYS, COLOR_KEYCAP, COLORS, DEFAULT_ROOT_INDEX, FRIENDLY_KEY_NAMES, FRIENDLY_KEYS, GRID_KEYS,
    INSTRUMENT_ALIASES, PERCUSSION, instruments, note_frequency, pitch_for,
)
from ..palette import KEY_COLORS, luminance, text_color_for
from .. import paper
from ..gfx import is_one_emoji, mix, rgb
from ..panels import FOOTER_EM, CodePanel, Echo, LoopPanel
from ..sounds import SoundBank
from ..ui import (ABC_PICTURE, CODE_HINT, LOOP, STOP, KID_MATH_KEYS, KID_MATH_REMAP, LEFT, RIGHT, draw_key_hint, key_hint_width,
                  draw_lone_stepper, draw_mode_switch, draw_status_row, HeldKey, hold_status, status_row_h)
from .base import Room

MODE_MUSIC, MODE_LETTERS = "music", "letters"
PAPER_OUTLINE = "#d0d0d0"
_KEY_TO_RC = {key: (r - 1, c) for r, row in enumerate(GRID_KEYS) if r >= 1 for c, key in enumerate(row)}
_STEPS = {key: (2 - r) * 7 + c for key, (r, c) in _KEY_TO_RC.items()}   # scale steps up from the bottom row's first key


def _smooth(d: int, color: tuple, paint) -> pygame.Surface:
    """A d by d mark painted 8x big and scaled down, so its edges are smooth at a few pixels. Its clear pixels
    carry its color, or scaling down would darken its edge."""
    big = pygame.Surface((d * 8, d * 8), pygame.SRCALPHA)
    big.fill((*color, 0))
    paint(big, 8, d * 4)
    return pygame.transform.smoothscale(big, (d, d))


@lru_cache(maxsize=256)
def _bead(r: float, color: tuple, drum: bool, glow: bool) -> pygame.Surface:
    """A note's round bead or a drum's short tick; the one playing has a soft glow around it."""
    def paint(s, k, c):
        if glow:
            pygame.draw.circle(s, (*color, 60), (c, c), r * 2.2 * k)
        if drum:
            pygame.draw.rect(s, color, pygame.Rect(c - r * 0.35 * k, c - r * 1.3 * k, r * 0.7 * k, r * 2.6 * k),
                             border_radius=round(r * 0.35 * k))
        else:
            pygame.draw.circle(s, color, (c, c), r * k)
    return _smooth(2 * math.ceil(r * (2.2 if glow else 1.4)) + 2, color, paint)


@lru_cache(maxsize=64)
def _rest_clock(r: int, left: float, track: tuple, ink: tuple) -> pygame.Surface:
    """A thin ring with `left` of it drawn round from the top, hollow so it never reads as a bead."""
    def paint(s, k, c):
        w, n = max(2, round(r * 0.35 * k)), 48
        pygame.draw.circle(s, (*track, 90), (c, c), r * k, width=w)
        if left > 0:
            rad = r * k - w / 2
            pygame.draw.lines(s, ink, False, [(c + rad * math.sin(2 * math.pi * left * i / n),
                                               c - rad * math.cos(2 * math.pi * left * i / n)) for i in range(n + 1)], w)
    return _smooth(2 * r + 2, ink, paint)


DIAL_COLORS = ("#c79be8", "#f0c94a", "#8ee0c0", "#8cc8ea")   # sound, bright, long, wobble


@lru_cache(maxsize=64)
def _dial(d: int, dial: int, value: int) -> pygame.Surface:
    """A Synth dial like a volume knob: a track round it that fills up to where it's turned, a tick for each
    position, a notch on the knob pointing at it, and a picture of what it does in the middle."""
    n = dial_synth.DIALS[dial][1]
    color, ink, tile = rgb(DIAL_COLORS[dial]), rgb(P.ON_PRIMARY), rgb(P.TILE)

    def at(c, a, r):
        return c + math.cos(a) * r, c + math.sin(a) * r

    def angle(i):
        return math.radians(-225 + 270 * i / (n - 1))

    def arc(s, c, r, upto, ink_, w):
        steps = max(2, round(upto * 12))
        pts = [at(c, angle(upto * j / steps), r) for j in range(steps + 1)]
        pygame.draw.lines(s, ink_, False, pts, w)
        for p in (pts[0], pts[-1]):
            pygame.draw.circle(s, ink_, p, w / 2)

    def paint(s, k, c):
        u = d * k
        w = round(u * 0.07)
        arc(s, c, u * 0.415, n - 1, rgb(mix(P.LINE, P.TILE, 0.45)), w)
        arc(s, c, u * 0.415, value, color, w)
        for i in range(n):
            pygame.draw.line(s, color if i <= value else rgb(P.LINE), at(c, angle(i), u * 0.46), at(c, angle(i), u * 0.5),
                             round(u * 0.025))
        pygame.draw.circle(s, rgb(P.FIELD), (c, c), u * 0.34)
        pygame.draw.circle(s, rgb(P.LINE), (c, c), u * 0.34, width=max(1, round(u * 0.012)))
        _DIAL_PICTURES[dial](s, u, c, value, color, ink, rgb(P.FIELD))
        pygame.draw.line(s, rgb(P.TEXT), at(c, angle(value), u * 0.25), at(c, angle(value), u * 0.33), round(u * 0.045))
    return _smooth(d, tile, paint)


def _shape(s, u, c, shape, color, ink, tile):
    """Smooth, square or buzzy: two waves of it."""
    def y(x):
        f = x % 1
        return (math.sin(2 * math.pi * f), 1 if f < 0.5 else -1, 1 - 2 * f)[shape]
    pts = [(c - u * 0.2 + i * u * 0.005, c - y(i / 40) * u * 0.08) for i in range(81)]
    pygame.draw.lines(s, color, False, pts, max(2, round(u * 0.035)))


def _sun(s, u, c, bright, color, ink, tile):
    """Dark to bright: a moon, then a sun that grows and gains rays."""
    if bright == 0:
        pygame.draw.circle(s, (190, 190, 230), (c, c), u * 0.13)
        pygame.draw.circle(s, tile, (c + u * 0.07, c - u * 0.04), u * 0.11)
        return
    r = u * (0.07 + 0.02 * bright)
    for i in range(2 * bright):
        a = 2 * math.pi * i / (2 * bright)
        pygame.draw.line(s, color, (c + math.cos(a) * (r + u * 0.03), c + math.sin(a) * (r + u * 0.03)),
                         (c + math.cos(a) * (r + u * 0.07), c + math.sin(a) * (r + u * 0.07)), max(1, round(u * 0.022)))
    pygame.draw.circle(s, color, (c, c), r)


def _dots(s, u, c, long_, color, ink, tile):
    """Short to long: one dot more for each step."""
    for i in range(long_ + 1):
        pygame.draw.circle(s, color, (c + (i - long_ / 2) * u * 0.085, c), u * 0.032)


def _wiggle(s, u, c, wobble, color, ink, tile):
    """A little wobble to a lot: a line that waves more and faster."""
    pts = [(c + x * u * 0.01, c + math.sin(x / (3.2 - 0.5 * wobble)) * (0.5 + wobble) * u * 0.022) for x in range(-20, 21)]
    pygame.draw.lines(s, color, False, pts, max(2, round(u * 0.035)))


@lru_cache(maxsize=8)
def _wave(w: int, h: int, line: tuple, ink: tuple) -> pygame.Surface:
    """The Synth's note as a thin line, drawn big and scaled down so it's smooth."""
    k = 3
    big = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    big.fill((*ink, 0))
    pad, amp, width = h * k // 4, h * k * 0.36, max(k * 2, round(h * k / 30))
    step = (w * k - 2 * pad) / (len(line) - 1)
    pts = [(pad + i * step, h * k / 2 - y * amp) for i, y in enumerate(line)]
    pygame.draw.lines(big, ink, False, pts, width)
    return pygame.transform.smoothscale(big, (w, h))


_DIAL_PICTURES = (_shape, _sun, _dots, _wiggle)


def drum_picture(key: str) -> str:
    return f"drums/{PERCUSSION[key].replace('-', '_')}.png"

PITCH_TRANSITION_DURATION = 0.25
LETTER_PICTURES = ("letters/names.png", "letters/sounds.png")
KEY_WORD = 0.75               # sizes the grid's side margin; changing it moves the grid
NOTE_STRIP = 0.62             # height of the tape's row under the grid, in keys
KEY_BAR = 0.28                # width of the key bar beside the grid, in keys
BEAD_STEP = 0.14              # between the song's beads, in keys; a phrase rest adds two more
BEAD_LIT_FADE_S = 1.0         # after playback, the lit beads sink back this slowly
BEAD_EDGE_FADE = 4            # beads that fade out toward a side where a long song goes on past the row
NOTE_FAINT = 0.72             # how far a key's note name sinks into the key until it sounds
LETTERS_MASH_S = 0.06         # letters closer than this are one hand landing at once
LETTER_FADE = (1, 1, 0.6, 0.35, 0.15)  # the same letter again and again; past the end it's silent
LETTER_FADE_REST_S = 1.0      # a rest this long, or another letter, brings it back to full
LETTER_AFTER_GAP_S = 0.15     # between Purple saying a key and the family's recording after it
ECHO_PAUSE_S = 2.0            # a rest this long starts a new line of echoed notes, and a new phrase on the tape
TAPE_MAX = 100                # notes kept on the music tape
ERASE_HINT = "{Backspace} erase, hold to clear"
ERASE_EVERY_S = 0.2           # a held Backspace takes a note this often, not at key repeat,
ERASE_BAR_AFTER_S = 0.6       # until it's held this long; then the hold bar starts toward clearing it all
TAPE_FADE = 0.9               # how far the tape has faded into the background by the time it clears
TAPE_REST_FADE = 0.65         # how far back the Notes tape sits, except while it plays back or loops
REST_STEPS = 20               # the tape fades and its clock empties in this many steps over its quiet rest
NOTE_ROW = 2                  # Shift plays a note by name on this grid row, the middle octave
SONG_REST_S = 20.0            # this long without a sound, and the Notes tape clears (still in Time Travel)
TAPE_HINT = "{Space} replay it"
STOP_HINT = f"{{Space}} {STOP}stop"   # the picture has its own margin, so no space after it
LAST_SONG_HINT = "{Space} last song"
RECORD_S = 10.0               # hold Enter with no song to loop: it records this long, then loops what was played
CLEAR_HINT = "{Backspace} clear"
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
    note = pitch_for(0, col, root)[0]
    return SHARP_TO_FLAT.get(note, note) if root in FLAT_KEYS else note.replace("#", "♯")


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
        self.synth = dial_synth.DEFAULT
        self._last_note = "A"     # the Synth plays it again when a dial turns
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
        self._tape: list = []     # (key, mode, when, (instrument, name)) of the song played in Notes; it plays back
                                  # on whichever instrument is set, and the instruments and names go into its code
        self._tape_origin = 0.0   # when the song began, and how many notes have dropped off its front,
        self._tape_base = 0       # so each note keeps its timeline key while the song grows
        self._last_song = None    # (tape, origin, base) of the song quiet cleared, which Space or hold Enter brings back
        self._tape_task = None
        self._tape_at = None      # the tape note playing back now, or looping
        self._lit = None          # (last bead lit, when playback ended) while the beads sink back
        self._loop_tape: dict = {}
        self._rest_timers: list = []
        self._active_at = 0.0     # the last sound, play back or erase: the tape clears once it's quiet this long
        self.echo = Echo(pause=ECHO_PAUSE_S)
        self.enter_hold = HeldKey(app, self._enter_hold_fired)
        self.erase_hold = HeldKey(app, self._erase_hold_fired)
        self._erasing_since = None
        self._erased_at = 0.0
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
        self._warm_synth()
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
        state.update(instrument=self.instrument_index, root=self.root_index, letters=self.letters_mode, sounds=self.say_sounds,
                     synth=list(self.synth))
        return state | self._tape_state()

    def _tape_state(self) -> dict:
        """The song a note per key, numbered from its start, so a Time Travel step adds only the notes new in it."""
        return {f"t:{self._tape_base + i}": [k, round((t - self._tape_origin) * 1000)] for i, (k, _, t, _) in enumerate(self._tape)}

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
        self.synth = dial_synth.setting(state.get("synth"))
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
            self._tape = [(*n, None) for n in tune if n[1] == MODE_MUSIC]
            self._tape_origin = end - notes[-1][-1] / 1000

    def on_open_save(self):
        """The saved picture as it was, and its tune played once over it."""
        if self._tune():
            self._play_tape(paint=False)

    # ---------------------------------------------------------------- sounds
    def _pitch_for_key(self, key: str):
        rc = _KEY_TO_RC.get(key)
        return None if rc is None else pitch_for(rc[0], rc[1], FRIENDLY_KEYS[self.root_index])

    def _note_sound(self, key: str, instrument_id: str):
        pitch = self._pitch_for_key(key)
        return None if pitch is None else self.sounds.note(instrument_id, *pitch, self.synth)

    def play_sound_with_instrument(self, key: str, instrument_index: int, volume_scale: float = 1.0):
        if self.app._effective_volume() == 0:
            return
        if key.isdigit():
            sound = self.sounds.percussion().get(key)
        else:
            sound = self._note_sound(key, self._instrument(instrument_index)[0])
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
            return self.app.invalidate()
        self.app.animate(self.app.room_patch)

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
            return self._stop_loop()   # a recording with nothing played
        tune = list(self._tape)
        offsets = self._tune_offsets(tune)
        gaps = [b - a for a, b in zip(offsets, offsets[1:])]
        tail = min(max(sum(gaps) / len(gaps), 0.25), TUNE_GAP_MAX_S) if gaps else 0.6
        self._stop_tape()
        events = [(k, m, o - offsets[0]) for (k, m, *_), o in zip(tune, offsets)]
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
        self._end_playback()
        if looped:   # the quiet starts when the loop does
            self._busy()
        self._sync_panels()

    def _start_loop_timer(self):
        if self._loop_timer is None:
            self._loop_timer = self.app.timers.every(0.15, self._loop_tick)

    def _loop_tick(self):
        if self.loop.state == RECORDING and not self.loop.recording_left():
            self._loop_tune()
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
        """A key played by hand: in Letters it spells."""
        if mode == MODE_LETTERS:
            self._spell(key, time.monotonic())
        self._replay(key, mode)

    def _replay(self, key: str, mode: str, paint: bool = True):
        """A key sounding, by hand, the tape or a loop: its color moves on the same either way."""
        if paint:
            self.next_color(key)
        if not key.isdigit():
            self._last_note = key
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
            fresh = self.echo.take()
            self.code_panel = CodePanel(self.app, "music", self._tape_code() or fresh)
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
        elif self.loop.state == RECORDING:
            self._loop_tune()
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
    def _tape_add(self, key: str, now: float, name: str | None = None):
        """The song grows, each note with the instrument it was played on and the note `name` Shift played it by;
        a long enough rest before a note marks a new phrase in it."""
        if not self._tape:
            self._tape_origin, self._tape_base = now, 0
        tape = self._tape + [(key, MODE_MUSIC, now, (self._instrument(self.instrument_index)[0], name))]
        self._tape_base += max(0, len(tape) - TAPE_MAX)
        self._tape = tape[-TAPE_MAX:]
        self._busy()

    def _tune(self) -> list:
        """What the tape holds, as (key, mode, when): the song in Notes, the letters in Letters."""
        if self.letters_mode:
            return [(c.upper(), MODE_LETTERS, t) for c, t in zip(self._spelled, self._typed_at)]
        return [n[:3] for n in self._tape]

    def _tape_code(self) -> str:
        """The whole song as code, the line scrolling if it's long: a part per phrase, `choose` where its
        instrument changes from the one set, `notes` where Shift played it by name and `music` back from that."""
        if self.letters_mode:
            return ""
        parts = []   # [instrument, by name, keys]
        for i, (key, _, t, how) in enumerate(self._tape):
            inst, name = how or (None, None)
            rest = i > 0 and t - self._tape[i - 1][2] >= ECHO_PAUSE_S
            if not parts or rest or (inst or parts[-1][0]) != parts[-1][0] or bool(name) != parts[-1][1]:
                parts.append([inst or (parts[-1][0] if parts else None), bool(name), ""])
            parts[-1][2] += (name or key).lower()
        inst, by_name, words = self._instrument(self.instrument_index)[0], False, []
        for p_inst, p_name, keys in parts:
            lead = [f"choose {p_inst}"] if p_inst and p_inst != inst else []
            lead += [("notes" if p_name else "music")] if p_name != by_name else []
            words.append(" ".join(lead + [keys]))
            inst, by_name = p_inst or inst, p_name
        return ", ".join(words)

    @staticmethod
    def _tune_offsets(tune: list) -> list:
        """When each note plays back, from the first: its rests as played, a long one cut short."""
        offsets = [0.0]
        for a, b in zip(tune, tune[1:]):
            offsets.append(offsets[-1] + min(b[2] - a[2], TUNE_GAP_MAX_S))
        return offsets

    def _play_tape(self, paint: bool = True):
        self._stop_tape()
        self._tape_task = asyncio.create_task(self._tape_playback(self._tune(), paint))

    async def _tape_playback(self, tune: list, paint: bool):
        """The tape again as it was played, its keys' colors moving on unless `paint` is off, nothing joining the
        loop or the code."""
        try:
            played = 0.0
            for i, ((key, mode, *_), at) in enumerate(zip(tune, self._tune_offsets(tune))):
                await asyncio.sleep(at - played)
                played, self._tape_at = at, i
                self._replay(key, mode, paint)
            await asyncio.sleep(0.3)
        finally:
            self._end_playback()
            self._busy()
            self.app.invalidate()

    def _stop_tape(self):
        if self._tape_task is not None and not self._tape_task.done():
            self._tape_task.cancel()
        self._tape_task = None
        self._end_playback()

    def _end_playback(self):
        if self._tape_at is not None:
            self._lit = (self._tape_at, time.monotonic())
            for i in range(1, 11):
                self.app.timers.after(BEAD_LIT_FADE_S * i / 10, self.app.invalidate)
        self._tape_at = None

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
            self._warm_synth()
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

    def _replaying(self) -> bool:
        return self._tape_task is not None and not self._tape_task.done()

    def _sounding(self) -> bool:
        return self._replaying() or self.loop.state != IDLE

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
            replaying = self._replaying()
            self._stop_tape()   # any key stops it, and Space only stops it, the way a player's Space does
            if replaying and self.code_panel is None and isinstance(action, ControlAction) and action.action == "space":
                self.app.invalidate()
                return
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
            self.erase_hold.other_key()
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
            if lookup.isdigit() and self._synth_on():   # 1 to 4 turn the dials; the rest of the row is the note's picture
                return self._turn_dial(lookup) if lookup in dial_synth.KEYS else None
            mode = self._current_mode()
            self.loop.record_event(lookup, mode)
            self._hit(lookup, mode)
            if mode == MODE_MUSIC and self.loop.state != LOOPING:
                self._tape_add(lookup, time.monotonic(), echo[1])
            self._echo_key(echo[0], echo[1] or lookup.lower())

    def _synth_on(self) -> bool:
        return not self.letters_mode and self._instrument(self.instrument_index)[0] == dial_synth.ID

    def _warm_synth(self):
        if self._synth_on():
            dial_synth.warm()

    def _turn_dial(self, digit: str):
        """1 to 4 turn the Synth's dials, and the last note plays again so the change is heard."""
        self.synth = dial_synth.turn(self.synth, digit)
        self.play_sound_with_instrument(self._last_note, self.instrument_index)
        self.app.invalidate()

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
        """Erases the last note (in Letters, letter), a few more while held; held on, the hold bar fills and the whole tape goes."""
        if not action.is_down:
            self._erasing_since = None
            self.erase_hold.up()
            return
        if self.app._littles_mode or self.loop.state != IDLE:
            return
        now = time.monotonic()
        if not action.is_repeat:
            self._erasing_since = self._erased_at = now
            if self._tune():
                self._erase()
            else:   # nothing left to erase: the last song goes, so hold Enter records anew
                self._last_song = None
        elif self._erasing_since is not None and self._tune() and now - self._erased_at >= ERASE_EVERY_S:
            if now - self._erasing_since < ERASE_BAR_AFTER_S:
                self._erased_at = now
                self._erase()
            else:
                self._erasing_since = None
                self.erase_hold.down()
        self.app.invalidate()

    def _erase_hold_fired(self):
        if self.loop.state == IDLE:
            self._erase(len(self._tune()))
        self.app.invalidate()

    def _erase(self, n: int = 1):
        """The last `n` notes or letters."""
        if not n:
            return
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
        self.erase_hold.other_key()

    def _enter_hold_fired(self):
        if self.app._littles_mode or self.code_panel is not None:
            return
        if self.loop.state == LOOPING:
            self._stop_loop()
        elif self.loop.state == RECORDING or self._loopable():
            self._loop_tune()
        elif self._can_loop():   # nothing to loop yet: record it first
            self._stop_tape()
            self.loop.record(RECORD_S)
            self._start_loop_timer()
            self._sync_panels()
        elif self.letters_mode:   # Letters has nothing to loop, so a hold is a tap
            self._next_voice()
        self.app.invalidate()

    def _loopable(self) -> bool:
        """Only a Notes song loops: Letters has Space to say its word, and its letters clear."""
        return self.app._music_looping_enabled and not self.letters_mode and bool(self._tape or self._last_song)

    def _can_loop(self) -> bool:
        """Hold Enter loops in Notes: the tape, or with none, what's played next."""
        return self.app._music_looping_enabled and not self.letters_mode

    def hold_progress(self):
        if (erasing := self.erase_hold.progress()) is not None:
            return hold_status(erasing, "Backspace", ICON_BROOM, "clear the letters" if self.letters_mode else "clear the song")
        held = self.enter_hold.progress()
        doing = "stop the loop" if self.loop.state == LOOPING else "loop it" if self._can_loop() else None
        return hold_status(held, "Enter", LOOP, doing) if held is not None and doing else None

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
            return
        tune = self._tune()
        space = "" if self.letters_mode else STOP_HINT if self._replaying() else TAPE_HINT if tune \
            else LAST_SONG_HINT if self._last_song else ""
        erase = ERASE_HINT if tune else CLEAR_HINT if space else ""
        rest = "   ".join(h for h in (self._hint_text(), erase) if h)
        # Space's hint keeps the room of its widest, so the row holds still as replay starts and stops
        slot = max(key_hint_width(g, h, px) for h in ((TAPE_HINT, STOP_HINT) if space in (TAPE_HINT, STOP_HINT) else (space,)))
        gap = key_hint_width(g, "   ", px) if space and rest else 0
        x = (left + right) // 2 - (slot + gap + key_hint_width(g, rest, px)) // 2
        if space:
            draw_key_hint(g, space, px, x, cy)
        if rest:
            draw_key_hint(g, rest, px, x + slot + gap, cy)

    def _tape_parts(self) -> tuple:
        """(letters, rest before each, underline from) for the Letters tape: a rest is 1 where a new word starts."""
        run, at = self._spelled.upper(), self._typed_at
        rests = [int(i > 0 and at[i] - at[i - 1] >= WORD_GAP_S) for i in range(len(run))]
        return list(run), rests, len(run) - len(self.word) if self.word else None

    def _song_rests(self) -> list:
        """1 before each note of the song that starts a new phrase."""
        return [0] + [int(b[2] - a[2] >= ECHO_PAUSE_S) for a, b in zip(self._tape, self._tape[1:])]

    def _tape_ink(self, color=P.TEXT, lit: float = 0.0) -> str:
        """The tape fades a little each clock step as the quiet grows, nearly gone when it clears; the song's beads
        also sit back, but for those `lit` by playback."""
        fade = (1 - self._rest_left()) * TAPE_FADE
        back = 0 if self.letters_mode else TAPE_REST_FADE * (1 - lit)
        return mix(color, P.SURFACE, max(fade, back))

    def _bead_lit(self, i: int) -> float:
        """How lit bead i is: the beads playback has reached, sinking back once it ends."""
        if self._tape_at is not None:
            return float(i <= self._tape_at)
        if self._lit and i <= self._lit[0]:
            return max(0.0, 1 - (time.monotonic() - self._lit[1]) / BEAD_LIT_FADE_S)
        return 0.0

    def _draw_note_names(self, g, xs, ys, letter_px):
        """Shift's seven notes in a row of their own, centered in the grid's place so they don't read as keys, each
        lit in its key's color while it sounds, with a few words on what they are under them."""
        tw, th = xs[1] - xs[0], ys[1] - ys[0]
        row = pygame.Rect(0, 0, tw * 7, th)
        row.center = ((xs[0] + xs[10]) // 2, (ys[0] + ys[4]) // 2 - th // 4)
        for col, key in enumerate(GRID_KEYS[NOTE_ROW][:7]):
            tile = pygame.Rect(row.x + col * tw, row.y, tw, th).inflate(-max(4, tw // 12), -max(4, tw // 12))
            bg = self.get_color(key)
            g.rect(bg, tile, radius=tw // 8) if bg != P.TILE else g.rect(P.LINE, tile, width=2, radius=tw // 8)
            ink = P.TEXT if bg == P.TILE else text_color_for(bg)
            self._draw_note(g, note_name(col, self.root_index), round(letter_px * 1.3), tile.center, ink)
        draw_key_hint(g, NOTE_NAMES_HINT, g.em(0.92), row.centerx, row.bottom + th // 2, anchor="center")

    @staticmethod
    def _draw_note(g, note: str, px: int, center: tuple, ink, sym: float = 0.55):
        """A note's name with a smaller ♪ before it, `sym` of its size, their ink centered together."""
        mark, big = (s.subsurface(s.get_bounding_rect()) for s in
                     (g.text("♪", round(px * sym), "mono-bold", ink, tr=False), g.text(note, px, "note", ink, tr=False)))
        gap = px // 5
        x = center[0] - (mark.get_width() + gap + big.get_width()) // 2
        g.surface.blit(mark, mark.get_rect(midleft=(x, center[1])))
        g.surface.blit(big, big.get_rect(midleft=(x + mark.get_width() + gap, center[1])))

    def _draw_tape(self, g, row: pygame.Rect, size: float):
        if self.letters_mode:
            self._draw_letters(g, row, size)
        elif self._tape:
            self._draw_beads(g, row, size)

    def _draw_beads(self, g, row: pygame.Rect, size: float):
        """The song as a line of beads under the grid, a higher note higher and a drum a tick in a lane below them,
        a phrase rest a wider gap. Too long for the row, it shows its end, or follows the note playing back, the
        beads fading out toward a side where it goes on."""
        r, px = max(2.5, size * 0.035), max(12, int(size * 0.2))
        step = round(size * BEAD_STEP)
        band = pygame.Rect(row.x, row.y + round(2 * r), row.w, row.h - round(7 * r))
        lead_w, clock_r = g.measure("♪", px, "note", tr=False)[0] + px // 2, round(r * 1.6)
        room = row.w - lead_w - (2 * clock_r + px)
        rests = self._song_rests()
        first, last = self._tape_window([step + 2 * step * rest for rest in rests], room, BEAD_EDGE_FADE)
        g.draw_text("♪", px, row.x, row.centery, "note", self._tape_ink(P.MUTED), anchor="midleft", tr=False)
        x = row.x + lead_w
        for i in range(first, last + 1):
            x += 2 * step * rests[i] if i > first else 0
            steps = _STEPS.get(self._tape[i][0])
            ink = mix(P.ACCENT, "#ffffff", 0.6) if i == self._tape_at else self._tape_ink(P.ACCENT, self._bead_lit(i))
            edge = min(i - first if first > 0 else BEAD_EDGE_FADE, last - i if last < len(rests) - 1 else BEAD_EDGE_FADE)
            ink = mix(ink, P.SURFACE, max(0, 1 - (edge + 1) / (BEAD_EDGE_FADE + 1)))
            y = round(band.bottom - band.h * steps / max(_STEPS.values()) if steps is not None else band.bottom + 3 * r)
            dot = _bead(r, rgb(ink), steps is None, i == self._tape_at)
            g.surface.blit(dot, dot.get_rect(center=(x, y)))
            x += step
        clipped = first > 0 or last < len(rests) - 1
        self._draw_rest_mark(g, (row.x + lead_w + room + px // 4 if clipped else x + step) + clock_r, row.centery, clock_r)

    def _draw_letters(self, g, row: pygame.Rect, size: float):
        """What was just typed, left to right under the grid, a rest as a gap, the word it ends with underlined.
        It holds SPELL_MAX letters, which always fit."""
        texts, rests, word_at = self._tape_parts()
        if not texts:
            return
        px = max(12, int(size * 0.2))
        cell = g.measure("M", px, "mono-heavy", tr=False)[0]
        step, clock_r = px // 3, round(px * 0.32)
        x, cy = row.x, row.centery + px // 4   # a little clear of the grid above
        ink = self._tape_ink()
        under = None
        for i, text in enumerate(texts):
            x += px * rests[i]
            lead_in = word_at is not None and i < word_at   # letters before the word step back
            lit = KEY_COLORS.get(text.lower(), P.ACCENT) if i == self._tape_at else None
            color = lit or (mix(ink, P.SURFACE, 0.5) if lead_in else ink)
            mid = g.draw_text(text, px, x, cy, "mono-heavy", color, anchor="midleft", tr=False).centerx
            if lit:   # a dot under what's sounding, in its key's color, below the word's underline
                pygame.draw.circle(g.surface, rgb(lit), (mid, cy + round(px * 1.1)), max(3, px // 4))
            if word_at is not None and i >= word_at:
                slot = pygame.Rect(x, cy, cell, round(px * 0.6))
                under = slot if under is None else under.union(slot)
            x += cell + step
        if under is not None:
            line = pygame.Rect(under.x, under.bottom + max(2, px // 10), under.w, max(2, px // 8))
            g.rect(self._tape_ink(P.ACCENT), line, radius=line.h // 2)
        x = self._draw_rest_mark(g, x + px // 4 + clock_r, cy, clock_r)
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

    def _tape_window(self, spans: list, room: int, lead: int) -> tuple:
        """(first, last) of the song that fit in `room`: its end, or from `lead` before the note playing back once
        that has come within `lead` of the cut."""
        n = len(spans)

        def fits(a, b):
            return sum(spans[a:b + 1]) <= room
        first, last = 0, n - 1
        while first < last and not fits(first, last):
            first += 1
        if self._tape_at is not None and first > 0 and self._tape_at < first + lead:
            first = last = max(0, self._tape_at - lead)
            while last + 1 < n and fits(first, last + 1):
                last += 1
        return first, last

    def _draw_rest_mark(self, g, cx, cy, r) -> int:
        """A small ring that empties while it's quiet, till the tape clears. Returns its right edge."""
        clock = _rest_clock(r, self._rest_left(), rgb(P.LINE), rgb(P.MUTED))
        g.surface.blit(clock, clock.get_rect(center=(cx, cy)))
        return cx + r

    def _hint_text(self) -> str:
        """Hold Enter loops the tape, or with none, records what's played next and loops that."""
        return f"{{hold Enter}} {LOOP} to loop" if self._can_loop() else ""

    def _draw_header(self, g, rect):
        """The same header as Art and Blocks: the Enter chip beside the Notes / Letters switch."""
        if self.app._littles_mode:
            draw_lone_stepper(g, rect.centerx, self.header_band(g, rect).centery, *self._header_chips()[0])
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
        dials = not named and not on_paper and self._synth_on()
        if named:
            self._draw_note_names(g, xs, ys, letter_px)
        elif dials:
            self._draw_dials(g, xs, ys, letter_px)
        for row_idx, row in enumerate(() if named else GRID_KEYS):
            melodic = row_idx >= 1
            for col_idx, key in enumerate(row):
                if dials and not melodic:
                    continue
                bg = self.get_color(key)
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
                label = (note if not self.letters_mode else None) if melodic \
                    else drum_picture(key) if sounding else None
                if label and not on_paper:
                    sweeping = melodic and self._transition_state_for_col(col_idx)[1]
                    ink = P.ACCENT if sweeping else mix(fg, bg, 0.3 if sounding else NOTE_FAINT)
                    label_px, at = max(10, int(size * 0.15)), (tile.centerx, tile.bottom - int(size * 0.17))
                    if melodic:
                        self._draw_note(g, label, label_px, at, ink, sym=1)
                    else:
                        pic = g.image(label, round(label_px * 1.1), ink)
                        g.surface.blit(pic, pic.get_rect(center=at))
        if not on_paper and self.code_panel is None:   # the code is its own composition
            gap = round(size * 0.06)
            self._draw_tape(g, pygame.Rect(xs[0], ys[4] + gap, xs[10] - xs[0], round(size * NOTE_STRIP) - gap), size)

    def _draw_dials(self, g, xs, ys, letter_px):
        """The Synth's dials, each in the place of the number key that turns it, that number under it."""
        h = ys[1] - ys[0]
        for dial, key in enumerate(dial_synth.KEYS):
            cx = (xs[dial] + xs[dial + 1]) // 2
            knob = _dial(round(h * 0.84), dial, self.synth[dial])
            g.surface.blit(knob, knob.get_rect(center=(cx, ys[0] + round(h * 0.37))))
            g.draw_text(key, round(letter_px * 0.75), cx, ys[0] + round(h * 0.78), "mono-bold", P.TEXT, anchor="center")
        self._draw_wave(g, pygame.Rect(xs[4], ys[0], xs[10] - xs[4], h).inflate(-h // 5, -h // 5))

    def _draw_wave(self, g, rect):
        """The note the dials make, in the color of the last key played, redrawn as a dial turns."""
        g.rect(P.BG, rect, radius=rect.h // 5)
        pitch = self._pitch_for_key(self._last_note)
        line = dial_synth.picture(self.synth, note_frequency(*pitch) if pitch else dial_synth.LOWEST_HZ * 4)
        ink = KEY_COLORS.get(self._last_note.lower(), P.ACCENT)
        ink = mix(ink, "#ffffff", 0.4) if luminance(ink) < 0.12 else ink   # the darkest keys would vanish on the dark ground
        wave = _wave(rect.w, rect.h, line, rgb(mix(ink, P.BG, 0.25)))
        g.surface.blit(wave, rect)

    @staticmethod
    def _strip_px(size) -> int:
        return max(10, int(size * 0.17))

    @staticmethod
    def _bar_h(size) -> int:
        return round(size * KEY_BAR)

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
