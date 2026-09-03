"""Instrument synthesis shared by the sound pack build (scripts/generate_sounds.py),
the startup chime (purple_tui/sound_check.py), and Purple Studio.

Every generator takes keyword parameters whose defaults are the shipped sound.
Studio exposes the same names as sliders and checks its JavaScript port against
renders of these functions, so keep the arithmetic here simple and ordered: see
scripts/export_studio.py and studio/README.md.
"""

from __future__ import annotations

import math
from collections.abc import Iterator

SAMPLE_RATE = 44100

# Slider defaults per instrument. Studio reads these from the export; nothing else may redefine them.
DEFAULTS: dict[str, dict[str, float]] = {
    "marimba": {
        "duration": 0.55, "attack_ms": 8, "bar_decay": 5.5,
        "wood": 0.5, "sparkle": 0.08, "tube": 0.25, "tube_decay": 6.0, "mallet": 0.25,
    },
    "ukulele": {
        "duration": 0.9, "damping": 0.996, "warmth": 0.4, "softness": 3, "pluck_pos": 0.25,
        "body_freq": 420.0, "body_q": 3.0, "body_mix": 0.35,
    },
    "accordion": {
        "duration": 0.55, "attack_ms": 80, "detune": 2.0, "harmonics": 10, "rolloff": 1000.0,
        "trem_rate": 5.0, "trem_depth": 0.015,
    },
    "glockenspiel": {
        "duration": 1.5, "ring": 1.0, "fundamental": 0.6, "bell": 0.9, "shimmer": 1.0, "ping": 0.35,
    },
}

_MASK = 0xFFFFFFFF


def noise(seed: float) -> Iterator[float]:
    """Deterministic noise in [-1, 1): mulberry32, so a JavaScript port yields the same stream."""
    a = int(seed) & _MASK
    while True:
        a = (a + 0x6D2B79F5) & _MASK
        t = a
        t = ((t ^ (t >> 15)) * (t | 1)) & _MASK
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & _MASK)) & _MASK
        yield (((t ^ (t >> 14)) & _MASK) / 4294967296) * 2 - 1


def loudness_compensated_peak(freq: float, base: float = 0.7) -> float:
    """Push low-pitched samples closer to digital ceiling.

    The ear is much less sensitive below ~500Hz (Fletcher-Munson / ISO 226), so
    low samples normalize hotter, up to ~+2.5dB at the lowest octaves.
    """
    if freq >= 500:
        return base
    boost = 1.0 + 0.4 * (1 - max(freq, 80) / 500)
    return min(0.95, base * boost)


def low_freq_partial_boost(freq: float) -> float:
    """Scale upper-partial amplitudes for low-pitched notes, whose fundamental
    sits below the ear's sensitive band. Returns 1.0 above 250Hz."""
    if freq >= 250:
        return 1.0
    return min(2.5, 250 / max(freq, 80))


def finalize_samples(samples: list[float], peak_level: float = 0.75,
                     freq: float | None = None) -> list[int]:
    """Normalize and convert to int16."""
    if freq is not None:
        peak_level = loudness_compensated_peak(freq, base=peak_level)
    peak = max(abs(s) for s in samples) or 1
    return [int(s / peak * peak_level * 32767) for s in samples]


def _cosine_fade(samples: list[float], duration: float, fade: float, sample_rate: int) -> None:
    start = duration - fade
    for i, s in enumerate(samples):
        t = i / sample_rate
        if t > start:
            samples[i] = s * 0.5 * (1 + math.cos(math.pi * (t - start) / fade))


def _params(name: str, duration: float | None, overrides: dict[str, float]) -> dict[str, float]:
    p = {**DEFAULTS[name], **overrides}
    if duration is not None:
        p["duration"] = duration
    return p


def generate_marimba(frequency: float, duration: float | None = None, sample_rate: int = SAMPLE_RATE,
                     **overrides: float) -> list[int]:
    """Crisp marimba: rosewood bar plus a tuned tube resonator at the fundamental.

    The 4x partial is the woody knock that makes a marimba sound like itself
    rather than a low sine; low notes get extra upper-partial gain.
    """
    p = _params("marimba", duration, overrides)
    nyquist = sample_rate / 2
    num_samples = int(sample_rate * p["duration"])
    boost = low_freq_partial_boost(frequency)
    bar_partials = [
        (1.0, 1.0, p["bar_decay"]),
        (4.0, p["wood"] * boost, p["bar_decay"] * 2),
        (9.2, p["sparkle"] * boost, p["bar_decay"] * 18 / 5.5),
    ]
    attack_s = p["attack_ms"] / 1000
    mallet_noise = noise(frequency * 1000)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        s = 0.0
        for ratio, amp, decay in bar_partials:
            f = frequency * ratio
            if f < nyquist:
                s += amp * math.exp(-t * decay) * math.sin(2 * math.pi * f * t)
        tube_env = (1 - math.exp(-t * 30)) * math.exp(-t * p["tube_decay"])
        s += p["tube"] * tube_env * math.sin(2 * math.pi * frequency * t)
        if t < 0.01:
            s += next(mallet_noise) * p["mallet"] * math.exp(-t * 400)
        samples.append(s * min(1.0, t / attack_s))
    _cosine_fade(samples, p["duration"], min(0.18, p["duration"] / 3), sample_rate)
    return finalize_samples(samples, peak_level=0.7, freq=frequency)


