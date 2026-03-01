"""
Block types for Build Mode.

Each block represents a single turtle command (move, turn, pen control).
Blocks are displayed as colored rectangles with icons and parameters.
"""

from dataclasses import dataclass, field
from enum import Enum


class BlockType(Enum):
    """The visual programming block types."""
    FORWARD = "forward"
    BACK = "back"
    RIGHT = "right"
    LEFT = "left"
    COLOR = "color"
    PEN_UP = "pen_up"
    PEN_DOWN = "pen_down"


# All block types in cycle order (up/down arrows cycle through these)
BLOCK_CYCLE = [
    BlockType.FORWARD,
    BlockType.BACK,
    BlockType.RIGHT,
    BlockType.LEFT,
    BlockType.COLOR,
    BlockType.PEN_UP,
    BlockType.PEN_DOWN,
]

# Pen colors the Color block cycles through
PEN_COLORS = [
    ("#E52B50", "red"),
    ("#FF6600", "orange"),
    ("#FFEB00", "yellow"),
    ("#228B22", "green"),
    ("#0047AB", "blue"),
    ("#7B2D8E", "purple"),
    ("#FF69B4", "pink"),
    ("#F5F5F5", "white"),
]

# Display info for each block type: (icon, background color, has_parameter)
BLOCK_INFO = {
    BlockType.FORWARD: ("⬆", "#2d8a4e", True),
    BlockType.BACK:    ("⬇", "#2d8a4e", True),
    BlockType.RIGHT:   ("↱", "#2d6a9e", True),
    BlockType.LEFT:    ("↰", "#2d6a9e", True),
    BlockType.COLOR:   ("██", None, False),       # bg set to the selected color
    BlockType.PEN_UP:  ("✋", "#606060", False),
    BlockType.PEN_DOWN:("✏", "#606060", False),
}


@dataclass
class Block:
    """A single block in the program."""
    type: BlockType
    param: int = 0       # distance (1-99) or angle (1-360)
    color_index: int = 0  # only used for COLOR blocks

    @property
    def icon(self) -> str:
        return BLOCK_INFO[self.type][0]

    @property
    def bg_color(self) -> str:
        if self.type == BlockType.COLOR:
            return PEN_COLORS[self.color_index % len(PEN_COLORS)][0]
        return BLOCK_INFO[self.type][1]

    @property
    def has_param(self) -> bool:
        return BLOCK_INFO[self.type][2]

    @property
    def display_text(self) -> str:
        """Short text shown inside the block rectangle."""
        if self.type == BlockType.COLOR:
            return PEN_COLORS[self.color_index % len(PEN_COLORS)][1]
        if self.has_param:
            return str(self.param)
        return ""


def make_block(block_type: BlockType) -> Block:
    """Create a new block with sensible defaults."""
    if block_type in (BlockType.FORWARD, BlockType.BACK):
        return Block(type=block_type, param=5)
    if block_type in (BlockType.RIGHT, BlockType.LEFT):
        return Block(type=block_type, param=90)
    return Block(type=block_type)


def cycle_block_type(current: BlockType, direction: int) -> BlockType:
    """Cycle to the next or previous block type.

    direction: +1 for next (down arrow), -1 for previous (up arrow)
    """
    idx = BLOCK_CYCLE.index(current)
    new_idx = (idx + direction) % len(BLOCK_CYCLE)
    return BLOCK_CYCLE[new_idx]


def default_program() -> list[Block]:
    """A starter program: a triangle."""
    blocks = []
    for _ in range(3):
        blocks.append(Block(type=BlockType.FORWARD, param=8))
        blocks.append(Block(type=BlockType.RIGHT, param=120))
    return blocks
