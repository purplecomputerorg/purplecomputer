"""
Tests for sticky shift behavior in KeyboardStateMachine.

Verifies intention-aware sticky shift:
- Tap shift alone -> sticky activates
- Hold shift + type key -> NO sticky (was used for physical shift)
- Sticky -> A -> Sticky -> NOT a double-tap (interrupted by A)
- Rapid uninterrupted double-tap -> caps lock toggle
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.keyboard import KeyboardStateMachine, CharacterAction, ShiftAction, CapsLockAction
from purple_tui.input import RawKeyEvent, KeyCode


# Base offset so timestamps are never 0.0 (which is falsy in Python,
# and the state machine uses `if press_time` checks)
T = 100.0


def shift_down(t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=KeyCode.KEY_LEFTSHIFT, is_down=True, timestamp=T + t)


def shift_up(t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=KeyCode.KEY_LEFTSHIFT, is_down=False, timestamp=T + t)


def key_down(keycode: int, t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=keycode, is_down=True, timestamp=T + t)


def key_up(keycode: int, t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=keycode, is_down=False, timestamp=T + t)


def has_action(actions, action_type):
    return any(isinstance(a, action_type) for a in actions)


def get_action(actions, action_type):
    for a in actions:
        if isinstance(a, action_type):
            return a
    return None


class TestStickyShiftActivation:
    """Tap shift alone -> sticky activates."""

    def test_quick_tap_activates_sticky(self):
        sm = KeyboardStateMachine()
        sticky_changes = []
        sm.on_sticky_shift_change(lambda active: sticky_changes.append(active))

        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))  # Quick tap (< 0.3s)

        assert sticky_changes == [True]
        assert sm._sticky_shift_active is True

    def test_slow_hold_does_not_activate_sticky(self):
        sm = KeyboardStateMachine()
        sticky_changes = []
        sm.on_sticky_shift_change(lambda active: sticky_changes.append(active))

        sm.process(shift_down(0.0))
        sm.process(shift_up(0.5))  # Slow release (>= 0.3s)

        assert sticky_changes == []
        assert sm._sticky_shift_active is False

    def test_sticky_shift_applies_to_next_character(self):
        sm = KeyboardStateMachine()

        # Tap shift
        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))

        # Type 'a' -> should be 'A'
        actions = sm.process(key_down(KeyCode.KEY_A, 0.5))
        char = get_action(actions, CharacterAction)
        assert char is not None
        assert char.char == 'A'

    def test_sticky_consumed_after_one_character(self):
        sm = KeyboardStateMachine()

        # Tap shift
        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))

        # Type 'a' -> 'A' (consumes sticky)
        sm.process(key_down(KeyCode.KEY_A, 0.5))
        sm.process(key_up(KeyCode.KEY_A, 0.55))

        # Type 'b' -> should be lowercase 'b'
        actions = sm.process(key_down(KeyCode.KEY_B, 0.7))
        char = get_action(actions, CharacterAction)
        assert char is not None
        assert char.char == 'b'


class TestHoldShiftNoSticky:
    """Hold shift + type key -> NO sticky activation."""

    def test_hold_shift_and_type_no_sticky(self):
        sm = KeyboardStateMachine()
        sticky_changes = []
        sm.on_sticky_shift_change(lambda active: sticky_changes.append(active))

        # Hold shift
        sm.process(shift_down(0.0))
        # Type 'a' while shift held -> 'A' via physical shift
        actions = sm.process(key_down(KeyCode.KEY_A, 0.05))
        char = get_action(actions, CharacterAction)
        assert char.char == 'A'
        assert char.shift_held is True

        # Release key, then release shift quickly
        sm.process(key_up(KeyCode.KEY_A, 0.08))
        sm.process(shift_up(0.1))

        # Sticky should NOT have activated
        assert sticky_changes == []
        assert sm._sticky_shift_active is False

    def test_hold_shift_type_multiple_no_sticky(self):
        sm = KeyboardStateMachine()
        sticky_changes = []
        sm.on_sticky_shift_change(lambda active: sticky_changes.append(active))

        sm.process(shift_down(0.0))
        sm.process(key_down(KeyCode.KEY_A, 0.05))
        sm.process(key_up(KeyCode.KEY_A, 0.08))
        sm.process(key_down(KeyCode.KEY_B, 0.10))
        sm.process(key_up(KeyCode.KEY_B, 0.13))
        sm.process(shift_up(0.15))

        assert sticky_changes == []
        assert sm._sticky_shift_active is False


class TestDoubleTapInterruption:
    """Double-tap shift requires uninterrupted consecutive taps."""

    def test_uninterrupted_double_tap_toggles_caps(self):
        sm = KeyboardStateMachine()

        # First tap
        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))
        assert sm._sticky_shift_active is True

        # Second tap immediately (no keys in between)
        sm.process(shift_down(0.2))
        actions = sm.process(shift_up(0.3))

        assert has_action(actions, CapsLockAction)
        assert sm._caps_lock_on is True
        # Sticky should be cleared when caps lock activates
        assert sm._sticky_shift_active is False

    def test_interrupted_double_tap_does_not_toggle_caps(self):
        """Sticky shift -> A -> Sticky shift should NOT be a double-tap."""
        sm = KeyboardStateMachine()
        sticky_changes = []
        sm.on_sticky_shift_change(lambda active: sticky_changes.append(active))

        # First tap: activates sticky
        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))
        assert sm._sticky_shift_active is True

        # Type 'A' (interrupts the double-tap sequence)
        sm.process(key_down(KeyCode.KEY_A, 0.2))
        sm.process(key_up(KeyCode.KEY_A, 0.25))

        # Second tap: should be a NEW sticky, NOT caps lock
        sm.process(shift_down(0.3))
        actions = sm.process(shift_up(0.4))

        assert not has_action(actions, CapsLockAction)
        assert sm._caps_lock_on is False
        # Should have activated sticky again
        assert sm._sticky_shift_active is True

    def test_interrupted_by_enter_no_double_tap(self):
        """Shift tap -> Enter -> Shift tap should not be double-tap."""
        sm = KeyboardStateMachine()

        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))

        # Enter interrupts
        sm.process(key_down(KeyCode.KEY_ENTER, 0.2))
        sm.process(key_up(KeyCode.KEY_ENTER, 0.25))

        sm.process(shift_down(0.3))
        actions = sm.process(shift_up(0.4))

        assert not has_action(actions, CapsLockAction)
        assert sm._caps_lock_on is False

    def test_interrupted_by_backspace_no_double_tap(self):
        """Shift tap -> Backspace -> Shift tap should not be double-tap."""
        sm = KeyboardStateMachine()

        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))

        sm.process(key_down(KeyCode.KEY_BACKSPACE, 0.2))
        sm.process(key_up(KeyCode.KEY_BACKSPACE, 0.25))

        sm.process(shift_down(0.3))
        actions = sm.process(shift_up(0.4))

        assert not has_action(actions, CapsLockAction)
        assert sm._caps_lock_on is False

    def test_interrupted_by_arrow_no_double_tap(self):
        """Shift tap -> Arrow -> Shift tap should not be double-tap."""
        sm = KeyboardStateMachine()

        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))

        sm.process(key_down(KeyCode.KEY_LEFT, 0.2))
        sm.process(key_up(KeyCode.KEY_LEFT, 0.25))

        sm.process(shift_down(0.3))
        actions = sm.process(shift_up(0.4))

        assert not has_action(actions, CapsLockAction)
        assert sm._caps_lock_on is False

    def test_interrupted_by_space_no_double_tap(self):
        """Shift tap -> Space -> Shift tap should not be double-tap."""
        sm = KeyboardStateMachine()

        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))

        sm.process(key_down(KeyCode.KEY_SPACE, 0.2))
        sm.process(key_up(KeyCode.KEY_SPACE, 0.25))

        sm.process(shift_down(0.3))
        actions = sm.process(shift_up(0.4))

        assert not has_action(actions, CapsLockAction)
        assert sm._caps_lock_on is False


class TestStickyIntentionSequences:
    """Real-world typing sequences to verify intention detection."""

    def test_capitalize_two_words(self):
        """Tap shift -> type H -> ... -> tap shift -> type W -> ..."""
        sm = KeyboardStateMachine()

        # Sticky for 'H'
        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))
        actions = sm.process(key_down(KeyCode.KEY_H, 0.3))
        assert get_action(actions, CharacterAction).char == 'H'
        sm.process(key_up(KeyCode.KEY_H, 0.35))

        # Type 'i'
        actions = sm.process(key_down(KeyCode.KEY_I, 0.4))
        assert get_action(actions, CharacterAction).char == 'i'
        sm.process(key_up(KeyCode.KEY_I, 0.45))

        # Sticky for 'W'
        sm.process(shift_down(1.0))
        sm.process(shift_up(1.1))
        actions = sm.process(key_down(KeyCode.KEY_W, 1.3))
        assert get_action(actions, CharacterAction).char == 'W'
        sm.process(key_up(KeyCode.KEY_W, 1.35))

        # No caps lock should have been triggered
        assert sm._caps_lock_on is False

    def test_sticky_then_cancel_with_second_tap(self):
        """Tap shift (sticky on) -> tap shift again immediately (sticky off, NOT caps lock).

        Wait, actually: two quick uninterrupted taps = caps lock toggle.
        This is the intended behavior: double-tap is caps lock.
        """
        sm = KeyboardStateMachine()

        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))
        assert sm._sticky_shift_active is True

        sm.process(shift_down(0.2))
        sm.process(shift_up(0.3))
        assert sm._caps_lock_on is True

    def test_three_sticky_taps_with_chars_between(self):
        """Shift -> A -> Shift -> B -> Shift -> C. Each should capitalize, no caps lock."""
        sm = KeyboardStateMachine()

        for i, key in enumerate([KeyCode.KEY_A, KeyCode.KEY_B, KeyCode.KEY_C]):
            base_t = i * 1.0

            # Tap shift
            sm.process(shift_down(base_t))
            sm.process(shift_up(base_t + 0.1))

            # Type character
            actions = sm.process(key_down(key, base_t + 0.3))
            char = get_action(actions, CharacterAction)
            assert char.char == chr(ord('A') + i), f"Expected {chr(ord('A') + i)}, got {char.char}"
            sm.process(key_up(key, base_t + 0.35))

        assert sm._caps_lock_on is False

    def test_right_shift_same_behavior(self):
        """Right shift should behave identically to left shift for sticky."""
        sm = KeyboardStateMachine()

        # Tap right shift
        sm.process(RawKeyEvent(keycode=KeyCode.KEY_RIGHTSHIFT, is_down=True, timestamp=T))
        sm.process(RawKeyEvent(keycode=KeyCode.KEY_RIGHTSHIFT, is_down=False, timestamp=T + 0.1))

        assert sm._sticky_shift_active is True

        # Type 'a' -> 'A'
        actions = sm.process(key_down(KeyCode.KEY_A, 0.3))
        assert get_action(actions, CharacterAction).char == 'A'

    def test_repeat_events_dont_trigger_sticky(self):
        """Key repeat events from held shift shouldn't interfere."""
        sm = KeyboardStateMachine()
        sticky_changes = []
        sm.on_sticky_shift_change(lambda active: sticky_changes.append(active))

        # Press shift
        sm.process(shift_down(0.0))
        # Repeat events (from OS auto-repeat)
        sm.process(RawKeyEvent(keycode=KeyCode.KEY_LEFTSHIFT, is_down=True, timestamp=T + 0.5, is_repeat=True))
        sm.process(RawKeyEvent(keycode=KeyCode.KEY_LEFTSHIFT, is_down=True, timestamp=T + 0.6, is_repeat=True))
        # Release after long hold
        sm.process(shift_up(0.8))

        # Should NOT activate sticky (hold was > 0.3s from press to release)
        assert sticky_changes == []

    def test_double_tap_caps_then_undo(self):
        """Double-tap for caps lock, then double-tap again to turn off."""
        sm = KeyboardStateMachine()

        # Double-tap on
        sm.process(shift_down(0.0))
        sm.process(shift_up(0.1))
        sm.process(shift_down(0.2))
        sm.process(shift_up(0.3))
        assert sm._caps_lock_on is True

        # Type some chars to clear any state
        sm.process(key_down(KeyCode.KEY_A, 0.5))
        sm.process(key_up(KeyCode.KEY_A, 0.55))

        # Double-tap off
        sm.process(shift_down(1.0))
        sm.process(shift_up(1.1))
        sm.process(shift_down(1.2))
        sm.process(shift_up(1.3))
        assert sm._caps_lock_on is False