def generate_accordion(frequency: float, duration: float | None = None, sample_rate: int = SAMPLE_RATE,
                       **overrides: float) -> list[int]:
    """Accordion: two band-limited sawtooth reeds a few cents apart, with a slow tremolo."""
    p = _params("accordion", duration, overrides)
    nyquist = sample_rate / 2
    num_samples = int(sample_rate * p["duration"])
    freqs = (frequency, frequency * (2 ** (p["detune"] / 1200.0)))
    max_n = min(int(p["harmonics"]), int(nyquist / max(frequency, 1.0)))
    attack_s = p["attack_ms"] / 1000
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        s = 0.0
        for f in freqs:
            for n in range(1, max_n + 1):
                fn = f * n
                if fn >= nyquist:
                    break
                amp = (1.0 / n) * (p["rolloff"] / fn if fn > p["rolloff"] else 1.0)
                s += amp * math.sin(2 * math.pi * fn * t)
        trem = 1.0 + p["trem_depth"] * math.sin(2 * math.pi * p["trem_rate"] * t)
        samples.append(s * min(1.0, t / attack_s) * trem)
    _cosine_fade(samples, p["duration"], min(0.12, p["duration"] / 3), sample_rate)
    return finalize_samples(samples, peak_level=0.4, freq=frequency)


def generate_ukulele(frequency: float, duration: float | None = None, sample_rate: int = SAMPLE_RATE,
                     **overrides: float) -> list[int]:
    """Ukulele via Karplus-Strong: a filtered delay line plus a small body resonator.

    Softened noise for a finger pluck, a lowpass in the loop so highs decay
    first, an allpass for fractional tuning, and a biquad bandpass for the body.
    """
    p = _params("ukulele", duration, overrides)
    num_samples = int(sample_rate * p["duration"])
    period = sample_rate / frequency
    n = int(period)
    frac = period - n
    allpass = (1 - frac) / (1 + frac)

    pluck_noise = noise(frequency * 1000)
    line = [next(pluck_noise) for _ in range(n)]
    for _ in range(int(p["softness"])):
        for j in range(1, n):
            line[j] = 0.5 * line[j] + 0.5 * line[j - 1]
    pluck = int(n * p["pluck_pos"])
    if pluck > 0:
        for j in range(pluck, n):
            line[j] = line[j] - 0.5 * line[j - pluck]

    samples = [0.0] * num_samples
    pos = 0
    ap_in = ap_out = prev = 0.0
    warmth = p["warmth"]
    for i in range(num_samples):
        cur = line[pos]
        filtered = warmth * cur + (1 - warmth) * prev
        prev = filtered
        a = allpass * filtered + ap_in - allpass * ap_out
        ap_in = filtered
        ap_out = a
        line[pos] = a * p["damping"]
        pos = (pos + 1) % n
        samples[i] = cur

    w0 = 2 * math.pi * p["body_freq"] / sample_rate
    alpha = math.sin(w0) / (2 * p["body_q"])
    a0 = 1 + alpha
    b0, b2, a1, a2 = alpha / a0, -alpha / a0, -2 * math.cos(w0) / a0, (1 - alpha) / a0
    x1 = x2 = y1 = y2 = 0.0
    for i in range(num_samples):
        x0 = samples[i]
        y0 = b0 * x0 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x0, y1, y0
        samples[i] = x0 + p["body_mix"] * y0
    _cosine_fade(samples, p["duration"], min(0.15, p["duration"] / 3), sample_rate)
    return finalize_samples(samples, peak_level=0.7, freq=frequency)


def generate_glockenspiel(frequency: float, duration: float | None = None, sample_rate: int = SAMPLE_RATE,
                          **overrides: float) -> list[int]:
    """Glockenspiel: inharmonic metal bar with the 2.8x partial louder than the
    fundamental, a short 4kHz mallet ping, and a long ring.

    The 2.8x partial creates a false autocorrelation peak ~85 cents below the
    fundamental; verify tuning with a DFT, not autocorrelation.
    """
    p = _params("glockenspiel", duration, overrides)
    nyquist = sample_rate / 2
    num_samples = int(sample_rate * p["duration"])
    boost = low_freq_partial_boost(frequency)
    ring = p["ring"]
    partials = [
        (1.0, p["fundamental"], 1.4 / ring),
        (2.8, p["bell"] * boost, 2.8 / ring),
        (5.42, 0.45 * p["shimmer"] * boost, 4.2 / ring),
        (8.6, 0.22 * p["shimmer"] * boost, 6.5 / ring),
        (11.7, 0.12 * p["shimmer"] * boost, 9.0 / ring),
    ]
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        s = 0.0
        for ratio, amp, dec in partials:
            f = frequency * ratio
            if f < nyquist:
                s += amp * math.exp(-t * dec) * math.sin(2 * math.pi * f * t)
        if t < 0.005:
            s += p["ping"] * math.exp(-t / 0.00125) * math.sin(2 * math.pi * 4000.0 * t)
        samples.append(s * min(1.0, t / 0.002))
    _cosine_fade(samples, p["duration"], min(0.7, p["duration"] / 2), sample_rate)
    return finalize_samples(samples, peak_level=0.7, freq=frequency)


GENERATORS = {
    "marimba": generate_marimba,
    "ukulele": generate_ukulele,
    "accordion": generate_accordion,
    "glockenspiel": generate_glockenspiel,
}
