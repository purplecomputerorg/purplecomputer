"""
Tests for Watch me! Recording: RecordingManager state machine, event capture,
single-room mode-aware block conversion.

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

    def test_start_recording(self):
        rm = RecordingManager()
        rm.start_recording("music")
        assert rm.state == RecordingState.RECORDING
        assert rm.is_recording
        assert rm.current is not None

    def test_stop_recording_returns_recording(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.start_recording("music")
        rm.record_event(CharacterAction(char="a"), "music")
        recording = rm.stop_recording()
        assert rm.state == RecordingState.IDLE
        assert not rm.is_recording
        assert recording is not None
        assert not recording.is_empty()

    def test_stop_recording_returns_none_when_empty(self):
        rm = RecordingManager()
        rm.start_recording("music")
        recording = rm.stop_recording()
        assert recording is None

    def test_stop_recording_returns_none_when_not_recording(self):
        rm = RecordingManager()
        recording = rm.stop_recording()
        assert recording is None

    def test_start_recording_stores_room(self):
        rm = RecordingManager()
        rm.start_recording("art", "paint")
        assert rm.target_room == "art"
        assert rm.target_mode == "paint"

    def test_current_cleared_after_stop(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(CharacterAction(char="a"), "music")
        rm.stop_recording()
        assert rm.current is None


# =============================================================================
# EVENT RECORDING
# =============================================================================

class TestEventRecording:
    def test_record_character(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(CharacterAction(char="a"), "music")
        assert len(rm.current.events) == 1

    def test_record_navigation(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("art")
        rm.record_event(NavigationAction(direction="up"), "art", "paint")
        assert len(rm.current.events) == 1

    def test_record_control(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(ControlAction(action="enter", is_down=True), "music")
        assert len(rm.current.events) == 1

    def test_ignores_when_not_recording(self):
        rm = RecordingManager()
        rm.record_event(CharacterAction(char="a"), "music")
        assert rm.current is None

    def test_ignores_key_up(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(ControlAction(action="space", is_down=False), "music")
        assert rm.current.is_empty()

    def test_ignores_key_repeat(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(CharacterAction(char="a", is_repeat=True), "music")
        assert rm.current.is_empty()

    def test_ignores_room_action(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(RoomAction(room="play"), "music")
        assert rm.current.is_empty()

    def test_ignores_escape(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(ControlAction(action="escape", is_down=True), "music")
        assert rm.current.is_empty()

    def test_records_mode(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording("music")
        rm.record_event(CharacterAction(char="a"), "music", "letters")
        assert rm.current.events[0].mode == "letters"


# =============================================================================
# RECORDING TO BLOCKS: SINGLE ROOM WITH TARGET
# =============================================================================

class TestRecordingToBlocksWithTarget:
    def test_empty_recording(self):
        r = Recording()
        assert r.to_blocks(TARGET_MUSIC_MUSIC) == []

    def test_prepends_mode_switch(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        blocks = r.to_blocks(TARGET_MUSIC_MUSIC)
        assert len(blocks) == 2
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        assert blocks[0].target == TARGET_MUSIC_MUSIC
        assert blocks[1].type == ProgramBlockType.KEY
        assert blocks[1].char == "a"

    def test_prepends_correct_target(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "art", "paint", 0.0)
        blocks = r.to_blocks(TARGET_ART_PAINT)
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        assert blocks[0].target == TARGET_ART_PAINT

    def test_no_extra_mode_switches(self):
        """Single room recording should only have one MODE_SWITCH."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "music", "music", 0.1)
        r.add_event(CharacterAction(char="c"), "music", "music", 0.2)
        blocks = r.to_blocks(TARGET_MUSIC_MUSIC)
        mode_switches = [b for b in blocks if b.type == ProgramBlockType.MODE_SWITCH]
        assert len(mode_switches) == 1


# =============================================================================
# RECORDING TO BLOCKS: MUSIC (SIMPLE KEY BLOCKS)
# =============================================================================

class TestRecordingToBlocksSimple:
    def test_single_event(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        blocks = r.to_blocks(TARGET_MUSIC_MUSIC)
        assert len(blocks) == 2  # MODE_SWITCH + KEY
        assert blocks[1].type == ProgramBlockType.KEY
        assert blocks[1].char == "a"

    def test_no_auto_collapse(self):
        """Repeated keys stay as separate blocks."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="a"), "music", "music", 0.1)
        r.add_event(CharacterAction(char="a"), "music", "music", 0.2)
        blocks = r.to_blocks(TARGET_MUSIC_MUSIC)
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        assert len(key_blocks) == 3

    def test_navigation_not_recorded_in_music(self):
        """Arrow keys in Music mode are not recorded (navigation only)."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(NavigationAction(direction="right"), "music", "music", 0.1)
        r.add_event(CharacterAction(char="b"), "music", "music", 0.2)
        blocks = r.to_blocks(TARGET_MUSIC_MUSIC)
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
        blocks = r.to_blocks(TARGET_PLAY)
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
        blocks = r.to_blocks(TARGET_PLAY)
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
        blocks = r.to_blocks(TARGET_PLAY)
        query_blocks = [b for b in blocks if b.type == ProgramBlockType.QUERY]
        assert query_blocks[0].query_text == "a b"

    def test_unflushed_query_at_end(self):
        """Query buffer is flushed at end even without Enter."""
        r = Recording()
        r.add_event(CharacterAction(char="h"), "play", "", 0.0)
        r.add_event(CharacterAction(char="i"), "play", "", 0.05)
        blocks = r.to_blocks(TARGET_PLAY)
        query_blocks = [b for b in blocks if b.type == ProgramBlockType.QUERY]
        assert len(query_blocks) == 1
        assert query_blocks[0].query_text == "hi"


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
        blocks = r.to_blocks(TARGET_ART_PAINT)
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) == 1
        assert stroke_blocks[0].direction == "right"
        assert stroke_blocks[0].distance == 3

    def test_different_directions_separate_strokes(self):
        r = Recording()
        r.add_event(NavigationAction(direction="right"), "art", "paint", 0.0)
        r.add_event(NavigationAction(direction="down"), "art", "paint", 0.05)
        blocks = r.to_blocks(TARGET_ART_PAINT)
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) == 2

    def test_char_keys_are_key_blocks(self):
        """In paint mode, character keys are KEY blocks (color selection)."""
        r = Recording()
        r.add_event(CharacterAction(char="r"), "art", "paint", 0.0)
        r.add_event(NavigationAction(direction="right"), "art", "paint", 0.05)
        blocks = r.to_blocks(TARGET_ART_PAINT)
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
        blocks = r.to_blocks(TARGET_MUSIC_MUSIC)
        pause_blocks = [b for b in blocks if b.type == ProgramBlockType.PAUSE]
        assert len(pause_blocks) >= 1

    def test_small_gap_no_pause(self):
        """Gaps < 300ms should NOT produce PAUSE blocks."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "music", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "music", "music", 0.1)  # 100ms gap
        blocks = r.to_blocks(TARGET_MUSIC_MUSIC)
        pause_blocks = [b for b in blocks if b.type == ProgramBlockType.PAUSE]
        assert len(pause_blocks) == 0
