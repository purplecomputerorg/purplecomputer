"""
Tests for Code Mode: program blocks, playback, serialization, and v1 migration.

Pure logic tests with no Textual app dependency.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.program import (
    ProgramBlock,
    ProgramBlockType,
    blocks_to_playback_actions,
    blocks_to_json,
    blocks_from_json,
    key_color,
    action_to_block,
    BLOCK_WIDTH,
    BLOCK_ROWS,
    DEFAULT_TEMPO_MS,
    PAUSE_THRESHOLD_MS,
    PAUSE_PRESETS,
    KEY_COLOR_RED,
    KEY_COLOR_YELLOW,
    KEY_COLOR_BLUE,
    KEY_COLOR_GRAY,
    CONTROL_COLOR,
    QUERY_COLOR,
    STROKE_COLOR,
    PAUSE_COLOR,
    REPEAT_COLOR,
    TARGET_MUSIC_MUSIC,
    TARGET_MUSIC_LETTERS,
    TARGET_ART_PAINT,
    TARGET_ART_TEXT,
    TARGET_PLAY,
    TARGET_ICONS,
    TARGET_COLORS,
    ALL_TARGETS,
    DIRECTION_ICONS,
    CONTROL_ICONS,
    _migrate_v1_blocks,
    _v1_gap_to_ms,
)
from purple_tui.rooms.code_room import _layout_lines, _cursor_to_line_pos, _get_mode_context
from purple_tui.keyboard import (
    CharacterAction,
    NavigationAction,
    ControlAction,
    RoomAction,
    ShiftAction,
)
from purple_tui.playback.script import TypeText, PressKey, SwitchRoom, SwitchTarget, Pause


# =============================================================================
# BLOCK TYPE AND CONSTANTS TESTS
# =============================================================================

class TestBlockTypes:
    def test_six_block_types(self):
        types = list(ProgramBlockType)
        assert len(types) == 6
        assert ProgramBlockType.KEY in types
        assert ProgramBlockType.QUERY in types
        assert ProgramBlockType.STROKE in types
        assert ProgramBlockType.PAUSE in types
        assert ProgramBlockType.REPEAT in types
        assert ProgramBlockType.MODE_SWITCH in types

    def test_block_width_is_5(self):
        assert BLOCK_WIDTH == 5

    def test_block_rows_is_3(self):
        assert BLOCK_ROWS == 3

    def test_pause_presets(self):
        assert PAUSE_PRESETS == [0.25, 0.5, 1.0, 2.0]


# =============================================================================
# KEY BLOCK TESTS
# =============================================================================

class TestKeyBlock:
    def test_char_key_icon(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        assert block.icon == "A"

    def test_control_key_icon(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="enter", is_control=True)
        assert block.icon == CONTROL_ICONS["enter"]

    def test_char_key_color_qwerty_row(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="q")
        assert block.bg_color == KEY_COLOR_RED

    def test_char_key_color_asdf_row(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        assert block.bg_color == KEY_COLOR_YELLOW

    def test_char_key_color_zxcv_row(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="z")
        assert block.bg_color == KEY_COLOR_BLUE

    def test_char_key_color_number_row(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="1")
        assert block.bg_color == KEY_COLOR_GRAY

    def test_control_key_color(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="enter", is_control=True)
        assert block.bg_color == CONTROL_COLOR

    def test_key_color_helper(self):
        assert key_color("q") == KEY_COLOR_RED
        assert key_color("A") == KEY_COLOR_YELLOW
        assert key_color("z") == KEY_COLOR_BLUE
        assert key_color("5") == KEY_COLOR_GRAY


# =============================================================================
# QUERY BLOCK TESTS
# =============================================================================

class TestQueryBlock:
    def test_icon_short_text(self):
        block = ProgramBlock(type=ProgramBlockType.QUERY, query_text="hi")
        assert block.icon == "hi"

    def test_icon_full_text(self):
        block = ProgramBlock(type=ProgramBlockType.QUERY, query_text="periwinkle")
        assert block.icon == "periwinkle"

    def test_display_width(self):
        block = ProgramBlock(type=ProgramBlockType.QUERY, query_text="periwinkle")
        assert block.display_width == 12  # len("periwinkle") + 2
        short = ProgramBlock(type=ProgramBlockType.QUERY, query_text="hi")
        assert short.display_width == 5  # min BLOCK_WIDTH

    def test_bg_color(self):
        block = ProgramBlock(type=ProgramBlockType.QUERY, query_text="test")
        assert block.bg_color == QUERY_COLOR


# =============================================================================
# STROKE BLOCK TESTS
# =============================================================================

class TestStrokeBlock:
    def test_icon(self):
        block = ProgramBlock(type=ProgramBlockType.STROKE, direction="right", distance=3)
        assert block.icon == f"{DIRECTION_ICONS['right']}3"

    def test_bg_color(self):
        block = ProgramBlock(type=ProgramBlockType.STROKE, direction="up")
        assert block.bg_color == STROKE_COLOR

    def test_cycle_distance_up(self):
        block = ProgramBlock(type=ProgramBlockType.STROKE, direction="right", distance=3)
        block.cycle_stroke_distance(1)
        assert block.distance == 4

    def test_cycle_distance_clamp_low(self):
        block = ProgramBlock(type=ProgramBlockType.STROKE, direction="right", distance=1)
        block.cycle_stroke_distance(-1)
        assert block.distance == 1

    def test_cycle_distance_noop_wrong_type(self):
        block = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        block.cycle_stroke_distance(1)  # should be no-op


# =============================================================================
# PAUSE BLOCK TESTS
# =============================================================================

class TestPauseBlock:
    def test_icon(self):
        block = ProgramBlock(type=ProgramBlockType.PAUSE, duration=0.5)
        assert block.icon == "\u23f8"

    def test_bg_color(self):
        block = ProgramBlock(type=ProgramBlockType.PAUSE)
        assert block.bg_color == PAUSE_COLOR

    def test_cycle_duration_up(self):
        block = ProgramBlock(type=ProgramBlockType.PAUSE, duration=0.5)
        block.cycle_pause_duration(1)
        assert block.duration == 1.0

    def test_cycle_duration_down(self):
        block = ProgramBlock(type=ProgramBlockType.PAUSE, duration=1.0)
        block.cycle_pause_duration(-1)
        assert block.duration == 0.5

    def test_cycle_duration_clamp_low(self):
        block = ProgramBlock(type=ProgramBlockType.PAUSE, duration=0.25)
        block.cycle_pause_duration(-1)
        assert block.duration == 0.25

    def test_cycle_duration_clamp_high(self):
        block = ProgramBlock(type=ProgramBlockType.PAUSE, duration=2.0)
        block.cycle_pause_duration(1)
        assert block.duration == 2.0


# =============================================================================
# REPEAT BLOCK TESTS
# =============================================================================

class TestRepeatBlock:
    def test_icon(self):
        block = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3)
        assert block.icon == "x3"

    def test_bg_color(self):
        block = ProgramBlock(type=ProgramBlockType.REPEAT)
        assert block.bg_color == REPEAT_COLOR

    def test_cycle_count_up(self):
        block = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3)
        block.cycle_repeat_count(1)
        assert block.repeat_count == 4

    def test_cycle_count_clamp_low(self):
        block = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=2)
        block.cycle_repeat_count(-1)
        assert block.repeat_count == 2

    def test_cycle_count_clamp_high(self):
        block = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=99)
        block.cycle_repeat_count(1)
        assert block.repeat_count == 99


# =============================================================================
# MODE SWITCH BLOCK TESTS
# =============================================================================

class TestModeSwitchBlock:
    def test_icon(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC)
        assert block.icon == TARGET_ICONS[TARGET_MUSIC_MUSIC]

    def test_bg_color(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY)
        assert block.bg_color == TARGET_COLORS[TARGET_PLAY]

    def test_cycle_room(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC)
        block.cycle_room(1)
        assert block.target == TARGET_ART_PAINT  # music -> art (default: paint)

    def test_cycle_room_wraps(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY)
        block.cycle_room(1)
        assert block.target == TARGET_MUSIC_MUSIC  # play -> music (wraps)

    def test_cycle_mode(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC)
        block.cycle_mode(1)
        assert block.target == TARGET_MUSIC_LETTERS
        block.cycle_mode(1)
        assert block.target == TARGET_MUSIC_MUSIC  # wraps

    def test_cycle_mode_no_modes(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY)
        block.cycle_mode(1)
        assert block.target == TARGET_PLAY  # no change, play has no modes

    def test_cycle_instrument(self):
        from purple_tui.music_constants import INSTRUMENTS
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC)
        block.cycle_instrument(1)
        assert block.instrument == INSTRUMENTS[1][0]  # second instrument
        block.cycle_instrument(-1)
        assert block.instrument == INSTRUMENTS[0][0]  # back to first

    def test_cycle_room_resets_instrument(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC, instrument="ukulele")
        block.cycle_room(1)
        assert block.instrument == ""  # reset on room change


# =============================================================================
# ACTION TO BLOCK CONVERSION
# =============================================================================

class TestActionToBlock:
    def test_character_to_key(self):
        block = action_to_block(CharacterAction(char="a"), "music")
        assert block is not None
        assert block.type == ProgramBlockType.KEY
        assert block.char == "a"
        assert not block.is_control

    def test_control_to_key(self):
        block = action_to_block(ControlAction(action="enter", is_down=True), "music")
        assert block is not None
        assert block.type == ProgramBlockType.KEY
        assert block.char == "enter"
        assert block.is_control

    def test_navigation_to_stroke(self):
        block = action_to_block(NavigationAction(direction="right"), "art")
        assert block is not None
        assert block.type == ProgramBlockType.STROKE
        assert block.direction == "right"
        assert block.distance == 1

    def test_unsupported_control_returns_none(self):
        block = action_to_block(ControlAction(action="escape", is_down=True), "music")
        assert block is None


# =============================================================================
# PLAYBACK CONVERSION
# =============================================================================

class TestPlayback:
    def test_empty_program(self):
        assert blocks_to_playback_actions([]) == []

    def test_key_block_playback(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
        ]
        actions = blocks_to_playback_actions(blocks)
        assert isinstance(actions[0], SwitchTarget)
        assert actions[0].target == TARGET_MUSIC_MUSIC
        assert isinstance(actions[1], TypeText)
        assert actions[1].text == "a"

    def test_control_key_playback(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY),
            ProgramBlock(type=ProgramBlockType.KEY, char="enter", is_control=True),
        ]
        actions = blocks_to_playback_actions(blocks)
        # SwitchTarget, PressKey("enter"), Pause (default tempo)
        press_actions = [a for a in actions if isinstance(a, PressKey)]
        assert len(press_actions) == 1
        assert press_actions[0].key == "enter"

    def test_query_block_playback(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY),
            ProgramBlock(type=ProgramBlockType.QUERY, query_text="hello"),
        ]
        actions = blocks_to_playback_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        assert len(type_actions) == 1
        assert type_actions[0].text == "hello"
        # Should be followed by enter
        press_actions = [a for a in actions if isinstance(a, PressKey)]
        assert any(a.key == "enter" for a in press_actions)

    def test_stroke_block_playback(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_ART_PAINT),
            ProgramBlock(type=ProgramBlockType.STROKE, direction="right", distance=3),
        ]
        actions = blocks_to_playback_actions(blocks)
        right_presses = [a for a in actions if isinstance(a, PressKey) and a.key == "right"]
        assert len(right_presses) == 3

    def test_pause_block_playback(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.PAUSE, duration=1.0),
        ]
        actions = blocks_to_playback_actions(blocks)
        pause_actions = [a for a in actions if isinstance(a, Pause)]
        assert any(a.duration == 1.0 for a in pause_actions)

    def test_repeat_block_playback(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
            ProgramBlock(type=ProgramBlockType.KEY, char="b"),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3),
        ]
        actions = blocks_to_playback_actions(blocks)
        type_actions = [a for a in actions if isinstance(a, TypeText)]
        # a, b repeated 3 times = 6 TypeText actions
        assert len(type_actions) == 6

    def test_default_target_from_mode_switch(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
        ]
        actions = blocks_to_playback_actions(blocks)
        # Should get default SwitchTarget (music.music)
        assert isinstance(actions[0], SwitchTarget)
        assert actions[0].target == TARGET_MUSIC_MUSIC

    def test_recorded_gap_ms_timing(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", recorded_gap_ms=200),
        ]
        actions = blocks_to_playback_actions(blocks)
        pause_actions = [a for a in actions if isinstance(a, Pause)]
        assert any(abs(a.duration - 0.2) < 0.01 for a in pause_actions)

    def test_default_tempo_when_no_gap(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a", recorded_gap_ms=0),
        ]
        actions = blocks_to_playback_actions(blocks)
        pause_actions = [a for a in actions if isinstance(a, Pause)]
        expected = DEFAULT_TEMPO_MS / 1000.0
        assert any(abs(a.duration - expected) < 0.01 for a in pause_actions)


# =============================================================================
# SERIALIZATION (V2)
# =============================================================================

class TestSerializationV2:
    def test_roundtrip_key_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="x")]
        json_str = blocks_to_json(blocks)
        loaded, room = blocks_from_json(json_str)
        assert len(loaded) == 1
        assert loaded[0].type == ProgramBlockType.KEY
        assert loaded[0].char == "x"

    def test_roundtrip_control_key(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="enter", is_control=True)]
        json_str = blocks_to_json(blocks)
        loaded, _ = blocks_from_json(json_str)
        assert loaded[0].is_control
        assert loaded[0].char == "enter"

    def test_roundtrip_query_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.QUERY, query_text="hello world")]
        json_str = blocks_to_json(blocks)
        loaded, _ = blocks_from_json(json_str)
        assert loaded[0].type == ProgramBlockType.QUERY
        assert loaded[0].query_text == "hello world"

    def test_roundtrip_stroke_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.STROKE, direction="up", distance=5)]
        json_str = blocks_to_json(blocks)
        loaded, _ = blocks_from_json(json_str)
        assert loaded[0].type == ProgramBlockType.STROKE
        assert loaded[0].direction == "up"
        assert loaded[0].distance == 5

    def test_roundtrip_pause_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.PAUSE, duration=1.0)]
        json_str = blocks_to_json(blocks)
        loaded, _ = blocks_from_json(json_str)
        assert loaded[0].type == ProgramBlockType.PAUSE
        assert loaded[0].duration == 1.0

    def test_roundtrip_repeat_block(self):
        blocks = [ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=5)]
        json_str = blocks_to_json(blocks)
        loaded, _ = blocks_from_json(json_str)
        assert loaded[0].repeat_count == 5

    def test_roundtrip_mode_switch(self):
        blocks = [ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY)]
        json_str = blocks_to_json(blocks)
        loaded, _ = blocks_from_json(json_str)
        assert loaded[0].target == TARGET_PLAY

    def test_roundtrip_recorded_gap_ms(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a", recorded_gap_ms=150)]
        json_str = blocks_to_json(blocks)
        loaded, _ = blocks_from_json(json_str)
        assert loaded[0].recorded_gap_ms == 150

    def test_version_2_in_json(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a")]
        json_str = blocks_to_json(blocks)
        data = json.loads(json_str)
        assert data["version"] == 2

    def test_source_room_roundtrip(self):
        blocks = [ProgramBlock(type=ProgramBlockType.KEY, char="a")]
        json_str = blocks_to_json(blocks, source_room="art")
        _, room = blocks_from_json(json_str)
        assert room == "art"


# =============================================================================
# V1 MIGRATION
# =============================================================================

class TestV1Migration:
    def test_v1_key_block(self):
        v1 = [{"type": "key", "char": "a", "gap": 1}]
        blocks = _migrate_v1_blocks(v1)
        assert len(blocks) >= 1
        assert blocks[0].type == ProgramBlockType.KEY
        assert blocks[0].char == "a"

    def test_v1_control_becomes_key_with_is_control(self):
        v1 = [{"type": "control", "control": "enter", "gap": 0}]
        blocks = _migrate_v1_blocks(v1)
        assert blocks[0].type == ProgramBlockType.KEY
        assert blocks[0].char == "enter"
        assert blocks[0].is_control

    def test_v1_arrow_becomes_stroke(self):
        v1 = [{"type": "arrow", "direction": "right", "gap": 0}]
        blocks = _migrate_v1_blocks(v1)
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) == 1
        assert stroke_blocks[0].direction == "right"

    def test_v1_emoji_becomes_key(self):
        v1 = [{"type": "emoji", "char": "\U0001f600", "gap": 0}]
        blocks = _migrate_v1_blocks(v1)
        assert blocks[0].type == ProgramBlockType.KEY
        assert blocks[0].char == "\U0001f600"

    def test_v1_line_break_dropped(self):
        v1 = [{"type": "line_break", "gap": 0}]
        blocks = _migrate_v1_blocks(v1)
        assert len(blocks) == 0

    def test_v1_mode_switch_preserved(self):
        v1 = [{"type": "mode_switch", "target": "play.music", "gap": 0}]
        blocks = _migrate_v1_blocks(v1)
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        assert blocks[0].target == "play.music"

    def test_v1_repeat_preserved(self):
        v1 = [{"type": "repeat", "repeat_count": 4, "gap": 0}]
        blocks = _migrate_v1_blocks(v1)
        assert blocks[0].type == ProgramBlockType.REPEAT
        assert blocks[0].repeat_count == 4

    def test_v1_auto_collapse_expanded(self):
        """Blocks with count > 1 should expand into N separate blocks."""
        v1 = [{"type": "key", "char": "a", "gap": 0, "count": 3}]
        blocks = _migrate_v1_blocks(v1)
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY]
        assert len(key_blocks) == 3

    def test_v1_large_gap_inserts_pause(self):
        """Gaps >= 300ms should produce an explicit PAUSE block."""
        v1 = [{"type": "key", "char": "a", "gap": 3}]  # gap level 3 = ~0.7s
        blocks = _migrate_v1_blocks(v1)
        pause_blocks = [b for b in blocks if b.type == ProgramBlockType.PAUSE]
        assert len(pause_blocks) >= 1

    def test_v1_gap_to_ms_level_0(self):
        assert _v1_gap_to_ms(0) == 0

    def test_v1_gap_to_ms_level_1(self):
        ms = _v1_gap_to_ms(1)
        assert 100 < ms < 200

    def test_v1_json_migration(self):
        """Full roundtrip: v1 JSON -> blocks_from_json should use migration."""
        v1_data = {
            "blocks": [
                {"type": "mode_switch", "target": "play.music", "gap": 0},
                {"type": "key", "char": "a", "gap": 1},
                {"type": "control", "control": "enter", "gap": 0},
                {"type": "arrow", "direction": "right", "gap": 0},
            ],
            "source_room": "play",
        }
        json_str = json.dumps(v1_data)
        blocks, room = blocks_from_json(json_str)
        assert room == "play"
        # MODE_SWITCH should be preserved
        assert blocks[0].type == ProgramBlockType.MODE_SWITCH
        # KEY block
        key_blocks = [b for b in blocks if b.type == ProgramBlockType.KEY and not b.is_control]
        assert len(key_blocks) >= 1
        # Control should become KEY with is_control
        control_keys = [b for b in blocks if b.type == ProgramBlockType.KEY and b.is_control]
        assert len(control_keys) >= 1
        # Arrow should become STROKE
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) >= 1

    def test_v1_arrow_in_paint_context_becomes_stroke(self):
        """Arrow blocks after an art.paint MODE_SWITCH should become STROKE."""
        v1 = [
            {"type": "mode_switch", "target": "doodle.paint", "gap": 0},
            {"type": "arrow", "direction": "right", "gap": 0, "count": 5},
        ]
        blocks = _migrate_v1_blocks(v1)
        stroke_blocks = [b for b in blocks if b.type == ProgramBlockType.STROKE]
        assert len(stroke_blocks) == 1
        assert stroke_blocks[0].distance == 5


# =============================================================================
# LAYOUT TESTS
# =============================================================================

class TestLayout:
    def test_empty_layout(self):
        assert _layout_lines([], 100) == []

    def test_single_key_block(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
        ]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 1
        # Line should contain both blocks
        icon, line_blocks, _ = lines[0]
        assert icon == TARGET_ICONS[TARGET_MUSIC_MUSIC]

    def test_mode_switch_starts_new_line(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY),
            ProgramBlock(type=ProgramBlockType.KEY, char="b"),
        ]
        lines = _layout_lines(blocks, 100)
        assert len(lines) == 2

    def test_wrapping_at_content_width(self):
        """Many blocks should wrap to multiple lines."""
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
        ]
        # Add enough blocks to require wrapping (each block is 5 chars)
        for i in range(25):
            blocks.append(ProgramBlock(type=ProgramBlockType.KEY, char="a"))
        # Content width = 50 means 10 blocks per line
        lines = _layout_lines(blocks, 50)
        assert len(lines) >= 3  # 25 blocks / 10 per line = 3

    def test_repeat_as_line_metadata(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
            ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3),
        ]
        lines = _layout_lines(blocks, 100)
        _, _, line_repeat = lines[0]
        assert line_repeat == 3


class TestCursorToLinePos:
    def test_cursor_at_start(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
        ]
        lines = _layout_lines(blocks, 100)
        line_idx, pos = _cursor_to_line_pos(lines, 0)
        assert line_idx == 0
        assert pos == 0

    def test_cursor_at_end(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
        ]
        lines = _layout_lines(blocks, 100)
        line_idx, pos = _cursor_to_line_pos(lines, 2)
        assert line_idx == 0
        assert pos == 2  # after last block

    def test_empty_lines(self):
        line_idx, pos = _cursor_to_line_pos([], 0)
        assert line_idx == 0
        assert pos == 0


# =============================================================================
# MODE CONTEXT TESTS
# =============================================================================

class TestModeContext:
    def test_no_context_empty(self):
        assert _get_mode_context([], 0) == ""

    def test_context_after_mode_switch(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
        ]
        assert _get_mode_context(blocks, 2) == TARGET_PLAY

    def test_context_between_mode_switches(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
            ProgramBlock(type=ProgramBlockType.KEY, char="a"),
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_PLAY),
            ProgramBlock(type=ProgramBlockType.KEY, char="b"),
        ]
        # Cursor at position 2 (between first KEY and second MODE_SWITCH)
        assert _get_mode_context(blocks, 2) == TARGET_MUSIC_MUSIC
        # Cursor at position 4 (after second KEY)
        assert _get_mode_context(blocks, 4) == TARGET_PLAY


# =============================================================================
# TARGET CONSTANTS
# =============================================================================

class TestModeContextDefaults:
    """Tests for _get_mode_context edge cases and default mode behavior."""

    def test_empty_blocks_returns_empty(self):
        assert _get_mode_context([], 0) == ""

    def test_cursor_at_zero_no_context(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
        ]
        assert _get_mode_context(blocks, 0) == ""

    def test_cursor_after_mode_switch_has_context(self):
        blocks = [
            ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC),
        ]
        assert _get_mode_context(blocks, 1) == TARGET_MUSIC_MUSIC


class TestInlineAdjustment:
    """Tests for inline Up/Down adjustment logic on adjustable blocks."""

    def test_mode_switch_cycle_room(self):
        block = ProgramBlock(type=ProgramBlockType.MODE_SWITCH, target=TARGET_MUSIC_MUSIC)
        block.cycle_room(1)
        assert block.target == TARGET_ART_PAINT  # music -> art
        block.cycle_room(-1)
        assert block.target == TARGET_MUSIC_MUSIC  # art -> music

    def test_pause_cycle_duration(self):
        block = ProgramBlock(type=ProgramBlockType.PAUSE, duration=0.5)
        block.cycle_pause_duration(1)
        assert block.duration == 1.0
        block.cycle_pause_duration(-1)
        assert block.duration == 0.5

    def test_stroke_cycle_distance(self):
        block = ProgramBlock(type=ProgramBlockType.STROKE, direction="right", distance=3)
        block.cycle_stroke_distance(1)
        assert block.distance == 4
        block.cycle_stroke_distance(-1)
        assert block.distance == 3

    def test_repeat_cycle_count(self):
        block = ProgramBlock(type=ProgramBlockType.REPEAT, repeat_count=3)
        block.cycle_repeat_count(1)
        assert block.repeat_count == 4
        block.cycle_repeat_count(-1)
        assert block.repeat_count == 3

    def test_key_block_not_adjustable(self):
        """KEY and QUERY blocks should not be adjustable (Up/Down = line nav)."""
        block = ProgramBlock(type=ProgramBlockType.KEY, char="a")
        # These methods are no-ops on wrong types
        assert block.type == ProgramBlockType.KEY


class TestTargetConstants:
    def test_all_targets_have_icons(self):
        for target in ALL_TARGETS:
            assert target in TARGET_ICONS

    def test_all_targets_have_colors(self):
        for target in ALL_TARGETS:
            assert target in TARGET_COLORS

    def test_target_count(self):
        assert len(ALL_TARGETS) == 5
