"""
Tests for Code Mode: program recording, editing, and playback.

Pure logic tests with no Textual app dependency.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.program import (
    ProgramBlock,
    ProgramBlockType,
    ActionRecorder,
    quantize_pause,
    gap_width,
    gap_duration,
    blocks_to_demo_actions,
    blocks_to_json,
    blocks_from_json,
    key_color,
    control_color,
    PAUSE_LEVELS,
    NUM_PAUSE_LEVELS,
    KEY_COLOR_RED,
    KEY_COLOR_YELLOW,
    KEY_COLOR_BLUE,
    KEY_COLOR_GRAY,
    ARROW_COLOR,
    ENTER_COLOR,
    BACKSPACE_COLOR,
    SPACE_COLOR,
    REPEAT_COLOR,
)
from purple_tui.keyboard import (
    CharacterAction,
    NavigationAction,
    ControlAction,
    ModeAction,
    ShiftAction,
)
from purple_tui.demo.script import TypeText, PressKey, SwitchMode, Pause


# =============================================================================
# PAUSE LEVEL TESTS
# =============================================================================

class TestPauseLevels:
    def test_quantize_simultaneous(self):
        assert quantize_pause(0.01) == 0

    def test_quantize_tiny(self):
        assert quantize_pause(0.1) == 1

    def test_quantize_short(self):
        assert quantize_pause(0.3) == 2

    def test_quantize_medium(self):
        assert quantize_pause(0.7) == 3

    def test_quantize_long(self):
        assert quantize_pause(1.5) == 4

    def test_quantize_very_long(self):
        """Anything beyond 2s still maps to level 4."""
        assert quantize_pause(10.0) == 4

    def test_gap_width_level_0(self):
        assert gap_width(0) == 0

    def test_gap_width_level_4(self):
        assert gap_width(4) == 12

    def test_gap_width_clamps_negative(self):
        assert gap_width(-1) == 0

    def test_gap_width_clamps_high(self):
        assert gap_width(99) == 12

    def test_gap_duration_level_0(self):
        assert gap_duration(0) == 0.0

    def test_gap_duration_level_1(self):
        """Level 1 should be midpoint of (0.05, 0.2)."""
        d = gap_duration(1)
        assert 0.1 < d < 0.15


# =============================================================================
# PROGRAM BLOCK TESTS
# =============================================================================

class TestProgramBlock:
    def test_key_block_icon(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        assert b.icon == "A"

    def test_key_block_color_qwerty(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="q")
        assert b.bg_color == KEY_COLOR_RED

    def test_key_block_color_asdf(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        assert b.bg_color == KEY_COLOR_YELLOW

    def test_key_block_color_zxcv(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="z")
        assert b.bg_color == KEY_COLOR_BLUE

    def test_key_block_color_number(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="5")
        assert b.bg_color == KEY_COLOR_GRAY

    def test_arrow_block_icon(self):
        b = ProgramBlock(type=ProgramBlockType.ARROW, direction="up")
        assert b.icon == "▲"

    def test_arrow_block_color(self):
        b = ProgramBlock(type=ProgramBlockType.ARROW, direction="left")
        assert b.bg_color == ARROW_COLOR

    def test_control_enter_icon(self):
        b = ProgramBlock(type=ProgramBlockType.CONTROL, control="enter")
        assert b.icon == "↵"

    def test_control_enter_color(self):
        b = ProgramBlock(type=ProgramBlockType.CONTROL, control="enter")
        assert b.bg_color == ENTER_COLOR

    def test_control_backspace_color(self):
        b = ProgramBlock(type=ProgramBlockType.CONTROL, control="backspace")
        assert b.bg_color == BACKSPACE_COLOR

    def test_control_space_color(self):
        b = ProgramBlock(type=ProgramBlockType.CONTROL, control="space")
        assert b.bg_color == SPACE_COLOR

    def test_total_width_no_gap(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0)
        assert b.total_width == 4  # icon only

    def test_total_width_with_gap(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=2)
        assert b.total_width == 4 + 4  # icon + 4 char gap

    def test_cycle_gap_up(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=1)
        b.cycle_gap(1)
        assert b.gap_level == 2

    def test_cycle_gap_down(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=2)
        b.cycle_gap(-1)
        assert b.gap_level == 1

    def test_cycle_gap_clamps_at_zero(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0)
        b.cycle_gap(-1)
        assert b.gap_level == 0

    def test_cycle_gap_clamps_at_max(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a",
                         gap_level=NUM_PAUSE_LEVELS - 1)
        b.cycle_gap(1)
        assert b.gap_level == NUM_PAUSE_LEVELS - 1


# =============================================================================
# REPEAT BLOCK TESTS
# =============================================================================

class TestRepeatBlock:
    def test_repeat_icon_default(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT)
        assert b.icon == "×2"

    def test_repeat_icon_custom_count(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=5)
        assert b.icon == "×5"

    def test_repeat_color(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT)
        assert b.bg_color == REPEAT_COLOR

    def test_cycle_repeat_count_up(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3)
        b.cycle_repeat_count(1)
        assert b.repeat_count == 4

    def test_cycle_repeat_count_down(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=5)
        b.cycle_repeat_count(-1)
        assert b.repeat_count == 4

    def test_cycle_repeat_count_clamps_at_2(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2)
        b.cycle_repeat_count(-1)
        assert b.repeat_count == 2

    def test_cycle_repeat_count_clamps_at_9(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=9)
        b.cycle_repeat_count(1)
        assert b.repeat_count == 9

    def test_repeat_total_width(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, gap_level=0)
        assert b.total_width == 4  # icon only, no gap

    def test_repeat_total_width_with_gap(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, gap_level=2)
        assert b.total_width == 4 + 4


# =============================================================================
# ACTION RECORDER TESTS
# =============================================================================

class TestActionRecorder:
    def test_empty_recorder(self):
        r = ActionRecorder()
        assert not r.has_events()
        assert r.get_blocks() == []

    def test_record_character(self):
        t = 0.0
        r = ActionRecorder(time_fn=lambda: t)
        r.record(CharacterAction(char="a"), "play")
        assert r.has_events()
        blocks = r.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == ProgramBlockType.KEY
        assert blocks[0].char == "a"

    def test_record_navigation(self):
        t = 0.0
        r = ActionRecorder(time_fn=lambda: t)
        r.record(NavigationAction(direction="up"), "doodle")
        blocks = r.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == ProgramBlockType.ARROW
        assert blocks[0].direction == "up"

    def test_record_control(self):
        t = 0.0
        r = ActionRecorder(time_fn=lambda: t)
        r.record(ControlAction(action="enter", is_down=True), "play")
        blocks = r.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].type == ProgramBlockType.CONTROL
        assert blocks[0].control == "enter"

    def test_ignores_non_recordable_mode(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(CharacterAction(char="a"), "build")
        assert not r.has_events()

    def test_ignores_explore_mode(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(CharacterAction(char="a"), "explore")
        assert not r.has_events()

    def test_ignores_key_up(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(ControlAction(action="space", is_down=False), "play")
        assert not r.has_events()

    def test_ignores_key_repeat(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(CharacterAction(char="a", is_repeat=True), "play")
        assert not r.has_events()

    def test_ignores_mode_action(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(ModeAction(mode="explore"), "play")
        assert not r.has_events()

    def test_ignores_escape(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(ControlAction(action="escape", is_down=True), "play")
        assert not r.has_events()

    def test_session_timeout(self):
        times = iter([0.0, 6.0])
        r = ActionRecorder(time_fn=lambda: next(times))
        r.record(CharacterAction(char="a"), "play")
        r.record(CharacterAction(char="b"), "play")
        # First event should be cleared due to 6s gap (> 5s timeout)
        blocks = r.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].char == "b"

    def test_timing_quantization(self):
        times = iter([0.0, 0.1, 0.5])
        r = ActionRecorder(time_fn=lambda: next(times))
        r.record(CharacterAction(char="a"), "play")
        r.record(CharacterAction(char="b"), "play")
        r.record(CharacterAction(char="c"), "play")
        blocks = r.get_blocks()
        assert len(blocks) == 3
        # a->b gap is 0.1s (level 1: tiny)
        assert blocks[0].gap_level == 1
        # b->c gap is 0.4s (level 2-3 range)
        assert blocks[1].gap_level in (2, 3)
        # last block has no gap
        assert blocks[2].gap_level == 0

    def test_max_recording_trim(self):
        """Events older than 30s from the latest are trimmed."""
        times = iter([0.0, 31.0])
        r = ActionRecorder(time_fn=lambda: next(times))
        r.record(CharacterAction(char="a"), "play")
        r.record(CharacterAction(char="b"), "play")
        blocks = r.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].char == "b"

    def test_clear(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(CharacterAction(char="a"), "play")
        r.clear()
        assert not r.has_events()

    def test_source_mode_play(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(CharacterAction(char="a"), "play")
        assert r.source_mode == "play"

    def test_source_mode_doodle(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(CharacterAction(char="a"), "doodle")
        assert r.source_mode == "doodle"

    def test_source_mode_majority(self):
        t = 0.0
        def tick():
            nonlocal t
            t += 0.1
            return t
        r = ActionRecorder(time_fn=tick)
        r.record(CharacterAction(char="a"), "play")
        r.record(CharacterAction(char="b"), "doodle")
        r.record(CharacterAction(char="c"), "doodle")
        assert r.source_mode == "doodle"


# =============================================================================
# PLAYBACK TESTS
# =============================================================================

class TestBlocksToDemoActions:
    def test_empty_blocks(self):
        actions = blocks_to_demo_actions([])
        assert actions == []

    def test_single_key_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0)]
        actions = blocks_to_demo_actions(blocks, "play")
        # Should have: SwitchMode + TypeText
        assert len(actions) == 2
        assert isinstance(actions[0], SwitchMode)
        assert actions[0].mode == "play"
        assert isinstance(actions[1], TypeText)
        assert actions[1].text == "a"

    def test_arrow_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.ARROW, direction="up", gap_level=0)]
        actions = blocks_to_demo_actions(blocks, "doodle")
        assert isinstance(actions[0], SwitchMode)
        assert actions[0].mode == "doodle"
        assert isinstance(actions[1], PressKey)
        assert actions[1].key == "up"

    def test_control_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.CONTROL, control="enter", gap_level=0)]
        actions = blocks_to_demo_actions(blocks)
        assert isinstance(actions[1], PressKey)
        assert actions[1].key == "enter"

    def test_gap_produces_pause(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=2),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        # SwitchMode, TypeText(a), Pause, TypeText(b)
        assert len(actions) == 4
        assert isinstance(actions[2], Pause)
        assert actions[2].duration > 0

    def test_no_pause_for_zero_gap(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        # SwitchMode, TypeText(a), TypeText(b) - no Pause
        assert len(actions) == 3
        assert not any(isinstance(a, Pause) for a in actions)

    def test_repeat_block_doubles_section(self):
        """[A][B][×2] should produce A B A B."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2, gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        # SwitchMode, then A B A B (2 repetitions)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        chars = [a.text for a in type_actions]
        assert chars == ["a", "b", "a", "b"]

    def test_repeat_block_triples_section(self):
        """[A][×3] should produce A A A."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3, gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        assert len(type_actions) == 3
        assert all(a.text == "a" for a in type_actions)

    def test_repeat_with_trailing_blocks(self):
        """[A][×2][B] should produce A A B."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2, gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        chars = [a.text for a in type_actions]
        assert chars == ["a", "a", "b"]

    def test_multiple_repeat_blocks(self):
        """[A][×2][B][×3] should produce A A B B B."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2, gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3, gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        chars = [a.text for a in type_actions]
        assert chars == ["a", "a", "b", "b", "b"]

    def test_repeat_preserves_pauses(self):
        """Pauses within repeated sections should be preserved."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=2),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2, gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        pause_actions = [a for a in actions if isinstance(a, Pause)]
        # Each repetition of A has a pause after it (gap_level=2)
        assert len(pause_actions) == 2

    def test_repeat_block_with_own_gap(self):
        """Repeat block's own gap adds a pause between sections."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2, gap_level=3),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        actions = blocks_to_demo_actions(blocks)
        # There should be a pause between the repeated section and B
        pause_actions = [a for a in actions if isinstance(a, Pause)]
        assert len(pause_actions) >= 1


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    def test_round_trip_key(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="q", gap_level=2,
                               source_mode="play")]
        json_str = blocks_to_json(blocks, "play")
        restored, mode = blocks_from_json(json_str)
        assert mode == "play"
        assert len(restored) == 1
        assert restored[0].type == ProgramBlockType.KEY
        assert restored[0].char == "q"
        assert restored[0].gap_level == 2

    def test_round_trip_arrow(self):
        blocks = [ProgramBlock(type=ProgramBlockType.ARROW, direction="left",
                               gap_level=3)]
        json_str = blocks_to_json(blocks)
        restored, _ = blocks_from_json(json_str)
        assert restored[0].direction == "left"
        assert restored[0].gap_level == 3

    def test_round_trip_control(self):
        blocks = [ProgramBlock(type=ProgramBlockType.CONTROL, control="enter",
                               gap_level=1)]
        json_str = blocks_to_json(blocks)
        restored, _ = blocks_from_json(json_str)
        assert restored[0].control == "enter"

    def test_round_trip_emoji(self):
        blocks = [ProgramBlock(type=ProgramBlockType.EMOJI, char="🐱",
                               gap_level=0)]
        json_str = blocks_to_json(blocks)
        restored, _ = blocks_from_json(json_str)
        assert restored[0].type == ProgramBlockType.EMOJI
        assert restored[0].char == "🐱"

    def test_round_trip_multiple(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=1),
            ProgramBlock(type=ProgramBlockType.ARROW, direction="up", gap_level=2),
            ProgramBlock(type=ProgramBlockType.CONTROL, control="space", gap_level=0),
        ]
        json_str = blocks_to_json(blocks, "doodle")
        restored, mode = blocks_from_json(json_str)
        assert mode == "doodle"
        assert len(restored) == 3
        assert restored[0].char == "a"
        assert restored[1].direction == "up"
        assert restored[2].control == "space"

    def test_json_has_saved_at(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="x")]
        json_str = blocks_to_json(blocks)
        data = json.loads(json_str)
        assert "saved_at" in data

    def test_round_trip_repeat(self):
        blocks = [ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=5,
                               gap_level=2)]
        json_str = blocks_to_json(blocks)
        restored, _ = blocks_from_json(json_str)
        assert len(restored) == 1
        assert restored[0].type == ProgramBlockType.REPEAT
        assert restored[0].repeat_count == 5
        assert restored[0].gap_level == 2

    def test_round_trip_mixed_with_repeat(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=1),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3, gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        json_str = blocks_to_json(blocks, "play")
        restored, mode = blocks_from_json(json_str)
        assert mode == "play"
        assert len(restored) == 3
        assert restored[0].type == ProgramBlockType.KEY
        assert restored[1].type == ProgramBlockType.REPEAT
        assert restored[1].repeat_count == 3
        assert restored[2].type == ProgramBlockType.KEY

    def test_empty_blocks_round_trip(self):
        json_str = blocks_to_json([])
        restored, _ = blocks_from_json(json_str)
        assert restored == []


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    def test_single_action_recording(self):
        r = ActionRecorder(time_fn=lambda: 0.0)
        r.record(CharacterAction(char="x"), "play")
        blocks = r.get_blocks()
        assert len(blocks) == 1
        assert blocks[0].gap_level == 0  # last block, no trailing gap

    def test_key_color_uppercase(self):
        """Uppercase characters should still map to the right row."""
        assert key_color("Q") == KEY_COLOR_RED
        assert key_color("A") == KEY_COLOR_YELLOW
        assert key_color("Z") == KEY_COLOR_BLUE

    def test_control_color_unknown(self):
        """Unknown control actions get default gray."""
        assert control_color("unknown") == SPACE_COLOR

    def test_block_source_mode_preserved(self):
        t = 0.0
        r = ActionRecorder(time_fn=lambda: t)
        r.record(CharacterAction(char="a"), "doodle")
        blocks = r.get_blocks()
        assert blocks[0].source_mode == "doodle"
