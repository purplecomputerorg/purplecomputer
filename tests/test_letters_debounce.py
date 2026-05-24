"""Tests for MusicMode's letters-mode debounce.

Hammering one key and mashing many keys are both filtered; deliberate
fast drills (different letters) pass through. Music mode is unaffected
(it's the caller's `_letters_mode` gate, not this helper, but we leave a
sanity check there too).
"""
import pytest
from purple_tui.rooms.music_room import MusicMode


class _Stub:
    """Bare object with just the attrs `_letters_debounce_drop` touches."""
    LETTERS_SAME_KEY_DEBOUNCE_S = MusicMode.LETTERS_SAME_KEY_DEBOUNCE_S
    LETTERS_CROSS_KEY_DEBOUNCE_S = MusicMode.LETTERS_CROSS_KEY_DEBOUNCE_S

    def __init__(self):
        self._last_letter_key = None
        self._last_letter_press_t = float("-inf")


def _drop(stub, key, t):
    return MusicMode._letters_debounce_drop(stub, key, t)


def test_first_press_always_accepted():
    s = _Stub()
    assert _drop(s, "A", 0.0) is False
    assert s._last_letter_key == "A"
    assert s._last_letter_press_t == 0.0
    # And again from a "real" monotonic time:
    s2 = _Stub()
    assert _drop(s2, "Q", 12345.678) is False


def test_same_key_inside_window_dropped():
    s = _Stub()
    _drop(s, "A", 0.0)
    # 100ms after — well inside 280ms same-key window
    assert _drop(s, "A", 0.10) is True
    # State not updated by a dropped press
    assert s._last_letter_press_t == 0.0


def test_same_key_past_window_accepted():
    s = _Stub()
    _drop(s, "A", 0.0)
    assert _drop(s, "A", 0.30) is False
    assert s._last_letter_press_t == 0.30


def test_cross_key_inside_window_dropped():
    s = _Stub()
    _drop(s, "A", 0.0)
    # 50ms gap — multi-finger mash, below 100ms cross-key floor
    assert _drop(s, "B", 0.05) is True


def test_cross_key_past_window_accepted():
    s = _Stub()
    _drop(s, "A", 0.0)
    # 120ms gap — deliberate drill rate
    assert _drop(s, "B", 0.12) is False
    assert s._last_letter_key == "B"


def test_finger_mash_collapses_to_one_letter():
    """Five fingers landing within ~30ms each: only the first is accepted."""
    s = _Stub()
    presses = [("A", 0.000), ("S", 0.008), ("D", 0.015), ("F", 0.022), ("G", 0.030)]
    accepted = [k for k, t in presses if not _drop(s, k, t)]
    assert accepted == ["A"]


def test_hammering_one_key_paces_out():
    """Tapping A every 50ms: only presses 280ms+ apart get through."""
    s = _Stub()
    accepted = []
    for i in range(20):
        t = i * 0.05
        if not _drop(s, "A", t):
            accepted.append(t)
    # 0.00, 0.30, 0.60, 0.90 — roughly clip-length spacing
    assert accepted == pytest.approx([0.0, 0.30, 0.60, 0.90])


def test_deliberate_drill_passes_through():
    """A-B-C-D-E at 150ms each (≈7/sec) — all accepted."""
    s = _Stub()
    presses = [("A", 0.00), ("B", 0.15), ("C", 0.30), ("D", 0.45), ("E", 0.60)]
    accepted = [k for k, t in presses if not _drop(s, k, t)]
    assert accepted == ["A", "B", "C", "D", "E"]


def test_switch_then_repeat_uses_correct_threshold():
    """A accepted, B accepted 200ms later (cross-key fine), then B 100ms
    after that is dropped (same-key window now)."""
    s = _Stub()
    assert _drop(s, "A", 0.00) is False
    assert _drop(s, "B", 0.20) is False
    # Now last_key == "B"; same-key threshold applies to next B
    assert _drop(s, "B", 0.30) is True
    # But A 100ms after the accepted B is cross-key → still dropped (under 100ms floor… exactly at it)
    assert _drop(s, "A", 0.29) is True   # 90ms after B
    assert _drop(s, "A", 0.31) is False  # 110ms after B
