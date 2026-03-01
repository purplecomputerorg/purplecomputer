"""
Build Mode: Visual Block Programming

A turtle-graphics builder where kids create programs by navigating
colored blocks with arrow keys. No reading required: icons and colors
convey meaning. Every combination of blocks produces a valid drawing.

Keyboard input is received via handle_keyboard_action() from the main app,
which reads directly from evdev.
"""

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from textual import events
from rich.segment import Segment
from rich.style import Style

from ..keyboard import CharacterAction, NavigationAction, ControlAction
from ..blocks import (
    Block, BlockType, BLOCK_CYCLE, PEN_COLORS, BLOCK_INFO,
    make_block, cycle_block_type, default_program,
)
from ..turtle import execute_blocks, heading_to_arrow


# =============================================================================
# CONSTANTS
# =============================================================================

# Canvas dimensions (characters)
CANVAS_HEIGHT = 22
# Block strip takes remaining space below the canvas

# Theme colors (matching doodle mode)
BG_DARK = "#2a1845"
BG_LIGHT = "#e8daf0"
FG_DARK = "#d4c4e8"
FG_LIGHT = "#3a2a50"

# Block rendering
BLOCK_WIDTH = 8       # characters per block in the strip
BLOCK_SELECTED_COLOR = "#FFD700"  # gold highlight for cursor

# Animation
ANIMATE_STEP_MS = 150  # milliseconds between steps during animation


# =============================================================================
# CANVAS WIDGET
# =============================================================================

