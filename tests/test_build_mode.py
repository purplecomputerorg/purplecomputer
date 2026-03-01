"""
Tests for Build Mode: blocks, turtle, and program execution.

Pure logic tests with no Textual app dependency.
"""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.blocks import (
    Block, BlockType, BLOCK_CYCLE, PEN_COLORS,
    make_block, cycle_block_type, default_program,
)
from purple_tui.turtle import (
    Turtle, execute_blocks, heading_to_arrow, _draw_line,
)


# =============================================================================
# BLOCK TESTS
# =============================================================================

class TestBlockType:
    def test_all_types_in_cycle(self):
        """Every block type appears in the cycle list."""
        for bt in BlockType:
            assert bt in BLOCK_CYCLE

    def test_cycle_wraps_forward(self):
        last = BLOCK_CYCLE[-1]
        assert cycle_block_type(last, 1) == BLOCK_CYCLE[0]

    def test_cycle_wraps_backward(self):
        first = BLOCK_CYCLE[0]
        assert cycle_block_type(first, -1) == BLOCK_CYCLE[-1]

    def test_cycle_forward_one(self):
        assert cycle_block_type(BlockType.FORWARD, 1) == BlockType.BACK

    def test_cycle_backward_one(self):
        assert cycle_block_type(BlockType.BACK, -1) == BlockType.FORWARD


class TestMakeBlock:
    def test_forward_default(self):
        b = make_block(BlockType.FORWARD)
        assert b.type == BlockType.FORWARD
        assert b.param == 5
        assert b.has_param is True

    def test_right_default(self):
        b = make_block(BlockType.RIGHT)
        assert b.type == BlockType.RIGHT
        assert b.param == 90

    def test_pen_up_no_param(self):
        b = make_block(BlockType.PEN_UP)
        assert b.has_param is False
        assert b.display_text == ""

    def test_color_block_shows_color_name(self):
        b = make_block(BlockType.COLOR)
        assert b.display_text == PEN_COLORS[0][1]

    def test_color_block_bg_is_color(self):
        b = Block(type=BlockType.COLOR, color_index=2)
        assert b.bg_color == PEN_COLORS[2][0]


class TestDefaultProgram:
    def test_returns_six_blocks(self):
        """Default program is a triangle: 3x (forward + right 120)."""
        prog = default_program()
        assert len(prog) == 6

    def test_alternates_forward_right(self):
        prog = default_program()
        for i in range(0, 6, 2):
            assert prog[i].type == BlockType.FORWARD
            assert prog[i + 1].type == BlockType.RIGHT
            assert prog[i + 1].param == 120


# =============================================================================
# TURTLE TESTS
# =============================================================================

class TestTurtle:
    def test_initial_position(self):
        t = Turtle()
        assert t.x == 0.0
        assert t.y == 0.0
        assert t.heading == 0.0
        assert t.pen_down is True

    def test_forward_heading_zero_goes_up(self):
        """Heading 0 means up, so forward decreases y."""
        t = Turtle(x=10.0, y=10.0, heading=0.0)
        grid = {}
        t.forward(5, grid, 20, 20)
        assert t.x == 10.0
        assert t.y == 5.0

    def test_forward_heading_90_goes_right(self):
        """Heading 90 means right, so forward increases x."""
        t = Turtle(x=10.0, y=10.0, heading=90.0)
        grid = {}
        t.forward(5, grid, 20, 20)
        assert abs(t.x - 15.0) < 0.01
        assert abs(t.y - 10.0) < 0.01

    def test_forward_heading_180_goes_down(self):
        t = Turtle(x=10.0, y=10.0, heading=180.0)
        grid = {}
        t.forward(5, grid, 20, 20)
        assert abs(t.x - 10.0) < 0.01
        assert abs(t.y - 15.0) < 0.01

    def test_back_is_reverse_forward(self):
        t = Turtle(x=10.0, y=10.0, heading=0.0)
        grid = {}
        t.back(5, grid, 20, 20)
        assert t.y == 15.0

    def test_right_turn(self):
        t = Turtle(heading=0.0)
        t.right(90)
        assert t.heading == 90.0

    def test_left_turn(self):
        t = Turtle(heading=0.0)
        t.left(90)
        assert t.heading == 270.0

    def test_turn_wraps(self):
        t = Turtle(heading=350.0)
        t.right(20)
        assert t.heading == 10.0

    def test_pen_up_no_drawing(self):
        t = Turtle(x=10.0, y=10.0, heading=0.0, pen_down=False)
        grid = {}
        t.forward(5, grid, 20, 20)
        assert len(grid) == 0
        assert t.y == 5.0

    def test_pen_down_draws(self):
        t = Turtle(x=10.0, y=10.0, heading=0.0, pen_down=True)
        grid = {}
        t.forward(5, grid, 20, 20)
        assert len(grid) > 0

    def test_set_color(self):
        t = Turtle()
        t.set_color(2)
        assert t.pen_color == PEN_COLORS[2][0]
        assert t.color_index == 2

    def test_set_color_wraps(self):
        t = Turtle()
        t.set_color(len(PEN_COLORS) + 1)
        assert t.color_index == 1


