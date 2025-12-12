"""
Unit tests for keyboard_normalizer.py

Tests the KeyEventProcessor class directly - no mocks needed since it's pure logic.
Timestamps are injected for deterministic testing.
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
    SHIFTABLE_KEY_CODES,
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
KEY_CAPSLOCK = KeyCodes.KEY_CAPSLOCK
KEY_ESC = KeyCodes.KEY_ESC
KEY_F1 = KeyCodes.KEY_F1
KEY_F12 = KeyCodes.KEY_F12
KEY_F24 = KeyCodes.KEY_F24
KEY_MINUS = KeyCodes.KEY_MINUS
KEY_1 = KeyCodes.KEY_1

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
    """Test that basic keys pass through (with buffering for shiftable keys)."""

    def test_letter_tap_emits_on_release(self, processor):
        """Letter key tap emits press+release on key up (buffered)."""
        # Press - buffered, no output yet
        result = processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        assert result == []

        # Release quickly - emits tap
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        assert result == [
            (EV_KEY, KEY_A, 1),
            (EV_KEY, KEY_A, 0),
        ]

    def test_space_key(self, processor):
        """Non-shiftable keys pass through immediately."""
        result = processor.process_event(EV_KEY, KEY_SPACE, 1, timestamp=0.0)
        assert result == [(EV_KEY, KEY_SPACE, 1)]

    def test_non_key_events_pass_through(self, processor):
        """Non-EV_KEY events pass through unchanged."""
        result = processor.process_event(EV_SYN, 0, 0, timestamp=0.0)
        assert result == [(EV_SYN, 0, 0)]


class TestCharacterLongPress:
    """Test long-press any key for shifted version."""

    def test_letter_tap_emits_lowercase(self, processor):
        """Quick letter tap emits lowercase."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        # Tap = lowercase
        assert result == [
            (EV_KEY, KEY_A, 1),
            (EV_KEY, KEY_A, 0),
        ]

    def test_letter_long_press_emits_uppercase(self, processor):
        """Hold letter >400ms emits uppercase (shift injected)."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)

        # Repeat event triggers long-press check
        result = processor.process_event(EV_KEY, KEY_A, 2, timestamp=0.5)
        # Should emit shift+key
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result
        assert (EV_KEY, KEY_A, 1) in result

    def test_letter_long_press_release(self, processor):
        """After long-press, release emits key+shift up."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 2, timestamp=0.5)  # Triggers long-press

        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.6)
        assert result == [
            (EV_KEY, KEY_A, 0),
            (EV_KEY, KEY_LEFTSHIFT, 0),
        ]

    def test_number_long_press_emits_symbol(self, processor):
        """Hold number >400ms emits shifted symbol (e.g., 1 -> !)."""
        processor.process_event(EV_KEY, KEY_1, 1, timestamp=0.0)

        result = processor.process_event(EV_KEY, KEY_1, 2, timestamp=0.5)
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result
        assert (EV_KEY, KEY_1, 1) in result

    def test_punctuation_long_press(self, processor):
        """Hold punctuation >400ms emits shifted version (e.g., - -> _)."""
        processor.process_event(EV_KEY, KEY_MINUS, 1, timestamp=0.0)

        result = processor.process_event(EV_KEY, KEY_MINUS, 2, timestamp=0.5)
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result
        assert (EV_KEY, KEY_MINUS, 1) in result

    def test_long_press_via_check_pending(self, processor):
        """Long-press can be detected via check_pending_events."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)

        result = processor.check_pending_events(timestamp=0.5)
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result
        assert (EV_KEY, KEY_A, 1) in result

    def test_physical_shift_bypasses_buffering(self, processor):
        """With physical shift held, keys emit immediately (no buffering)."""
        # Hold shift
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)

        # Press A - should emit immediately (shift already held)
        result = processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.1)
        assert result == [(EV_KEY, KEY_A, 1)]


class TestShiftTapVsHold:
    """Test tap-vs-hold shift key behavior for sticky shift."""

    def test_sticky_shift_starts_off(self, processor):
        """Sticky shift starts disabled."""
        assert processor.sticky_shift is False

    def test_shift_tap_activates_sticky_shift(self, processor):
        """Quick shift tap (<300ms, no other keys) activates sticky shift."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        assert processor.sticky_shift is False  # Not active yet

        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.2)
        assert processor.sticky_shift is True  # Now active

    def test_shift_hold_does_not_activate_sticky(self, processor):
        """Long shift hold (>300ms) does not activate sticky shift."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.5)
        assert processor.sticky_shift is False

    def test_shift_with_key_press_does_not_activate_sticky(self, processor):
        """Shift + another key does not activate sticky shift."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        # Press A while shift is held (emits immediately due to shift held)
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.1)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.15)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.2)
        assert processor.sticky_shift is False  # Key was pressed during hold

    def test_shift_forwards_events(self, processor):
        """Shift press/release events are forwarded."""
        result = processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        assert result == [(EV_KEY, KEY_LEFTSHIFT, 1)]

        result = processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.2)
        assert result == [(EV_KEY, KEY_LEFTSHIFT, 0)]

    def test_right_shift_also_works(self, processor):
        """Right shift tap also activates sticky shift."""
        processor.process_event(EV_KEY, KEY_RIGHTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_RIGHTSHIFT, 0, timestamp=0.2)
        assert processor.sticky_shift is True

    def test_sticky_shift_applied_to_tap(self, processor):
        """With sticky shift on, letter tap gets shift applied."""
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        # Tap with sticky shift = shifted
        assert result == [
            (EV_KEY, KEY_LEFTSHIFT, 1),
            (EV_KEY, KEY_A, 1),
            (EV_KEY, KEY_A, 0),
            (EV_KEY, KEY_LEFTSHIFT, 0),
        ]

    def test_sticky_shift_consumed_after_one_char(self, processor):
        """Sticky shift is consumed after one character tap."""
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        assert processor.sticky_shift is False  # Consumed


