"""Tests for code_runner command splitting, fuzzy matching, and resolution."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from purple_tui.code_runner import (
    _split_clauses, _split_commands, _merge_multiword,
)
from purple_tui.fuzzy import fuzzy_match_small


# ---------------------------------------------------------------------------
# _split_clauses
# ---------------------------------------------------------------------------

class TestSplitClauses:
    def test_comma(self):
        assert _split_clauses("turn right, down 3") == ["turn right", "down 3"]

    def test_semicolon(self):
        assert _split_clauses("forward 5; turn left") == ["forward 5", "turn left"]

    def test_pipe(self):
        assert _split_clauses("up 3 | right 2") == ["up 3", "right 2"]

    def test_period(self):
        assert _split_clauses("go 5. turn right") == ["go 5", "turn right"]

    def test_no_separator(self):
        assert _split_clauses("turn right down 3") == ["turn right down 3"]

    def test_empty_clauses_stripped(self):
        assert _split_clauses("forward 5,,turn left") == ["forward 5", "turn left"]

    def test_whitespace_trimmed(self):
        assert _split_clauses("  go 3 , turn left  ") == ["go 3", "turn left"]


# ---------------------------------------------------------------------------
# _split_commands
# ---------------------------------------------------------------------------

class TestSplitCommands:
    def test_single_command(self):
        assert _split_commands("forward 10") == ["forward 10"]

    def test_two_commands(self):
        assert _split_commands("forward 10 turn left") == ["forward 10", "turn left"]

    def test_turn_right_down(self):
        assert _split_commands("turn right down 3") == ["turn right", "down 3"]

    def test_turn_left_forward(self):
        assert _split_commands("turn left forward 5") == ["turn left", "forward 5"]

    def test_direction_direction(self):
        assert _split_commands("right 5 left 3") == ["right 5", "left 3"]

    def test_pen_down_right(self):
        assert _split_commands("pen down right 3") == ["pen down", "right 3"]

    def test_pen_up_forward(self):
        assert _split_commands("pen up forward 10") == ["pen up", "forward 10"]

    def test_three_commands(self):
        assert _split_commands("forward 10 turn left forward 5") == [
            "forward 10", "turn left", "forward 5",
        ]

    def test_turn_around(self):
        assert _split_commands("turn around forward 5") == ["turn around", "forward 5"]

    def test_bare_turn_right(self):
        assert _split_commands("turn right") == ["turn right"]

    def test_case_insensitive(self):
        assert _split_commands("Turn Right Down 3") == ["Turn Right", "Down 3"]

    def test_direction_then_turn(self):
        assert _split_commands("right 3 turn left") == ["right 3", "turn left"]

    def test_no_keywords(self):
        assert _split_commands("hello world") == ["hello world"]

    def test_repeat_forward_turn(self):
        assert _split_commands("repeat 4 forward 20") == ["repeat 4", "forward 20"]

    # New keyword tests
    def test_spin_forward(self):
        assert _split_commands("spin forward 5") == ["spin", "forward 5"]

    def test_face_right_forward(self):
        assert _split_commands("face right forward 5") == ["face right", "forward 5"]

    def test_rotate_forward(self):
        assert _split_commands("rotate forward 3") == ["rotate", "forward 3"]

    def test_back_forward(self):
        assert _split_commands("back 3 forward 5") == ["back 3", "forward 5"]

    def test_backward_spin(self):
        assert _split_commands("backward 2 spin") == ["backward 2", "spin"]

    def test_turn_back_forward(self):
        assert _split_commands("turn back forward 5") == ["turn back", "forward 5"]


# ---------------------------------------------------------------------------
# _merge_multiword
# ---------------------------------------------------------------------------

class TestMergeMultiword:
    def test_turn_plus_direction(self):
        assert _merge_multiword(["turn", "right", "down 3"]) == ["turn right", "down 3"]

    def test_pen_plus_down(self):
        assert _merge_multiword(["pen", "down", "right 3"]) == ["pen down", "right 3"]

    def test_pen_plus_up(self):
        assert _merge_multiword(["pen", "up", "forward 5"]) == ["pen up", "forward 5"]

    def test_no_merge_needed(self):
        assert _merge_multiword(["forward 10", "turn left"]) == ["forward 10", "turn left"]

    def test_turn_at_end(self):
        assert _merge_multiword(["forward 5", "turn"]) == ["forward 5", "turn"]

    def test_pen_not_followed_by_direction(self):
        assert _merge_multiword(["pen", "forward 5"]) == ["pen", "forward 5"]

    def test_turn_plus_numeric(self):
        assert _merge_multiword(["turn", "90"]) == ["turn 90"]

    def test_face_plus_direction(self):
        assert _merge_multiword(["face", "right", "forward 5"]) == ["face right", "forward 5"]

    def test_face_plus_up(self):
        assert _merge_multiword(["face", "up"]) == ["face up"]

    def test_face_not_followed_by_number(self):
        assert _merge_multiword(["face", "90"]) == ["face", "90"]

    def test_turn_plus_back(self):
        assert _merge_multiword(["turn", "back", "forward 5"]) == ["turn back", "forward 5"]


# ---------------------------------------------------------------------------
# _fuzzy
# ---------------------------------------------------------------------------

class TestFuzzyMatchSmall:
    def test_exact_match(self):
        assert fuzzy_match_small("forward", ["forward", "turn"]) == "forward"

    def test_typo_match(self):
        assert fuzzy_match_small("forwrd", ["forward", "turn", "left"]) == "forward"

    def test_no_match(self):
        assert fuzzy_match_small("xyzzy", ["forward", "turn"]) is None

    def test_short_word_skipped(self):
        assert fuzzy_match_small("go", ["go", "turn"]) is None

    def test_color_fuzzy(self):
        assert fuzzy_match_small("bleu", ["blue", "red", "green"]) == "blue"

    def test_keymash_no_match(self):
        assert fuzzy_match_small("fdsajkl", ["forward", "turn", "blue"]) is None


# ---------------------------------------------------------------------------
# ArtCodeRunner smart resolution
# ---------------------------------------------------------------------------

class _FakeCanvas:
    """Minimal canvas for testing ArtCodeRunner resolution."""

    def __init__(self):
        self._cursor_x = 0
        self._cursor_y = 0
        self._heading = 'right'
        self._use_heading_cursor = False
        self._grid = {}
        self._painted_positions = set()
        self._last_key_color = "#FF0000"
        self._paint_mode = True
        self._typed_chars = []
        self._painted_chars = []

    @property
    def canvas_width(self):
        return 20

    @property
    def canvas_height(self):
        return 10

    def _mark_cursor_dirty(self): pass
    def _invalidate_all(self): pass
    def _restart_blink(self): pass
    def refresh(self): pass
    def _set_paint_mode(self, on): self._paint_mode = on
    def _move_in_direction(self, d):
        if d == 'right': return self._move_cursor_right()
        if d == 'left': return self._move_cursor_left()
        if d == 'up': return self._move_cursor_up()
        if d == 'down': return self._move_cursor_down()
        return False
    def _move_cursor_right(self):
        if self._cursor_x < self.canvas_width - 1:
            self._cursor_x += 1
            return True
        return False

    def _move_cursor_left(self):
        if self._cursor_x > 0:
            self._cursor_x -= 1
            return True
        return False

    def _move_cursor_up(self):
        if self._cursor_y > 0:
            self._cursor_y -= 1
            return True
        return False

    def _move_cursor_down(self):
        if self._cursor_y < self.canvas_height - 1:
            self._cursor_y += 1
            return True
        return False
    def _paint_at_cursor(self): self._painted_positions.add((self._cursor_x, self._cursor_y))
    def post_message(self, msg): pass

    def type_char(self, ch, direction=None):
        self._typed_chars.append(ch)

    def paint_char(self, ch, direction=None):
        self._painted_chars.append(ch)

    def execute_logo_command(self, action, direction, distance):
        from purple_tui.rooms.art_room import ArtCanvas
        ArtCanvas.execute_logo_command(self, action, direction, distance)

    def turn(self, direction):
        from purple_tui.rooms.art_room import ArtCanvas
        ArtCanvas.turn(self, direction)

    _TURN_RIGHT = {'right': 'down', 'down': 'left', 'left': 'up', 'up': 'right'}
    _TURN_LEFT = {'right': 'up', 'up': 'left', 'left': 'down', 'down': 'right'}


class TestSmartResolution:
    @pytest.fixture
    def canvas(self):
        return _FakeCanvas()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_bare_color_switches(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["blue"]))
        assert canvas._last_key_color != "#FF0000"  # changed from default red
        assert canvas._paint_mode is True

    def test_modified_color(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["dark blue"]))
        assert canvas._last_key_color != "#FF0000"
        assert canvas._paint_mode is True

    def test_color_command_with_modified(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["color dark green"]))
        assert canvas._last_key_color != "#FF0000"

    def test_fuzzy_color_in_command(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["color bleu"]))
        assert canvas._last_key_color != "#FF0000"
        assert len(runner.corrections) > 0

    def test_no_match_does_nothing(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["xyzzyplugh"]))
        assert canvas._typed_chars == []
        assert canvas._painted_chars == []

    def test_write_mode_still_types(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["write on", "hello"]))
        assert canvas._typed_chars == list("hello")

    def test_corrections_recorded(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["color bleu"]))
        assert len(runner.corrections) >= 1
        orig, corrected = runner.corrections[0]
        assert "bleu" in orig
        assert "blue" in corrected

    def test_paint_inline_color(self, canvas):
        """'paint red' should paint one block in red."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint red"]))
        assert len(canvas._painted_chars) == 1  # one block

    def test_paint_inline_text(self, canvas):
        """'paint abc' should paint each char as a block."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint abc"]))
        assert canvas._painted_chars == ['a', 'b', 'c']

    def test_write_inline(self, canvas):
        """'write hello' should type each character."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["write hello"]))
        assert canvas._typed_chars == list("hello")

    def test_fuzzy_turn_arg(self, canvas):
        """'turn rite' should fuzzy match to 'turn right'."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._heading = 'up'
        self._run(runner.run(["turn rite"]))
        assert canvas._heading == 'right'
        assert len(runner.corrections) >= 1

    def test_fuzzy_face_arg(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["face dwon"]))
        assert canvas._heading == 'down'
        assert len(runner.corrections) >= 1

    def test_back_movement(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._cursor_x = 5
        self._run(runner.run(["paint off", "back 3"]))
        assert canvas._cursor_x == 2

    def test_keymash_does_nothing(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["fdsalkfsadjlfads"]))
        assert canvas._typed_chars == []
        assert canvas._painted_chars == []
