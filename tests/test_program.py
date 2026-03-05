"""
Tests for Code Mode: program blocks, playback, and serialization.

Pure logic tests with no Textual app dependency.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.program import (
    ProgramBlock,
    ProgramBlockType,
    quantize_pause,
    gap_width,
    gap_duration,
    blocks_to_playback_actions,
    blocks_to_json,
    blocks_from_json,
    key_color,
    control_color,
    action_to_block,
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
    TARGET_PLAY_MUSIC,
    TARGET_PLAY_LETTERS,
    TARGET_DOODLE_PAINT,
    TARGET_DOODLE_TEXT,
    TARGET_EXPLORE,
    TARGET_ICONS,
    TARGET_COLORS,
    ALL_TARGETS,
)
from purple_tui.rooms.build_room import _layout_lines, _cursor_to_line_pos
from purple_tui.keyboard import (
    CharacterAction,
    NavigationAction,
    ControlAction,
    RoomAction,
    ShiftAction,
)
from purple_tui.playback.script import TypeText, PressKey, SwitchRoom, SwitchTarget, Pause


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

    def test_cycle_repeat_count_clamps_at_99(self):
        """Repeat max is now 99 (up from 9)."""
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=99)
        b.cycle_repeat_count(1)
        assert b.repeat_count == 99

    def test_cycle_repeat_count_can_reach_99(self):
        """Can increment all the way up to 99."""
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=50)
        b.cycle_repeat_count(1)
        assert b.repeat_count == 51

    def test_repeat_total_width(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, gap_level=0)
        assert b.total_width == 4  # icon only, no gap

    def test_repeat_total_width_with_gap(self):
        b = ProgramBlock(type=ProgramBlockType.REPEAT, gap_level=2)
        assert b.total_width == 4 + 4


# =============================================================================
# MODE_SWITCH BLOCK TESTS
# =============================================================================

class TestModeSwitchBlock:
    def test_mode_switch_icon(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC)
        assert b.icon == TARGET_ICONS[TARGET_PLAY_MUSIC]

    def test_mode_switch_color(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC)
        assert b.bg_color == TARGET_COLORS[TARGET_PLAY_MUSIC]

    def test_mode_switch_explore(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_EXPLORE)
        assert b.icon == TARGET_ICONS[TARGET_EXPLORE]
        assert b.bg_color == TARGET_COLORS[TARGET_EXPLORE]

    def test_mode_switch_doodle_paint(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_DOODLE_PAINT)
        assert b.bg_color == TARGET_COLORS[TARGET_DOODLE_PAINT]

    def test_cycle_target(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=ALL_TARGETS[0])
        b.cycle_target(1)
        assert b.target == ALL_TARGETS[1]

    def test_cycle_target_wraps(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=ALL_TARGETS[-1])
        b.cycle_target(1)
        assert b.target == ALL_TARGETS[0]

    def test_cycle_target_backwards(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=ALL_TARGETS[0])
        b.cycle_target(-1)
        assert b.target == ALL_TARGETS[-1]

    def test_mode_switch_unknown_target(self):
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target="unknown")
        assert b.icon == "?"


# =============================================================================
# PLAYBACK TESTS
# =============================================================================

class TestBlocksToDemoActions:
    def test_empty_blocks(self):
        actions = blocks_to_playback_actions([])
        assert actions == []

    def test_single_key_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a",
                               gap_level=0, source_room="play")]
        actions = blocks_to_playback_actions(blocks)
        # Should have: SwitchTarget + TypeText
        assert len(actions) == 2
        assert isinstance(actions[0], SwitchTarget)
        assert actions[0].target == TARGET_PLAY_MUSIC
        assert isinstance(actions[1], TypeText)
        assert actions[1].text == "a"

    def test_arrow_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.ARROW, direction="up",
                               gap_level=0, source_room="doodle")]
        actions = blocks_to_playback_actions(blocks)
        assert isinstance(actions[0], SwitchTarget)
        assert actions[0].target == "doodle.text"
        assert isinstance(actions[1], PressKey)
        assert actions[1].key == "up"

    def test_control_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.CONTROL, control="enter", gap_level=0)]
        actions = blocks_to_playback_actions(blocks)
        assert isinstance(actions[1], PressKey)
        assert actions[1].key == "enter"

    def test_gap_produces_pause(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=2),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
        # SwitchTarget, TypeText(a), Pause, TypeText(b)
        assert len(actions) == 4
        assert isinstance(actions[2], Pause)
        assert actions[2].duration > 0

    def test_no_pause_for_zero_gap(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
        # SwitchTarget, TypeText(a), TypeText(b)
        assert len(actions) == 3
        assert not any(isinstance(a, Pause) for a in actions)

    def test_repeat_block_doubles_section(self):
        """[A][B][×2] should produce A B A B."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2, gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        chars = [a.text for a in type_actions]
        assert chars == ["a", "b", "a", "b"]

    def test_repeat_block_triples_section(self):
        """[A][×3] should produce A A A."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3, gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
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
        actions = blocks_to_playback_actions(blocks)
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
        actions = blocks_to_playback_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        chars = [a.text for a in type_actions]
        assert chars == ["a", "a", "b", "b", "b"]

    def test_repeat_preserves_pauses(self):
        """Pauses within repeated sections should be preserved."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=2),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2, gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
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
        actions = blocks_to_playback_actions(blocks)
        pause_actions = [a for a in actions if isinstance(a, Pause)]
        assert len(pause_actions) >= 1

    def test_mode_switch_emits_switch_target(self):
        """MODE_SWITCH blocks emit SwitchTarget actions."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_DOODLE_PAINT),
            ProgramBlock(type=ProgramBlockType.ARROW, direction="right", gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
        switch_actions = [a for a in actions if isinstance(a, SwitchTarget)]
        assert len(switch_actions) == 2
        assert switch_actions[0].target == TARGET_PLAY_MUSIC
        assert switch_actions[1].target == TARGET_DOODLE_PAINT

    def test_no_leading_switch_when_first_block_is_mode_switch(self):
        """No extra SwitchTarget at start if blocks begin with MODE_SWITCH."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_EXPLORE),
            ProgramBlock(type=ProgramBlockType.KEY, char="2", gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
        switch_actions = [a for a in actions if isinstance(a, SwitchTarget)]
        assert len(switch_actions) == 1
        assert switch_actions[0].target == TARGET_EXPLORE

    def test_default_target_from_source_room(self):
        """Default target inferred from source_room when no MODE_SWITCH at start."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0,
                         source_room="doodle"),
        ]
        actions = blocks_to_playback_actions(blocks)
        assert isinstance(actions[0], SwitchTarget)
        assert actions[0].target == "doodle.text"


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    def test_round_trip_key(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="q", gap_level=2,
                               source_room="play")]
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

    def test_round_trip_mode_switch(self):
        blocks = [ProgramBlock(type=ProgramBlockType.MODE_SWITCH,
                               target=TARGET_PLAY_MUSIC, gap_level=0)]
        json_str = blocks_to_json(blocks)
        restored, _ = blocks_from_json(json_str)
        assert len(restored) == 1
        assert restored[0].type == ProgramBlockType.MODE_SWITCH
        assert restored[0].target == TARGET_PLAY_MUSIC

    def test_round_trip_mode_switch_with_blocks(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=1),
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_DOODLE_PAINT),
            ProgramBlock(type=ProgramBlockType.ARROW, direction="right", gap_level=0),
        ]
        json_str = blocks_to_json(blocks, "play")
        restored, _ = blocks_from_json(json_str)
        assert len(restored) == 4
        assert restored[0].target == TARGET_PLAY_MUSIC
        assert restored[2].target == TARGET_DOODLE_PAINT


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    def test_action_to_block_character(self):
        block = action_to_block(CharacterAction(char="x"), "play")
        assert block.type == ProgramBlockType.KEY
        assert block.char == "x"

    def test_action_to_block_navigation(self):
        block = action_to_block(NavigationAction(direction="left"), "doodle")
        assert block.type == ProgramBlockType.ARROW
        assert block.direction == "left"

    def test_action_to_block_control(self):
        block = action_to_block(ControlAction(action="enter", is_down=True), "play")
        assert block.type == ProgramBlockType.CONTROL
        assert block.control == "enter"

    def test_action_to_block_ignores_escape(self):
        block = action_to_block(ControlAction(action="escape", is_down=True), "play")
        assert block is None

    def test_key_color_uppercase(self):
        """Uppercase characters should still map to the right row."""
        assert key_color("Q") == KEY_COLOR_RED
        assert key_color("A") == KEY_COLOR_YELLOW
        assert key_color("Z") == KEY_COLOR_BLUE

    def test_control_color_unknown(self):
        """Unknown control actions get default gray."""
        assert control_color("unknown") == SPACE_COLOR

    def test_block_source_room_preserved(self):
        block = action_to_block(CharacterAction(char="a"), "doodle")
        assert block.source_room == "doodle"


# =============================================================================
# LINE LAYOUT TESTS
# =============================================================================

class TestLayoutLines:
    """Tests for _layout_lines and _cursor_to_line_pos from build_mode."""

    def test_empty_blocks(self):
        lines = _layout_lines([], 100)
        assert lines == []

    def test_single_key_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0)]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 1
        icon, line_blocks, line_repeat = lines[0]
        assert icon == ""  # no mode switch, so no icon
        assert len(line_blocks) == 1
        assert line_blocks[0][0] == 0  # block index
        assert line_repeat == 0

    def test_mode_switch_starts_new_line(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 1
        icon, line_blocks, _ = lines[0]
        assert icon == TARGET_ICONS[TARGET_PLAY_MUSIC]
        # MODE_SWITCH + 2 key blocks on same line
        assert len(line_blocks) == 3

    def test_two_mode_switches_create_two_lines(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_EXPLORE),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 2
        assert lines[0][0] == TARGET_ICONS[TARGET_PLAY_MUSIC]
        assert lines[1][0] == TARGET_ICONS[TARGET_EXPLORE]

    def test_line_wraps_on_overflow(self):
        # Each key block with gap_level=0 is 4 chars wide
        # With content_width=10, we can fit 2 blocks (8 chars), 3rd wraps
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="c", gap_level=0),
        ]
        lines = _layout_lines(blocks, 10)
        assert len(lines) == 2
        assert len(lines[0][1]) == 2  # a, b
        assert len(lines[1][1]) == 1  # c (wrapped)

    def test_continuation_line_has_empty_icon(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="c", gap_level=0),
        ]
        lines = _layout_lines(blocks, 10)
        assert lines[0][0] == ""  # first line: no icon (no mode switch)
        assert lines[1][0] == ""  # continuation: also no icon


class TestCursorToLinePos:
    """Tests for _cursor_to_line_pos from build_mode."""

    def test_cursor_on_first_block(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        line_idx, pos = _cursor_to_line_pos(lines, 0)
        assert line_idx == 0
        assert pos == 0

    def test_cursor_on_second_block(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        line_idx, pos = _cursor_to_line_pos(lines, 1)
        assert line_idx == 0
        assert pos == 1

    def test_cursor_on_second_line(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_EXPLORE),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        # Cursor on block index 3 (second "b" key)
        line_idx, pos = _cursor_to_line_pos(lines, 3)
        assert line_idx == 1
        assert pos == 1

    def test_cursor_on_wrapped_line(self):
        # 3 blocks, width=10 => first 2 on line 0, third on line 1
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="c", gap_level=0),
        ]
        lines = _layout_lines(blocks, 10)
        line_idx, pos = _cursor_to_line_pos(lines, 2)
        assert line_idx == 1
        assert pos == 0


# =============================================================================
# BLOCK COUNT TESTS
# =============================================================================

class TestBlockCount:
    def test_block_count_default_is_1(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        assert b.count == 1

    def test_block_count_icon_unchanged(self):
        """Icon stays the same regardless of count (badge is rendered separately)."""
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", count=5)
        assert b.icon == "A"

    def test_block_with_count_serialization_round_trip(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=1, count=5)]
        json_str = blocks_to_json(blocks, "play")
        restored, _ = blocks_from_json(json_str)
        assert restored[0].count == 5
        assert restored[0].char == "a"

    def test_block_count_1_not_serialized(self):
        """Count of 1 is the default and should not be in serialized JSON."""
        import json as json_mod
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a", count=1)]
        json_str = blocks_to_json(blocks, "play")
        data = json_mod.loads(json_str)
        assert "count" not in data["blocks"][0]

    def test_block_count_in_playback(self):
        """A block with count=3 should produce 3 actions."""
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0, count=3)]
        actions = blocks_to_playback_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        assert len(type_actions) == 3
        assert all(a.text == "a" for a in type_actions)

    def test_block_count_with_gap(self):
        """Gap applies after each repetition of a counted block."""
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=2, count=3)]
        actions = blocks_to_playback_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        pause_actions = [a for a in actions if isinstance(a, Pause)]
        assert len(type_actions) == 3
        assert len(pause_actions) == 3  # one pause after each repetition

    def test_matches_same_key(self):
        a = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        assert a.matches(b)

    def test_matches_different_key(self):
        a = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        b = ProgramBlock(type=ProgramBlockType.KEY, char="b")
        assert not a.matches(b)

    def test_matches_same_arrow(self):
        a = ProgramBlock(type=ProgramBlockType.ARROW, direction="left")
        b = ProgramBlock(type=ProgramBlockType.ARROW, direction="left")
        assert a.matches(b)

    def test_matches_different_arrow(self):
        a = ProgramBlock(type=ProgramBlockType.ARROW, direction="left")
        b = ProgramBlock(type=ProgramBlockType.ARROW, direction="right")
        assert not a.matches(b)

    def test_matches_same_control(self):
        a = ProgramBlock(type=ProgramBlockType.CONTROL, control="enter")
        b = ProgramBlock(type=ProgramBlockType.CONTROL, control="enter")
        assert a.matches(b)

    def test_matches_different_type(self):
        a = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        b = ProgramBlock(type=ProgramBlockType.ARROW, direction="left")
        assert not a.matches(b)

    def test_matches_mode_switch_never(self):
        a = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC)
        b = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY_MUSIC)
        assert not a.matches(b)

    def test_matches_emoji_never(self):
        a = ProgramBlock(type=ProgramBlockType.EMOJI, char="x")
        b = ProgramBlock(type=ProgramBlockType.EMOJI, char="x")
        assert not a.matches(b)

    def test_matches_repeat_never(self):
        a = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2)
        b = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2)
        assert not a.matches(b)

    def test_cycle_count_up(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", count=3)
        b.cycle_count(1)
        assert b.count == 4

    def test_cycle_count_down(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", count=3)
        b.cycle_count(-1)
        assert b.count == 2

    def test_cycle_count_clamps_at_1(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", count=1)
        b.cycle_count(-1)
        assert b.count == 1

    def test_cycle_count_clamps_at_99(self):
        b = ProgramBlock(type=ProgramBlockType.KEY, char="a", count=99)
        b.cycle_count(1)
        assert b.count == 99

    def test_repeat_block_serialization_backward_compat(self):
        """Old format: REPEAT blocks stored repeat_count as 'count'.
        New format: uses 'repeat_count'. Both should deserialize correctly."""
        # Old format
        old_json = '{"blocks": [{"type": "repeat", "gap": 0, "count": 5}], "source_room": "play", "saved_at": "2025-01-01"}'
        restored, _ = blocks_from_json(old_json)
        assert restored[0].repeat_count == 5
        assert restored[0].count == 1  # collapse count defaults to 1

        # New format
        new_json = '{"blocks": [{"type": "repeat", "gap": 0, "repeat_count": 5}], "source_room": "play", "saved_at": "2025-01-01"}'
        restored2, _ = blocks_from_json(new_json)
        assert restored2[0].repeat_count == 5


# =============================================================================
# AUTO-COLLAPSE TESTS
# =============================================================================

class TestAutoCollapse:
    def test_recording_collapses_consecutive_same_keys(self):
        """Recording.to_blocks() should collapse consecutive same keys."""
        from purple_tui.recording import Recording

        rec = Recording()
        for i in range(5):
            rec.add_event(
                action=CharacterAction(char="a"),
                room_name="play",
                timestamp=float(i) * 0.01,
            )

        blocks = rec.to_blocks()
        # Should have MODE_SWITCH + 1 collapsed block (not 5 separate blocks)
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        assert len(key_blocks) == 1
        assert key_blocks[0].count == 5
        assert key_blocks[0].char == "a"

    def test_recording_different_keys_not_collapsed(self):
        """Different keys should not collapse."""
        from purple_tui.recording import Recording

        rec = Recording()
        rec.add_event(action=CharacterAction(char="a"), room_name="play", timestamp=0.0)
        rec.add_event(action=CharacterAction(char="b"), room_name="play", timestamp=0.01)

        blocks = rec.to_blocks()
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        assert len(key_blocks) == 2
        assert key_blocks[0].char == "a"
        assert key_blocks[1].char == "b"

    def test_recording_collapses_same_arrows(self):
        """Same arrow keys should collapse."""
        from purple_tui.recording import Recording

        rec = Recording()
        for i in range(3):
            rec.add_event(
                action=NavigationAction(direction="right"),
                room_name="doodle",
                timestamp=float(i) * 0.01,
            )

        blocks = rec.to_blocks()
        arrow_blocks = [b for b in blocks if b.type == ProgramBlockType.ARROW]
        assert len(arrow_blocks) == 1
        assert arrow_blocks[0].count == 3
        assert arrow_blocks[0].direction == "right"

    def test_recording_collapses_same_control(self):
        """Same control actions should collapse."""
        from purple_tui.recording import Recording

        rec = Recording()
        for i in range(4):
            rec.add_event(
                action=ControlAction(action="enter", is_down=True),
                room_name="play",
                timestamp=float(i) * 0.01,
            )

        blocks = rec.to_blocks()
        ctrl_blocks = [b for b in blocks if b.type == ProgramBlockType.CONTROL]
        assert len(ctrl_blocks) == 1
        assert ctrl_blocks[0].count == 4
        assert ctrl_blocks[0].control == "enter"


# =============================================================================
# LINE REPEAT TESTS
# =============================================================================

class TestLineRepeat:
    def test_layout_lines_extracts_repeat_metadata(self):
        """REPEAT block at end of line sets line_repeat in layout."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3, gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 1
        _, _, line_repeat = lines[0]
        assert line_repeat == 3

    def test_layout_lines_no_repeat(self):
        """Lines without REPEAT block have line_repeat=0."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 1
        _, _, line_repeat = lines[0]
        assert line_repeat == 0

    def test_layout_lines_repeat_not_at_end(self):
        """REPEAT block not at end of line: line_repeat is 0."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3, gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
        ]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 1
        _, _, line_repeat = lines[0]
        assert line_repeat == 0

    def test_repeat_block_in_playback_repeats_line(self):
        """REPEAT block repeats preceding section N times in playback."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a", gap_level=0),
            ProgramBlock(type=ProgramBlockType.KEY, char="b", gap_level=0),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3, gap_level=0),
        ]
        actions = blocks_to_playback_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        chars = [a.text for a in type_actions]
        assert chars == ["a", "b", "a", "b", "a", "b"]
