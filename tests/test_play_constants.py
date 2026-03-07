"""Tests for play_constants: verify note names match frequencies."""

import math
from purple_tui.play_constants import (
    NOTE_FREQUENCIES, NOTE_NAMES, INSTRUMENTS, PERCUSSION_NAMES, GRID_KEYS,
)

# Standard A440 tuning reference frequencies across octaves
STANDARD_NOTES = {
    'C':  [32.70, 65.41, 130.81, 261.63, 523.25, 1046.50],
    'D':  [36.71, 73.42, 146.83, 293.66, 587.33, 1174.66],
    'E':  [41.20, 82.41, 164.81, 329.63, 659.25, 1318.51],
    'F#': [46.25, 92.50, 185.00, 369.99, 739.99, 1479.98],
    'G':  [49.00, 98.00, 196.00, 392.00, 783.99, 1567.98],
    'A':  [55.00, 110.00, 220.00, 440.00, 880.00, 1760.00],
    'B':  [61.74, 123.47, 246.94, 493.88, 987.77, 1975.53],
}

# NOTE_FREQUENCIES uses internal names for punctuation
INTERNAL_TO_DISPLAY = {'semicolon': ';', 'comma': ',', 'period': '.', 'slash': '/'}


def _closest_note(freq: float) -> str:
    """Return the note name closest to the given frequency."""
    best_note = None
    best_cents = float("inf")
    for note, freqs in STANDARD_NOTES.items():
        for f in freqs:
            cents = abs(1200 * math.log2(freq / f))
            if cents < best_cents:
                best_cents = cents
                best_note = note
    return best_note


def test_note_names_match_frequencies():
    """Every NOTE_NAME must match the actual musical note of its frequency."""
    for key, freq in NOTE_FREQUENCIES.items():
        display_key = INTERNAL_TO_DISPLAY.get(key, key)
        claimed = NOTE_NAMES[display_key]
        actual = _closest_note(freq)
        assert claimed == actual, (
            f"Key {key}: {freq} Hz is {actual}, but NOTE_NAMES says {claimed}"
        )


def test_all_melodic_keys_have_note_names():
    """Every non-digit key in the grid has a note name."""
    for row in GRID_KEYS:
        for key in row:
            if not key.isdigit():
                assert key in NOTE_NAMES, f"Key {key} missing from NOTE_NAMES"


def test_all_digit_keys_have_percussion_names():
    """Every digit key has a percussion display name."""
    for row in GRID_KEYS:
        for key in row:
            if key.isdigit():
                assert key in PERCUSSION_NAMES, f"Key {key} missing from PERCUSSION_NAMES"


def test_instruments_have_unique_ids():
    """Instrument IDs must be unique."""
    ids = [i[0] for i in INSTRUMENTS]
    assert len(ids) == len(set(ids))


def test_instruments_have_display_names():
    """Every instrument has a non-empty display name."""
    for inst_id, display_name in INSTRUMENTS:
        assert inst_id, "Empty instrument ID"
        assert display_name, f"Empty display name for {inst_id}"
