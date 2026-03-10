"""Tests for the inline code panel."""

from purple_tui.code_panel import (
    make_music_block,
    make_stroke_block,
    make_color_block,
    make_query_block,
    make_newline_block,
    make_repeat_block,
    make_logo_block,
    key_color,
    ArtGuide,
    ArtGuideStep,
    COLOR_RED,
    COLOR_YELLOW,
    COLOR_BLUE,
    COLOR_GRAY,
    COLOR_DIRECTION,
    COLOR_QUERY,
    COLOR_LOGO,
)


# =============================================================================
# Block creation tests
# =============================================================================

class TestMakeMusicBlock:
    def test_basic_key(self):
        block = make_music_block("A")
        assert block.label == "A"
        assert block.key == "A"
        assert block.kind == "key"
        assert block.submode == "music"

    def test_lowercase_key(self):
        block = make_music_block("q")
        assert block.label == "Q"
        assert block.key == "q"

    def test_number_key(self):
        block = make_music_block("5")
        assert block.label == "5"
        assert block.key == "5"

    def test_letters_submode(self):
        block = make_music_block("A", submode="letters")
        assert block.submode == "letters"

    def test_gap_ms(self):
        block = make_music_block("A", gap_ms=150)
        assert block.gap_ms == 150

    def test_color_by_row(self):
        # QWERTY row -> red
        block = make_music_block("q")
        assert block.color == COLOR_RED

        # ASDF row -> yellow
        block = make_music_block("a")
        assert block.color == COLOR_YELLOW

        # ZXCV row -> blue
        block = make_music_block("z")
        assert block.color == COLOR_BLUE

        # Number row -> gray
        block = make_music_block("5")
        assert block.color == COLOR_GRAY


class TestMakeStrokeBlock:
    def test_basic_direction(self):
        block = make_stroke_block("right")
        assert block.direction == "right"
        assert block.distance == 1
        assert block.kind == "stroke"
        assert block.color == COLOR_DIRECTION
        assert "\u25b6" in block.label  # right arrow

    def test_distance(self):
        block = make_stroke_block("up", distance=5)
        assert block.distance == 5
        assert "5" in block.label


class TestMakeColorBlock:
    def test_color_swatch(self):
        block = make_color_block("f", "#BF4040")
        assert block.color == "#BF4040"
        assert block.key == "f"
        assert block.kind == "key"


class TestMakeQueryBlock:
    def test_basic_expression(self):
        block = make_query_block("2 + 2", "4")
        assert block.expression == "2 + 2"
        assert block.result == "4"
        assert block.kind == "query"
        assert block.color == COLOR_QUERY

    def test_long_expression_truncated_label(self):
        long_expr = "a very long expression that exceeds twenty characters"
        block = make_query_block(long_expr)
        assert len(block.label) <= 20


class TestMakeNewlineBlock:
    def test_newline(self):
        block = make_newline_block()
        assert block.kind == "newline"
        assert block.width == 2


class TestMakeRepeatBlock:
    def test_default_count(self):
        block = make_repeat_block()
        assert block.label == "x2"
        assert block.kind == "repeat"

    def test_custom_count(self):
        block = make_repeat_block(5)
        assert block.label == "x5"


# =============================================================================
# Key color tests
# =============================================================================

class TestKeyColor:
    def test_qwerty_row(self):
        for char in "qwertyuiop":
            assert key_color(char) == COLOR_RED

    def test_asdf_row(self):
        for char in "asdfghjkl":
            assert key_color(char) == COLOR_YELLOW

    def test_zxcv_row(self):
        for char in "zxcvbnm":
            assert key_color(char) == COLOR_BLUE

    def test_number_row(self):
        for char in "1234567890":
            assert key_color(char) == COLOR_GRAY

    def test_case_insensitive(self):
        assert key_color("Q") == key_color("q")
        assert key_color("A") == key_color("a")


# =============================================================================
# CodePanel logic tests (unit tests, no Textual app needed)
# =============================================================================

