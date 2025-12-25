"""
Tests for keyboard_normalizer.py

Tests KeyEventProcessor class directly - pure logic, no mocks needed.
Timestamps are injected for deterministic testing.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from keyboard_normalizer import KeyCodes, KeyEventProcessor

# Constants
EV_KEY = KeyCodes.EV_KEY
EV_MSC = KeyCodes.EV_MSC
MSC_SCAN = KeyCodes.MSC_SCAN
KEY_A = 30
KEY_SPACE = KeyCodes.KEY_SPACE
KEY_LEFTSHIFT = KeyCodes.KEY_LEFTSHIFT
KEY_RIGHTSHIFT = KeyCodes.KEY_RIGHTSHIFT
KEY_CAPSLOCK = KeyCodes.KEY_CAPSLOCK
KEY_ESC = KeyCodes.KEY_ESC
KEY_F1 = KeyCodes.KEY_F1
KEY_F24 = KeyCodes.KEY_F24

# Fake scancodes for testing
SCANCODE_F1 = 0x3B
SCANCODE_BRIGHTNESS = 0xE0


@pytest.fixture
def processor():
    """Processor with no scancode mapping."""
    return KeyEventProcessor()


@pytest.fixture
def processor_with_mapping():
    """Processor with scancode mapping (brightness key → F1)."""
    return KeyEventProcessor(scancode_map={SCANCODE_BRIGHTNESS: KEY_F1})


class TestBasicPassthrough:
    """Basic key events pass through."""

    def test_key_press_passthrough(self, processor):
        result = processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        assert result == [(EV_KEY, KEY_A, 1)]

    def test_key_release_passthrough(self, processor):
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.0)
        assert result == [(EV_KEY, KEY_A, 0)]

    def test_space_passthrough(self, processor):
        result = processor.process_event(EV_KEY, KEY_SPACE, 1, timestamp=0.0)
        assert result == [(EV_KEY, KEY_SPACE, 1)]


class TestScancodeRemapping:
    """Scancode-based key remapping."""

    def test_scancode_captured_before_keycode(self, processor_with_mapping):
        """MSC_SCAN event is captured, used for next EV_KEY."""
        # Scancode arrives first
        result = processor_with_mapping.process_event(EV_MSC, MSC_SCAN, SCANCODE_BRIGHTNESS, timestamp=0.0)
        assert result == []  # Captured, not emitted

        # Then keycode - should be remapped
        result = processor_with_mapping.process_event(EV_KEY, 224, 1, timestamp=0.0)  # 224 = KEY_BRIGHTNESSDOWN
        assert result == [(EV_KEY, KEY_F1, 1)]

    def test_scancode_remaps_release(self, processor_with_mapping):
        """Release events also remapped via scancode."""
        processor_with_mapping.process_event(EV_MSC, MSC_SCAN, SCANCODE_BRIGHTNESS, timestamp=0.0)
        result = processor_with_mapping.process_event(EV_KEY, 224, 0, timestamp=0.0)
        assert result == [(EV_KEY, KEY_F1, 0)]

    def test_unknown_scancode_passes_through(self, processor_with_mapping):
        """Unknown scancodes don't remap."""
        processor_with_mapping.process_event(EV_MSC, MSC_SCAN, 0x9999, timestamp=0.0)
        result = processor_with_mapping.process_event(EV_KEY, 224, 1, timestamp=0.0)
        assert result == [(EV_KEY, 224, 1)]  # Unchanged

    def test_no_scancode_passes_through(self, processor_with_mapping):
        """Without preceding scancode, keycode passes through."""
        result = processor_with_mapping.process_event(EV_KEY, 224, 1, timestamp=0.0)
        assert result == [(EV_KEY, 224, 1)]