class TestEscapeLongPress:
    """Test escape key long-press detection."""

    def test_escape_tap_emits_escape(self, processor):
        """Quick escape tap (<1s) emits normal escape on release."""
        # Press escape
        result = processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)
        assert result == []  # Buffered, not emitted yet

        # Release escape quickly
        result = processor.process_event(EV_KEY, KEY_ESC, 0, timestamp=0.5)
        # Should emit buffered escape (press + release)
        assert result == [
            (EV_KEY, KEY_ESC, 1),
            (EV_KEY, KEY_ESC, 0),
        ]

    def test_escape_long_press_emits_f24(self, processor):
        """Escape held >1s emits F24 instead of escape."""
        # Press escape
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        # Repeat events trigger long-press check
        result = processor.process_event(EV_KEY, KEY_ESC, 2, timestamp=1.1)
        # Should emit F24 (press + release)
        assert result == [
            (EV_KEY, KEY_F24, 1),
            (EV_KEY, KEY_F24, 0),
        ]

    def test_escape_long_press_no_escape_on_release(self, processor):
        """After long-press F24, no escape emitted on release."""
        # Press escape
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        # Trigger long-press
        processor.process_event(EV_KEY, KEY_ESC, 2, timestamp=1.1)

        # Release escape
        result = processor.process_event(EV_KEY, KEY_ESC, 0, timestamp=1.2)
        assert result == []  # No additional events

    def test_escape_long_press_via_check_pending(self, processor):
        """Long-press can be detected via check_pending_events."""
        # Press escape
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        # Check pending after threshold
        result = processor.check_pending_events(timestamp=1.1)
        assert result == [
            (EV_KEY, KEY_F24, 1),
            (EV_KEY, KEY_F24, 0),
        ]

    def test_escape_long_press_only_fires_once(self, processor):
        """Long-press F24 only fires once per hold."""
        # Press escape
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        # First check - fires
        result = processor.check_pending_events(timestamp=1.1)
        assert len(result) == 2

        # Second check - doesn't fire again
        result = processor.check_pending_events(timestamp=1.2)
        assert result == []