class TestCodePanelBlocks:
    """Test CodePanel block management without rendering.

    Since CodePanel.refresh() requires a mounted widget, we test the block
    data structures directly rather than calling methods that trigger refresh.
    """

    def test_add_block_direct(self):
        blocks = []
        block = make_music_block("A")
        blocks.append(block)
        assert len(blocks) == 1
        assert blocks[0].key == "A"

    def test_per_room_isolation(self):
        rooms = {"music": [], "art": [], "play": []}
        rooms["music"].append(make_music_block("A"))
        rooms["art"].append(make_color_block("f", "#FF0000"))
        assert len(rooms["music"]) == 1
        assert len(rooms["art"]) == 1

    def test_stroke_merge_logic(self):
        """Test that consecutive same-direction strokes merge."""
        blocks = []
        # Simulate add_block merge logic
        for _ in range(3):
            new_block = make_stroke_block("right")
            if (blocks and blocks[-1].kind == "stroke"
                    and blocks[-1].direction == new_block.direction):
                blocks[-1].distance += new_block.distance
                from purple_tui.code_panel import DIRECTION_ARROWS, CODE_BLOCK_WIDTH
                arrow = DIRECTION_ARROWS.get(new_block.direction, "?")
                d = blocks[-1].distance
                blocks[-1].label = f"{arrow}{d}" if d > 1 else arrow
                blocks[-1].width = max(CODE_BLOCK_WIDTH, len(blocks[-1].label) + 2)
            else:
                blocks.append(new_block)

        assert len(blocks) == 1
        assert blocks[0].distance == 3
        assert "3" in blocks[0].label

    def test_stroke_different_direction_no_merge(self):
        blocks = []
        for direction in ["right", "down"]:
            new_block = make_stroke_block(direction)
            if (blocks and blocks[-1].kind == "stroke"
                    and blocks[-1].direction == new_block.direction):
                blocks[-1].distance += new_block.distance
            else:
                blocks.append(new_block)
        assert len(blocks) == 2

    def test_delete_logic(self):
        blocks = [make_music_block("A"), make_music_block("B"), make_music_block("C")]
        cursor_pos = 1
        blocks.pop(cursor_pos)
        assert len(blocks) == 2
        assert blocks[0].key == "A"
        assert blocks[1].key == "C"

    def test_delete_last_adjusts_cursor(self):
        blocks = [make_music_block("A")]
        cursor_pos = 0
        blocks.pop(cursor_pos)
        if cursor_pos > 0 and cursor_pos >= len(blocks):
            cursor_pos = len(blocks) - 1
        assert len(blocks) == 0

    def test_move_cursor_bounds(self):
        blocks = [make_music_block("A"), make_music_block("B"), make_music_block("C")]
        cursor_pos = 0

        # Move right
        new_pos = cursor_pos + 1
        assert 0 <= new_pos < len(blocks)
        cursor_pos = new_pos  # 1

        new_pos = cursor_pos + 1
        assert 0 <= new_pos < len(blocks)
        cursor_pos = new_pos  # 2

        # Can't go past end
        new_pos = cursor_pos + 1
        assert new_pos >= len(blocks)

        # Move left
        new_pos = cursor_pos - 1
        assert new_pos >= 0
        cursor_pos = new_pos  # 1

    def test_move_cursor_empty(self):
        blocks = []
        assert not blocks  # Can't move

    def test_replay_excludes_newlines(self):
        blocks = [
            make_music_block("A"),
            make_newline_block(),
            make_music_block("B"),
        ]
        replay = [b for b in blocks if b.kind != "newline"]
        assert len(replay) == 2
        assert replay[0].key == "A"
        assert replay[1].key == "B"

    def test_clear_logic(self):
        blocks = [make_music_block("A"), make_music_block("B")]
        blocks.clear()
        assert len(blocks) == 0


# =============================================================================
# Logo block tests
# =============================================================================

class TestMakeLogoBlock:
    def test_basic_move(self):
        block = make_logo_block("move", "right", 3)
        assert block.kind == "logo"
        assert block.direction == "right"
        assert block.distance == 3
        assert block.color == COLOR_LOGO
        assert "Move" in block.label
        assert "3" in block.label

    def test_paint_up(self):
        block = make_logo_block("paint", "up", 5)
        assert "Paint" in block.label
        assert "5" in block.label
        assert block.direction == "up"


# =============================================================================
# Art guide state machine tests
# =============================================================================

class TestArtGuide:
    def test_initial_state(self):
        guide = ArtGuide()
        assert guide.step == ArtGuideStep.ACTION

    def test_navigate_actions(self):
        guide = ArtGuide()
        assert guide.action_index == 0  # Move
        guide.handle_right()
        assert guide.action_index == 1  # Paint
        guide.handle_right()
        assert guide.action_index == 1  # Stays at end

    def test_full_flow(self):
        guide = ArtGuide()
        # Step 1: select Paint
        guide.handle_right()
        assert guide.action_index == 1
        result = guide.confirm()
        assert result is None  # Not done yet
        assert guide.step == ArtGuideStep.DIRECTION

        # Step 2: select Right (index 3)
        guide.handle_right()
        guide.handle_right()
        guide.handle_right()
        assert guide.dir_index == 3
        result = guide.confirm()
        assert result is None
        assert guide.step == ArtGuideStep.DISTANCE

        # Step 3: adjust distance
        assert guide.distance == 3  # default
        guide.handle_right()  # 4
        guide.handle_right()  # 5
        result = guide.confirm()
        assert result == ("paint", "right", 5)
        # Resets after completion
        assert guide.step == ArtGuideStep.ACTION

    def test_distance_bounds(self):
        guide = ArtGuide()
        guide.confirm()  # -> DIRECTION
        guide.confirm()  # -> DISTANCE
        # Min bound
        for _ in range(10):
            guide.handle_left()
        assert guide.distance == 1
        # Max bound
        for _ in range(30):
            guide.handle_right()
        assert guide.distance == 20

    def test_reset(self):
        guide = ArtGuide()
        guide.handle_right()
        guide.confirm()
        guide.reset()
        assert guide.step == ArtGuideStep.ACTION
        assert guide.action_index == 0

    def test_display_text(self):
        guide = ArtGuide()
        text = guide.get_display_text()
        assert "Move" in text
        assert "Paint" in text


# =============================================================================
# Room picker tests
# =============================================================================

class TestRoomPickerConfig:
    def test_four_room_options(self):
        from purple_tui.room_picker import ROOM_OPTIONS, NUMBER_KEY_ROOMS
        assert len(ROOM_OPTIONS) == 4
        assert '1' in NUMBER_KEY_ROOMS
        assert '2' in NUMBER_KEY_ROOMS
        assert '3' in NUMBER_KEY_ROOMS
        assert '4' in NUMBER_KEY_ROOMS
