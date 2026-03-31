"""Tests for code_runner command splitting and clause parsing."""

import pytest

from purple_tui.code_runner import _split_clauses, _split_commands, _merge_multiword


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
        """The original bug: 'turn right down 3' must split correctly."""
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
        """Just 'turn right' should stay as one command."""
        assert _split_commands("turn right") == ["turn right"]

    def test_case_insensitive(self):
        assert _split_commands("Turn Right Down 3") == ["Turn Right", "Down 3"]

    def test_direction_then_turn(self):
        assert _split_commands("right 3 turn left") == ["right 3", "turn left"]

    def test_no_keywords(self):
        assert _split_commands("hello world") == ["hello world"]

    def test_repeat_forward_turn(self):
        assert _split_commands("repeat 4 forward 20") == ["repeat 4", "forward 20"]


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
        """Bare 'turn' at end with no following chunk stays bare."""
        assert _merge_multiword(["forward 5", "turn"]) == ["forward 5", "turn"]

    def test_pen_not_followed_by_direction(self):
        assert _merge_multiword(["pen", "forward 5"]) == ["pen", "forward 5"]

    def test_turn_plus_numeric(self):
        assert _merge_multiword(["turn", "90"]) == ["turn 90"]
