"""The Synth instrument: each note is made when it's played, from four dials the number row turns.
numpy loads lazily: it's slow to import, and the i686 build has none."""

import functools
import importlib
import importlib.util
import math
import threading

ID, NAME = "synth", "Synth"
DIALS = (("sound", 3), ("bright", 5), ("long", 5), ("wobble", 4))   # (name, positions)
DEFAULT = (0, 2, 1, 0)
SURPRISE = len(DIALS)    # the fifth pair of number keys rolls every dial
CUTOFF_HZ = (250, 700, 2000, 5500, 16000)
DECAY_S = (0.07, 0.18, 0.4, 0.8, 1.6)
WOBBLE = (0.0, 0.006, 0.015, 0.03)   # vibrato depth, a fraction of the pitch
WOBBLE_HZ = 5.5
PEAK = (0.55, 0.32, 0.4)   # sine, square, saw: about equally loud
TABLE = 2048
FADE_S = 0.02


@functools.cache
def available() -> bool:
    return importlib.util.find_spec("numpy") is not None


@functools.cache
def warm():
    """numpy loads in the background once the Synth is picked, so its first note isn't late."""
    threading.Thread(target=importlib.import_module, args=("numpy",), daemon=True, name="synth-warm").start()


def setting(saved) -> tuple:
    """Dials from a save, or where they start if it has none or they don't fit."""
    ok = isinstance(saved, list) and len(saved) == len(DIALS) and all(
        isinstance(v, int) and 0 <= v < n for v, (_, n) in zip(saved, DIALS))
    return tuple(saved) if ok else DEFAULT


def dial_for_key(digit: str) -> tuple[int, int]:
    """(dial, step) a number key turns: 1 and 2 turn the first dial down and up, 9 and 0 are Surprise."""
    i = "1234567890".index(digit)
    return i // 2, 1 if i % 2 else -1


def turn(dials: tuple, dial: int, step: int, rng) -> tuple:
    if dial == SURPRISE:
        return tuple(rng.randrange(n) for _, n in DIALS)
    _, n = DIALS[dial]
    return dials[:dial] + (max(0, min(n - 1, dials[dial] + step)),) + dials[dial + 1:]


def _cycle(np, shape: int, bright: int, freq: float):
    """One cycle of the wave, its harmonics rolled off above the Bright cutoff, peak 1."""
    x = np.arange(TABLE) / TABLE
    top = 1 if shape == 0 else max(1, min(60, int(19000 / freq)))
    wave = np.zeros(TABLE)
    for n in range(1, top + 1):
        if shape == 1 and n % 2 == 0:
            continue
        amp = (1 if shape == 0 else 1 / n) * (-1 if shape == 2 and n % 2 == 0 else 1)
        wave += amp / math.sqrt(1 + (n * freq / CUTOFF_HZ[bright]) ** 4) * np.sin(2 * math.pi * n * x)
    return wave / (np.abs(wave).max() or 1)


def render(freq: float, setting: tuple, rate: int, channels: int) -> bytes:
    """A note as signed 16-bit frames for the mixer."""
    import numpy as np
    shape, bright, long_, wobble = setting
    decay = DECAY_S[long_]
    t = np.arange(int(rate * min(3.0, 0.05 + decay * 5))) / rate
    w = 2 * math.pi * WOBBLE_HZ
    cycles = freq * (t - WOBBLE[wobble] / w * (np.cos(w * t) - 1))
    table = _cycle(np, shape, bright, freq)
    wave = np.interp(cycles % 1 * TABLE, np.arange(TABLE + 1), np.append(table, table[0]))
    env = np.minimum(1, t / 0.006) * np.exp(-t / decay)
    tail = t > t[-1] - FADE_S
    env[tail] *= 0.5 * (1 + np.cos(math.pi * (t[tail] - t[-1] + FADE_S) / FADE_S))
    frames = (wave * env * PEAK[shape] * 32767).astype(np.int16)
    return np.repeat(frames, channels).tobytes()
