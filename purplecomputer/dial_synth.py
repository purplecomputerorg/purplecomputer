"""The Synth instrument: each note is made when it's played, from four dials that 1 to 4 turn.
numpy makes it fast and loads lazily, since it's slow to import; without it (the i686 build, and Purple
in Studio's browser) plain Python makes the same note."""

import array
import functools
import importlib
import importlib.util
import math
import threading

ID, NAME = "synth", "Synth"
DIALS = (("sound", 3), ("bright", 5), ("long", 5), ("wobble", 4))   # (name, positions)
DEFAULT = (0, 2, 1, 0)
KEYS = "1234"   # one per dial; the rest of the number row shows the note
CUTOFF_HZ = (250, 700, 2000, 5500, 16000)
DECAY_S = (0.07, 0.18, 0.4, 0.8, 1.6)
WOBBLE = (0.0, 0.006, 0.015, 0.03)   # vibrato depth, a fraction of the pitch
WOBBLE_HZ = 5.5
PEAK = (0.55, 0.32, 0.4)   # sine, square, saw: about equally loud
TABLE = 2048
FADE_S = 0.02
ATTACK_S = 0.006
SINE_OVERTONE = 0.15
LOWEST_HZ = 65.4       # the grid's lowest note, Z in C, draws
PICTURE_CYCLES = 3     # this many waves across the picture, a higher note more, closer together,
PICTURE_SPREAD = 0.67  # about 14 at its highest: far fewer than to scale, so each one shows,
PICTURE_FADE = (0.12, 0.25, 0.45, 0.8, 1.6)   # fading over this much of its width for each Long,
PICTURE_WOBBLE = 1.7   # and its wobble drawn bigger than it is


@functools.cache
def _has_numpy() -> bool:
    return importlib.util.find_spec("numpy") is not None


@functools.cache
def warm():
    """numpy loads in the background once the Synth is picked, so its first note isn't late."""
    if _has_numpy():
        threading.Thread(target=importlib.import_module, args=("numpy",), daemon=True, name="synth-warm").start()


def setting(saved) -> tuple:
    """Dials from a save, or where they start if it has none or they don't fit."""
    ok = isinstance(saved, list) and len(saved) == len(DIALS) and all(
        isinstance(v, int) and 0 <= v < n for v, (_, n) in zip(saved, DIALS))
    return tuple(saved) if ok else DEFAULT


def turn(dials: tuple, key: str) -> tuple:
    """A dial's key steps it round, back to the start after its last position, the way Enter steps instruments."""
    dial = KEYS.index(key)
    return dials[:dial] + ((dials[dial] + 1) % DIALS[dial][1],) + dials[dial + 1:]


def _partials(shape: int, bright: int, freq: float) -> list[tuple[int, float]]:
    """(harmonic, amplitude) of a sine, square or saw, rolled off above the Bright cutoff. A pure sine has
    nothing for the cutoff to take away, so Bright gives it a few overtones of its own instead."""
    if shape == 0:
        return [(1, 1.0)] + [(n, SINE_OVERTONE * bright / n ** 2) for n in (2, 3, 4) if n * freq < 19000]
    top = max(1, min(60, int(19000 / freq)))
    return [(n, 1 / n * (-1 if shape == 2 and n % 2 == 0 else 1)
             / math.sqrt(1 + (n * freq / CUTOFF_HZ[bright]) ** 4))
            for n in range(1, top + 1) if not (shape == 1 and n % 2 == 0)]


def _cycle(np, shape: int, bright: int, freq: float):
    """One cycle of the wave, peak 1."""
    x = np.arange(TABLE) / TABLE
    wave = sum(a * np.sin(2 * math.pi * n * x) for n, a in _partials(shape, bright, freq))
    return wave / (np.abs(wave).max() or 1)


@functools.lru_cache(maxsize=64)
def picture(dials: tuple, freq: float, points: int = 400) -> tuple:
    """A note as a line from -1 to 1 to draw, every dial showing in it: its wave's shape and sharpness,
    how soon it fades and how much it wobbles, and its pitch as how close together its waves are.
    Plain math, so drawing never waits on numpy."""
    shape, bright, long_, wobble = dials
    parts = _partials(shape, bright, freq)
    waves = PICTURE_CYCLES * (freq / LOWEST_HZ) ** PICTURE_SPREAD

    def wave(cycles):
        return sum(a * math.sin(2 * math.pi * n * cycles) for n, a in parts)
    peak = max(abs(wave(i / 200)) for i in range(200)) or 1
    line = []
    for i in range(points):
        x = i / (points - 1)
        cycles = waves * (x + WOBBLE[wobble] * PICTURE_WOBBLE * math.sin(2 * math.pi * 2.5 * x))
        line.append(wave(cycles) / peak * math.exp(-x / PICTURE_FADE[long_]))
    return tuple(line)


def render(freq: float, dials: tuple, rate: int, channels: int) -> bytes:
    """A note as signed 16-bit frames for the mixer."""
    return (_render_numpy if _has_numpy() else _render_plain)(freq, dials, rate, channels)


def _frames(rate: int, decay: float) -> int:
    return int(rate * min(3.0, 0.05 + decay * 5))


def _render_numpy(freq: float, dials: tuple, rate: int, channels: int) -> bytes:
    import numpy as np
    shape, bright, long_, wobble = dials
    decay = DECAY_S[long_]
    t = np.arange(_frames(rate, decay)) / rate
    w = 2 * math.pi * WOBBLE_HZ
    cycles = freq * (t - WOBBLE[wobble] / w * (np.cos(w * t) - 1))
    table = _cycle(np, shape, bright, freq)
    wave = np.interp(cycles % 1 * TABLE, np.arange(TABLE + 1), np.append(table, table[0]))
    env = np.minimum(1, t / ATTACK_S) * np.exp(-t / decay)
    tail = t > t[-1] - FADE_S
    env[tail] *= 0.5 * (1 + np.cos(math.pi * (t[tail] - t[-1] + FADE_S) / FADE_S))
    frames = (wave * env * PEAK[shape] * 32767).astype(np.int16)
    return np.repeat(frames, channels).tobytes()


def _render_plain(freq: float, dials: tuple, rate: int, channels: int) -> bytes:
    """_render_numpy a sample at a time: a sine table looked up by index, the decay as a running product."""
    shape, bright, long_, wobble = dials
    decay, w = DECAY_S[long_], 2 * math.pi * WOBBLE_HZ
    depth, n = WOBBLE[wobble] / w, _frames(rate, decay)
    sines = [math.sin(2 * math.pi * i / TABLE) for i in range(TABLE)]
    parts = _partials(shape, bright, freq)
    table = [sum(a * sines[k * i % TABLE] for k, a in parts) for i in range(TABLE)]
    gain = PEAK[shape] * 32767 / (max(map(abs, table)) or 1)
    table = [v * gain for v in table + table[:1]]
    tail_from, step, cos = (n - 1) / rate - FADE_S, math.exp(-1 / (rate * decay)), math.cos
    mono, env = array.array("h", bytes(2 * n)), 1.0
    for i in range(n):
        t = i / rate
        c = freq * (t - depth * (cos(w * t) - 1)) % 1 * TABLE
        j = int(c)
        a = env * min(1.0, t / ATTACK_S)
        if t > tail_from:
            a *= 0.5 * (1 + cos(math.pi * (t - tail_from) / FADE_S))
        mono[i] = int((table[j] + (table[j + 1] - table[j]) * (c - j)) * a)
        env *= step
    frames = array.array("h", bytes(2 * n * channels))
    for ch in range(channels):
        frames[ch::channels] = mono
    return frames.tobytes()
