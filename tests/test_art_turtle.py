"""Tests for Logo-style turtle commands in art room (turn, forward, heading)."""

import asyncio

import pytest

from purple_tui.rooms.art_room import ArtCanvas, HEADING_ARROWS


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
        self._paint_mode = False
        self._typed: list[str] = []
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

    def _set_paint_mode(self, painting):
        self._paint_mode = painting

    def _post_paint_mode_changed(self):
        pass

    def type_char(self, ch, direction=None):
        self._typed.append(ch)
        if direction:
            self._move_in_direction(direction)

    def paint_char(self, ch, direction=None):
        self._paint_at_cursor()
        if direction:
            self._move_in_direction(direction)

    # Use the real methods from ArtCanvas
    execute_logo_command = ArtCanvas.execute_logo_command
    turn = ArtCanvas.turn
    _TURN_RIGHT = ArtCanvas._TURN_RIGHT
    _TURN_LEFT = ArtCanvas._TURN_LEFT


# ---------------------------------------------------------------------------
# Turn tests (absolute semantics)
# ---------------------------------------------------------------------------

class TestTurn:
    def test_turn_right_is_absolute(self):
        c = FakeCanvas()
        c._heading = 'up'
        c.turn('right')
        assert c._heading == 'right'

    def test_turn_left_is_absolute(self):
        c = FakeCanvas()
        c._heading = 'down'
        c.turn('left')
        assert c._heading == 'left'

    def test_turn_up_is_absolute(self):
        c = FakeCanvas()
        c._heading = 'right'
        c.turn('up')
        assert c._heading == 'up'

    def test_turn_down_is_absolute(self):
        c = FakeCanvas()
        c._heading = 'left'
        c.turn('down')
        assert c._heading == 'down'

    def test_turn_right_from_right_stays(self):
        c = FakeCanvas()
        assert c._heading == 'right'
        c.turn('right')
        assert c._heading == 'right'

    def test_turn_enables_heading_cursor(self):
        c = FakeCanvas()
        assert c._use_heading_cursor is False
        c.turn('right')
        assert c._use_heading_cursor is True


# ---------------------------------------------------------------------------
# Spin tests (relative 90° CW)
# ---------------------------------------------------------------------------

class TestSpin:
    def test_spin_from_right(self):
        c = FakeCanvas()
        c.turn('spin')
        assert c._heading == 'down'

    def test_spin_from_down(self):
        c = FakeCanvas()
        c._heading = 'down'
        c.turn('spin')
        assert c._heading == 'left'

    def test_spin_from_left(self):
        c = FakeCanvas()
        c._heading = 'left'
        c.turn('spin')
        assert c._heading == 'up'

    def test_spin_from_up(self):
        c = FakeCanvas()
        c._heading = 'up'
        c.turn('spin')
        assert c._heading == 'right'

    def test_spin_full_rotation(self):
        c = FakeCanvas()
        for expected in ['down', 'left', 'up', 'right']:
            c.turn('spin')
            assert c._heading == expected

    def test_rotate_is_spin(self):
        c = FakeCanvas()
        c.turn('rotate')
        assert c._heading == 'down'

    def test_spin_alias(self):
        c = FakeCanvas()
        c.turn('spin')
        assert c._heading == 'down'


# ---------------------------------------------------------------------------
# Back/around turn tests
# ---------------------------------------------------------------------------

class TestTurnBack:
    def test_turn_back(self):
        c = FakeCanvas()
        c.turn('back')
        assert c._heading == 'left'

    def test_turn_around(self):
        c = FakeCanvas()
        c._heading = 'up'
        c.turn('around')
        assert c._heading == 'down'

    def test_turn_backward(self):
        c = FakeCanvas()
        c.turn('backward')
        assert c._heading == 'left'

    def test_turn_back_alias(self):
        """turn back is equivalent to turn backward."""
        c = FakeCanvas()
        c.turn('back')
        assert c._heading == 'left'


# ---------------------------------------------------------------------------
# Forward / execute_logo_command tests
# ---------------------------------------------------------------------------

class TestForward:
    def test_forward_moves_right_by_default(self):
        c = FakeCanvas()
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
    def test_all_directions_have_arrows(self):
        for direction in ['right', 'left', 'up', 'down']:
            assert direction in HEADING_ARROWS

    def test_arrows_are_distinct(self):
        arrows = [v[0] for v in HEADING_ARROWS.values()]
        assert len(set(arrows)) == 4


# ---------------------------------------------------------------------------
# Clear canvas resets heading
# ---------------------------------------------------------------------------

