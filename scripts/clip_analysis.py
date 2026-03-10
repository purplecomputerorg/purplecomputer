#!/usr/bin/env python3
"""Analyze actual waveform overlap clipping for each instrument."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.generate_sounds import (
    generate_marimba, generate_xylophone, generate_ukulele, generate_music_box
)

SET_VOLUME = 0.5
SAMPLE_RATE = 44100
INTERVAL = 0.05  # 50ms between rapid hits
NUM_NOTES = 5

instruments = {
    'marimba': generate_marimba,
    'xylophone': generate_xylophone,
    'ukulele': generate_ukulele,
    'musicbox': generate_music_box,
}

FREQ = 261.63  # Middle C

print(f"Actual waveform overlap analysis")
print(f"set_volume={SET_VOLUME}, interval={INTERVAL*1000:.0f}ms, freq={FREQ}Hz")
print("=" * 70)

for name, gen_func in instruments.items():
    samples = gen_func(FREQ)
    # Normalize to float [-1, 1] (samples are already int16)
    peak = max(abs(s) for s in samples) or 1
    float_samples = [s / 32767.0 for s in samples]

    # Simulate N overlapping notes, each offset by INTERVAL
    interval_samples = int(INTERVAL * SAMPLE_RATE)
    total_len = len(samples) + interval_samples * (NUM_NOTES - 1)
    mixed = [0.0] * total_len

    for n in range(NUM_NOTES):
        offset = n * interval_samples
        for i, s in enumerate(float_samples):
            mixed[offset + i] += s * SET_VOLUME

    max_amp = max(abs(s) for s in mixed)
    # Find when clipping first occurs (> 1.0)
    clip_sample = None
    for i, s in enumerate(mixed):
        if abs(s) > 1.0:
            clip_sample = i
            break

    # Find max for each note count
    print(f"\n  {name}:")
    print(f"    Single note peak: {max(abs(s) for s in float_samples) * SET_VOLUME:.3f}")
    for n in range(2, NUM_NOTES + 1):
        mix_n = [0.0] * (len(samples) + interval_samples * (n - 1))
        for j in range(n):
            offset = j * interval_samples
            for i, s in enumerate(float_samples):
                mix_n[offset + i] += s * SET_VOLUME
        peak_n = max(abs(s) for s in mix_n)
        clipped = " ** CLIPS **" if peak_n > 1.0 else ""
        print(f"    {n} notes overlapping: peak {peak_n:.3f}{clipped}")

print()
print("=" * 70)
print("Safe set_volume for 4 overlapping notes:")
print("-" * 50)
for name, gen_func in instruments.items():
    samples = gen_func(FREQ)
    float_samples = [s / 32767.0 for s in samples]
    interval_samples = int(INTERVAL * SAMPLE_RATE)

    mix_4 = [0.0] * (len(samples) + interval_samples * 3)
    for j in range(4):
        offset = j * interval_samples
        for i, s in enumerate(float_samples):
            mix_4[offset + i] += s  # volume=1.0 to find raw peak
    raw_peak = max(abs(s) for s in mix_4)
    safe_vol = 1.0 / raw_peak if raw_peak > 0 else 1.0
    print(f"  {name:<12} set_volume <= {safe_vol:.2f}  (raw 4-note peak: {raw_peak:.2f})")
