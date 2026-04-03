"""
Tests for backslash hold behavior in KeyboardStateMachine.

Holding the backslash key for 3 seconds opens the parent menu.
This is an alternative to the escape long-hold for keyboards where
escape/backtick may not work reliably (e.g., some Mac laptops).
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.keyboard import KeyboardStateMachine, CharacterAction
from purple_tui.input import RawKeyEvent, KeyCode

# Base offset so timestamps are never 0.0 (which is falsy in Python)
T = 100.0


def backslash_down(t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=KeyCode.KEY_BACKSLASH, is_down=True, timestamp=T + t)


def backslash_up(t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=KeyCode.KEY_BACKSLASH, is_down=False, timestamp=T + t)


def backslash_repeat(t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=KeyCode.KEY_BACKSLASH, is_down=True, timestamp=T + t, is_repeat=True)


def key_down(keycode: int, t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=keycode, is_down=True, timestamp=T + t)


class TestBackslashHoldTracking:
    """Backslash press starts tracking for parent menu."""

    def test_press_starts_tracking(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))
        assert sm._backslash_press_time is not None

    def test_release_clears_tracking(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))
        sm.process(backslash_up(0.5))
        assert sm._backslash_press_time is None
        assert sm._backslash_hold_triggered is False

    def test_repeat_does_not_restart_tracking(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))
        start = sm._backslash_press_time
        sm.process(backslash_repeat(0.5))
        assert sm._backslash_press_time == start


class TestBackslashHoldCheck:
    """check_backslash_hold() fires after threshold."""

    def test_fires_after_threshold(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))

        with patch('purple_tui.keyboard.time') as mock_time:
            mock_time.time.return_value = sm._backslash_press_time + 3.1
            assert sm.check_backslash_hold() is True

    def test_does_not_fire_before_threshold(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))

        with patch('purple_tui.keyboard.time') as mock_time:
            mock_time.time.return_value = sm._backslash_press_time + 1.0
            assert sm.check_backslash_hold() is False

    def test_fires_only_once(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))

        with patch('purple_tui.keyboard.time') as mock_time:
            mock_time.time.return_value = sm._backslash_press_time + 3.1
            assert sm.check_backslash_hold() is True
            assert sm.check_backslash_hold() is False

    def test_does_not_fire_if_released_early(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))
        sm.process(backslash_up(0.5))
        assert sm.check_backslash_hold() is False

    def test_repress_restarts_tracking(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))
        sm.process(backslash_up(0.5))

        sm.process(backslash_down(1.0))
        assert sm._backslash_press_time is not None
        assert sm._backslash_hold_triggered is False

        with patch('purple_tui.keyboard.time') as mock_time:
            mock_time.time.return_value = sm._backslash_press_time + 3.1
            assert sm.check_backslash_hold() is True


class TestBackslashHoldProperty:
    """backslash_held property."""

    def test_false_when_not_pressed(self):
        sm = KeyboardStateMachine()
        assert sm.backslash_held is False

    def test_true_when_pressed(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))
        assert sm.backslash_held is True

    def test_false_after_released(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))
        sm.process(backslash_up(0.5))
        assert sm.backslash_held is False


class TestBackslashStillTypesCharacter:
    """Backslash still produces a character action (short press)."""

    def test_short_press_produces_character(self):
        sm = KeyboardStateMachine()
        actions = sm.process(backslash_down(0.0))
        chars = [a for a in actions if isinstance(a, CharacterAction)]
        assert len(chars) == 1
        assert chars[0].char == '\\'