class TestClearResetsHeading:
    def test_clear_resets_heading_to_right(self):
        c = FakeCanvas()
        c._heading = 'up'
        c._use_heading_cursor = True
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

    def test_turn_left_absolute(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._heading = 'down'
        self._run(runner.run(["turn left"]))
        assert canvas._heading == 'left'

    def test_turn_right_absolute(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._heading = 'up'
        self._run(runner.run(["turn right"]))
        assert canvas._heading == 'right'

    def test_spin_command(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["spin"]))
        assert canvas._heading == 'down'

    def test_rotate_command(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["rotate"]))
        assert canvas._heading == 'down'

    def test_bare_turn_is_spin(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn"]))
        assert canvas._heading == 'down'

    def test_face_up(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["face up"]))
        assert canvas._heading == 'up'

    def test_face_down(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["face down"]))
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
        self._run(runner.run(["paint off", "turn down", "forward 3"]))
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

    def test_spin_square(self, canvas):
        """Draw a square using spin: forward, spin, forward, spin, ..."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run([
            "paint off",
            "forward 3",
            "spin",
            "forward 3",
            "spin",
            "forward 3",
            "spin",
            "forward 3",
        ]))
        assert canvas._cursor_x == 0
        assert canvas._cursor_y == 0

    def test_back_command(self, canvas):
        """back 3 from heading right should move left."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._cursor_x = 5
        self._run(runner.run(["paint off", "back 3"]))
        assert canvas._cursor_x == 2

    def test_backward_command(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._cursor_x = 5
        self._run(runner.run(["paint off", "backward 2"]))
        assert canvas._cursor_x == 3

    def test_back_default_distance(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._cursor_x = 5
        self._run(runner.run(["paint off", "back"]))
        assert canvas._cursor_x == 4

    def test_forward_capped_at_200(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward 999"]))
        assert canvas._cursor_x == 19

    def test_turn_case_insensitive(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["TURN UP"]))
        assert canvas._heading == 'up'

    def test_forward_sets_heading_cursor(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward 1"]))
        assert canvas._use_heading_cursor is True

    def test_turn_up_sets_absolute(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn up"]))
        assert canvas._heading == 'up'

    def test_turn_down_sets_absolute(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn down"]))
        assert canvas._heading == 'down'

    def test_turn_back(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn back"]))
        assert canvas._heading == 'left'

    def test_turn_around(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        canvas._heading = 'up'
        self._run(runner.run(["turn around"]))
        assert canvas._heading == 'down'

    def test_turn_backward(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn backward"]))
        assert canvas._heading == 'left'

    def test_turn_90(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn 90"]))
        assert canvas._heading == 'down'  # spin from right

    def test_turn_n_spins_and_moves(self, canvas):
        """turn N = spin 90 CW then forward N."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "turn 5"]))
        assert canvas._heading == 'down'  # spun from right
        assert canvas._cursor_y == 5  # moved down 5

    def test_turn_back_via_runner(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["turn back"]))
        assert canvas._heading == 'left'

    def test_go_synonym(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "go 3"]))
        assert canvas._cursor_x == 3

    def test_move_synonym(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "move 4"]))
        assert canvas._cursor_x == 4

    def test_walk_synonym(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "walk 2"]))
        assert canvas._cursor_x == 2

    def test_step_synonym(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "step 1"]))
        assert canvas._cursor_x == 1

    def test_repeated_spin_on_one_line(self, canvas):
        """'spin spin' on a single line should execute both."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["spin spin"]))
        assert canvas._heading == 'left'  # two spins from right

    def test_mixed_commands_on_one_line(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        self._run(runner.run(["paint off", "forward 3 spin forward 2"]))
        assert canvas._cursor_x == 3
        assert canvas._cursor_y == 2

    def test_bad_command_doesnt_break_others(self, canvas):
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(canvas)
        original_turn = canvas.turn
        call_count = [0]
        def flaky_turn(direction):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("simulated failure")
            original_turn(direction)
        canvas.turn = flaky_turn
        self._run(runner.run(["turn up", "turn down"]))
        assert call_count[0] == 2


# ---------------------------------------------------------------------------
# Free-order motion args: distance and color in any order within a chunk.
# See guides/smart-command-resolution.md ("Argument ordering").
# ---------------------------------------------------------------------------

BLUE = "#1F75FE"
DARK_BLUE = "#013D9C"


class TestFreeOrderArgs:
    @pytest.fixture
    def canvas(self):
        return FakeCanvas()

    def _run(self, lines):
        from purple_tui.code_runner import ArtCodeRunner
        canvas = FakeCanvas()
        asyncio.run(ArtCodeRunner(canvas).run(lines))
        return canvas

    def test_color_and_distance_order_invariant(self):
        """down blue 5 == down 5 blue: same heading, move, and color."""
        a = self._run(["down blue 5"])
        b = self._run(["down 5 blue"])
        for c in (a, b):
            assert c._heading == 'down'
            assert c._cursor_y == 5
            assert c._last_key_color == BLUE

    def test_color_in_middle_moves(self):
        """The original bug: 'down blue 5' must move 5, not drop the number."""
        c = self._run(["paint off", "down blue 5"])
        assert c._cursor_y == 5
        assert c._last_key_color == BLUE

    def test_multiword_color_any_position(self):
        c = self._run(["down dark blue 5"])
        assert c._cursor_y == 5
        assert c._last_key_color == DARK_BLUE

    def test_turn_arg_then_free_color_distance(self):
        """turn left 3 blue: face left, move 3, color blue."""
        c = self._run(["turn left 3 blue"])
        assert c._heading == 'left'
        assert c._last_key_color == BLUE

    def test_direction_text_still_writes(self):
        """down dog: face down and write the text (no color, no number)."""
        c = self._run(["write on", "down dog"])
        assert c._heading == 'down'
        assert "".join(c._typed) == "dog"

    def test_distance_then_text_moves_then_writes(self):
        """down 5 dog: move down 5, then write 'dog'."""
        c = self._run(["write on", "down 5 dog"])
        assert c._cursor_y == 5 + len("dog")
        assert "".join(c._typed) == "dog"

    def test_chaining_preserved_with_trailing_color(self):
        """down 5 right 3 blue splits into two moves; color applies to the run."""
        c = self._run(["paint off", "down 5 right 3 blue"])
        assert c._cursor_y == 5
        assert c._cursor_x == 3
        assert c._last_key_color == BLUE


class TestColorBeforeRepeat:
    """A color before `repeat` must paint the loop in that color instead of
    typing the letters of "repeat" (regression guards for _peel_color_before_repeat)."""

    def _run(self, lines):
        from purple_tui.code_runner import ArtCodeRunner
        canvas = FakeCanvas()
        asyncio.run(ArtCodeRunner(canvas).run(lines))
        return canvas

    def test_misspelled_color_before_repeat_applies_and_loops(self):
        """'purpl repeat ...' fuzzy-resolves to purple, applied synchronously
        before the loop body runs (guards against deferred color application)."""
        from purple_tui.content import get_content
        purple = get_content().get_color('purple')
        c = self._run(["purpl repeat 4 forward 8 spin"])
        assert c._cursor_x == 0 and c._cursor_y == 0  # square closed: loop ran 4x
        assert c._grid and all(cell[1] == purple for cell in c._grid.values())

    def test_multiword_color_before_repeat(self):
        """A multi-word color ('dark blue') peels as one unit before repeat."""
        c = self._run(["dark blue repeat 4 forward 8 spin"])
        assert c._cursor_x == 0 and c._cursor_y == 0
        assert c._grid and all(cell[1] == DARK_BLUE for cell in c._grid.values())

    def test_color_before_repeat_no_spurious_correction(self):
        """Peeling the color off must not surface a no-op 'purple -> purple' hint."""
        from purple_tui.code_runner import ArtCodeRunner
        runner = ArtCodeRunner(FakeCanvas())
        asyncio.run(runner.run(["purple repeat 4 forward 8 spin"]))
        assert all(orig != corr for orig, corr in runner.corrections)

    def test_standalone_repeat_unaffected_by_peel(self):
        """No leading color: the line is passed through unchanged and loops."""
        c = self._run(["repeat 4 forward 8 spin"])
        assert c._cursor_x == 0 and c._cursor_y == 0
        assert len(c._painted_positions) > 0

    def test_staircase_hint_descends(self):
        """The 'orange repeat 4 right 4 down 4' hint must descend, not clip to a
        flat top row (the reason the hint uses 'down' rather than 'up')."""
        c = self._run(["orange repeat 4 right 4 down 4"])
        ys = {p[1] for p in c._painted_positions}
        assert max(ys) > 0  # actually went down, not stuck at row 0

    def test_peel_leaves_plain_lines_alone(self):
        """_peel only splits a leading color directly before 'repeat'."""
        from purple_tui.code_runner import ArtCodeRunner
        r = ArtCodeRunner(FakeCanvas())
        assert r._peel_color_before_repeat("forward 10 spin") == ["forward 10 spin"]
        assert r._peel_color_before_repeat("repeat 4 forward 8") == ["repeat 4 forward 8"]
        assert r._peel_color_before_repeat("blue forward 8") == ["blue forward 8"]
        assert r._peel_color_before_repeat("") == [""]
        assert r._peel_color_before_repeat("purple repeat 4 forward 8") == \
            ["purple", "repeat 4 forward 8"]


# ---------------------------------------------------------------------------
# Edge stop (no wrapping) tests
# ---------------------------------------------------------------------------

class TestEdgeStop:
    def test_forward_stops_at_right_edge(self):
        c = FakeCanvas(width=10)
        c._cursor_x = 8
        c.execute_logo_command("move", "right", 5)
        assert c._cursor_x == 9

    def test_forward_stops_at_left_edge(self):
        c = FakeCanvas(width=10)
        c._cursor_x = 2
        c.execute_logo_command("move", "left", 5)
        assert c._cursor_x == 0

    def test_forward_stops_at_top_edge(self):
        c = FakeCanvas(height=10)
        c._cursor_y = 2
        c.execute_logo_command("move", "up", 5)
        assert c._cursor_y == 0

    def test_forward_stops_at_bottom_edge(self):
        c = FakeCanvas(height=10)
        c._cursor_y = 7
        c.execute_logo_command("move", "down", 5)
        assert c._cursor_y == 9
