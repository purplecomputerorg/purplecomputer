"""
Turtle graphics engine for Build Mode.

Executes a list of blocks and produces drawable line segments on a
character grid. Uses Bresenham's algorithm adapted for terminal cells.
"""

import math
from dataclasses import dataclass, field

from .blocks import Block, BlockType, PEN_COLORS


@dataclass
class DrawnSegment:
    """A line segment drawn by the turtle."""
    x0: int
    y0: int
    x1: int
    y1: int
    color: str  # hex color


# Turtle cursor arrows based on heading (nearest 45-degree direction)
TURTLE_ARROWS = {
    0: "▲",     # up
    45: "▶",    # up-right (approximate)
    90: "▶",    # right
    135: "▼",   # down-right (approximate)
    180: "▼",   # down
    225: "◀",   # down-left (approximate)
    270: "◀",   # left
    315: "▲",   # up-left (approximate)
}


def heading_to_arrow(heading: float) -> str:
    """Convert heading in degrees to the nearest turtle arrow character."""
    # Normalize to 0-360
    h = heading % 360
    # Snap to nearest 45
    snapped = round(h / 45) * 45 % 360
    return TURTLE_ARROWS.get(snapped, "▲")


# Line-drawing characters based on direction
def _line_char(dx: int, dy: int) -> str:
    """Pick a line character based on step direction."""
    if dx == 0:
        return "│"
    if dy == 0:
        return "─"
    # Diagonal: dx and dy both nonzero
    if (dx > 0 and dy > 0) or (dx < 0 and dy < 0):
        return "╲"
    return "╱"


@dataclass
class Turtle:
    """A Logo-style turtle that draws on a character grid."""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # degrees, 0 = up, 90 = right
    pen_down: bool = True
    pen_color: str = "#F5F5F5"  # white by default
    color_index: int = 0

    def forward(self, distance: float, grid: dict, width: int, height: int) -> None:
        """Move forward, drawing a line if pen is down."""
        rad = math.radians(self.heading)
        # In terminal coords: heading 0 = up (-y), 90 = right (+x)
        dx = math.sin(rad) * distance
        dy = -math.cos(rad) * distance
        new_x = self.x + dx
        new_y = self.y + dy

        if self.pen_down:
            _draw_line(grid, width, height,
                       self.x, self.y, new_x, new_y, self.pen_color)

        self.x = new_x
        self.y = new_y

    def back(self, distance: float, grid: dict, width: int, height: int) -> None:
        """Move backward (draw in current direction, move opposite)."""
        self.forward(-distance, grid, width, height)

    def right(self, angle: float) -> None:
        """Turn clockwise."""
        self.heading = (self.heading + angle) % 360

    def left(self, angle: float) -> None:
        """Turn counterclockwise."""
        self.heading = (self.heading - angle) % 360

    def set_color(self, color_index: int) -> None:
        """Set pen color from the palette."""
        self.color_index = color_index % len(PEN_COLORS)
        self.pen_color = PEN_COLORS[self.color_index][0]


def _draw_line(grid: dict, width: int, height: int,
               x0: float, y0: float, x1: float, y1: float, color: str) -> None:
    """Draw a line on the character grid using Bresenham's algorithm.

    grid: dict mapping (col, row) -> (char, fg_color)
    """
    # Convert to integer grid coordinates
    ix0, iy0 = round(x0), round(y0)
    ix1, iy1 = round(x1), round(y1)

    dx = abs(ix1 - ix0)
    dy = abs(iy1 - iy0)
    sx = 1 if ix0 < ix1 else -1
    sy = 1 if iy0 < iy1 else -1

    cx, cy = ix0, iy0

    if dx == 0 and dy == 0:
        if 0 <= cx < width and 0 <= cy < height:
            grid[(cx, cy)] = ("·", color)
        return

    err = dx - dy

    while True:
        if 0 <= cx < width and 0 <= cy < height:
            # Determine line character from direction
            step_dx = 1 if ix1 > ix0 else (-1 if ix1 < ix0 else 0)
            step_dy = 1 if iy1 > iy0 else (-1 if iy1 < iy0 else 0)
            char = _line_char(step_dx, step_dy)
            grid[(cx, cy)] = (char, color)

        if cx == ix1 and cy == iy1:
            break

        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy


def execute_blocks(blocks: list[Block], canvas_width: int, canvas_height: int,
                   stop_after: int | None = None) -> tuple[dict, Turtle]:
    """Execute a program and return the drawn grid and final turtle state.

    Args:
        blocks: The program to execute.
        canvas_width: Width of the canvas in characters.
        canvas_height: Height of the canvas in characters.
        stop_after: If set, only execute this many blocks (for animation).

    Returns:
        (grid, turtle) where grid maps (col, row) -> (char, fg_color)
        and turtle is the final turtle state.
    """
    grid: dict[tuple[int, int], tuple[str, str]] = {}

    # Start turtle at center of canvas
    turtle = Turtle(
        x=canvas_width / 2,
        y=canvas_height / 2,
    )

    count = len(blocks) if stop_after is None else min(stop_after, len(blocks))

    for i in range(count):
        block = blocks[i]

        if block.type == BlockType.FORWARD:
            turtle.forward(block.param, grid, canvas_width, canvas_height)
        elif block.type == BlockType.BACK:
            turtle.back(block.param, grid, canvas_width, canvas_height)
        elif block.type == BlockType.RIGHT:
            turtle.right(block.param)
        elif block.type == BlockType.LEFT:
            turtle.left(block.param)
        elif block.type == BlockType.COLOR:
            turtle.set_color(block.color_index)
        elif block.type == BlockType.PEN_UP:
            turtle.pen_down = False
        elif block.type == BlockType.PEN_DOWN:
            turtle.pen_down = True

    return grid, turtle
