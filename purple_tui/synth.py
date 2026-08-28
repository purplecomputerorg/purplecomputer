"""Instrument synthesis shared by the sound pack build (scripts/generate_sounds.py)
and the startup chime (purple_tui/sound_check.py)."""

from __future__ import annotations

import math
import random


def loudness_compensated_peak(freq: float, base: float = 0.7) -> float:
    """Push low-pitched samples closer to digital ceiling.

    The ear is much less sensitive below ~500Hz (Fletcher-Munson / ISO 226).
    Even on good speakers, a 100Hz note at the same digital level as a
    1kHz note sounds substantially quieter. Compensate by letting low
    samples normalize hotter — up to ~+2.5dB at the lowest octaves.
    """
    if freq >= 500:
        return base
    boost = 1.0 + 0.4 * (1 - max(freq, 80) / 500)
    return min(0.95, base * boost)


def low_freq_partial_boost(freq: float) -> float:
    """Scale upper-partial amplitudes for low-pitched notes.

    A low note's upper partials sit in the ear's most sensitive band
    (1–4kHz). Boosting them adds perceived loudness without changing pitch
    or smearing the fundamental. Returns 1.0 for notes above 250Hz.
    """
    if freq >= 250:
        return 1.0
    return min(2.5, 250 / max(freq, 80))


def finalize_samples(samples: list[float], peak_level: float = 0.75,
                     freq: float | None = None) -> list[int]:
    """Normalize and convert to int16.

    If freq is provided, scale peak_level via loudness_compensated_peak so
    low-frequency samples normalize hotter to offset ear insensitivity.
    """
    if freq is not None:
        peak_level = loudness_compensated_peak(freq, base=peak_level)
    peak = max(abs(s) for s in samples) or 1
    return [int(s / peak * peak_level * 32767) for s in samples]


def generate_marimba(frequency: float, duration: float = 0.55, sample_rate: int = 44100) -> list[int]:
    """
    Crisp marimba: rosewood bar + tuned tube resonator at the fundamental.

    Real marimba bars are tuned so the second mode lands ~2 octaves above the
    fundamental (4:1) — that's the woody character. The tube resonator
    reinforces only the fundamental. Earlier versions stacked a 0.5x
    sub-octave sine and three tube partials, which produced a muddy clash
    against the bar fundamental and a low rumble that smeared the pitch.
    """
    nyquist = sample_rate / 2
    num_samples = int(sample_rate * duration)

    # (ratio, amp, decay_rate). 4.0 is the defining marimba partial — the
    # woody "knock" that makes a marimba sound like itself rather than a
    # low sine. For low-pitched notes the upper partials get extra gain
    # because the fundamental sits below the ear's sensitive band.
    boost = low_freq_partial_boost(frequency)
    bar_partials = [
        (1.0, 1.0, 5.5),
        (4.0, 0.5 * boost, 11.0),
        (9.2, 0.08 * boost, 18.0),
    ]

    samples = []
    fade_out_duration = 0.18
    fade_out_start = duration - fade_out_duration

    # Soft mallet noise burst — adds the "thock" without muddying sustain.
    random.seed(int(frequency * 1000))

    for i in range(num_samples):
        t = i / sample_rate
        sample = 0.0

        if t < 0.008:
            attack = t / 0.008
        else:
            attack = 1.0

        for ratio, amp, decay_rate in bar_partials:
            f = frequency * ratio
            if f >= nyquist:
                continue
            sample += amp * math.exp(-t * decay_rate) * math.sin(2 * math.pi * f * t)

        # Tuned tube resonator: fundamental only, slow attack, fast decay.
        # Quieter and shorter than the bar so it adds body without smearing
        # pitch into the bar's own fundamental.
        tube_env = (1 - math.exp(-t * 30)) * math.exp(-t * 6.0)
        sample += 0.25 * tube_env * math.sin(2 * math.pi * frequency * t)

        # Mallet "thock": noise burst, ~6ms, lowpassed by the bar.
        if t < 0.01:
            mallet = (random.random() * 2 - 1) * 0.25 * math.exp(-t * 400)
            sample += mallet

        sample *= attack

        if t > fade_out_start:
            fade_progress = (t - fade_out_start) / fade_out_duration
            sample *= 0.5 * (1 + math.cos(math.pi * fade_progress))

        samples.append(sample)

    return finalize_samples(samples, peak_level=0.7, freq=frequency)
