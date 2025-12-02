"""
Unit tests for keyboard_normalizer.py

Tests the KeyEventProcessor class directly - no mocks needed since it's pure logic.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from keyboard_normalizer import (
    KeyCodes,
    KeyEventProcessor,
    build_extra_key_map,
    NORMAL_KEY_CODES,
    LETTER_KEY_CODES,
    F_KEY_CODES,
)


# Helper constants
EV_KEY = KeyCodes.EV_KEY
EV_SYN = KeyCodes.EV_SYN
KEY_A = KeyCodes.KEY_A
KEY_B = KeyCodes.KEY_B
KEY_Z = KeyCodes.KEY_Z
KEY_SPACE = KeyCodes.KEY_SPACE
KEY_LEFTSHIFT = KeyCodes.KEY_LEFTSHIFT
KEY_RIGHTSHIFT = KeyCodes.KEY_RIGHTSHIFT
KEY_LEFTMETA = KeyCodes.KEY_LEFTMETA
KEY_CAPSLOCK = KeyCodes.KEY_CAPSLOCK
KEY_F1 = KeyCodes.KEY_F1
KEY_F12 = KeyCodes.KEY_F12

# Fake "media keys" not in NORMAL_KEY_CODES (using codes > 200)
MEDIA_KEY_1 = 400
MEDIA_KEY_2 = 401
MEDIA_KEY_3 = 402


@pytest.fixture
def processor():
    """Create a processor with no extra key mapping."""
    return KeyEventProcessor(extra_key_map={})


@pytest.fixture
def processor_with_media_keys():
    """Create a processor with media keys mapped to F1-F3."""
    return KeyEventProcessor(extra_key_map={
        MEDIA_KEY_1: KEY_F1,
        MEDIA_KEY_2: KeyCodes.KEY_F2,
        MEDIA_KEY_3: KeyCodes.KEY_F3,
    })


class TestBasicKeyPassthrough:
    """Test that basic keys pass through unchanged."""

    def test_letter_key_down(self, processor):
        """Letter key down passes through."""
        result = processor.process_event(EV_KEY, KEY_A, 1)
        assert result == [(EV_KEY, KEY_A, 1)]

    def test_letter_key_up(self, processor):
        """Letter key up passes through."""
        # First press down to track state
        processor.process_event(EV_KEY, KEY_A, 1)
        result = processor.process_event(EV_KEY, KEY_A, 0)
        assert result == [(EV_KEY, KEY_A, 0)]

    def test_letter_key_repeat(self, processor):
        """Letter key repeat passes through."""
        processor.process_event(EV_KEY, KEY_A, 1)
        result = processor.process_event(EV_KEY, KEY_A, 2)
        assert result == [(EV_KEY, KEY_A, 2)]

    def test_space_key(self, processor):
        """Non-letter keys pass through."""
        result = processor.process_event(EV_KEY, KEY_SPACE, 1)
        assert result == [(EV_KEY, KEY_SPACE, 1)]

    def test_non_key_events_pass_through(self, processor):
        """Non-EV_KEY events pass through unchanged."""
        result = processor.process_event(EV_SYN, 0, 0)
        assert result == [(EV_SYN, 0, 0)]


class TestStickyShift:
    """Test sticky shift toggle behavior."""

    def test_sticky_shift_starts_off(self, processor):
        """Sticky shift starts disabled."""
        assert processor.sticky_shift is False

    def test_meta_key_toggles_sticky_shift(self, processor):
        """Left meta key toggles sticky shift on."""
        result = processor.process_event(EV_KEY, KEY_LEFTMETA, 1)
        assert processor.sticky_shift is True
        assert result == []  # Key is consumed, not forwarded

    def test_meta_key_toggles_off(self, processor):
        """Second press toggles sticky shift off."""
        processor.process_event(EV_KEY, KEY_LEFTMETA, 1)
        processor.process_event(EV_KEY, KEY_LEFTMETA, 0)  # release
        processor.process_event(EV_KEY, KEY_LEFTMETA, 1)  # press again
        assert processor.sticky_shift is False

    def test_meta_release_does_not_toggle(self, processor):
        """Key release does not toggle sticky shift."""
        processor.process_event(EV_KEY, KEY_LEFTMETA, 1)
        assert processor.sticky_shift is True
        processor.process_event(EV_KEY, KEY_LEFTMETA, 0)
        assert processor.sticky_shift is True  # Still true

    def test_sticky_shift_injects_shift_for_letter(self, processor):
        """With sticky shift on, letters get shift injected."""
        processor.sticky_shift = True
        result = processor.process_event(EV_KEY, KEY_A, 1)
        # Should inject shift down, then letter down
        assert result == [
            (EV_KEY, KEY_LEFTSHIFT, 1),
            (EV_KEY, KEY_A, 1),
        ]

    def test_sticky_shift_releases_shift_on_letter_up(self, processor):
        """On letter release, injected shift is released."""
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_A, 1)
        result = processor.process_event(EV_KEY, KEY_A, 0)
        # Should release letter, then release shift
        assert result == [
            (EV_KEY, KEY_A, 0),
            (EV_KEY, KEY_LEFTSHIFT, 0),
        ]

    def test_sticky_shift_repeat_no_extra_shift(self, processor):
        """On repeat, no extra shift events."""
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_A, 1)
        result = processor.process_event(EV_KEY, KEY_A, 2)
        assert result == [(EV_KEY, KEY_A, 2)]

    def test_custom_sticky_shift_key(self):
        """Can use different key for sticky shift."""
        processor = KeyEventProcessor(
            extra_key_map={},
            sticky_shift_key=KeyCodes.KEY_RIGHTALT,
        )
        processor.process_event(EV_KEY, KeyCodes.KEY_RIGHTALT, 1)
        assert processor.sticky_shift is True

        # Left meta should NOT toggle now
        processor.process_event(EV_KEY, KEY_LEFTMETA, 1)
        assert processor.sticky_shift is True  # unchanged
        # And should be forwarded
        # (need to check it wasn't consumed)


class TestCapsLock:
    """Test caps lock toggle behavior."""

    def test_caps_lock_starts_off(self, processor):
        """Caps lock starts disabled."""
        assert processor.caps_lock is False

    def test_caps_lock_toggles_on(self, processor):
        """Caps lock key toggles caps lock on."""
        result = processor.process_event(EV_KEY, KEY_CAPSLOCK, 1)
        assert processor.caps_lock is True
        # Caps lock IS forwarded (unlike sticky shift)
        assert result == [(EV_KEY, KEY_CAPSLOCK, 1)]

    def test_caps_lock_toggles_off(self, processor):
        """Second press toggles caps lock off."""
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 1)
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 0)
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 1)
        assert processor.caps_lock is False

    def test_caps_lock_injects_shift(self, processor):
        """With caps lock on, letters get shift injected."""
        processor.caps_lock = True
        result = processor.process_event(EV_KEY, KEY_A, 1)
        assert result == [
            (EV_KEY, KEY_LEFTSHIFT, 1),
            (EV_KEY, KEY_A, 1),
        ]


class TestCapsLockStickyShiftXOR:
    """Test XOR behavior between caps lock and sticky shift."""

    def test_both_on_produces_lowercase(self, processor):
        """Caps lock + sticky shift = lowercase (XOR)."""
        processor.caps_lock = True
        processor.sticky_shift = True
        result = processor.process_event(EV_KEY, KEY_A, 1)
        # No shift injection
        assert result == [(EV_KEY, KEY_A, 1)]

    def test_only_caps_produces_uppercase(self, processor):
        """Only caps lock = uppercase."""
        processor.caps_lock = True
        processor.sticky_shift = False
        result = processor.process_event(EV_KEY, KEY_A, 1)
        assert len(result) == 2
        assert result[0] == (EV_KEY, KEY_LEFTSHIFT, 1)

    def test_only_sticky_produces_uppercase(self, processor):
        """Only sticky shift = uppercase."""
        processor.caps_lock = False
        processor.sticky_shift = True
        result = processor.process_event(EV_KEY, KEY_A, 1)
        assert len(result) == 2
        assert result[0] == (EV_KEY, KEY_LEFTSHIFT, 1)

    def test_neither_produces_lowercase(self, processor):
        """Neither = lowercase."""
        processor.caps_lock = False
        processor.sticky_shift = False
        result = processor.process_event(EV_KEY, KEY_A, 1)
        assert result == [(EV_KEY, KEY_A, 1)]


class TestPhysicalShiftInteraction:
    """Test interaction with physical shift key."""

    def test_physical_shift_with_sticky_produces_lowercase(self, processor):
        """Physical shift + sticky shift = lowercase."""
        processor.sticky_shift = True
        # Hold physical shift
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1)
        # Press letter
        result = processor.process_event(EV_KEY, KEY_A, 1)
        # Should NOT inject another shift
        assert result == [(EV_KEY, KEY_A, 1)]

    def test_physical_shift_without_modifiers_normal(self, processor):
        """Physical shift alone works normally."""
        # Hold physical shift
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1)
        # Press letter - should just forward (user is manually shifting)
        result = processor.process_event(EV_KEY, KEY_A, 1)
        assert result == [(EV_KEY, KEY_A, 1)]

    def test_right_shift_also_tracked(self, processor):
        """Right shift is also tracked."""
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_RIGHTSHIFT, 1)
        result = processor.process_event(EV_KEY, KEY_A, 1)
        # Physical shift held, so no injection
        assert result == [(EV_KEY, KEY_A, 1)]


class TestExtraKeyRemapping:
    """Test extra key to F-key remapping."""

    def test_media_key_remapped_to_f1(self, processor_with_media_keys):
        """Media key is remapped to F1."""
        result = processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 1)
        assert result == [(EV_KEY, KEY_F1, 1)]

    def test_media_key_up_also_remapped(self, processor_with_media_keys):
        """Key up events are also remapped."""
        processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 1)
        result = processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 0)
        assert result == [(EV_KEY, KEY_F1, 0)]

    def test_media_key_repeat_remapped(self, processor_with_media_keys):
        """Key repeat events are also remapped."""
        processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 1)
        result = processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 2)
        assert result == [(EV_KEY, KEY_F1, 2)]

    def test_unmapped_keys_pass_through(self, processor_with_media_keys):
        """Keys not in the map pass through."""
        unmapped_key = 999
        result = processor_with_media_keys.process_event(EV_KEY, unmapped_key, 1)
        assert result == [(EV_KEY, unmapped_key, 1)]


class TestHeldKeyTracking:
    """Test held key state tracking."""

    def test_key_down_tracked(self, processor):
        """Key down adds to held_keys."""
        processor.process_event(EV_KEY, KEY_A, 1)
        assert KEY_A in processor.held_keys

    def test_key_up_removed(self, processor):
        """Key up removes from held_keys."""
        processor.process_event(EV_KEY, KEY_A, 1)
        processor.process_event(EV_KEY, KEY_A, 0)
        assert KEY_A not in processor.held_keys

    def test_multiple_keys_tracked(self, processor):
        """Multiple keys can be held."""
        processor.process_event(EV_KEY, KEY_A, 1)
        processor.process_event(EV_KEY, KEY_B, 1)
        assert KEY_A in processor.held_keys
        assert KEY_B in processor.held_keys

    def test_repeat_does_not_affect_tracking(self, processor):
        """Repeat events don't affect held_keys."""
        processor.process_event(EV_KEY, KEY_A, 1)
        processor.process_event(EV_KEY, KEY_A, 2)
        assert KEY_A in processor.held_keys