class BuildCanvas(Widget):
    """Canvas that shows the turtle drawing.

    Uses render_line() with Strip/Segment for full control over every cell,
    following the same pattern as ArtCanvas in Doodle mode.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._grid: dict[tuple[int, int], tuple[str, str]] = {}
        self._turtle_x: float = 0
        self._turtle_y: float = 0
        self._turtle_heading: float = 0
        self._turtle_visible: bool = True

    def update_drawing(self, grid: dict, turtle_x: float, turtle_y: float,
                       turtle_heading: float) -> None:
        """Update the canvas with new drawing data."""
        self._grid = grid
        self._turtle_x = turtle_x
        self._turtle_y = turtle_y
        self._turtle_heading = turtle_heading
        self.refresh()

    def _get_bg(self) -> str:
        try:
            return BG_DARK if "dark" in self.app.theme else BG_LIGHT
        except Exception:
            return BG_DARK

    def _get_fg(self) -> str:
        try:
            return FG_DARK if "dark" in self.app.theme else FG_LIGHT
        except Exception:
            return FG_DARK

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        bg = self._get_bg()
        bg_style = Style(bgcolor=bg)

        if y < 0 or y >= self.size.height:
            return Strip([Segment(" " * width, bg_style)])

        segments = []
        turtle_col = round(self._turtle_x)
        turtle_row = round(self._turtle_y)

        for col in range(width):
            if col == turtle_col and y == turtle_row and self._turtle_visible:
                # Draw turtle cursor
                arrow = heading_to_arrow(self._turtle_heading)
                style = Style(color="#00FF00", bgcolor=bg, bold=True)
                segments.append(Segment(arrow, style))
            elif (col, y) in self._grid:
                char, fg_color = self._grid[(col, y)]
                style = Style(color=fg_color, bgcolor=bg)
                segments.append(Segment(char, style))
            else:
                segments.append(Segment(" ", bg_style))

        return Strip(segments)

    async def _on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()


# =============================================================================
# BLOCK STRIP WIDGET
# =============================================================================

class BlockStrip(Widget):
    """Horizontal strip of colored blocks representing the program.

    Each block is a colored rectangle with an icon and parameter.
    The cursor block has a gold highlight.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._blocks: list[Block] = []
        self._cursor: int = 0
        self._scroll_offset: int = 0  # horizontal scroll

    def set_blocks(self, blocks: list[Block], cursor: int) -> None:
        self._blocks = blocks
        self._cursor = cursor
        self._update_scroll()
        self.refresh()

    def _update_scroll(self) -> None:
        """Ensure the cursor block is visible."""
        if not self._blocks:
            self._scroll_offset = 0
            return
        visible_blocks = max(1, self.size.width // BLOCK_WIDTH)
        # Scroll so cursor is visible
        if self._cursor < self._scroll_offset:
            self._scroll_offset = self._cursor
        elif self._cursor >= self._scroll_offset + visible_blocks:
            self._scroll_offset = self._cursor - visible_blocks + 1

    def _get_bg(self) -> str:
        try:
            return BG_DARK if "dark" in self.app.theme else BG_LIGHT
        except Exception:
            return BG_DARK

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        height = self.size.height
        bg = self._get_bg()
        bg_style = Style(bgcolor=bg)

        if not self._blocks:
            # Empty program: show hint
            if y == height // 2:
                hint = "Press Enter to add a block"
                pad = max(0, (width - len(hint)) // 2)
                dim_style = Style(color="#808080", bgcolor=bg)
                return Strip([
                    Segment(" " * pad, bg_style),
                    Segment(hint, dim_style),
                    Segment(" " * max(0, width - pad - len(hint)), bg_style),
                ])
            return Strip([Segment(" " * width, bg_style)])

        # Block strip has 3 zones vertically:
        #   Row 0: top border / play indicator
        #   Row 1-2: block content (icon + param)
        #   Row 3: cursor indicator (▲ under selected)
        #   Row 4+: hints

        segments = []
        visible_blocks = max(1, width // BLOCK_WIDTH)
        left_pad = max(0, (width - visible_blocks * BLOCK_WIDTH) // 2)

        if left_pad > 0:
            segments.append(Segment(" " * left_pad, bg_style))

        chars_used = left_pad

        # Content row within the block
        block_content_top = 1
        block_content_bot = 3
        cursor_row = 4
        hint_row = height - 1

        for i in range(self._scroll_offset, min(self._scroll_offset + visible_blocks, len(self._blocks))):
            block = self._blocks[i]
            is_selected = (i == self._cursor)

            block_bg = block.bg_color
            if is_selected:
                border_color = BLOCK_SELECTED_COLOR
            else:
                border_color = None

            # Determine text for this block
            icon = block.icon
            param_text = block.display_text

            if y == 0:
                # Top border row
                if is_selected:
                    style = Style(color=border_color, bgcolor=bg)
                    segments.append(Segment("▾" * BLOCK_WIDTH, style))
                else:
                    segments.append(Segment(" " * BLOCK_WIDTH, bg_style))
            elif block_content_top <= y <= block_content_bot:
                # Block body
                inner_y = y - block_content_top
                text_color = "#FFFFFF" if _is_dark_color(block_bg) else "#1A1A1A"
                body_style = Style(color=text_color, bgcolor=block_bg, bold=is_selected)

                if inner_y == 0:
                    # Icon row (centered)
                    # Icons like ⬆ can be wide, but we treat them as taking display width
                    cell = _center_text(icon, BLOCK_WIDTH)
                    segments.append(Segment(cell, body_style))
                elif inner_y == 1:
                    # Parameter row (centered)
                    cell = _center_text(param_text, BLOCK_WIDTH)
                    segments.append(Segment(cell, body_style))
                else:
                    segments.append(Segment(" " * BLOCK_WIDTH, body_style))
            elif y == cursor_row:
                # Cursor indicator
                if is_selected:
                    style = Style(color=border_color, bgcolor=bg)
                    indicator = _center_text("▴", BLOCK_WIDTH)
                    segments.append(Segment(indicator, style))
                else:
                    segments.append(Segment(" " * BLOCK_WIDTH, bg_style))
            elif y == hint_row:
                # Hints (only render once, not per-block)
                if i == self._scroll_offset:
                    hint = "← → move   ↑↓ change   0-9 number   Enter add   Bksp delete   Space play"
                    # Trim to fit
                    total_strip_width = visible_blocks * BLOCK_WIDTH
                    hint = hint[:total_strip_width]
                    dim_style = Style(color="#808080", bgcolor=bg)
                    segments.append(Segment(hint, dim_style))
                    remaining = total_strip_width - len(hint)
                    if remaining > 0:
                        segments.append(Segment(" " * remaining, bg_style))
                    # Skip remaining blocks for this row
                    chars_used += total_strip_width
                    break
            else:
                segments.append(Segment(" " * BLOCK_WIDTH, bg_style))

            chars_used += BLOCK_WIDTH

        # Fill remaining width
        remaining = width - chars_used
        if remaining > 0:
            segments.append(Segment(" " * remaining, bg_style))

        return Strip(segments)

    async def _on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()


# =============================================================================
# BUILD MODE CONTAINER
# =============================================================================

class BuildMode(Container, can_focus=True):
    """Build Mode: visual block programming with turtle graphics.

    Kids build programs by adding and editing colored blocks.
    The canvas shows a live preview of what the program draws.
    """

    DEFAULT_CSS = """
    BuildMode {
        width: 100%;
        height: 100%;
    }

    BuildCanvas {
        width: 100%;
        height: 22;
    }

    #strip-separator {
        width: 100%;
        height: 1;
        color: $primary;
        text-align: center;
    }

    BlockStrip {
        width: 100%;
        height: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._blocks: list[Block] = default_program()
        self._cursor: int = 0
        self._animating: bool = False
        self._animate_step: int = 0
        self._animate_timer = None
        self._digit_buffer: str = ""  # accumulates multi-digit number input

    def compose(self) -> ComposeResult:
        yield BuildCanvas(id="build-canvas")
        yield Static("─" * 80, id="strip-separator")
        yield BlockStrip(id="block-strip")

    def on_mount(self) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        """Re-execute the program and update both canvas and strip."""
        canvas = self.query_one("#build-canvas", BuildCanvas)
        strip = self.query_one("#block-strip", BlockStrip)

        width = canvas.size.width or 112
        height = canvas.size.height or CANVAS_HEIGHT

        if self._animating:
            grid, turtle = execute_blocks(self._blocks, width, height,
                                          stop_after=self._animate_step)
        else:
            grid, turtle = execute_blocks(self._blocks, width, height)

        canvas.update_drawing(grid, turtle.x, turtle.y, turtle.heading)
        strip.set_blocks(self._blocks, self._cursor)

    # ── Keyboard handling ──────────────────────────────────────────────

    async def handle_keyboard_action(self, action) -> None:
        """Route keyboard actions to the appropriate handler."""
        if self._animating:
            # During animation, only Space stops it
            if isinstance(action, ControlAction) and action.is_down:
                if action.action == 'space':
                    self._stop_animation()
            return

        if isinstance(action, NavigationAction):
            await self._handle_navigation(action)
            return

        if isinstance(action, ControlAction) and action.is_down:
            await self._handle_control(action)
            return

        if isinstance(action, CharacterAction):
            await self._handle_character(action)
            return

    async def _handle_navigation(self, action: NavigationAction) -> None:
        if action.direction == 'left':
            if self._blocks and self._cursor > 0:
                self._flush_digits()
                self._cursor -= 1
                self._refresh_all()
        elif action.direction == 'right':
            if self._blocks and self._cursor < len(self._blocks) - 1:
                self._flush_digits()
                self._cursor += 1
                self._refresh_all()
        elif action.direction == 'up':
            self._cycle_block(-1)
        elif action.direction == 'down':
            self._cycle_block(1)

    async def _handle_control(self, action: ControlAction) -> None:
        if action.action == 'enter':
            self._insert_block()
        elif action.action == 'backspace':
            self._delete_block()
        elif action.action == 'space':
            self._start_animation()

    async def _handle_character(self, action: CharacterAction) -> None:
        char = action.char
        if char.isdigit():
            self._type_digit(char)

    # ── Block operations ───────────────────────────────────────────────

    def _cycle_block(self, direction: int) -> None:
        """Cycle the block type at cursor position."""
        if not self._blocks:
            return

        block = self._blocks[self._cursor]
        if block.type == BlockType.COLOR:
            # For color blocks, cycle through colors instead of types
            block.color_index = (block.color_index + direction) % len(PEN_COLORS)
        else:
            new_type = cycle_block_type(block.type, direction)
            new_block = make_block(new_type)
            # Preserve parameter if the new type also has one
            if new_block.has_param and block.has_param:
                new_block.param = block.param
            self._blocks[self._cursor] = new_block

        self._digit_buffer = ""
        self._refresh_all()

    def _insert_block(self) -> None:
        """Insert a new Forward block after the cursor."""
        self._flush_digits()
        new_block = make_block(BlockType.FORWARD)
        if self._blocks:
            self._blocks.insert(self._cursor + 1, new_block)
            self._cursor += 1
        else:
            self._blocks.append(new_block)
            self._cursor = 0
        self._refresh_all()

    def _delete_block(self) -> None:
        """Delete the block at cursor."""
        if not self._blocks:
            return
        self._digit_buffer = ""
        self._blocks.pop(self._cursor)
        if self._cursor >= len(self._blocks) and self._cursor > 0:
            self._cursor -= 1
        self._refresh_all()

    def _type_digit(self, digit: str) -> None:
        """Handle a digit keypress for setting block parameters."""
        if not self._blocks:
            return
        block = self._blocks[self._cursor]
        if not block.has_param:
            return

        self._digit_buffer += digit
        # Parse the accumulated digits
        value = int(self._digit_buffer)

        # Clamp based on block type
        if block.type in (BlockType.FORWARD, BlockType.BACK):
            value = max(1, min(99, value))
        elif block.type in (BlockType.RIGHT, BlockType.LEFT):
            value = max(1, min(360, value))

        block.param = value

        # If buffer is getting long enough, auto-flush
        if block.type in (BlockType.FORWARD, BlockType.BACK) and len(self._digit_buffer) >= 2:
            self._digit_buffer = ""
        elif block.type in (BlockType.RIGHT, BlockType.LEFT) and len(self._digit_buffer) >= 3:
            self._digit_buffer = ""

        self._refresh_all()

    def _flush_digits(self) -> None:
        """Clear the digit buffer when moving away from a block."""
        self._digit_buffer = ""

    # ── Animation ──────────────────────────────────────────────────────

    def _start_animation(self) -> None:
        """Animate the program step by step."""
        if not self._blocks:
            return
        self._animating = True
        self._animate_step = 0
        self._refresh_all()
        self._animate_timer = self.set_interval(
            ANIMATE_STEP_MS / 1000.0, self._animation_tick
        )

    def _animation_tick(self) -> None:
        """Advance animation by one block."""
        self._animate_step += 1
        if self._animate_step > len(self._blocks):
            self._stop_animation()
            return
        self._refresh_all()

    def _stop_animation(self) -> None:
        """Stop animation and show the full drawing."""
        self._animating = False
        self._animate_step = 0
        if self._animate_timer:
            self._animate_timer.stop()
            self._animate_timer = None
        self._refresh_all()

    async def _on_key(self, event: events.Key) -> None:
        """Suppress terminal key events. All input comes via evdev."""
        event.stop()
        event.prevent_default()


# =============================================================================
# HELPERS
# =============================================================================

def _center_text(text: str, width: int) -> str:
    """Center text within a fixed width, padding with spaces."""
    if len(text) >= width:
        return text[:width]
    pad_left = (width - len(text)) // 2
    pad_right = width - len(text) - pad_left
    return " " * pad_left + text + " " * pad_right


def _is_dark_color(hex_color: str) -> bool:
    """Check if a hex color is dark (for choosing text contrast)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return True
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    # Perceived luminance
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 128
