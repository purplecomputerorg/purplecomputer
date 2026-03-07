"""Tests for Play Mode session recording and replay.

Run with: pytest tests/test_play_session.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from purple_tui.play_session import (
    PlaySession,
    SESSION_TIMEOUT,
    LONG_PAUSE_THRESHOLD,
    MODE_MUSIC,
    MODE_LETTERS,
)


# =============================================================================
# Recording
# =============================================================================

class TestRecording:
    """Test basic event recording."""

    def test_record_single_event(self):
        s = PlaySession()
        s.record('A', now=1.0)
        assert s.has_events()

    def test_empty_session(self):
        s = PlaySession()
        assert not s.has_events()
        assert s.get_replay() == []

    def test_single_event_replay(self):
        s = PlaySession()
        s.record('A', now=1.0)
        assert s.get_replay() == [('A', MODE_MUSIC, 0.0)]

    def test_multiple_events_timing(self):
        s = PlaySession()
        s.record('A', now=1.0)
        s.record('B', now=1.5)
        s.record('C', now=2.0)
        assert s.get_replay() == [
            ('A', MODE_MUSIC, 0.0),
            ('B', MODE_MUSIC, 0.5),
            ('C', MODE_MUSIC, 0.5),
        ]

    def test_preserves_event_order(self):
        s = PlaySession()
        s.record('Z', now=0.0)
        s.record('A', now=0.1)
        s.record('M', now=0.2)
        keys = [key for key, _, _ in s.get_replay()]
        assert keys == ['Z', 'A', 'M']

    def test_rapid_keypresses(self):
        s = PlaySession()
        s.record('A', now=0.0)
        s.record('B', now=0.01)
        s.record('C', now=0.02)
        replay = s.get_replay()
        assert replay[1][2] == pytest.approx(0.01)
        assert replay[2][2] == pytest.approx(0.01)

    def test_same_key_repeated(self):
        s = PlaySession()
        s.record('A', now=0.0)
        s.record('A', now=0.5)
        s.record('A', now=1.0)
        assert s.get_replay() == [
            ('A', MODE_MUSIC, 0.0),
            ('A', MODE_MUSIC, 0.5),
            ('A', MODE_MUSIC, 0.5),
        ]

    def test_default_submode_is_music(self):
        s = PlaySession()
        s.record('A', now=1.0)
        _, submode, _ = s.get_replay()[0]
        assert submode == MODE_MUSIC


# =============================================================================
# Sub-mode recording
# =============================================================================

class TestSubmodeRecording:
    """Test that sub-mode is preserved per event."""

    def test_record_with_letters_submode(self):
        s = PlaySession()
        s.record('A', MODE_LETTERS, now=1.0)
        assert s.get_replay() == [('A', MODE_LETTERS, 0.0)]

    def test_mixed_submodes(self):
        """Session can contain events from both sub-modes."""
        s = PlaySession()
        s.record('A', MODE_MUSIC, now=1.0)
        s.record('B', MODE_LETTERS, now=1.5)
        s.record('C', MODE_MUSIC, now=2.0)
        replay = s.get_replay()
        assert replay[0] == ('A', MODE_MUSIC, 0.0)
        assert replay[1] == ('B', MODE_LETTERS, 0.5)
        assert replay[2] == ('C', MODE_MUSIC, 0.5)

    def test_submode_preserved_across_timeout_boundary(self):
        """After timeout reset, submode of new events is still recorded."""
        s = PlaySession()
        s.record('A', MODE_MUSIC, now=0.0)
        s.record('B', MODE_LETTERS, now=SESSION_TIMEOUT + 1)
        replay = s.get_replay()
        assert replay == [('B', MODE_LETTERS, 0.0)]

    def test_numbers_in_letters_mode(self):
        """Non-letter keys in letters mode still record as letters submode."""
        s = PlaySession()
        s.record('5', MODE_LETTERS, now=1.0)
        assert s.get_replay() == [('5', MODE_LETTERS, 0.0)]


# =============================================================================
# Session timeout
# =============================================================================

class TestSessionTimeout:
    """Test the 30-second session timeout."""

    def test_timeout_clears_old_events(self):
        s = PlaySession()
        s.record('A', now=1.0)
        s.record('B', now=1.5)
        # More than SESSION_TIMEOUT later
        s.record('C', now=1.5 + SESSION_TIMEOUT + 1)
        assert s.get_replay() == [('C', MODE_MUSIC, 0.0)]

    def test_within_timeout_preserves(self):
        s = PlaySession()
        s.record('A', now=1.0)
        # Exactly at boundary (gap == 30.0, not > 30.0)
        s.record('B', now=1.0 + SESSION_TIMEOUT)
        assert len(s.get_replay()) == 2

    def test_just_over_timeout(self):
        s = PlaySession()
        s.record('A', now=1.0)
        s.record('B', now=1.0 + SESSION_TIMEOUT + 0.001)
        assert s.get_replay() == [('B', MODE_MUSIC, 0.0)]

    def test_multiple_timeouts(self):
        """Multiple timeout resets in sequence."""
        s = PlaySession()
        s.record('A', now=0.0)
        s.record('B', now=5.0)   # timeout, reset
        s.record('C', now=10.0)  # timeout again
        s.record('D', now=10.5)  # within timeout of C
        assert s.get_replay() == [
            ('C', MODE_MUSIC, 0.0),
            ('D', MODE_MUSIC, 0.5),
        ]

    def test_long_session_no_timeout(self):
        """Many keys over a long time, but each within timeout of the previous."""
        s = PlaySession()
        for i in range(100):
            s.record('A', now=i * 1.0)  # every 1 second (within 2s timeout)
        assert len(s.get_replay()) == 100


# =============================================================================
# Clear
# =============================================================================

class TestClear:
    """Test session clear (used when replay starts)."""

    def test_clear_empties_session(self):
        s = PlaySession()
        s.record('A', now=1.0)
        s.record('B', now=1.5)
        s.clear()
        assert not s.has_events()
        assert s.get_replay() == []

    def test_record_after_clear(self):
        s = PlaySession()
        s.record('A', now=1.0)
        s.clear()
        s.record('B', now=2.0)
        assert s.get_replay() == [('B', MODE_MUSIC, 0.0)]


# =============================================================================
# Replay workflow
# =============================================================================

class TestReplayWorkflow:
    """Test the full replay-starts-new-session workflow."""

    def test_get_replay_then_clear_then_new_session(self):
        """Simulates: press keys, get replay data, clear, press new keys."""
        s = PlaySession()
        s.record('A', now=1.0)
        s.record('B', now=1.5)

        # Get replay data (what would be played back)
        replay = s.get_replay()
        assert len(replay) == 2
        assert replay[0] == ('A', MODE_MUSIC, 0.0)
        assert replay[1] == ('B', MODE_MUSIC, 0.5)

        # Clear for new session (replay started)
        s.clear()

        # New keys during/after replay
        s.record('C', now=2.0)
        s.record('D', now=2.5)

        new_replay = s.get_replay()
        assert new_replay == [
            ('C', MODE_MUSIC, 0.0),
            ('D', MODE_MUSIC, 0.5),
        ]

    def test_replay_with_no_new_input(self):
        """Replay with no new keys pressed afterwards."""
        s = PlaySession()
        s.record('A', now=1.0)
        s.get_replay()
        s.clear()
        assert not s.has_events()

    def test_multiple_replay_cycles(self):
        """Multiple record-replay cycles."""
        s = PlaySession()

        # First session
        s.record('A', now=0.0)
        s.record('B', now=0.5)
        replay1 = s.get_replay()
        assert len(replay1) == 2
        s.clear()

        # Second session (during/after first replay)
        s.record('C', now=1.0)
        replay2 = s.get_replay()
        assert replay2 == [('C', MODE_MUSIC, 0.0)]
        s.clear()

        # Third session
        s.record('D', now=2.0)
        s.record('E', now=2.1)
        replay3 = s.get_replay()
        assert replay3 == [
            ('D', MODE_MUSIC, 0.0),
            ('E', MODE_MUSIC, pytest.approx(0.1)),
        ]

    def test_empty_replay_does_nothing(self):
        """Getting replay from empty session returns empty list."""
        s = PlaySession()
        assert s.get_replay() == []
        # Clear on empty session is fine
        s.clear()
        assert s.get_replay() == []

    def test_mixed_submode_replay(self):
        """Replay preserves sub-modes from a mixed session."""
        s = PlaySession()
        s.record('A', MODE_MUSIC, now=0.0)
        s.record('B', MODE_LETTERS, now=0.5)
        s.record('1', MODE_LETTERS, now=1.0)
        s.record('C', MODE_MUSIC, now=1.5)

        replay = s.get_replay()
        assert replay == [
            ('A', MODE_MUSIC, 0.0),
            ('B', MODE_LETTERS, 0.5),
            ('1', MODE_LETTERS, 0.5),
            ('C', MODE_MUSIC, 0.5),
        ]


# =============================================================================
# Custom time function
# =============================================================================

class TestTimeFn:
    """Test custom time function injection (for testing without real time)."""

    def test_auto_timestamp(self):
        """Records use time_fn when no explicit timestamp given."""
        clock = [0.0]

        def fake_time():
            clock[0] += 1.0
            return clock[0]

        s = PlaySession(time_fn=fake_time)
        s.record('A')
        s.record('B')
        assert s.get_replay() == [
            ('A', MODE_MUSIC, 0.0),
            ('B', MODE_MUSIC, 1.0),
        ]

    def test_explicit_overrides_time_fn(self):
        """Explicit now= parameter overrides time_fn."""
        s = PlaySession(time_fn=lambda: 999.0)
        s.record('A', now=1.0)
        s.record('B', now=2.0)
        assert s.get_replay() == [
            ('A', MODE_MUSIC, 0.0),
            ('B', MODE_MUSIC, 1.0),
        ]


# =============================================================================
# Recent replay (smart Space behavior)
# =============================================================================

class TestRecentReplay:
    """Test get_recent_replay() for smart Space key behavior."""

    def test_empty_session(self):
        s = PlaySession()
        assert s.get_recent_replay() == []

    def test_short_session_returns_all(self):
        """A short session returns everything."""
        s = PlaySession()
        s.record('A', now=0.0)
        s.record('B', now=0.5)
        s.record('C', now=1.0)
        replay = s.get_recent_replay()
        assert len(replay) == 3
        assert [k for k, _, _ in replay] == ['A', 'B', 'C']

    def test_caps_at_10_seconds(self):
        """Events older than 10 seconds are excluded."""
        s = PlaySession()
        # 30 events at 0.5s intervals (total 15s, no long pauses)
        for i in range(31):
            s.record('A', now=i * 0.5)
        replay = s.get_recent_replay(max_seconds=10.0)
        # Last 10 seconds = events from t=5.0 to t=15.0 = 21 events
        assert len(replay) == 21

    def test_long_pause_cuts_replay(self):
        """A long pause within the session limits what gets replayed."""
        s = PlaySession()
        s.record('A', now=0.0)
        s.record('B', now=0.5)
        # Long pause (>= LONG_PAUSE_THRESHOLD)
        s.record('C', now=0.5 + LONG_PAUSE_THRESHOLD + 0.1)
        s.record('D', now=0.5 + LONG_PAUSE_THRESHOLD + 0.6)
        replay = s.get_recent_replay()
        # Should only get C and D (after the long pause)
        keys = [k for k, _, _ in replay]
        assert keys == ['C', 'D']

    def test_no_long_pause_uses_time_cap(self):
        """Without a long pause, all events within max_seconds are returned."""
        s = PlaySession()
        s.record('A', now=0.0)
        s.record('B', now=0.3)
        s.record('C', now=0.6)
        replay = s.get_recent_replay(max_seconds=10.0)
        assert len(replay) == 3

    def test_preserves_timing(self):
        """Recent replay preserves timing between events."""
        s = PlaySession()
        s.record('A', now=5.0)
        s.record('B', now=5.3)
        s.record('C', now=5.8)
        replay = s.get_recent_replay()
        assert replay[0] == ('A', MODE_MUSIC, 0.0)
        assert replay[1][2] == pytest.approx(0.3)
        assert replay[2][2] == pytest.approx(0.5)

    def test_preserves_submodes(self):
        """Recent replay preserves sub-modes."""
        s = PlaySession()
        s.record('A', MODE_MUSIC, now=0.0)
        s.record('B', MODE_LETTERS, now=0.5)
        replay = s.get_recent_replay()
        assert replay[0][1] == MODE_MUSIC
        assert replay[1][1] == MODE_LETTERS

    def test_long_pause_preferred_over_time_cap(self):
        """When a long pause is more recent than the time cap, use the pause."""
        s = PlaySession()
        # 8 seconds of events, then a 1.5s pause, then 2 more events
        for i in range(9):
            s.record('A', now=i * 1.0)
        s.record('B', now=9.0 + LONG_PAUSE_THRESHOLD + 0.1)
        s.record('C', now=9.0 + LONG_PAUSE_THRESHOLD + 0.5)
        replay = s.get_recent_replay(max_seconds=10.0)
        # The long pause is within the 10s window, so we get just B, C
        keys = [k for k, _, _ in replay]
        assert keys == ['B', 'C']
