"""
Tests for DoubleTapDetector

Pure logic tests with injected timestamps for deterministic behavior.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.keyboard import DoubleTapDetector, SHIFT_MAP


class TestDoubleTapDetector:
    """Tests for the DoubleTapDetector class."""

    def test_first_tap_returns_false(self):
        """First tap of any key should return False."""
        detector = DoubleTapDetector(threshold=0.4)
        assert detector.check('a', timestamp=0.0) is False

    def test_double_tap_same_key_returns_true(self):
        """Two taps of same key within threshold returns True."""
        detector = DoubleTapDetector(threshold=0.4)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.2) is True

    def test_double_tap_too_slow_returns_false(self):
        """Two taps of same key beyond threshold returns False."""
        detector = DoubleTapDetector(threshold=0.4)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.5) is False

    def test_different_keys_no_double_tap(self):
        """Different keys don't trigger double-tap."""
        detector = DoubleTapDetector(threshold=0.4)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('b', timestamp=0.1) is False

    def test_triple_tap_only_fires_once(self):
        """Triple tap only fires on second tap, not third."""
        detector = DoubleTapDetector(threshold=0.4)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.1) is True   # Double-tap fires
        assert detector.check('a', timestamp=0.2) is False  # Third tap is new first

    def test_allowed_keys_filter(self):
        """Only allowed keys can trigger double-tap."""
        detector = DoubleTapDetector(threshold=0.4, allowed_keys={'a', 'b'})

        # Allowed key works
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.1) is True

        # Non-allowed key doesn't work
        assert detector.check('c', timestamp=0.5) is False
        assert detector.check('c', timestamp=0.6) is False

    def test_allowed_keys_none_allows_all(self):
        """When allowed_keys is None, all keys work."""
        detector = DoubleTapDetector(threshold=0.4, allowed_keys=None)

        assert detector.check('x', timestamp=0.0) is False
        assert detector.check('x', timestamp=0.1) is True

        assert detector.check('z', timestamp=0.5) is False
        assert detector.check('z', timestamp=0.6) is True

    def test_reset_clears_state(self):
        """Reset clears the detector state."""
        detector = DoubleTapDetector(threshold=0.4)
        detector.check('a', timestamp=0.0)  # First tap
        detector.reset()
        assert detector.check('a', timestamp=0.1) is False  # Should be first tap again

    def test_just_under_threshold(self):
        """Tap just under threshold triggers double-tap."""
        detector = DoubleTapDetector(threshold=0.4)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.399) is True

    def test_just_over_threshold(self):
        """Tap just over threshold doesn't trigger double-tap."""
        detector = DoubleTapDetector(threshold=0.4)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.401) is False

    def test_works_with_keycodes(self):
        """Works with integer keycodes (for evdev)."""
        detector = DoubleTapDetector(threshold=0.4, allowed_keys={30, 31, 32})

        # Allowed keycode
        assert detector.check(30, timestamp=0.0) is False
        assert detector.check(30, timestamp=0.1) is True

        # Non-allowed keycode
        assert detector.check(99, timestamp=0.5) is False
        assert detector.check(99, timestamp=0.6) is False

    def test_non_allowed_key_resets_state(self):
        """Pressing a non-allowed key resets the detector state."""
        detector = DoubleTapDetector(threshold=0.4, allowed_keys={'a', 'b'})

        detector.check('a', timestamp=0.0)  # First tap of 'a'
        detector.check('c', timestamp=0.1)  # Non-allowed key resets
        assert detector.check('a', timestamp=0.2) is False  # Should be first tap again

    def test_default_threshold(self):
        """Default threshold is 0.4 seconds."""
        detector = DoubleTapDetector()
        assert detector.threshold == 0.4

    def test_shift_map_integration(self):
        """Works with SHIFT_MAP keys for character shifting."""
        detector = DoubleTapDetector(
            threshold=0.5,
            allowed_keys=set(SHIFT_MAP.keys()),
        )

        # Dash -> underscore
        assert detector.check('-', timestamp=0.0) is False
        is_double = detector.check('-', timestamp=0.2)
        assert is_double is True
        if is_double:
            assert SHIFT_MAP['-'] == '_'

        # Semicolon -> colon
        assert detector.check(';', timestamp=0.5) is False
        is_double = detector.check(';', timestamp=0.7)
        assert is_double is True
        if is_double:
            assert SHIFT_MAP[';'] == ':'

    def test_rapid_alternating_keys(self):
        """Rapidly alternating between two keys doesn't trigger false positives."""
        detector = DoubleTapDetector(threshold=0.4)

        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('b', timestamp=0.05) is False
        assert detector.check('a', timestamp=0.1) is False  # Reset by 'b'
        assert detector.check('b', timestamp=0.15) is False  # Reset by 'a'
        assert detector.check('a', timestamp=0.2) is False   # Reset by 'b'


class TestDoubleTapEdgeCases:
    """Edge cases and boundary conditions."""

    def test_zero_threshold(self):
        """Zero threshold never triggers double-tap."""
        detector = DoubleTapDetector(threshold=0.0)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.0) is False  # Even exact same time fails with < comparison
        assert detector.check('a', timestamp=0.001) is False  # Any delay also fails

    def test_very_long_threshold(self):
        """Very long threshold allows slow double-taps."""
        detector = DoubleTapDetector(threshold=10.0)
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=9.9) is True

    def test_empty_allowed_keys(self):
        """Empty allowed_keys set means nothing triggers."""
        detector = DoubleTapDetector(threshold=0.4, allowed_keys=set())
        assert detector.check('a', timestamp=0.0) is False
        assert detector.check('a', timestamp=0.1) is False

    def test_special_characters(self):
        """Works with special characters."""
        detector = DoubleTapDetector(threshold=0.4)

        assert detector.check(';', timestamp=0.0) is False
        assert detector.check(';', timestamp=0.1) is True

        detector.reset()

        assert detector.check("'", timestamp=0.5) is False
        assert detector.check("'", timestamp=0.6) is True

    def test_unicode_characters(self):
        """Works with unicode characters."""
        detector = DoubleTapDetector(threshold=0.4)

        assert detector.check('ñ', timestamp=0.0) is False
        assert detector.check('ñ', timestamp=0.1) is True

    def test_timestamps_can_be_any_float(self):
        """Timestamps work with any float values (not just starting from 0)."""
        detector = DoubleTapDetector(threshold=0.4)

        assert detector.check('a', timestamp=1000.0) is False
        assert detector.check('a', timestamp=1000.2) is True
