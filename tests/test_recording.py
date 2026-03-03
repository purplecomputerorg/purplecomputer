"""
Tests for F5 Recording: RecordingManager state machine, event capture, block conversion.

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
    TARGET_PLAY_MUSIC,
    TARGET_PLAY_LETTERS,
    TARGET_DOODLE_TEXT,
    TARGET_DOODLE_PAINT,
    TARGET_EXPLORE,
)
from purple_tui.keyboard import (
    CharacterAction,
    NavigationAction,
    ControlAction,
    ModeAction,
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
        rm.toggle()  # IDLE → RECORDING
        # Add an event so recording isn't empty
        rm.record_event(CharacterAction(char="a"), "play")
        new_state = rm.toggle()  # RECORDING → IDLE
        assert new_state == RecordingState.IDLE
        assert rm.current is not None  # recording preserved

    def test_toggle_idle_with_recording_to_playing(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # IDLE → RECORDING
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()  # RECORDING → IDLE
        new_state = rm.toggle()  # IDLE (has recording) → PLAYING
        assert new_state == RecordingState.PLAYING

    def test_toggle_playing_to_idle(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # IDLE → RECORDING
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()  # RECORDING → IDLE
        rm.toggle()  # IDLE → PLAYING
        new_state = rm.toggle()  # PLAYING → IDLE
        assert new_state == RecordingState.IDLE

    def test_empty_recording_discarded(self):
        rm = RecordingManager()
        rm.toggle()  # IDLE → RECORDING
        rm.toggle()  # RECORDING → IDLE (empty recording)
        assert rm.current is None  # discarded
        # Next toggle should start new recording, not play
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
        rm.record_event(CharacterAction(char="a"), "play")
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
        rm.record_event(CharacterAction(char="a"), "play")
        assert rm.has_recording()
        assert len(rm.current.events) == 1

    def test_record_navigation(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(NavigationAction(direction="up"), "doodle", "paint")
        assert len(rm.current.events) == 1

    def test_record_control(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(ControlAction(action="enter", is_down=True), "explore")
        assert len(rm.current.events) == 1

    def test_ignores_when_not_recording(self):
        rm = RecordingManager()
        rm.record_event(CharacterAction(char="a"), "play")
        assert not rm.has_recording()

    def test_ignores_key_up(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(ControlAction(action="space", is_down=False), "play")
        assert rm.current.is_empty()

    def test_ignores_key_repeat(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a", is_repeat=True), "play")
        assert rm.current.is_empty()

    def test_ignores_mode_action(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(ModeAction(mode="explore"), "play")
        assert rm.current.is_empty()

    def test_ignores_escape(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(ControlAction(action="escape", is_down=True), "play")
        assert rm.current.is_empty()

    def test_records_sub_mode(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "play", "letters")
        assert rm.current.events[0].sub_mode == "letters"


# =============================================================================
# RECORDING TO BLOCKS
# =============================================================================

class TestRecordingToBlocks:
    def test_empty_recording(self):
        r = Recording()
        assert r.to_blocks() == []

    def test_single_event(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "music", 0.0)
        blocks = r.to_blocks()
        # MODE_SWITCH + KEY block
        assert len(blocks) == 2
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        assert blocks[0].target == TARGET_PLAY_MUSIC
        assert blocks[1].type == ProgramBlockType.KEY
        assert blocks[1].char == "a"

    def test_mode_switch_on_mode_change(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "doodle", "text", 0.5)
        blocks = r.to_blocks()
        # play.music MODE_SWITCH, KEY(a), doodle.text MODE_SWITCH, KEY(b)
        assert len(blocks) == 4
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        assert blocks[0].target == TARGET_PLAY_MUSIC
        assert blocks[1].type == ProgramBlockType.KEY
        assert blocks[2].type == ProgramBlockType.MODE_SWITCH
        assert blocks[2].target == TARGET_DOODLE_TEXT
        assert blocks[3].type == ProgramBlockType.KEY

    def test_sub_mode_change_inserts_switch(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "play", "letters", 0.1)
        blocks = r.to_blocks()
        # play.music MODE_SWITCH, KEY(a), play.letters MODE_SWITCH, KEY(b)
        assert len(blocks) == 4
        assert blocks[0].target == TARGET_PLAY_MUSIC
        assert blocks[2].target == TARGET_PLAY_LETTERS

    def test_no_switch_when_same_mode(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "play", "music", 0.1)
        blocks = r.to_blocks()
        # play.music MODE_SWITCH, KEY(a), KEY(b)
        assert len(blocks) == 3

    def test_timing_quantization(self):
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "play", "music", 0.1)
        r.add_event(CharacterAction(char="c"), "play", "music", 0.6)
        blocks = r.to_blocks()
        # MODE_SWITCH, KEY(a), KEY(b), KEY(c)
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        # a->b gap is 0.1s (level 1)
        assert key_blocks[0].gap_level == 1
        # b->c gap is 0.5s (level 2 or 3)
        assert key_blocks[1].gap_level in (2, 3)
        # last block has no gap
        assert key_blocks[2].gap_level == 0

    def test_cross_mode_recording(self):
        """Recording that spans play and doodle modes."""
        r = Recording()
        r.add_event(CharacterAction(char="a"), "play", "music", 0.0)
        r.add_event(CharacterAction(char="b"), "play", "music", 0.1)
        r.add_event(NavigationAction(direction="right"), "doodle", "paint", 0.5)
        r.add_event(NavigationAction(direction="down"), "doodle", "paint", 0.6)
        blocks = r.to_blocks()

        # play.music SWITCH, KEY(a), KEY(b), doodle.paint SWITCH, ARROW(right), ARROW(down)
        assert len(blocks) == 6
        assert blocks[0].target == TARGET_PLAY_MUSIC
        assert blocks[3].target == TARGET_DOODLE_PAINT

    def test_explore_mode(self):
        r = Recording()
        r.add_event(CharacterAction(char="2"), "explore", "", 0.0)
        blocks = r.to_blocks()
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        assert blocks[0].target == TARGET_EXPLORE


# =============================================================================
# RECORDING MANAGER HELPERS
# =============================================================================

class TestRecordingManagerHelpers:
    def test_indicator_idle(self):
        rm = RecordingManager()
        assert rm.indicator == ""

    def test_indicator_recording(self):
        rm = RecordingManager()
        rm.toggle()  # IDLE → RECORDING
        assert rm.indicator == "⏺"

    def test_indicator_playing(self):
        rm = RecordingManager(time_fn=lambda: 1.0)
        rm.toggle()  # IDLE → RECORDING
        rm.record_event(CharacterAction(char="a"), "play")
        rm.toggle()  # RECORDING → IDLE
        rm.toggle()  # IDLE → PLAYING
        assert rm.indicator == "▶"

    def test_to_blocks_delegation(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="x"), "play", "music")
        rm.stop_recording()
        blocks = rm.to_blocks()
        assert len(blocks) == 2  # MODE_SWITCH + KEY
        assert blocks[1].char == "x"

    def test_clear(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "play")
        rm.stop_recording()
        rm.clear()
        assert not rm.has_recording()

    def test_has_recording_false_when_empty(self):
        rm = RecordingManager()
        assert not rm.has_recording()

    def test_has_recording_true_after_events(self):
        rm = RecordingManager(time_fn=lambda: 0.0)
        rm.start_recording()
        rm.record_event(CharacterAction(char="a"), "play")
        rm.stop_recording()
        assert rm.has_recording()
