"""Tests for the music room loop station.

Run with: pytest tests/test_loop_station.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from purple_tui.loop_station import (
    LoopStation,
    IDLE,
    RECORDING,
    LOOPING,
    MAX_LOOP_DURATION,
)
from purple_tui.music_session import MODE_MUSIC, MODE_LETTERS


# =============================================================================
# State transitions
# =============================================================================

class TestStateTransitions:
    """Test the idle → recording → looping → idle state machine."""

    def test_initial_state_is_idle(self):
        loop = LoopStation()
        assert loop.state == IDLE

    def test_start_recording(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        assert loop.state == RECORDING

    def test_finish_recording_starts_looping(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        events, duration = loop.finish_recording(now=1.0)
        assert loop.state == LOOPING
        assert len(events) == 1
        assert duration == 1.0

    def test_finish_recording_no_events_stays_idle(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        events, duration = loop.finish_recording(now=1.0)
        assert events == []
        assert duration == 0.0
        # State doesn't change (caller should call stop())

    def test_stop_from_recording(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.stop()
        assert loop.state == IDLE

    def test_stop_from_looping(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=1.0)
        assert loop.state == LOOPING
        loop.stop()
        assert loop.state == IDLE

    def test_stop_clears_all_data(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=1.0)
        loop.stop()
        assert loop.loop_events == []
        assert loop.loop_duration == 0.0

    def test_start_recording_clears_previous_loop(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=1.0)
        # Start a new recording
        loop.start_recording(now=2.0)
        assert loop.state == RECORDING
        assert loop.loop_events == []
        assert loop.loop_duration == 0.0


# =============================================================================
# Recording
# =============================================================================

class TestRecording:
    """Test event recording during the RECORDING state."""

    def test_record_single_event(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        assert loop.has_recording_events()

    def test_record_preserves_offset(self):
        loop = LoopStation()
        loop.start_recording(now=1.0)
        loop.record_event('A', MODE_MUSIC, now=1.5)
        loop.record_event('B', MODE_MUSIC, now=2.0)
        events, duration = loop.finish_recording(now=3.0)
        assert events[0] == ('A', MODE_MUSIC, 0.5)
        assert events[1] == ('B', MODE_MUSIC, 1.0)

    def test_record_preserves_mode(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.record_event('B', MODE_LETTERS, now=1.0)
        events, _ = loop.finish_recording(now=2.0)
        assert events[0][1] == MODE_MUSIC
        assert events[1][1] == MODE_LETTERS

    def test_record_in_idle_is_ignored(self):
        loop = LoopStation()
        loop.record_event('A', MODE_MUSIC, now=0.5)
        assert not loop.has_recording_events()

    def test_duration_includes_trailing_silence(self):
        """Duration spans to when Space was pressed, not just last note."""
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        events, duration = loop.finish_recording(now=3.0)
        assert duration == 3.0

    def test_duration_at_least_covers_last_event(self):
        """Edge case: finish called at same time as last event."""
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=2.0)
        events, duration = loop.finish_recording(now=1.0)  # before last event
        assert duration == 2.0  # must cover the event


# =============================================================================
# Max duration
# =============================================================================

class TestMaxDuration:
    """Test recording time limit."""

    def test_events_beyond_max_are_dropped(self):
        loop = LoopStation(max_duration=5.0)
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=1.0)
        loop.record_event('B', MODE_MUSIC, now=6.0)  # beyond max
        events, _ = loop.finish_recording(now=7.0)
        assert len(events) == 1
        assert events[0][0] == 'A'

    def test_is_at_max_duration(self):
        loop = LoopStation(max_duration=5.0)
        loop.start_recording(now=0.0)
        assert not loop.is_at_max_duration(now=4.9)
        assert loop.is_at_max_duration(now=5.0)
        assert loop.is_at_max_duration(now=6.0)

    def test_recording_progress(self):
        loop = LoopStation(max_duration=10.0)
        loop.start_recording(now=0.0)
        assert loop.recording_progress(now=0.0) == pytest.approx(0.0)
        assert loop.recording_progress(now=5.0) == pytest.approx(0.5)
        assert loop.recording_progress(now=10.0) == pytest.approx(1.0)
        assert loop.recording_progress(now=15.0) == pytest.approx(1.0)  # capped

    def test_recording_remaining(self):
        loop = LoopStation(max_duration=10.0)
        loop.start_recording(now=0.0)
        assert loop.recording_remaining(now=0.0) == pytest.approx(10.0)
        assert loop.recording_remaining(now=7.0) == pytest.approx(3.0)
        assert loop.recording_remaining(now=10.0) == pytest.approx(0.0)
        assert loop.recording_remaining(now=15.0) == pytest.approx(0.0)  # floor at 0

    def test_progress_and_remaining_zero_when_not_recording(self):
        loop = LoopStation()
        assert loop.recording_progress() == 0.0
        assert loop.recording_remaining() == 0.0
        assert not loop.is_at_max_duration()

    def test_duration_capped_at_max(self):
        loop = LoopStation(max_duration=5.0)
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=1.0)
        events, duration = loop.finish_recording(now=10.0)
        assert duration == 5.0


# =============================================================================
# Overlay and merging
# =============================================================================

class TestOverlay:
    """Test recording overlay events during looping and merging."""

    def test_overlay_records_during_looping(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=2.0)
        # Play overlay note at 0.5s into the cycle
        loop.record_event('B', MODE_MUSIC, now=2.5)
        assert loop.has_overlay_events()

    def test_overlay_offset_relative_to_cycle(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=2.0)  # cycle_start = 2.0
        loop.record_event('B', MODE_MUSIC, now=2.8)  # offset = 0.8
        events, duration = loop.merge_overlay(now=3.0)
        offsets = {e[0]: e[2] for e in events}
        assert offsets['A'] == pytest.approx(0.5)
        assert offsets['B'] == pytest.approx(0.8)

    def test_merge_sorts_by_offset(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=1.0)
        loop.finish_recording(now=2.0)
        # Overlay note earlier in the cycle than A
        loop.record_event('B', MODE_MUSIC, now=2.3)  # offset 0.3
        events, _ = loop.merge_overlay(now=3.0)
        keys = [e[0] for e in events]
        assert keys == ['B', 'A']  # B at 0.3, A at 1.0

    def test_merge_preserves_duration(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        events, duration = loop.finish_recording(now=2.0)
        loop.record_event('B', MODE_MUSIC, now=2.5)
        events, new_duration = loop.merge_overlay(now=3.0)
        assert new_duration == duration  # duration doesn't change

    def test_merge_with_no_overlay(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=2.0)
        events, duration = loop.merge_overlay(now=3.0)
        assert len(events) == 1  # just the original
        assert duration == 2.0

    def test_multiple_merges(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=2.0)

        # First layer
        loop.record_event('B', MODE_MUSIC, now=2.3)
        loop.merge_overlay(now=4.0)

        # Second layer
        loop.record_event('C', MODE_MUSIC, now=4.8)
        events, _ = loop.merge_overlay(now=6.0)

        keys = sorted(e[0] for e in events)
        assert keys == ['A', 'B', 'C']

    def test_overlay_wraps_around_cycle(self):
        """Overlay offset wraps if played past the loop duration."""
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=2.0)  # duration=2.0, cycle_start=2.0
        # Play at 2.5s into cycle (duration is 2.0, so offset = 0.5)
        loop.record_event('B', MODE_MUSIC, now=4.5)
        events, _ = loop.merge_overlay(now=5.0)
        b_offset = [e[2] for e in events if e[0] == 'B'][0]
        assert b_offset == pytest.approx(0.5)

    def test_merge_when_not_looping(self):
        loop = LoopStation()
        events, duration = loop.merge_overlay()
        assert events == []
        assert duration == 0.0


# =============================================================================
# Cycle management
# =============================================================================

class TestCycleManagement:
    def test_start_new_cycle(self):
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=2.0)
        loop.start_new_cycle(now=4.0)
        # Overlay should be relative to new cycle start
        loop.record_event('B', MODE_MUSIC, now=4.3)
        events, _ = loop.merge_overlay(now=5.0)
        b_offset = [e[2] for e in events if e[0] == 'B'][0]
        assert b_offset == pytest.approx(0.3)


# =============================================================================
# Properties
# =============================================================================

class TestProperties:
    def test_loop_events_is_copy(self):
        """loop_events returns a copy, not the internal list."""
        loop = LoopStation()
        loop.start_recording(now=0.0)
        loop.record_event('A', MODE_MUSIC, now=0.5)
        loop.finish_recording(now=1.0)
        events = loop.loop_events
        events.clear()
        assert len(loop.loop_events) == 1  # internal list unchanged

    def test_max_duration_property(self):
        loop = LoopStation(max_duration=15.0)
        assert loop.max_duration == 15.0

    def test_default_max_duration(self):
        loop = LoopStation()
        assert loop.max_duration == MAX_LOOP_DURATION


# =============================================================================
# Time function injection
# =============================================================================

class TestTimeFn:
    def test_custom_time_fn(self):
        clock = [0.0]
        def tick():
            clock[0] += 1.0
            return clock[0]

        loop = LoopStation(time_fn=tick)
        loop.start_recording()  # now=1.0
        loop.record_event('A', MODE_MUSIC)  # now=2.0, offset=1.0
        events, duration = loop.finish_recording()  # now=3.0, duration=2.0
        assert events[0][2] == pytest.approx(1.0)
        assert duration == pytest.approx(2.0)