class TestCapsLock:
    """Test caps lock toggle behavior."""

    def test_caps_lock_starts_off(self, processor):
        """Caps lock starts disabled."""
        assert processor.caps_lock is False

    def test_caps_lock_toggles_on(self, processor):
        """Caps lock key toggles caps lock on."""
        result = processor.process_event(EV_KEY, KEY_CAPSLOCK, 1, timestamp=0.0)
        assert processor.caps_lock is True
        # Caps lock IS forwarded
        assert result == [(EV_KEY, KEY_CAPSLOCK, 1)]

    def test_caps_lock_toggles_off(self, processor):
        """Second press toggles caps lock off."""
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 0, timestamp=0.1)
        processor.process_event(EV_KEY, KEY_CAPSLOCK, 1, timestamp=0.2)
        assert processor.caps_lock is False

    def test_caps_lock_affects_letter_tap(self, processor):
        """With caps lock on, letter tap gets shift applied."""
        processor.caps_lock = True
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        # Tap with caps = shifted
        assert result == [
            (EV_KEY, KEY_LEFTSHIFT, 1),
            (EV_KEY, KEY_A, 1),
            (EV_KEY, KEY_A, 0),
            (EV_KEY, KEY_LEFTSHIFT, 0),
        ]


class TestCapsLockStickyShiftXOR:
    """Test XOR behavior between caps lock and sticky shift."""

    def test_both_on_produces_lowercase(self, processor):
        """Caps lock + sticky shift = lowercase (XOR)."""
        processor.caps_lock = True
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        # XOR: both on = lowercase (no shift)
        assert result == [
            (EV_KEY, KEY_A, 1),
            (EV_KEY, KEY_A, 0),
        ]

    def test_only_caps_produces_uppercase(self, processor):
        """Only caps lock = uppercase."""
        processor.caps_lock = True
        processor.sticky_shift = False
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result

    def test_only_sticky_produces_uppercase(self, processor):
        """Only sticky shift = uppercase."""
        processor.caps_lock = False
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result

    def test_neither_produces_lowercase(self, processor):
        """Neither = lowercase."""
        processor.caps_lock = False
        processor.sticky_shift = False
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        # No shift
        assert result == [
            (EV_KEY, KEY_A, 1),
            (EV_KEY, KEY_A, 0),
        ]