class TestStateProperty:
    """Test state property."""

    def test_initial_state(self, processor):
        """Initial state has all defaults."""
        state = processor.state
        assert state['sticky_shift'] is False
        assert state['caps_lock'] is False
        assert state['held_keys'] == []
        assert state['injected_shift'] is False

    def test_state_reflects_changes(self, processor):
        """State reflects current processor state."""
        processor.sticky_shift = True
        processor.caps_lock = True
        processor.process_event(EV_KEY, KEY_A, 1)

        state = processor.state
        assert state['sticky_shift'] is True
        assert state['caps_lock'] is True
        assert KEY_A in state['held_keys']


class TestBuildExtraKeyMap:
    """Test build_extra_key_map function."""

    def test_empty_input(self):
        """Empty input returns empty map."""
        result = build_extra_key_map(set())
        assert result == {}

    def test_only_normal_keys(self):
        """Only normal keys returns empty map."""
        result = build_extra_key_map({KEY_A, KEY_B, KEY_SPACE})
        assert result == {}

    def test_extra_keys_mapped_to_f_keys(self):
        """Extra keys are mapped to F1-F12."""
        extra_keys = {MEDIA_KEY_1, MEDIA_KEY_2}
        all_keys = extra_keys | {KEY_A, KEY_B}
        result = build_extra_key_map(all_keys)

        assert len(result) == 2
        assert set(result.values()) <= set(F_KEY_CODES)

    def test_max_12_extra_keys(self):
        """At most 12 extra keys are mapped."""
        # Create 20 extra keys
        extra_keys = {500 + i for i in range(20)}
        result = build_extra_key_map(extra_keys)

        assert len(result) == 12
        assert set(result.values()) == set(F_KEY_CODES)

    def test_extra_keys_sorted_before_mapping(self):
        """Extra keys are sorted so mapping is deterministic."""
        extra_keys = {500, 400, 600}
        result = build_extra_key_map(extra_keys)

        # Lowest key code should map to F1
        assert result[400] == KEY_F1


