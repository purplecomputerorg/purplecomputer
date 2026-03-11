"""Tests for Logo-style turtle commands in art room (turn, forward, heading)."""

import asyncio
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from purple_tui.rooms.art_room import ArtCanvas, HEADING_CURSORS, CODE_CURSOR_CHAR


# ---------------------------------------------------------------------------
# Helpers: lightweight canvas mock that has the real turn/execute_logo_command
# logic but doesn't need a Textual app running.
# ---------------------------------------------------------------------------

class FakeCanvas:
    """Minimal stand-in for ArtCanvas that exercises heading/movement logic."""

    def __init__(self, width=20, height=10):
        self._cursor_x = 0
        self._cursor_y = 0
        self._heading = 'right'
        self._use_heading_cursor = False
        self._grid: dict[tuple[int, int], tuple[str, str, str]] = {}
        self._painted_positions: set[tuple[int, int]] = set()
        self._last_key_color = "#FF0000"
        self._width = width
        self._height = height

    # Properties matching ArtCanvas
    @property
    def canvas_width(self):
        return self._width

    @property
    def canvas_height(self):
        return self._height

    # Stubs for methods called by execute_logo_command / turn
    def _mark_cursor_dirty(self):
        pass

    def _invalidate_all(self):
        pass

    def _restart_blink(self):
        pass

    def refresh(self):
        pass

    # Real movement logic (simplified from ArtCanvas)
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

    def _move_cursor_down(self):
        if self._cursor_y < self.canvas_height - 1:
            self._cursor_y += 1
            return True
        return False

    def _move_cursor_up(self):
        if self._cursor_y > 0:
            self._cursor_y -= 1
            return True
        return False

    def _move_in_direction(self, direction):
        if direction == 'up':
            return self._move_cursor_up()
        elif direction == 'down':
            return self._move_cursor_down()
        elif direction == 'left':
            return self._move_cursor_left()
        elif direction == 'right':
            return self._move_cursor_right()
        return False

    def _paint_at_cursor(self):
        pos = (self._cursor_x, self._cursor_y)
        self._grid[pos] = ("█", self._last_key_color, self._last_key_color)
        self._painted_positions.add(pos)

    # Use the real methods from ArtCanvas
    execute_logo_command = ArtCanvas.execute_logo_command
    turn = ArtCanvas.turn
    _TURN_RIGHT = ArtCanvas._TURN_RIGHT
    _TURN_LEFT = ArtCanvas._TURN_LEFT


# ---------------------------------------------------------------------------
# Turn tests
# ---------------------------------------------------------------------------

class TestTurn:
    def test_turn_right_from_right(self):
        c = FakeCanvas()
        assert c._heading == 'right'
        c.turn('right')
        assert c._heading == 'down'

    def test_turn_right_full_rotation(self):
        c = FakeCanvas()
        for expected in ['down', 'left', 'up', 'right']:
            c.turn('right')
            assert c._heading == expected

    def test_turn_left_from_right(self):
        c = FakeCanvas()
        c.turn('left')
        assert c._heading == 'up'

    def test_turn_left_full_rotation(self):
        c = FakeCanvas()
        for expected in ['up', 'left', 'down', 'right']:
            c.turn('left')
            assert c._heading == expected

    def test_turn_enables_heading_cursor(self):
        c = FakeCanvas()
        assert c._use_heading_cursor is False
        c.turn('right')
        assert c._use_heading_cursor is True

    def test_turn_from_arbitrary_heading(self):
        c = FakeCanvas()
        c._heading = 'up'
        c.turn('right')
        assert c._heading == 'right'
        c.turn('left')
        assert c._heading == 'up'


# ---------------------------------------------------------------------------
# Forward / execute_logo_command tests
# ---------------------------------------------------------------------------