class TestStickyShift:
    """Tap shift = sticky shift, hold shift = normal."""

    def test_sticky_starts_off(self, processor):
        assert processor.sticky_shift is False

    def test_shift_tap_activates_sticky(self, processor):
        """Quick shift tap (<300ms) toggles sticky shift."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.2)
        assert processor.sticky_shift is True

    def test_shift_hold_no_sticky(self, processor):
        """Long shift hold (>300ms) doesn't activate sticky."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.5)
        assert processor.sticky_shift is False

    def test_shift_with_key_no_sticky(self, processor):
        """Shift + another key doesn't activate sticky."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.1)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.15)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.2)
        assert processor.sticky_shift is False

    def test_shift_events_forwarded(self, processor):
        """Shift press/release events are forwarded."""
        result = processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        assert result == [(EV_KEY, KEY_LEFTSHIFT, 1)]

        result = processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.2)
        assert result == [(EV_KEY, KEY_LEFTSHIFT, 0)]

    def test_right_shift_also_works(self, processor):
        """Right shift tap also activates sticky."""
        processor.process_event(EV_KEY, KEY_RIGHTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_RIGHTSHIFT, 0, timestamp=0.2)
        assert processor.sticky_shift is True

    def test_sticky_toggles(self, processor):
        """Multiple taps toggle sticky on/off."""
        # First tap - on
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.1)
        assert processor.sticky_shift is True

        # Second tap - off
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.5)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.6)
        assert processor.sticky_shift is False


class TestEscapeLongPress:
    """Hold Escape 1s = F24 (parent mode), tap = normal."""

    def test_escape_tap_emits_escape(self, processor):
        """Quick escape tap emits normal escape on release."""
        result = processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)
        assert result == []  # Buffered

        result = processor.process_event(EV_KEY, KEY_ESC, 0, timestamp=0.5)
        assert result == [(EV_KEY, KEY_ESC, 1), (EV_KEY, KEY_ESC, 0)]

    def test_escape_long_press_emits_f24(self, processor):
        """Escape held >1s emits F24."""
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        # Repeat triggers check
        result = processor.process_event(EV_KEY, KEY_ESC, 2, timestamp=1.1)
        assert result == [(EV_KEY, KEY_F24, 1), (EV_KEY, KEY_F24, 0)]

    def test_escape_long_press_no_escape_on_release(self, processor):
        """After F24, no escape on release."""
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_ESC, 2, timestamp=1.1)

        result = processor.process_event(EV_KEY, KEY_ESC, 0, timestamp=1.2)
        assert result == []

    def test_escape_via_check_pending(self, processor):
        """Long-press detected via check_pending."""
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        result = processor.check_pending(ts=1.1)
        assert result == [(EV_KEY, KEY_F24, 1), (EV_KEY, KEY_F24, 0)]

    def test_escape_only_fires_once(self, processor):
        """F24 only fires once per hold."""
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        result = processor.check_pending(ts=1.1)
        assert len(result) == 2

        result = processor.check_pending(ts=1.2)
        assert result == []


class TestCapsLock:
    """Caps lock toggle."""

    def test_caps_starts_off(self, processor):
        assert processor.caps_lock is False

    def test_caps_toggles_on(self, processor):
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 1, timestamp=0.0)
        assert processor.caps_lock is True

    def test_caps_toggles_off(self, processor):
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 0, timestamp=0.1)
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 1, timestamp=0.2)
        assert processor.caps_lock is False


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_shift_tap_just_under_threshold(self, processor):
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.299)
        assert processor.sticky_shift is True

    def test_shift_tap_just_over_threshold(self, processor):
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.301)
        assert processor.sticky_shift is False

    def test_escape_just_under_threshold(self, processor):
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)
        result = processor.check_pending(ts=0.999)
        assert result == []

    def test_escape_just_over_threshold(self, processor):
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)
        result = processor.check_pending(ts=1.001)
        assert result == [(EV_KEY, KEY_F24, 1), (EV_KEY, KEY_F24, 0)]

    def test_rapid_shift_tapping(self, processor):
        """5 rapid taps = sticky on (odd toggles)."""
        for i in range(5):
            t = i * 0.3
            processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=t)
            processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=t + 0.1)
        assert processor.sticky_shift is True


class TestDoubleTap:
    """Double-tap same key = shifted version."""

    def test_double_tap_letter_produces_uppercase(self, processor):
        """Tap 'a' twice quickly = 'A' (backspace + shift + a)."""
        # First tap
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)

        # Second tap within threshold
        result = processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.2)

        # Should emit: backspace, shift down, key down
        assert (EV_KEY, 14, 1) in result  # KEY_BACKSPACE down
        assert (EV_KEY, 14, 0) in result  # KEY_BACKSPACE up
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result
        assert (EV_KEY, KEY_A, 1) in result

    def test_double_tap_release_releases_shift(self, processor):
        """After double-tap, key release also releases shift."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.2)

        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.3)
        assert (EV_KEY, KEY_A, 0) in result
        assert (EV_KEY, KEY_LEFTSHIFT, 0) in result

    def test_slow_double_tap_no_shift(self, processor):
        """Taps too far apart = normal keys, no shift."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)

        # Second tap after threshold
        result = processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.6)
        assert result == [(EV_KEY, KEY_A, 1)]  # Normal key, no shift

    def test_different_keys_no_double_tap(self, processor):
        """Different keys don't trigger double-tap."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)

        # Different key
        result = processor.process_event(EV_KEY, 48, 1, timestamp=0.2)  # KEY_B
        assert result == [(EV_KEY, 48, 1)]


class TestKeyCodesConstants:
    """KeyCodes constants are correct."""

    def test_event_types(self):
        assert KeyCodes.EV_KEY == 1
        assert KeyCodes.EV_MSC == 4

    def test_msc_scan(self):
        assert KeyCodes.MSC_SCAN == 4

    def test_f24(self):
        assert KeyCodes.KEY_F24 == 194

    def test_f1_f12(self):
        assert KeyCodes.KEY_F1 == 59
        assert KeyCodes.KEY_F12 == 88
