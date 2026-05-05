"""
Tests for InputFloodGuard

Pure logic tests with injected timestamps for deterministic behavior.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.keyboard import (
    InputFloodGuard,
    CharacterAction, NavigationAction, ControlAction,
    ShiftAction, RoomAction, LongHoldAction,
)


class TestInputFloodGuard:
    """Tests for the InputFloodGuard class."""

    def test_first_action_allowed(self):
        """First action should pass when burst is available."""
        guard = InputFloodGuard()
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is False

    def test_burst_allows_initial_flood(self):
        """All actions within burst count should pass at the same timestamp."""
        guard = InputFloodGuard(burst=5)
        for i in range(5):
            assert guard.should_drop(CharacterAction(char=chr(ord('a') + i)), timestamp=0.0) is False

    def test_drops_after_burst_exhausted(self):
        """Action beyond burst at same timestamp should be dropped."""
        guard = InputFloodGuard(burst=5)
        for i in range(5):
            guard.should_drop(CharacterAction(char=chr(ord('a') + i)), timestamp=0.0)
        assert guard.should_drop(CharacterAction(char='z'), timestamp=0.0) is True

    def test_sustained_rate_passes(self):
        """Actions spaced at the rate limit should all pass."""
        guard = InputFloodGuard(rate=15.0, burst=5)
        # Use integer milliseconds to avoid float rounding issues
        # 15 actions/sec = 1 action per 67ms
        for i in range(5):
            guard.should_drop(CharacterAction(char='a'), timestamp=0.0)
        # Now at 0 tokens; each 67ms should refill ~1.005 tokens (enough)
        for i in range(1, 21):
            assert guard.should_drop(
                CharacterAction(char='a'), timestamp=i * 0.067,
            ) is False

    def test_rapid_flood_drops_excess(self):
        """20 actions in 0.1s: first 5 pass (burst), rest dropped."""
        guard = InputFloodGuard(rate=15.0, burst=5)
        passed = 0
        for i in range(20):
            if not guard.should_drop(CharacterAction(char='a'), timestamp=i * 0.005):
                passed += 1
        assert passed == 6  # 5 burst + ~1 from refill over 0.1s

    def test_navigation_action_throttled(self):
        """NavigationAction is subject to the same rate limiting."""
        guard = InputFloodGuard(burst=2)
        assert guard.should_drop(NavigationAction(direction='up'), timestamp=0.0) is False
        assert guard.should_drop(NavigationAction(direction='down'), timestamp=0.0) is False
        assert guard.should_drop(NavigationAction(direction='left'), timestamp=0.0) is True

    def test_never_drops_control_action(self):
        """ControlAction should never be dropped."""
        guard = InputFloodGuard(burst=0)
        assert guard.should_drop(ControlAction(action='backspace'), timestamp=0.0) is False
        assert guard.should_drop(ControlAction(action='enter'), timestamp=0.0) is False
        assert guard.should_drop(ControlAction(action='space'), timestamp=0.0) is False
        assert guard.should_drop(ControlAction(action='escape'), timestamp=0.0) is False

    def test_never_drops_shift_action(self):
        """ShiftAction should never be dropped."""
        guard = InputFloodGuard(burst=0)
        assert guard.should_drop(ShiftAction(is_down=True), timestamp=0.0) is False
        assert guard.should_drop(ShiftAction(is_down=False), timestamp=0.0) is False

    def test_never_drops_room_action(self):
        """RoomAction should never be dropped."""
        guard = InputFloodGuard(burst=0)
        assert guard.should_drop(RoomAction(room='parent'), timestamp=0.0) is False

    def test_never_drops_long_hold_action(self):
        """LongHoldAction should never be dropped."""
        guard = InputFloodGuard(burst=0)
        assert guard.should_drop(LongHoldAction(key='escape'), timestamp=0.0) is False

    def test_tokens_refill_over_time(self):
        """After exhausting burst, waiting should refill tokens."""
        guard = InputFloodGuard(rate=15.0, burst=5)
        # Exhaust burst
        for i in range(5):
            guard.should_drop(CharacterAction(char='a'), timestamp=0.0)
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is True
        # Wait 1 second (15 tokens refill, capped at burst=5)
        assert guard.should_drop(CharacterAction(char='a'), timestamp=1.0) is False

    def test_tokens_cap_at_burst(self):
        """Tokens should not accumulate beyond burst even after long idle."""
        guard = InputFloodGuard(rate=15.0, burst=5)
        # Wait 10 seconds (would be 150 tokens uncapped)
        for i in range(5):
            assert guard.should_drop(CharacterAction(char='a'), timestamp=10.0) is False
        assert guard.should_drop(CharacterAction(char='a'), timestamp=10.0) is True

    def test_reset_refills_bucket(self):
        """Reset should restore full burst allowance."""
        guard = InputFloodGuard(burst=3)
        for i in range(3):
            guard.should_drop(CharacterAction(char='a'), timestamp=0.0)
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is True
        guard.reset()
        assert guard.should_drop(CharacterAction(char='a'), timestamp=1.0) is False

    def test_partial_token_refill(self):
        """After exhaustion, waiting for exactly one token interval allows one action."""
        guard = InputFloodGuard(rate=15.0, burst=1)
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is False
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is True
        # Wait 1/15 second = one token
        t = 1.0 / 15.0
        assert guard.should_drop(CharacterAction(char='a'), timestamp=t) is False
        assert guard.should_drop(CharacterAction(char='a'), timestamp=t) is True


class TestInputFloodGuardEdgeCases:
    """Edge case tests for InputFloodGuard."""

    def test_interleaved_throttled_and_unthrottled(self):
        """Unthrottled actions pass even when bucket is empty."""
        guard = InputFloodGuard(burst=2)
        guard.should_drop(CharacterAction(char='a'), timestamp=0.0)
        guard.should_drop(CharacterAction(char='b'), timestamp=0.0)
        # Bucket empty
        assert guard.should_drop(CharacterAction(char='c'), timestamp=0.0) is True
        # But control actions still pass
        assert guard.should_drop(ControlAction(action='enter'), timestamp=0.0) is False

    def test_unthrottled_actions_dont_consume_tokens(self):
        """ControlAction should not consume tokens from the bucket."""
        guard = InputFloodGuard(burst=2)
        # Send many control actions
        for _ in range(10):
            guard.should_drop(ControlAction(action='enter'), timestamp=0.0)
        # Bucket should still have 2 tokens for character actions
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is False
        assert guard.should_drop(CharacterAction(char='b'), timestamp=0.0) is False

    def test_zero_burst_drops_immediately(self):
        """With burst=0, the first character action is dropped."""
        guard = InputFloodGuard(burst=0)
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is True

    def test_mixed_character_and_navigation(self):
        """Character and navigation actions share the same token bucket."""
        guard = InputFloodGuard(burst=3)
        assert guard.should_drop(CharacterAction(char='a'), timestamp=0.0) is False
        assert guard.should_drop(NavigationAction(direction='up'), timestamp=0.0) is False
        assert guard.should_drop(CharacterAction(char='b'), timestamp=0.0) is False
        assert guard.should_drop(NavigationAction(direction='down'), timestamp=0.0) is True