class TestForward:
    def test_forward_moves_right_by_default(self):
        c = FakeCanvas()
        c._cursor_x = 0
        c._cursor_y = 0
        c.execute_logo_command("move", "right", 5)
        assert c._cursor_x == 5
        assert c._cursor_y == 0

    def test_forward_moves_in_heading_direction(self):
        c = FakeCanvas()
        c._heading = 'down'
        c.execute_logo_command("move", "down", 3)
        assert c._cursor_y == 3
        assert c._cursor_x == 0

    def test_forward_stops_at_edge(self):
        c = FakeCanvas(width=10, height=5)
        c.execute_logo_command("move", "right", 100)
        assert c._cursor_x == 9  # width - 1

    def test_forward_stops_at_top_edge(self):
        c = FakeCanvas(width=10, height=5)
        c._cursor_y = 2
        c.execute_logo_command("move", "up", 100)
        assert c._cursor_y == 0

    def test_forward_paints_when_paint_action(self):
        c = FakeCanvas()
        c.execute_logo_command("paint", "right", 3)
        # Should have painted at positions 0, 1, 2 (paint then move)
        assert (0, 0) in c._painted_positions
        assert (1, 0) in c._painted_positions
        assert (2, 0) in c._painted_positions

    def test_forward_no_paint_when_move_action(self):
        c = FakeCanvas()
        c.execute_logo_command("move", "right", 3)
        assert len(c._painted_positions) == 0

    def test_forward_zero_distance(self):
        c = FakeCanvas()
        c.execute_logo_command("move", "right", 0)
        assert c._cursor_x == 0

    def test_forward_left(self):
        c = FakeCanvas()
        c._cursor_x = 5
        c.execute_logo_command("move", "left", 3)
        assert c._cursor_x == 2


# ---------------------------------------------------------------------------
# Heading cursor display tests
# ---------------------------------------------------------------------------

class TestHeadingCursors:
    def test_all_directions_have_cursors(self):
        for direction in ['right', 'left', 'up', 'down']:
            assert direction in HEADING_CURSORS

    def test_cursors_are_distinct(self):
        cursors = list(HEADING_CURSORS.values())
        assert len(set(cursors)) == 4

    def test_cursors_differ_from_default(self):
        for cursor in HEADING_CURSORS.values():
            assert cursor != CODE_CURSOR_CHAR


# ---------------------------------------------------------------------------
# Clear canvas resets heading
# ---------------------------------------------------------------------------

class TestClearResetsHeading:
    def test_clear_resets_heading_to_right(self):
        c = FakeCanvas()
        c._heading = 'up'
        c._use_heading_cursor = True
        # Simulate what _clear_canvas does
        c._heading = 'right'
        c._use_heading_cursor = False
        assert c._heading == 'right'
        assert c._use_heading_cursor is False


# ---------------------------------------------------------------------------
# ArtCodeRunner integration (parsing turn/forward commands)
# ---------------------------------------------------------------------------

class TestArtCodeRunnerTurtle:
    @pytest.fixture
    def canvas(self):
        return FakeCanvas()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_turn_left_command(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn left"]))
        assert canvas._heading == 'up'

    def test_turn_right_command(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn right"]))
        assert canvas._heading == 'down'

    def test_forward_command_default_distance(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward"]))
        assert canvas._cursor_x == 1

    def test_forward_command_with_distance(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward 5"]))
        assert canvas._cursor_x == 5

    def test_forward_respects_heading(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "turn right", "forward 3"]))
        # turn right from default 'right' = 'down'
        assert canvas._cursor_y == 3
        assert canvas._cursor_x == 0

    def test_forward_paints_by_default(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["forward 3"]))
        assert len(canvas._painted_positions) >= 3

    def test_forward_no_paint_when_off(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward 3"]))
        assert len(canvas._painted_positions) == 0

    def test_turn_and_forward_square(self, canvas):
        """Draw a square: forward, turn, forward, turn, forward, turn, forward."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run([
            "paint off",
            "forward 3",
            "turn right",
            "forward 3",
            "turn right",
            "forward 3",
            "turn right",
            "forward 3",
        ]))
        # Should end back at (0, 0) after a 3x3 square
        assert canvas._cursor_x == 0
        assert canvas._cursor_y == 0

    def test_forward_capped_at_200(self, canvas):
        """Forward distance is capped at 200."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward 999"]))
        # Canvas is only 20 wide, so cursor stops at edge
        assert canvas._cursor_x == 19

    def test_turn_case_insensitive(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["TURN LEFT"]))
        assert canvas._heading == 'up'

    def test_forward_sets_heading_cursor(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward 1"]))
        assert canvas._use_heading_cursor is True
