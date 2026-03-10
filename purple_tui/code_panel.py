"""
Inline Code Panel: a live trail of actions that appears below the viewport.

Shows blocks as colored cells in a horizontal grid. Each room has its own
content. Blocks appear automatically as you play. You can arrow down into
the panel to navigate/edit, backspace to delete, space to replay.

Per-room block types:
  Music: KEY blocks (colored note cells)
  Art: KEY blocks (color swatches) and STROKE blocks (direction + distance)
  Play: QUERY blocks (expression + result)
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum

from textual.widget import Widget
from textual.strip import Strip
from textual.message import Message
from rich.segment import Segment
from rich.style import Style

from .constants import CODE_BLOCK_WIDTH


# =============================================================================
# BLOCK DATA
# =============================================================================

# Block colors by keyboard row (matching music/art room conventions)
_QWERTY_ROW = set("qwertyuiop[]\\")
_ASDF_ROW = set("asdfghjkl;'")
_ZXCV_ROW = set("zxcvbnm,./")
_NUMBER_ROW = set("1234567890-=+`")

COLOR_RED = "#BF4040"
COLOR_YELLOW = "#BFA040"
COLOR_BLUE = "#4060BF"
COLOR_GRAY = "#808080"
COLOR_DIRECTION = "#2d6a9e"
COLOR_QUERY = "#44AADD"
COLOR_RESULT = "#2a5040"
COLOR_NEWLINE = "#3a3a3a"
COLOR_REPEAT = "#2d9e8a"

DIRECTION_ARROWS = {
    "up": "\u25b2",
    "down": "\u25bc",
    "left": "\u25c0",
    "right": "\u25b6",
}


def key_color(char: str) -> str:
    """Get block color for a character based on keyboard row."""
    lower = char.lower()
    if lower in _QWERTY_ROW:
        return COLOR_RED
    elif lower in _ASDF_ROW:
        return COLOR_YELLOW
    elif lower in _ZXCV_ROW:
        return COLOR_BLUE
    elif lower in _NUMBER_ROW:
        return COLOR_GRAY
    return COLOR_GRAY


@dataclass
class CodeBlock:
    """A single block in the code panel trail."""
    label: str              # Display text (1-3 chars typically)
    color: str              # Background color hex
    width: int = CODE_BLOCK_WIDTH  # Display width in chars

    # Music replay metadata
    key: str = ""           # Original key (for sound replay)
    submode: str = ""       # "music" or "letters"
    gap_ms: int = 0         # Milliseconds since previous block (for timing replay)

    # Art metadata
    direction: str = ""     # up/down/left/right (for STROKE blocks)
    distance: int = 0       # Number of steps

    # Play metadata
    expression: str = ""    # Full expression text
    result: str = ""        # Evaluation result text

    # Type tag for dispatch
    kind: str = "key"       # "key", "stroke", "query", "newline"


def make_music_block(key: str, submode: str = "music", gap_ms: int = 0) -> CodeBlock:
    """Create a music note block."""
    return CodeBlock(
        label=key.upper() if len(key) == 1 else key[:3],
        color=key_color(key),
        key=key,
        submode=submode,
        gap_ms=gap_ms,
        kind="key",
    )


def make_stroke_block(direction: str, distance: int = 1) -> CodeBlock:
    """Create an art direction/stroke block."""
    arrow = DIRECTION_ARROWS.get(direction, "?")
    label = f"{arrow}{distance}" if distance > 1 else arrow
    return CodeBlock(
        label=label,
        color=COLOR_DIRECTION,
        width=max(CODE_BLOCK_WIDTH, len(label) + 2),
        direction=direction,
        distance=distance,
        kind="stroke",
    )


def make_color_block(key: str, color_hex: str) -> CodeBlock:
    """Create an art color swatch block."""
    return CodeBlock(
        label="\u2588",  # Full block character
        color=color_hex,
        key=key,
        kind="key",
    )


def make_query_block(expression: str, result: str = "") -> CodeBlock:
    """Create a play expression block."""
    return CodeBlock(
        label=expression[:20],
        color=COLOR_QUERY,
        width=max(CODE_BLOCK_WIDTH, min(30, len(expression) + 2)),
        expression=expression,
        result=result,
        kind="query",
    )


def make_newline_block() -> CodeBlock:
    """Create a visual line break marker."""
    return CodeBlock(
        label="\u21b5",  # Return symbol
        color=COLOR_NEWLINE,
        width=2,
        kind="newline",
    )


def make_repeat_block(count: int = 2) -> CodeBlock:
    """Create a repeat block (music only in v1)."""
    return CodeBlock(
        label=f"x{count}",
        color=COLOR_REPEAT,
        width=CODE_BLOCK_WIDTH,
        kind="repeat",
    )


COLOR_LOGO = "#3a7a5e"

def make_logo_block(action: str, direction: str, distance: int) -> CodeBlock:
    """Create a logo-style command block (art guided mode)."""
    arrow = DIRECTION_ARROWS.get(direction, "?")
    label = f"{action.title()}{arrow}{distance}"
    return CodeBlock(
        label=label,
        color=COLOR_LOGO,
        width=max(CODE_BLOCK_WIDTH, len(label) + 2),
        direction=direction,
        distance=distance,
        kind="logo",
    )


# =============================================================================
# ART GUIDE (Logo-like step-by-step flow)
# =============================================================================

class ArtGuideStep(Enum):
    ACTION = "action"
    DIRECTION = "direction"
    DISTANCE = "distance"

_ACTIONS = ["Move", "Paint"]
_DIRECTIONS = ["up", "down", "left", "right"]
_DIRECTION_LABELS = ["\u25b2 Up", "\u25bc Down", "\u25c0 Left", "\u25b6 Right"]


class ArtGuide:
    """State machine for guided Logo-like art commands."""

    def __init__(self):
        self.step = ArtGuideStep.ACTION
        self.action_index = 0   # 0=Move, 1=Paint
        self.dir_index = 0      # 0-3
        self.distance = 3       # 1-20

    def reset(self):
        self.step = ArtGuideStep.ACTION
        self.action_index = 0
        self.dir_index = 0
        self.distance = 3

    def get_display_text(self) -> str:
        """Get the display text for the current step."""
        if self.step == ArtGuideStep.ACTION:
            parts = []
            for i, a in enumerate(_ACTIONS):
                if i == self.action_index:
                    parts.append(f"[{a}]")
                else:
                    parts.append(f" {a} ")
            return "  ".join(parts)
        elif self.step == ArtGuideStep.DIRECTION:
            parts = []
            for i, d in enumerate(_DIRECTION_LABELS):
                if i == self.dir_index:
                    parts.append(f"[{d}]")
                else:
                    parts.append(f" {d} ")
            return "  ".join(parts)
        else:  # DISTANCE
            return f"Steps: \u25c0 {self.distance} \u25b6"

    def handle_left(self):
        if self.step == ArtGuideStep.ACTION:
            self.action_index = max(0, self.action_index - 1)
        elif self.step == ArtGuideStep.DIRECTION:
            self.dir_index = max(0, self.dir_index - 1)
        elif self.step == ArtGuideStep.DISTANCE:
            self.distance = max(1, self.distance - 1)

    def handle_right(self):
        if self.step == ArtGuideStep.ACTION:
            self.action_index = min(len(_ACTIONS) - 1, self.action_index + 1)
        elif self.step == ArtGuideStep.DIRECTION:
            self.dir_index = min(len(_DIRECTIONS) - 1, self.dir_index + 1)
        elif self.step == ArtGuideStep.DISTANCE:
            self.distance = min(20, self.distance + 1)

    def confirm(self) -> tuple[str, str, int] | None:
        """Confirm current step. Returns (action, direction, distance) when complete, else None."""
        if self.step == ArtGuideStep.ACTION:
            self.step = ArtGuideStep.DIRECTION
            return None
        elif self.step == ArtGuideStep.DIRECTION:
            self.step = ArtGuideStep.DISTANCE
            return None
        else:
            action = _ACTIONS[self.action_index].lower()
            direction = _DIRECTIONS[self.dir_index]
            distance = self.distance
            self.reset()
            return (action, direction, distance)


# =============================================================================
# CODE PANEL WIDGET
# =============================================================================

class CodePanelFocusChanged(Message):
    """Posted when code panel focus state changes."""
    def __init__(self, focused: bool):
        super().__init__()
        self.focused = focused


class LogoCommand(Message):
    """Posted when an art guide logo command is confirmed."""
    def __init__(self, action: str, direction: str, distance: int):
        super().__init__()
        self.action = action
        self.direction = direction
        self.distance = distance


class EvaluateExpression(Message):
    """Posted when the play panel input wants to evaluate an expression."""
    def __init__(self, expression: str):
        super().__init__()
        self.expression = expression


class CodePanel(Widget):
    """Inline code panel showing a live trail of blocks.

    Renders blocks as colored cells in a horizontal layout, wrapping to
    new lines. Each room has separate content. Supports cursor navigation,
    deletion, and replay.
    """

    DEFAULT_CSS = """
    CodePanel {
        width: 100%;
        height: 100%;
        background: #120a20;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Per-room block lists
        self._blocks: dict[str, list[CodeBlock]] = {
            "music": [],
            "art": [],
            "play": [],
        }
        self._room = "music"
        self._panel_focused = False
        self._cursor_pos = 0        # Index into current room's block list
        self._scroll_offset = 0     # First visible line index
        self._replay_task: asyncio.Task | None = None
        self._backspace_start: float = 0  # For hold-to-clear detection
        self._HOLD_CLEAR_THRESHOLD = 0.8  # Seconds to hold for clear all

        # Art guide (Logo-like step-by-step flow)
        self._art_guide = ArtGuide()

        # Play state (expression accumulation with `it`)
        self._play_state: dict = {"it": None}
        self._play_input_buffer: str = ""

    @property
    def panel_focused(self) -> bool:
        return self._panel_focused

    def set_room(self, room: str) -> None:
        """Switch which room's blocks are displayed."""
        if room in self._blocks:
            self._room = room
            self._cursor_pos = min(self._cursor_pos, len(self._blocks[room]))
            self.refresh()

    def enter_panel(self) -> None:
        """Called when user arrows down into the panel."""
        self._panel_focused = True
        blocks = self._blocks[self._room]
        self._cursor_pos = max(0, len(blocks) - 1)
        self._art_guide.reset()
        self._play_input_buffer = ""
        self.refresh()
        self.post_message(CodePanelFocusChanged(True))

    def exit_panel(self) -> None:
        """Called when user arrows up out of the panel."""
        self._panel_focused = False
        self.refresh()
        self.post_message(CodePanelFocusChanged(False))

    def add_block(self, block: CodeBlock) -> None:
        """Add a block to the current room's trail."""
        blocks = self._blocks[self._room]

        # For strokes, merge consecutive same-direction
        if (block.kind == "stroke" and blocks
                and blocks[-1].kind == "stroke"
                and blocks[-1].direction == block.direction):
            blocks[-1].distance += block.distance
            arrow = DIRECTION_ARROWS.get(block.direction, "?")
            d = blocks[-1].distance
            blocks[-1].label = f"{arrow}{d}" if d > 1 else arrow
            blocks[-1].width = max(CODE_BLOCK_WIDTH, len(blocks[-1].label) + 2)
        else:
            blocks.append(block)

        # Auto-scroll to bottom
        self._scroll_to_bottom()
        self.refresh()

    def delete_at_cursor(self) -> None:
        """Delete the block at the cursor position."""
        blocks = self._blocks[self._room]
        if not blocks or self._cursor_pos >= len(blocks):
            return
        blocks.pop(self._cursor_pos)
        if self._cursor_pos > 0 and self._cursor_pos >= len(blocks):
            self._cursor_pos = len(blocks) - 1
        self.refresh()

    def clear_room(self) -> None:
        """Clear all blocks for the current room."""
        self._blocks[self._room].clear()
        self._cursor_pos = 0
        self._scroll_offset = 0
        self.refresh()

    def move_cursor(self, direction: int) -> bool:
        """Move cursor left (-1) or right (+1). Returns False if at boundary."""
        blocks = self._blocks[self._room]
        if not blocks:
            return False
        new_pos = self._cursor_pos + direction
        if new_pos < 0:
            return False  # At left edge
        if new_pos >= len(blocks):
            return False  # At right edge
        self._cursor_pos = new_pos
        self.refresh()
        return True

    def get_blocks(self) -> list[CodeBlock]:
        """Get the current room's blocks."""
        return self._blocks[self._room]

    def get_replay_data(self) -> list[CodeBlock]:
        """Get blocks for replay (excludes newline markers)."""
        return [b for b in self._blocks[self._room] if b.kind != "newline"]

    # ── Layout helpers ────────────────────────────────────────────

    def _layout_lines(self) -> list[list[tuple[CodeBlock, int]]]:
        """Layout blocks into lines that fit the panel width.

        Returns list of lines, each line is list of (block, block_index) tuples.
        """
        blocks = self._blocks[self._room]
        if not blocks:
            return []

        width = self.size.width
        if width <= 0:
            return []

        lines: list[list[tuple[CodeBlock, int]]] = []
        current_line: list[tuple[CodeBlock, int]] = []
        line_width = 0

        for i, block in enumerate(blocks):
            if block.kind == "newline":
                current_line.append((block, i))
                lines.append(current_line)
                current_line = []
                line_width = 0
                continue

            bw = block.width + 1  # +1 for gap between blocks
            if line_width + bw > width and current_line:
                lines.append(current_line)
                current_line = []
                line_width = 0

            current_line.append((block, i))
            line_width += bw

        if current_line:
            lines.append(current_line)

        return lines

    def _scroll_to_bottom(self) -> None:
        """Ensure the last line is visible."""
        lines = self._layout_lines()
        visible_rows = self._visible_rows()
        # Each line takes 1 row in the panel
        if len(lines) > visible_rows:
            self._scroll_offset = len(lines) - visible_rows
        else:
            self._scroll_offset = 0

    def _visible_rows(self) -> int:
        """How many rows of blocks are visible (panel height minus header and guide/input)."""
        reserved = 1  # header
        if self._panel_focused and self._room in ("art", "play"):
            reserved += 1  # guide or input line
        return max(1, self.size.height - reserved)

    # ── Rendering ─────────────────────────────────────────────────

    def render_line(self, y: int) -> Strip:
        """Render one line of the code panel."""
        width = self.size.width
        if width <= 0:
            return Strip.blank(0)

        bg = "#120a20"
        bg_style = Style(bgcolor=bg)

        # Line 0: header bar
        if y == 0:
            return self._render_header(width)

        height = self.size.height
        last_row = height - 1

        # Last row: art guide or play input when focused
        if self._panel_focused and y == last_row:
            if self._room == "art":
                return self._render_art_guide_line(width)
            elif self._room == "play":
                return self._render_play_input_line(width)

        # Block lines (reserve last row for guide/input when applicable)
        line_idx = y - 1 + self._scroll_offset
        lines = self._layout_lines()

        if line_idx < 0 or line_idx >= len(lines):
            return Strip([Segment(" " * width, bg_style)])

        return self._render_block_line(lines[line_idx], width)

    def _render_header(self, width: int) -> Strip:
        """Render the header bar showing room name and hints."""
        caps = getattr(self.app, 'caps_text', lambda x: x)

        room_label = caps(self._room.title())
        blocks = self._blocks[self._room]
        count = len([b for b in blocks if b.kind != "newline"])

        # Scroll indicators
        lines = self._layout_lines()
        visible = self._visible_rows()
        has_above = self._scroll_offset > 0
        has_below = len(lines) > self._scroll_offset + visible
        scroll_ind = ""
        if has_above:
            scroll_ind += " \u25b2"
        if has_below:
            scroll_ind += " \u25bc"

        if self._panel_focused:
            if self._room == "play":
                it_val = self._play_state.get("it")
                it_text = f"  it = {it_val}" if it_val is not None else ""
                header = f" {room_label} [{count}]{it_text}{scroll_ind}"
            elif self._room == "art":
                step_name = self._art_guide.step.value.title()
                header = f" {room_label} [{count}]  {caps(step_name)}{scroll_ind}"
            else:
                hints = caps("\u25c0\u25b6 move  \u232b delete  Space replay  \u25b2 back")
                header = f" {room_label} [{count}]{scroll_ind}  {hints}"
        else:
            header = f" {room_label} [{count}]{scroll_ind}"

        # Pad/truncate
        if len(header) < width:
            header = header + " " * (width - len(header))
        else:
            header = header[:width]

        style = Style(bgcolor="#1e1035", color="#b8a0d0", bold=True)
        return Strip([Segment(header, style)])

    def _render_block_line(self, line: list[tuple[CodeBlock, int]], width: int) -> Strip:
        """Render a single line of blocks."""
        segments: list[Segment] = []
        bg = "#120a20"
        bg_style = Style(bgcolor=bg)
        used = 0

        for block, idx in line:
            bw = block.width
            is_cursor = self._panel_focused and idx == self._cursor_pos

            # Block background
            block_bg = block.color
            if is_cursor:
                # Brighten for cursor
                block_bg = self._brighten(block_bg)

            text_color = "#FFFFFF"
            block_style = Style(
                bgcolor=block_bg,
                color=text_color,
                bold=is_cursor,
            )

            # For query blocks with results, show "expr → result"
            if block.kind == "query" and block.result:
                display = f"{block.expression} \u2192 {block.result}"
                bw = max(bw, len(display) + 2)

                result_style = Style(
                    bgcolor=COLOR_RESULT if not is_cursor else self._brighten(COLOR_RESULT),
                    color="#88ffaa",
                    bold=is_cursor,
                )
                expr_part = f" {block.expression} \u2192 "
                result_part = f"{block.result} "
                segments.append(Segment(expr_part, block_style))
                segments.append(Segment(result_part, result_style))
            else:
                # Center label in block width
                label = block.label[:bw]
                pad_left = (bw - len(label)) // 2
                pad_right = bw - pad_left - len(label)

                segments.append(Segment(" " * pad_left, Style(bgcolor=block_bg)))
                segments.append(Segment(label, block_style))
                segments.append(Segment(" " * pad_right, Style(bgcolor=block_bg)))

            # Gap between blocks
            if used + bw < width:
                segments.append(Segment(" ", bg_style))
                used += bw + 1
            else:
                used += bw

        # Fill remaining width
        remaining = width - used
        if remaining > 0:
            segments.append(Segment(" " * remaining, bg_style))

        return Strip(segments)

    def _render_art_guide_line(self, width: int) -> Strip:
        """Render the art guide menu at the bottom of the panel."""
        text = self._art_guide.get_display_text()
        style = Style(bgcolor="#1a2a3a", color="#88ccff", bold=True)
        if len(text) < width:
            text = " " + text + " " * (width - len(text) - 1)
        else:
            text = text[:width]
        return Strip([Segment(text, style)])

    def _render_play_input_line(self, width: int) -> Strip:
        """Render the play expression input line at the bottom of the panel."""
        prompt = "> "
        text = prompt + self._play_input_buffer + "\u2588"  # block cursor
        style = Style(bgcolor="#1a2a1a", color="#88ff88", bold=True)
        if len(text) < width:
            text = text + " " * (width - len(text))
        else:
            text = text[:width]
        return Strip([Segment(text, style)])

    @staticmethod
    def _brighten(hex_color: str) -> str:
        """Brighten a hex color for cursor highlight."""
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            r = min(255, r + 60)
            g = min(255, g + 60)
            b = min(255, b + 60)
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return "#808080"

    # ── Keyboard handling (when panel is focused) ─────────────────

    async def handle_keyboard_action(self, action) -> bool:
        """Handle keyboard input when panel is focused.

        Returns True if the action was consumed.
        """
        # Route to specialized handlers for art guide and play input
        if self._room == "art":
            return await self._art_guide_handle(action)
        if self._room == "play":
            return await self._play_input_handle(action)

        # Default handler (music and fallback)
        return await self._default_handle(action)

    async def _default_handle(self, action) -> bool:
        """Default keyboard handler for music room."""
        from .keyboard import NavigationAction, ControlAction, CharacterAction

        if isinstance(action, NavigationAction):
            if action.direction == "up":
                if self._scroll_offset > 0:
                    self._scroll_offset -= 1
                    self.refresh()
                else:
                    self.exit_panel()
                return True
            elif action.direction == "left":
                self.move_cursor(-1)
                return True
            elif action.direction == "right":
                self.move_cursor(1)
                return True
            elif action.direction == "down":
                lines = self._layout_lines()
                visible = self._visible_rows()
                max_offset = max(0, len(lines) - visible)
                if self._scroll_offset < max_offset:
                    self._scroll_offset += 1
                    self.refresh()
                return True

        # Reset backspace hold on key-up
        if isinstance(action, ControlAction) and not action.is_down:
            if action.action == "backspace":
                self._backspace_start = 0
            return True

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == "backspace":
                if action.is_repeat:
                    if (self._backspace_start > 0
                            and (time.monotonic() - self._backspace_start)
                            >= self._HOLD_CLEAR_THRESHOLD):
                        self.clear_room()
                        self._backspace_start = 0
                        return True
                else:
                    self._backspace_start = time.monotonic()
                self.delete_at_cursor()
                return True
            if action.action == "space":
                self._start_replay()
                return True
            if action.action == "escape":
                self.exit_panel()
                return True
            if action.action == "enter":
                # Enter cycles instruments in music, no-op in panel
                return True

        # Character keys in music: exit panel and let room handle them
        if isinstance(action, CharacterAction):
            self.exit_panel()
            return False

        return False

    # ── Art guide handler ────────────────────────────────────────

    async def _art_guide_handle(self, action) -> bool:
        """Handle keyboard when panel is focused in art room (Logo guide)."""
        from .keyboard import NavigationAction, ControlAction, CharacterAction

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == "escape":
                self._art_guide.reset()
                self.exit_panel()
                return True
            if action.action in ("enter", "space"):
                result = self._art_guide.confirm()
                if result is not None:
                    action_name, direction, distance = result
                    block = make_logo_block(action_name, direction, distance)
                    self.add_block(block)
                    self.post_message(LogoCommand(action_name, direction, distance))
                self.refresh()
                return True
            if action.action == "backspace":
                if not action.is_repeat:
                    self._backspace_start = time.monotonic()
                elif (self._backspace_start > 0
                      and (time.monotonic() - self._backspace_start)
                      >= self._HOLD_CLEAR_THRESHOLD):
                    self.clear_room()
                    self._backspace_start = 0
                    return True
                self.delete_at_cursor()
                return True

        if isinstance(action, ControlAction) and not action.is_down:
            if action.action == "backspace":
                self._backspace_start = 0
            return True

        if isinstance(action, NavigationAction):
            if action.direction == "left":
                self._art_guide.handle_left()
                self.refresh()
                return True
            elif action.direction == "right":
                self._art_guide.handle_right()
                self.refresh()
                return True
            elif action.direction == "up":
                if self._scroll_offset > 0:
                    self._scroll_offset -= 1
                    self.refresh()
                else:
                    self._art_guide.reset()
                    self.exit_panel()
                return True
            elif action.direction == "down":
                lines = self._layout_lines()
                visible = self._visible_rows()
                max_offset = max(0, len(lines) - visible)
                if self._scroll_offset < max_offset:
                    self._scroll_offset += 1
                    self.refresh()
                return True

        # Character keys exit panel in art
        if isinstance(action, CharacterAction):
            self._art_guide.reset()
            self.exit_panel()
            return False

        return False

    # ── Play input handler ───────────────────────────────────────

    async def _play_input_handle(self, action) -> bool:
        """Handle keyboard when panel is focused in play room (expression input)."""
        from .keyboard import NavigationAction, ControlAction, CharacterAction

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == "escape":
                self._play_input_buffer = ""
                self.exit_panel()
                return True
            if action.action == "enter":
                if self._play_input_buffer.strip():
                    self.post_message(EvaluateExpression(self._play_input_buffer.strip()))
                self.refresh()
                return True
            if action.action == "backspace":
                if self._play_input_buffer:
                    self._play_input_buffer = self._play_input_buffer[:-1]
                    self.refresh()
                else:
                    if not action.is_repeat:
                        self._backspace_start = time.monotonic()
                    elif (self._backspace_start > 0
                          and (time.monotonic() - self._backspace_start)
                          >= self._HOLD_CLEAR_THRESHOLD):
                        self.clear_room()
                        self._backspace_start = 0
                        return True
                    self.delete_at_cursor()
                return True
            if action.action == "space":
                self._play_input_buffer += " "
                self.refresh()
                return True

        if isinstance(action, ControlAction) and not action.is_down:
            if action.action == "backspace":
                self._backspace_start = 0
            return True

        if isinstance(action, NavigationAction):
            if action.direction == "up":
                if self._scroll_offset > 0:
                    self._scroll_offset -= 1
                    self.refresh()
                else:
                    self.exit_panel()
                return True
            elif action.direction == "down":
                lines = self._layout_lines()
                visible = self._visible_rows()
                max_offset = max(0, len(lines) - visible)
                if self._scroll_offset < max_offset:
                    self._scroll_offset += 1
                    self.refresh()
                return True
            elif action.direction in ("left", "right"):
                # Could add cursor movement in input buffer later
                return True

        if isinstance(action, CharacterAction):
            self._play_input_buffer += action.char
            self.refresh()
            return True

        return False

    def add_play_result(self, expression: str, result: str) -> None:
        """Add a query block with result from evaluation, update `it`."""
        self._play_state["it"] = result
        self._play_input_buffer = ""
        block = make_query_block(expression, result)
        self.add_block(block)
        self.refresh()

    # ── Replay ────────────────────────────────────────────────────

    def _start_replay(self) -> None:
        """Start replaying the current room's blocks."""
        if self._replay_task and not self._replay_task.done():
            self._replay_task.cancel()
            return
        blocks = self.get_replay_data()
        if blocks:
            self._replay_task = asyncio.create_task(self._do_replay(blocks))

    async def _do_replay(self, blocks: list[CodeBlock]) -> None:
        """Replay blocks with timing. Emits ReplayBlock messages."""
        try:
            for block in blocks:
                if block.gap_ms > 0:
                    await asyncio.sleep(block.gap_ms / 1000.0)
                self.post_message(ReplayBlock(block))
        except asyncio.CancelledError:
            pass


class ReplayBlock(Message):
    """Posted during replay for each block that should be executed."""
    def __init__(self, block: CodeBlock):
        super().__init__()
        self.block = block
