#!/usr/bin/env python3
"""Find marimba decay rates that don't clip at 10 notes / set_volume=0.4 while keeping duration=0.55."""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.music_constants import NOTE_FREQUENCIES
from scripts.generate_sounds import finalize_samples

SET_VOLUME = 0.4
SAMPLE_RATE = 44100
INTERVAL = 0.03
NUM_NOTES = 10

freqs = list(NOTE_FREQUENCIES.values())[:NUM_NOTES]

def gen_marimba(freq, duration, bar_decay_mult, tube_decay_mult):
    """Generate marimba with adjustable decay multipliers."""
    num_samples = int(SAMPLE_RATE * duration)

    bar_partials = [
        (1.0, 1.0, 3.5 * bar_decay_mult),
        (3.9, 0.15, 7.0 * bar_decay_mult),
        (9.2, 0.05, 13.0 * bar_decay_mult),
    ]
    tube_modes = [
        (1.0, 0.7, 3.0 * tube_decay_mult),
        (2.0, 0.3, 4.0 * tube_decay_mult),
        (3.0, 0.12, 5.0 * tube_decay_mult),
    ]

    samples = []
    fade_out_duration = 0.18
    fade_out_start = duration - fade_out_duration

    for i in range(num_samples):
        t = i / SAMPLE_RATE
        sample = 0

        if t < 0.012:
            attack = t / 0.012
        elif t < 0.06:
            attack = 1.0 + 0.2 * math.sin(math.pi * (t - 0.012) / 0.048)
        else:
            attack = 1.0

        for ratio, amp, decay_rate in bar_partials:
            partial_decay = math.exp(-t * decay_rate)
            sample += amp * partial_decay * math.sin(2 * math.pi * freq * ratio * t)

        for ratio, amp, decay_rate in tube_modes:
            tube_env = (1 - math.exp(-t * 25)) * math.exp(-t * decay_rate)
            sample += amp * tube_env * math.sin(2 * math.pi * freq * ratio * t)

        sub_bass = 0.3 * math.exp(-t * 3.5 * bar_decay_mult) * math.sin(2 * math.pi * freq * 0.5 * t)
        sample += sub_bass
        sample *= attack

        if t > fade_out_start:
            fade_progress = (t - fade_out_start) / fade_out_duration
            sample *= 0.5 * (1 + math.cos(math.pi * fade_progress))

        samples.append(sample)

    return finalize_samples(samples, peak_level=0.7)

# Test different decay multipliers
for mult in [1.0, 1.2, 1.4, 1.5, 1.6, 1.8, 2.0]:
    all_samples = []
    for freq in freqs:
        samples = gen_marimba(freq, 0.55, mult, mult)
        float_samples = [s / 32767.0 for s in samples]
        all_samples.append(float_samples)

    interval_samples = int(INTERVAL * SAMPLE_RATE)
    max_len = max(len(s) for s in all_samples)
    total_len = max_len + interval_samples * (NUM_NOTES - 1)

    mixed = [0.0] * total_len
    for j in range(NUM_NOTES):
        offset = j * interval_samples
        for i, s in enumerate(all_samples[j]):
            if offset + i < total_len:
                mixed[offset + i] += s * SET_VOLUME

    peak = max(abs(s) for s in mixed)
    status = "CLIPS" if peak > 1.0 else "OK"
    print(f"  decay_mult={mult:.1f}x  10-note peak={peak:.3f}  {status}")
