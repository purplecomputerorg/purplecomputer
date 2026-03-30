"""
Tests for HoldOrTap

Pure logic tests. Timer is faked via a mock set_timer function.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.keyboard import HoldOrTap


class FakeTimer:
    """Fake Textual timer for testing."""

    def __init__(self, callback):
        self.callback = callback
        self.stopped = False

    def stop(self):
        self.stopped = True

    def fire(self):
        """Simulate the timer firing."""
        if not self.stopped:
            self.callback()


def make_hold(hold_seconds=0.5):
    """Create a HoldOrTap with a fake set_timer that captures the timer."""
    hold = HoldOrTap(hold_seconds=hold_seconds)
    timers = []

    def fake_set_timer(seconds, callback):
        timer = FakeTimer(callback)
        timers.append(timer)
        return timer

    return hold, fake_set_timer, timers


class TestHoldOrTapBasics:
    def test_tap_returns_true_on_up(self):
        """Quick press and release (no timer fire) is a tap."""
        hold, set_timer, timers = make_hold()
        hold.on_down(set_timer, lambda: None)
        assert hold.on_up() is True

    def test_hold_returns_false_on_up(self):
        """Hold (timer fires before release) is not a tap."""
        hold, set_timer, timers = make_hold()
        hold_fired = []
        hold.on_down(set_timer, lambda: hold_fired.append(True))
        timers[0].fire()
        assert len(hold_fired) == 1
        assert hold.on_up() is False

    def test_on_up_without_on_down_returns_false(self):
        """Release without a prior press is not a tap."""
        hold, _, _ = make_hold()
        assert hold.on_up() is False


class TestOtherKeyFlush:
    """The critical fix: another key while pending flushes the tap."""

    def test_other_key_while_pending_returns_true(self):
        """Pressing another key while space is pending flushes the tap."""
        hold, set_timer, timers = make_hold()
        hold.on_down(set_timer, lambda: None)
        assert hold.on_other_key() is True

    def test_other_key_cancels_timer(self):
        """Flushing via other key stops the hold timer."""
        hold, set_timer, timers = make_hold()
        hold.on_down(set_timer, lambda: None)
        hold.on_other_key()
        assert timers[0].stopped is True

    def test_other_key_after_hold_fired_returns_false(self):
        """If hold already fired, other key doesn't flush a tap."""
        hold, set_timer, timers = make_hold()
        hold.on_down(set_timer, lambda: None)
        timers[0].fire()
        assert hold.on_other_key() is False

    def test_other_key_when_not_pending_returns_false(self):
        """Other key when no space is pending does nothing."""
        hold, _, _ = make_hold()
        assert hold.on_other_key() is False

    def test_other_key_then_up_does_not_double_tap(self):
        """After flush via other key, key-up should not also return tap."""
        hold, set_timer, timers = make_hold()
        hold.on_down(set_timer, lambda: None)
        assert hold.on_other_key() is True  # Flushed
        assert hold.on_up() is False  # Already flushed, not a second tap

    def test_fast_typing_sequence(self):
        """Simulate typing "left 10" fast: space down, '1' down, space up.

        Before the fix, space would arrive after '1'. Now it flushes before.
        """
        hold, set_timer, timers = make_hold()
        events = []

        # Space down
        hold.on_down(set_timer, lambda: events.append("hold"))

        # '1' pressed before space released
        if hold.on_other_key():
            events.append("space_flushed")
        events.append("char_1")

        # Space up
        if hold.on_up():
            events.append("space_tap")  # Should NOT happen

        assert events == ["space_flushed", "char_1"]


class TestIsPending:
    def test_pending_after_down(self):
        hold, set_timer, _ = make_hold()
        hold.on_down(set_timer, lambda: None)
        assert hold.is_pending is True

    def test_not_pending_after_up(self):
        hold, set_timer, _ = make_hold()
        hold.on_down(set_timer, lambda: None)
        hold.on_up()
        assert hold.is_pending is False

    def test_not_pending_after_hold_fires(self):
        hold, set_timer, timers = make_hold()
        hold.on_down(set_timer, lambda: None)
        timers[0].fire()
        assert hold.is_pending is False

    def test_not_pending_after_other_key_flush(self):
        hold, set_timer, _ = make_hold()
        hold.on_down(set_timer, lambda: None)
        hold.on_other_key()
        assert hold.is_pending is False


class TestReuse:
    """HoldOrTap should work correctly across multiple press cycles."""

    def test_tap_then_hold(self):
        hold, set_timer, timers = make_hold()

        # First: tap
        hold.on_down(set_timer, lambda: None)
        assert hold.on_up() is True

        # Second: hold
        fired = []
        hold.on_down(set_timer, lambda: fired.append(True))
        timers[1].fire()
        assert len(fired) == 1
        assert hold.on_up() is False

    def test_flush_then_tap(self):
        hold, set_timer, timers = make_hold()

        # First: flush via other key
        hold.on_down(set_timer, lambda: None)
        assert hold.on_other_key() is True

        # Second: normal tap
        hold.on_down(set_timer, lambda: None)
        assert hold.on_up() is True
