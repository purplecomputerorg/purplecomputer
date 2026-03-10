#!/usr/bin/env python3
"""Analyze clipping with different frequencies (realistic key mashing)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.generate_sounds import generate_marimba
from purple_tui.music_constants import NOTE_FREQUENCIES

SET_VOLUME = 0.4
SAMPLE_RATE = 44100
INTERVAL = 0.03  # 30ms between hits (fast mashing)

# Use the actual note frequencies mapped to keys
freqs = list(NOTE_FREQUENCIES.values())[:10]

print(f"Multi-frequency overlap analysis (10 different marimba notes)")
print(f"set_volume={SET_VOLUME}, interval={INTERVAL*1000:.0f}ms")
print(f"Frequencies: {[f'{f:.0f}Hz' for f in freqs]}")
print("=" * 70)

# Generate all 10 notes
all_samples = []
for freq in freqs:
    samples = generate_marimba(freq)
    float_samples = [s / 32767.0 for s in samples]
    all_samples.append(float_samples)

interval_samples = int(INTERVAL * SAMPLE_RATE)
max_len = max(len(s) for s in all_samples)
total_len = max_len + interval_samples * 9

for n in range(1, 11):
    mixed = [0.0] * total_len
    for j in range(n):
        offset = j * interval_samples
        for i, s in enumerate(all_samples[j]):
            if offset + i < total_len:
                mixed[offset + i] += s * SET_VOLUME
    peak = max(abs(s) for s in mixed)
    clipped = " ** CLIPS **" if peak > 1.0 else ""
    print(f"  {n:2d} different notes: peak {peak:.3f}{clipped}")

# Find safe volume for 10 different notes
mixed_raw = [0.0] * total_len
for j in range(10):
    offset = j * interval_samples
    for i, s in enumerate(all_samples[j]):
        if offset + i < total_len:
            mixed_raw[offset + i] += s
raw_peak = max(abs(s) for s in mixed_raw)
safe_vol = 1.0 / raw_peak
print(f"\nSafe set_volume for 10 different notes: <= {safe_vol:.2f} (raw peak: {raw_peak:.2f})")