class TestKeyCodesConstants:
    """Test that KeyCodes constants are correct."""

    def test_letter_codes_in_range(self):
        """Letter codes are in valid range."""
        for code in LETTER_KEY_CODES:
            assert 0 < code < 256

    def test_f_keys_count(self):
        """F_KEY_CODES has exactly 12 keys."""
        assert len(F_KEY_CODES) == 12

    def test_normal_keys_includes_letters(self):
        """NORMAL_KEY_CODES includes all letters."""
        assert LETTER_KEY_CODES <= NORMAL_KEY_CODES

    def test_normal_keys_includes_f_keys(self):
        """NORMAL_KEY_CODES includes F1-F12."""
        assert set(F_KEY_CODES) <= NORMAL_KEY_CODES


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_all_letters_work(self, processor):
        """All letter keys work correctly."""
        processor.sticky_shift = True
        for letter_code in LETTER_KEY_CODES:
            result = processor.process_event(EV_KEY, letter_code, 1)
            assert len(result) == 2
            assert result[0] == (EV_KEY, KEY_LEFTSHIFT, 1)
            # Clean up
            processor.process_event(EV_KEY, letter_code, 0)

    def test_rapid_sticky_shift_toggling(self, processor):
        """Rapid toggling works correctly."""
        for _ in range(10):
            processor.process_event(EV_KEY, KEY_LEFTMETA, 1)
            processor.process_event(EV_KEY, KEY_LEFTMETA, 0)
        # After 10 toggles, should be off
        assert processor.sticky_shift is False

    def test_shift_not_double_released(self, processor):
        """Shift is not released twice if letter released twice."""
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_A, 1)
        processor.process_event(EV_KEY, KEY_A, 0)
        # Second release should not crash or emit extra shift
        result = processor.process_event(EV_KEY, KEY_A, 0)
        assert result == [(EV_KEY, KEY_A, 0)]
