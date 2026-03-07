#!/usr/bin/env python3
"""Verify that NOTE_NAMES matches the actual frequencies in NOTE_FREQUENCIES."""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from purple_tui.play_constants import NOTE_FREQUENCIES, NOTE_NAMES

# Standard A440 tuning reference frequencies across octaves
STANDARD = {
    'C':  [16.35, 32.70, 65.41, 130.81, 261.63, 523.25, 1046.50],
    'D':  [18.35, 36.71, 73.42, 146.83, 293.66, 587.33, 1174.66],
    'E':  [20.60, 41.20, 82.41, 164.81, 329.63, 659.25, 1318.51],
    'F#': [23.12, 46.25, 92.50, 185.00, 369.99, 739.99, 1479.98],
    'G':  [24.50, 49.00, 98.00, 196.00, 392.00, 783.99, 1567.98],
    'A':  [27.50, 55.00, 110.00, 220.00, 440.00, 880.00, 1760.00],
    'B':  [30.87, 61.74, 123.47, 246.94, 493.88, 987.77, 1975.53],
}

# NOTE_FREQUENCIES uses internal names for punctuation, NOTE_NAMES uses display chars
INTERNAL_TO_DISPLAY = {'semicolon': ';', 'comma': ',', 'period': '.', 'slash': '/'}

errors = []
for key, freq in NOTE_FREQUENCIES.items():
    display_key = INTERNAL_TO_DISPLAY.get(key, key)
    claimed_note = NOTE_NAMES.get(display_key)
    if not claimed_note:
        errors.append(f"{key}: no note name assigned")
        continue
    best_note = None
    best_dist = float("inf")
    for note, freqs in STANDARD.items():
        for f in freqs:
            cents = abs(1200 * math.log2(freq / f))
            if cents < best_dist:
                best_dist = cents
                best_note = note
    if best_note != claimed_note:
        errors.append(
            f"{key}: freq {freq} Hz is {best_note}, "
            f"but NOTE_NAMES says {claimed_note} ({best_dist:.1f} cents off)"
        )
    else:
        print(f"  {key}: {freq:>8.2f} Hz = {claimed_note} (match, {best_dist:.1f} cents)")

if errors:
    print()
    print("ERRORS:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print()
    print("All note names are correct!")
