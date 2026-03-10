#!/usr/bin/env python3
"""Find the longest marimba duration that doesn't clip at 10 notes / set_volume=0.4."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.music_constants import NOTE_FREQUENCIES

SET_VOLUME = 0.4
SAMPLE_RATE = 44100
INTERVAL = 0.03  # 30ms
NUM_NOTES = 10

freqs = list(NOTE_FREQUENCIES.values())[:NUM_NOTES]

# Test durations from 0.55 down to 0.25
for dur in [0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25]:
    # Re-import with different duration by calling directly
    from scripts.generate_sounds import generate_marimba
    import types

    # Generate all notes at this duration
    all_samples = []
    for freq in freqs:
        samples = generate_marimba(freq, duration=dur)
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
    print(f"  duration={dur:.2f}s  10-note peak={peak:.3f}  {status}")
