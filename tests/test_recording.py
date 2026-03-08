"""
Tests for F5 Recording: RecordingManager state machine, event capture,
mode-aware block conversion.

Pure logic tests with no Textual app dependency.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.recording import (
    RecordingManager,
    RecordingState,
    Recording,
    RecordedEvent,
)
from purple_tui.program import (
    ProgramBlock,
    ProgramBlockType,
    TARGET_MUSIC_MUSIC,
    TARGET_MUSIC_LETTERS,
    TARGET_ART_TEXT,
    TARGET_ART_PAINT,
    TARGET_PLAY,
)
from purple_tui.keyboard import (
    CharacterAction,
    NavigationAction,
    ControlAction,
    RoomAction,
    ShiftAction,
)


# =============================================================================
# RECORDING MANAGER STATE MACHINE
# =============================================================================

class TestRecordingManagerStates:
    def test_initial_state_is_idle(self):
        rm = RecordingManager()
        assert rm.state == RecordingState.IDLE

    def test_toggle_idle_to_recording(self):
        rm = RecordingManager()
        new_state = rm.toggle()
        assert new_state == RecordingState.RECORDING
        assert rm.current is not None

    def test_toggle_recording_to_idle(self):
        rm = RecordingManager()
        rm.toggle()  # IDLE -> RECORDING
        rm.record_event(CharacterAction(char="a"), "music")
        new_state = rm.toggle()  # RECORDING -> IDLE
        assert new_state == RecordingState.IDLE
        assert rm.current is not None

    def test_toggle_idle_with_recording_starts_new_recording(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # IDLE -> RECORDING
        rm.record_event(CharacterAction(char="a"), "music")
        rm.toggle()  # RECORDING -> IDLE
        new_state = rm.toggle()  # IDLE -> RECORDING (overwrites previous)
        assert new_state == RecordingState.RECORDING
        assert rm.current.is_empty()  # new recording, no events yet

    def test_toggle_during_playback_starts_recording(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # IDLE -> RECORDING
        rm.record_event(CharacterAction(char="a"), "music")
        rm.toggle()  # RECORDING -> IDLE
        rm.start_playback()  # IDLE -> PLAYING
        new_state = rm.toggle()  # PLAYING -> RECORDING
        assert new_state == RecordingState.RECORDING

    def test_empty_recording_discarded(self):
        rm = RecordingManager()
        rm.toggle()  # IDLE -> RECORDING
        rm.toggle()  # RECORDING -> IDLE (empty recording)
        assert rm.current is None
        new_state = rm.toggle()
        assert new_state == RecordingState.RECORDING

    def test_start_recording_explicit(self):
        rm = RecordingManager()
        rm.start_recording()
        assert rm.state == RecordingState.RECORDING
        assert rm.current is not None

    def test_stop_recording_explicit(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "music")
        rm.stop_recording()
        assert rm.state == RecordingState.IDLE
        assert rm.has_recording()


# =============================================================================
# EVENT RECORDING
# =============================================================================

class TestEventRecording:
    def test_record_character(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "music")
        assert rm.has_recording()
        assert len(rm.current.events) == 1

    def test_record_navigation(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(NavigationAction(direction="up"), "art", "paint")
        assert len(rm.current.events) == 1

    def test_record_control(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(ControlAction(action="enter", is_down=True), "music")
        assert len(rm.current.events) == 1

    def test_ignores_when_not_recording(self):
        rm = RecordingManager()
        rm.record_event(CharacterAction(char="a"), "music")
        assert not rm.has_recording()

    def test_ignores_key_up(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(ControlAction(action="space", is_down=False), "music")
        assert rm.current.is_empty()

    def test_ignores_key_repeat(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a", is_repeat=True), "music")
        assert rm.current.is_empty()

    def test_ignores_room_action(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(RoomAction(room="play"), "music")
        assert rm.current.is_empty()

    def test_ignores_escape(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(ControlAction(action="escape", is_down=True), "music")
        assert rm.current.is_empty()

    def test_records_mode(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "music", "letters")
        assert rm.current.events[0].mode == "letters"


# =============================================================================
# RECORDING TO BLOCKS: MUSIC/ART TEXT (SIMPLE)
# =============================================================================

class TestRecordingToBlocksSimple:
    def test_empty_recording(self):
        r = Recording()
        assert r.to_blocks() == []

    def test_single_event(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        blocks = r.to_blocks()
        # MODE_SWITCH + KEY block
        assert len(blocks) == 2
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        assert blocks[0].target == TARGET_MUSIC_MUSIC
        assert blocks[1].type == ProgramBlockType.KEY
        assert blocks[1].char == "a"

    def test_mode_switch_on_room_change(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "art", "text", 0.5)
        blocks = r.to_blocks()
        mode_switches = [b for b in blocks if b.type == ProgramBlockType.MODE_SWITCH]
        assert len(mode_switches) == 2
        assert mode_switches[0].target == TARGET_MUSIC_MUSIC
        assert mode_switches[1].target == TARGET_ART_TEXT

    def test_no_switch_when_same_mode(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "music", "music", 0.1)
        blocks = r.to_blocks()
        mode_switches = [b for b in blocks if b.type == ProgramBlockType.MODE_SWITCH]
        assert len(mode_switches) == 1

    def test_no_auto_collapse(self):
        """Repeated keys stay as separate blocks (no auto-collapse in v2)."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="a"), "music", "music", 0.1)
        r.add_event(CharacterAction(char="a"), "music", "music", 0.2)
        blocks = r.to_blocks()
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        assert len(key_blocks) == 3

    def test_navigation_not_recorded_in_play(self):
        """Arrow keys in Music mode are not recorded (navigation only)."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(NavigationAction(direction="right"), "music", "music", 0.1)
        r.add_event(CharacterAction(char="b"), "music", "music", 0.2)
        blocks = r.to_blocks()
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        assert len(key_blocks) == 2
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) == 0


# =============================================================================
# RECORDING TO BLOCKS: PLAY (QUERY BUFFERING)
# =============================================================================

class TestRecordingToBlocksPlay:
    def test_query_block_from_typing(self):
        """Characters followed by Enter become a single QUERY block."""
        r = Recording()
        r.add_event(CharacterAction(char="h"), "play", "", 0.0)
        r.add_event(CharacterAction(char="i"), "play", "", 0.05)
        r.add_event(ControlAction(action="enter", is_down=True), "play", "", 0.1)
        blocks = r.to_blocks()
        query_blocks = [b for b in blocks if b.type == ProgramBlockType.QUERY]
        assert len(query_blocks) == 1
        assert query_blocks[0].query_text == "hi"

    def test_backspace_edits_query(self):
        """Backspace removes the last character from the query buffer."""
        r = Recording()
        r.add_event(CharacterAction(char="h"), "play", "", 0.0)
        r.add_event(CharacterAction(char="x"), "play", "", 0.05)
        r.add_event(ControlAction(action="backspace", is_down=True), "play", "", 0.1)
        r.add_event(CharacterAction(char="i"), "play", "", 0.15)
        r.add_event(ControlAction(action="enter", is_down=True), "play", "", 0.2)
        blocks = r.to_blocks()
        query_blocks = [b for b in blocks if b.type == ProgramBlockType.QUERY]
        assert len(query_blocks) == 1
        assert query_blocks[0].query_text == "hi"

    def test_space_in_query(self):
        """Space adds a space to the query text."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "", 0.0)
        r.add_event(ControlAction(action="space", is_down=True), "play", "", 0.05)
        r.add_event(CharacterAction(char="b"), "play", "", 0.1)
        r.add_event(ControlAction(action="enter", is_down=True), "play", "", 0.15)
        blocks = r.to_blocks()
        query_blocks = [b for b in blocks if b.type == ProgramBlockType.QUERY]
        assert query_blocks[0].query_text == "a b"

    def test_unflushed_query_at_end(self):
        """Query buffer is flushed at end even without Enter."""
        r = Recording()
        r.add_event(CharacterAction(char="h"), "play", "", 0.0)
        r.add_event(CharacterAction(char="i"), "play", "", 0.05)
        blocks = r.to_blocks()
        query_blocks = [b for b in blocks if b.type == ProgramBlockType.QUERY]
        assert len(query_blocks) == 1
        assert query_blocks[0].query_text == "hi"

    def test_query_flushed_on_mode_change(self):
        """Query buffer is flushed when switching away from Play."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "", 0.0)
        r.add_event(CharacterAction(char="b"), "music", "music", 0.5)
        blocks = r.to_blocks()
        query_blocks = [b for b in blocks if b.type == ProgramBlockType.QUERY]
        assert len(query_blocks) == 1
        assert query_blocks[0].query_text == "a"


# =============================================================================
# RECORDING TO BLOCKS: ART PAINT (STROKE MERGING)
# =============================================================================

class TestRecordingToBlocksPaint:
    def test_arrows_merge_into_stroke(self):
        """Consecutive same-direction arrows merge into one STROKE block."""
        r = Recording()
        r.add_event(NavigationAction(direction="right"), "art", "paint", 0.0)
        r.add_event(NavigationAction(direction="right"), "art", "paint", 0.05)
        r.add_event(NavigationAction(direction="right"), "art", "paint", 0.1)
        blocks = r.to_blocks()
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) == 1
        assert stroke_blocks[0].direction == "right"
        assert stroke_blocks[0].distance == 3

    def test_different_directions_separate_strokes(self):
        r = Recording()
        r.add_event(NavigationAction(direction="right"), "art", "paint", 0.0)
        r.add_event(NavigationAction(direction="down"), "art", "paint", 0.05)
        blocks = r.to_blocks()
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) == 2

    def test_char_keys_are_key_blocks(self):
        """In paint mode, character keys are KEY blocks (color selection)."""
        r = Recording()
        r.add_event(CharacterAction(char="r"), "art", "paint", 0.0)
        r.add_event(NavigationAction(direction="right"), "art", "paint", 0.05)
        blocks = r.to_blocks()
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        assert len(key_blocks) == 1
        assert key_blocks[0].char == "r"


# =============================================================================
# PAUSE INSERTION
# =============================================================================

class TestPauseInsertion:
    def test_large_gap_inserts_pause(self):
        """Gaps >= 300ms between events should produce PAUSE blocks."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "music", "music", 1.0)  # 1000ms gap
        blocks = r.to_blocks()
        pause_blocks = [b for b in blocks if b.type == ProgramBlockType.PAUSE]
        assert len(pause_blocks) >= 1

    def test_small_gap_no_pause(self):
        """Gaps < 300ms should NOT produce PAUSE blocks."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "music", "music", 0.1)  # 100ms gap
        blocks = r.to_blocks()
        pause_blocks = [b for b in blocks if b.type == ProgramBlockType.PAUSE]
        assert len(pause_blocks) == 0


# =============================================================================
# RECORDING MANAGER HELPERS
# =============================================================================

class TestRecordingManagerHelpers:
    def test_indicator_idle(self):
        rm = RecordingManager()
        assert rm.indicator == ""

    def test_indicator_recording(self):
        rm = RecordingManager()
        rm.toggle()
        assert "\u23fa" in rm.indicator
        assert "keys" in rm.indicator.lower()

    def test_indicator_playing(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()
        rm.record_event(CharacterAction(char="a"), "music")
        rm.toggle()
        rm.start_playback()
        assert rm.indicator == "\u25b6"

    def test_to_blocks_delegation(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="x"), "music", "music")
        rm.stop_recording()
        blocks = rm.to_blocks()
        assert len(blocks) == 2  # MODE_SWITCH + KEY
        assert blocks[1].char == "x"

    def test_clear(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "music")
        rm.stop_recording()
        rm.clear()
        assert not rm.has_recording()

    def test_has_recording_false_when_empty(self):
        rm = RecordingManager()
        assert not rm.has_recording()

    def test_has_recording_true_after_events(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "music")
        rm.stop_recording()
        assert rm.has_recording()


# =============================================================================
# CONCURRENT RECORDING AND PLAYBACK
# =============================================================================

class TestConcurrentRecordingPlayback:
    def test_can_record_during_playback(self):
        """Starting recording while playing doesn't stop playback."""
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # start recording
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()  # stop recording
        rm.start_playback()
        assert rm.is_playing
        rm.toggle()  # start new recording
        assert rm.is_recording
        assert rm.is_playing  # playback continues

    def test_can_start_playback_during_recording(self):
        """Starting playback while recording doesn't stop recording."""
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # start recording
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()  # stop recording (has a recording now)
        rm.toggle()  # start new recording
        assert rm.is_recording
        rm.start_playback()
        assert rm.is_playing
        assert rm.is_recording  # recording continues

    def test_finish_playback_preserves_recording(self):
        """finish_playback() only clears playing, not recording."""
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # start recording
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()  # stop recording
        rm.start_playback()
        rm.toggle()  # start new recording
        assert rm.is_recording and rm.is_playing
        rm.finish_playback()
        assert not rm.is_playing
        assert rm.is_recording  # still recording

    def test_state_priority_recording_over_playing(self):
        """state property returns RECORDING when both are active."""
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()
        rm.start_playback()
        rm.toggle()  # start recording again
        assert rm.state == RecordingState.RECORDING

    def test_is_recording_and_is_playing_properties(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        assert not rm.is_recording
        assert not rm.is_playing
        rm.toggle()
        assert rm.is_recording
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()
        assert not rm.is_recording
        rm.start_playback()
        assert rm.is_playing