class TestPhysicalShiftInteraction:
    """Test interaction with physical shift key."""

    def test_physical_shift_emits_immediately(self, processor):
        """Physical shift held = keys emit immediately (no buffering)."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.1)
        # Immediate emission (shift already held by user)
        assert result == [(EV_KEY, KEY_A, 1)]

    def test_physical_shift_consumes_sticky(self, processor):
        """Physical shift + sticky shift: sticky is consumed but key emits normally."""
        processor.sticky_shift = True
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.1)
        # Sticky was consumed
        assert processor.sticky_shift is False

    def test_right_shift_also_bypasses_buffering(self, processor):
        """Right shift also causes immediate key emission."""
        processor.process_event(EV_KEY, KEY_RIGHTSHIFT, 1, timestamp=0.0)
        result = processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.1)
        assert result == [(EV_KEY, KEY_A, 1)]


class TestExtraKeyRemapping:
    """Test extra key to F-key remapping."""

    def test_media_key_remapped_to_f1(self, processor_with_media_keys):
        """Media key is remapped to F1."""
        result = processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 1, timestamp=0.0)
        assert result == [(EV_KEY, KEY_F1, 1)]

    def test_media_key_up_also_remapped(self, processor_with_media_keys):
        """Key up events are also remapped."""
        processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 1, timestamp=0.0)
        result = processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 0, timestamp=0.1)
        assert result == [(EV_KEY, KEY_F1, 0)]

    def test_media_key_repeat_remapped(self, processor_with_media_keys):
        """Key repeat events are also remapped."""
        processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 1, timestamp=0.0)
        result = processor_with_media_keys.process_event(EV_KEY, MEDIA_KEY_1, 2, timestamp=0.1)
        assert result == [(EV_KEY, KEY_F1, 2)]

    def test_unmapped_keys_pass_through(self, processor_with_media_keys):
        """Keys not in the map pass through."""
        unmapped_key = 999
        result = processor_with_media_keys.process_event(EV_KEY, unmapped_key, 1, timestamp=0.0)
        assert result == [(EV_KEY, unmapped_key, 1)]


class TestHeldKeyTracking:
    """Test held key state tracking."""

    def test_key_down_tracked(self, processor):
        """Key down adds to held_keys."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        assert KEY_A in processor.held_keys

    def test_key_up_removed(self, processor):
        """Key up removes from held_keys."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.1)
        assert KEY_A not in processor.held_keys

    def test_multiple_keys_tracked(self, processor):
        """Multiple keys can be held."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_B, 1, timestamp=0.05)
        assert KEY_A in processor.held_keys
        assert KEY_B in processor.held_keys

    def test_repeat_does_not_affect_tracking(self, processor):
        """Repeat events don't affect held_keys."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_A, 2, timestamp=0.1)
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
        assert state['shift_key_held'] is None
        assert state['escape_buffered'] is False
        assert state['escape_long_press_fired'] is False
        assert state['char_buffered_key'] is None
        assert state['char_long_press_fired'] is False

    def test_state_reflects_char_buffering(self, processor):
        """State reflects character buffering."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        state = processor.state
        assert state['char_buffered_key'] == KEY_A


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

    def test_f24_exists(self):
        """KEY_F24 exists for escape long-press signal."""
        assert KeyCodes.KEY_F24 == 194


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_rapid_shift_tapping(self, processor):
        """Rapid shift tapping works correctly."""
        for i in range(5):
            t = i * 0.3
            processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=t)
            processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=t + 0.1)

        # After 5 taps, sticky should be on (odd number of activations)
        assert processor.sticky_shift is True

    def test_escape_then_other_key_during_buffer(self, processor):
        """Other keys during escape buffer don't break state."""
        # Press escape (buffered)
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

        # Press another key while escape buffered (A is also buffered)
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.1)

        # Release escape - should still emit buffered escape
        result = processor.process_event(EV_KEY, KEY_ESC, 0, timestamp=0.2)
        assert result == [
            (EV_KEY, KEY_ESC, 1),
            (EV_KEY, KEY_ESC, 0),
        ]

    def test_shift_tap_just_under_threshold(self, processor):
        """Shift released just under threshold activates sticky."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.299)
        assert processor.sticky_shift is True

    def test_shift_tap_just_over_threshold(self, processor):
        """Shift released just over threshold does NOT activate sticky."""
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 1, timestamp=0.0)
        processor.process_event(EV_KEY, KEY_LEFTSHIFT, 0, timestamp=0.301)
        assert processor.sticky_shift is False

    def test_escape_long_press_just_under_threshold(self, processor):
        """Escape released just under 1s emits normal escape."""
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)
        result = processor.check_pending_events(timestamp=0.999)
        assert result == []  # Not yet

        result = processor.process_event(EV_KEY, KEY_ESC, 0, timestamp=0.999)
        assert (EV_KEY, KEY_ESC, 1) in result

    def test_escape_long_press_just_over_threshold(self, processor):
        """Escape held just over 1s emits F24."""
        processor.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)
        result = processor.check_pending_events(timestamp=1.001)
        assert result == [
            (EV_KEY, KEY_F24, 1),
            (EV_KEY, KEY_F24, 0),
        ]

    def test_char_long_press_just_under_threshold(self, processor):
        """Character released just under 400ms emits normal tap."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.check_pending_events(timestamp=0.399)
        assert result == []  # Not yet long-press

        result = processor.process_event(EV_KEY, KEY_A, 0, timestamp=0.399)
        # Normal tap
        assert result == [
            (EV_KEY, KEY_A, 1),
            (EV_KEY, KEY_A, 0),
        ]

    def test_char_long_press_just_over_threshold(self, processor):
        """Character held just over 400ms emits shifted version."""
        processor.process_event(EV_KEY, KEY_A, 1, timestamp=0.0)
        result = processor.check_pending_events(timestamp=0.401)
        assert (EV_KEY, KEY_LEFTSHIFT, 1) in result
        assert (EV_KEY, KEY_A, 1) in result

    def test_shiftable_codes_include_all_expected(self):
        """SHIFTABLE_KEY_CODES includes letters, numbers, and punctuation."""
        assert LETTER_KEY_CODES <= SHIFTABLE_KEY_CODES
        assert KEY_1 in SHIFTABLE_KEY_CODES
        assert KEY_MINUS in SHIFTABLE_KEY_CODES
