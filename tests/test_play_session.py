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
    SUBMODE_MUSIC,
    SUBMODE_LETTERS,
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
        assert s.get_replay() == [('A', SUBMODE_MUSIC, 0.0)]

    def test_multiple_events_timing(self):
        s = PlaySession()
        s.record('A', now=1.0)
        s.record('B', now=1.5)
        s.record('C', now=2.0)
        assert s.get_replay() == [
            ('A', SUBMODE_MUSIC, 0.0),
            ('B', SUBMODE_MUSIC, 0.5),
            ('C', SUBMODE_MUSIC, 0.5),
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
            ('A', SUBMODE_MUSIC, 0.0),
            ('A', SUBMODE_MUSIC, 0.5),
            ('A', SUBMODE_MUSIC, 0.5),
        ]

    def test_default_submode_is_music(self):
        s = PlaySession()
        s.record('A', now=1.0)
        _, submode, _ = s.get_replay()[0]
        assert submode == SUBMODE_MUSIC


# =============================================================================
# Sub-mode recording
# =============================================================================

class TestSubmodeRecording:
    """Test that sub-mode is preserved per event."""

    def test_record_with_letters_submode(self):
        s = PlaySession()
        s.record('A', SUBMODE_LETTERS, now=1.0)
        assert s.get_replay() == [('A', SUBMODE_LETTERS, 0.0)]

    def test_mixed_submodes(self):
        """Session can contain events from both sub-modes."""
        s = PlaySession()
        s.record('A', SUBMODE_MUSIC, now=1.0)
        s.record('B', SUBMODE_LETTERS, now=1.5)
        s.record('C', SUBMODE_MUSIC, now=2.0)
        replay = s.get_replay()
        assert replay[0] == ('A', SUBMODE_MUSIC, 0.0)
        assert replay[1] == ('B', SUBMODE_LETTERS, 0.5)
        assert replay[2] == ('C', SUBMODE_MUSIC, 0.5)

    def test_submode_preserved_across_timeout_boundary(self):
        """After timeout reset, submode of new events is still recorded."""
        s = PlaySession()
        s.record('A', SUBMODE_MUSIC, now=0.0)
        s.record('B', SUBMODE_LETTERS, now=SESSION_TIMEOUT + 1)
        replay = s.get_replay()
        assert replay == [('B', SUBMODE_LETTERS, 0.0)]

    def test_numbers_in_letters_mode(self):
        """Non-letter keys in letters mode still record as letters submode."""
        s = PlaySession()
        s.record('5', SUBMODE_LETTERS, now=1.0)
        assert s.get_replay() == [('5', SUBMODE_LETTERS, 0.0)]


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
        assert s.get_replay() == [('C', SUBMODE_MUSIC, 0.0)]

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
        assert s.get_replay() == [('B', SUBMODE_MUSIC, 0.0)]

    def test_multiple_timeouts(self):
        """Multiple timeout resets in sequence."""
        s = PlaySession()
        s.record('A', now=0.0)
        s.record('B', now=5.0)   # timeout, reset
        s.record('C', now=10.0)  # timeout again
        s.record('D', now=10.5)  # within timeout of C
        assert s.get_replay() == [
            ('C', SUBMODE_MUSIC, 0.0),
            ('D', SUBMODE_MUSIC, 0.5),
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
        assert s.get_replay() == [('B', SUBMODE_MUSIC, 0.0)]


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
        assert replay[0] == ('A', SUBMODE_MUSIC, 0.0)
        assert replay[1] == ('B', SUBMODE_MUSIC, 0.5)

        # Clear for new session (replay started)
        s.clear()

        # New keys during/after replay
        s.record('C', now=2.0)
        s.record('D', now=2.5)

        new_replay = s.get_replay()
        assert new_replay == [
            ('C', SUBMODE_MUSIC, 0.0),
            ('D', SUBMODE_MUSIC, 0.5),
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
        assert replay2 == [('C', SUBMODE_MUSIC, 0.0)]
        s.clear()

        # Third session
        s.record('D', now=2.0)
        s.record('E', now=2.1)
        replay3 = s.get_replay()
        assert replay3 == [
            ('D', SUBMODE_MUSIC, 0.0),
            ('E', SUBMODE_MUSIC, pytest.approx(0.1)),
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
        s.record('A', SUBMODE_MUSIC, now=0.0)
        s.record('B', SUBMODE_LETTERS, now=0.5)
        s.record('1', SUBMODE_LETTERS, now=1.0)
        s.record('C', SUBMODE_MUSIC, now=1.5)

        replay = s.get_replay()
        assert replay == [
            ('A', SUBMODE_MUSIC, 0.0),
            ('B', SUBMODE_LETTERS, 0.5),
            ('1', SUBMODE_LETTERS, 0.5),
            ('C', SUBMODE_MUSIC, 0.5),
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
            ('A', SUBMODE_MUSIC, 0.0),
            ('B', SUBMODE_MUSIC, 1.0),
        ]

    def test_explicit_overrides_time_fn(self):
        """Explicit now= parameter overrides time_fn."""
        s = PlaySession(time_fn=lambda: 999.0)
        s.record('A', now=1.0)
        s.record('B', now=2.0)
        assert s.get_replay() == [
            ('A', SUBMODE_MUSIC, 0.0),
            ('B', SUBMODE_MUSIC, 1.0),
        ]
