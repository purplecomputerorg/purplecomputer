"""
Tests for backslash hold behavior in KeyboardStateMachine.

Holding the backslash key (or Esc) alone for 3 seconds opens the parent menu.
This is an alternative to the escape long-hold for keyboards where
escape/backtick may not work reliably (e.g., some Mac laptops).
"""

import sys
from pathlib import Path
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from purplecomputer.keyboard import KeyboardStateMachine, CharacterAction
from purplecomputer.input import RawKeyEvent, KeyCode

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

        with patch('purplecomputer.keyboard.time') as mock_time:
            mock_time.time.return_value = sm._backslash_press_time + 3.1
            assert sm.check_backslash_hold() is True

    def test_does_not_fire_before_threshold(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))

        with patch('purplecomputer.keyboard.time') as mock_time:
            mock_time.time.return_value = sm._backslash_press_time + 1.0
            assert sm.check_backslash_hold() is False

    def test_fires_only_once(self):
        sm = KeyboardStateMachine()
        sm.process(backslash_down(0.0))

        with patch('purplecomputer.keyboard.time') as mock_time:
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

        with patch('purplecomputer.keyboard.time') as mock_time:
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


def esc_down(t: float) -> RawKeyEvent:
    return RawKeyEvent(keycode=KeyCode.KEY_ESC, is_down=True, timestamp=T + t)


def _after_hold(sm, check, since):
    with patch('purplecomputer.keyboard.time') as mock_time:
        mock_time.time.return_value = since + 3.1
        return check()


class TestGrownupHoldsAreOneKeyAlone:
    """Esc and backslash open the parent menu only when held by themselves, so a leaning hand or mashing can't."""

    def test_esc_alone_fires(self):
        sm = KeyboardStateMachine()
        sm.process(esc_down(0.0))
        assert _after_hold(sm, sm.check_escape_hold, sm._escape_press_time) is True

    def test_esc_does_not_fire_before_three_seconds(self):
        sm = KeyboardStateMachine()
        sm.process(esc_down(0.0))
        with patch('purplecomputer.keyboard.time') as mock_time:
            mock_time.time.return_value = sm._escape_press_time + 1.5
            assert sm.check_escape_hold() is False

    def test_another_key_during_the_hold_cancels_it(self):
        for down, check, since in ((esc_down, "check_escape_hold", "_escape_press_time"),
                                   (backslash_down, "check_backslash_hold", "_backslash_press_time")):
            sm = KeyboardStateMachine()
            sm.process(down(0.0))
            start = getattr(sm, since)
            sm.process(key_down(KeyCode.KEY_A, 1.0))
            assert getattr(sm, since) is None
            assert _after_hold(sm, getattr(sm, check), start) is False

    def test_a_hand_landing_just_before_does_not_start_it(self):
        sm = KeyboardStateMachine()
        sm.process(key_down(KeyCode.KEY_A, 0.0))
        sm.process(esc_down(0.1))
        assert sm._escape_press_time is None

    def test_an_old_stuck_key_does_not_block_it(self):
        sm = KeyboardStateMachine()
        sm.process(key_down(KeyCode.KEY_A, 0.0))   # its release never arrived
        sm.process(esc_down(30.0))
        assert _after_hold(sm, sm.check_escape_hold, sm._escape_press_time) is True


def test_a_grownup_hold_shows_its_bar_only_after_a_kids_press_and_leaves_no_hint():
    import asyncio
    from types import SimpleNamespace
    from purplecomputer.harness import make_app, run

    async def go():
        app = make_app()
        await app._handle_raw_key_event(RawKeyEvent(keycode=KeyCode.KEY_ESC, is_down=True, timestamp=time.monotonic()))
        assert app.hold_progress()[0] == 0 and app._hold_bar() is None, "no bar during a kid's press"
        app._keyboard_state_machine._escape_press_time -= 2.25
        fraction, label, _ = app.hold_progress()
        assert 0.4 < fraction < 0.6 and label.endswith("Parent Menu") and app._hold_bar() is not None
        assert app._grownup_ring is not None
        await app._handle_raw_key_event(RawKeyEvent(keycode=KeyCode.KEY_ESC, is_down=False, timestamp=time.monotonic()))
        await asyncio.sleep(0.1)
        assert app.hold_progress() is None and app._hold_nudge is None and app._grownup_ring is None

        app._power_button_reader = SimpleNamespace(held_since=time.time() - 2.25, hold_seconds=3)
        fraction, label, _ = app.hold_progress()
        assert label.endswith("Turning off") and 0.4 < fraction < 0.6
    run(go())


def test_the_grownup_bar_shows_over_the_room_picker():
    from purplecomputer.harness import make_app, run
    from purplecomputer import palette as P

    async def go():
        app = make_app()
        app._show_room_picker()
        await app._handle_raw_key_event(RawKeyEvent(keycode=KeyCode.KEY_ESC, is_down=True, timestamp=time.monotonic()))
        app._keyboard_state_machine._escape_press_time -= 2.25
        app._draw()
        strip = app._hold_bar()[0]
        assert tuple(app.g.surface.get_at((strip.x + 2, strip.centery)))[:3] == P.rgb(P.SURFACE)[:3]
    run(go())