class TestHeadingToArrow:
    def test_up(self):
        assert heading_to_arrow(0) == "▲"

    def test_right(self):
        assert heading_to_arrow(90) == "▶"

    def test_down(self):
        assert heading_to_arrow(180) == "▼"

    def test_left(self):
        assert heading_to_arrow(270) == "◀"

    def test_wraps_360(self):
        assert heading_to_arrow(360) == "▲"

    def test_negative(self):
        assert heading_to_arrow(-90) == "◀"


class TestDrawLine:
    def test_vertical_line(self):
        grid = {}
        _draw_line(grid, 20, 20, 5.0, 5.0, 5.0, 10.0, "#FFFFFF")
        # Should have cells from (5,5) to (5,10)
        for y in range(5, 11):
            assert (5, y) in grid

    def test_horizontal_line(self):
        grid = {}
        _draw_line(grid, 20, 20, 5.0, 5.0, 10.0, 5.0, "#FFFFFF")
        for x in range(5, 11):
            assert (x, 5) in grid

    def test_out_of_bounds_clipped(self):
        grid = {}
        _draw_line(grid, 10, 10, 5.0, 5.0, 15.0, 5.0, "#FFFFFF")
        # Only cells within 0-9 should be drawn
        for key in grid:
            assert 0 <= key[0] < 10
            assert 0 <= key[1] < 10

    def test_single_point(self):
        grid = {}
        _draw_line(grid, 20, 20, 5.0, 5.0, 5.0, 5.0, "#FFFFFF")
        assert (5, 5) in grid


# =============================================================================
# PROGRAM EXECUTION TESTS
# =============================================================================

class TestExecuteBlocks:
    def test_empty_program(self):
        grid, turtle = execute_blocks([], 40, 20)
        assert len(grid) == 0
        assert turtle.x == 20.0  # center
        assert turtle.y == 10.0

    def test_single_forward(self):
        blocks = [Block(type=BlockType.FORWARD, param=5)]
        grid, turtle = execute_blocks(blocks, 40, 20)
        assert len(grid) > 0
        assert turtle.y < 10.0  # moved up from center

    def test_square_returns_near_start(self):
        """A square (4x forward + right 90) should end near the start."""
        blocks = []
        for _ in range(4):
            blocks.append(Block(type=BlockType.FORWARD, param=5))
            blocks.append(Block(type=BlockType.RIGHT, param=90))
        grid, turtle = execute_blocks(blocks, 40, 20)
        assert abs(turtle.x - 20.0) < 1.0
        assert abs(turtle.y - 10.0) < 1.0

    def test_stop_after(self):
        """stop_after limits how many blocks are executed."""
        blocks = [
            Block(type=BlockType.FORWARD, param=5),
            Block(type=BlockType.RIGHT, param=90),
            Block(type=BlockType.FORWARD, param=5),
        ]
        grid1, t1 = execute_blocks(blocks, 40, 20, stop_after=1)
        grid2, t2 = execute_blocks(blocks, 40, 20, stop_after=3)
        # After 1 block: moved up, heading 0
        assert t1.heading == 0.0
        # After 3 blocks: moved up, turned right, moved right
        assert t2.heading == 90.0
        assert len(grid2) > len(grid1)

    def test_pen_up_then_down(self):
        blocks = [
            Block(type=BlockType.PEN_UP),
            Block(type=BlockType.FORWARD, param=5),
            Block(type=BlockType.PEN_DOWN),
            Block(type=BlockType.FORWARD, param=5),
        ]
        grid, turtle = execute_blocks(blocks, 40, 20)
        # First forward drew nothing, second drew something
        assert len(grid) > 0

    def test_color_change(self):
        blocks = [
            Block(type=BlockType.COLOR, color_index=3),
            Block(type=BlockType.FORWARD, param=5),
        ]
        grid, turtle = execute_blocks(blocks, 40, 20)
        assert turtle.pen_color == PEN_COLORS[3][0]
        # Check that drawn segments use the new color
        for (x, y), (char, color) in grid.items():
            assert color == PEN_COLORS[3][0]

    def test_triangle_program(self):
        """The default triangle program should produce drawing."""
        blocks = default_program()
        grid, turtle = execute_blocks(blocks, 60, 30)
        assert len(grid) > 0
        # Triangle should return near start
        assert abs(turtle.x - 30.0) < 2.0
        assert abs(turtle.y - 15.0) < 2.0
