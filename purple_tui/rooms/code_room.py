"""
Code Room (F4): Cross-Room Visual Programming

Shows recorded blocks in a uniform grid layout. Every block is 5 chars wide,
3 rows tall. MODE_SWITCH blocks start new lines with gutter icons.
REPEAT blocks show as gutter metadata. Tab opens a menu modal.
Space plays the program. "Watch me!" captures keypresses in another room.

Mode-aware editing: what a keypress does depends on the MODE_SWITCH context.
Play context uses compose mode for QUERY blocks.

Keyboard input is received via handle_keyboard_action() from the main app,
which reads directly from evdev.
"""

import asyncio
from typing import Callable

from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from textual.message import Message
from textual import events
from rich.segment import Segment
from rich.style import Style

from ..keyboard import CharacterAction, NavigationAction, ControlAction
from ..caps import caps_strip
from ..program import (
    ProgramBlock,
    ProgramBlockType,
    BLOCK_WIDTH,
    BLOCK_ROWS,
    QUERY_COLOR,
    blocks_to_playback_actions,
    save_program,
    load_program,
    TARGET_ICONS,
    TARGET_COLORS,
    TARGET_LABELS,
    TARGET_MUSIC_MUSIC,
    TARGET_PLAY,
    TARGET_ART_PAINT,
    ALL_TARGETS,
    PAUSE_PRESETS,
    DIRECTION_ICONS,
    ROOM_ICONS,
    ROOM_COLORS,
    ROOM_ORDER,
    ROOMS,
    target_room,
    default_target_for_room,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# Theme colors (matching art mode)
BG_DARK = "#2a1845"
BG_LIGHT = "#e8daf0"
FG_DARK = "#d4c4e8"
FG_LIGHT = "#3a2a50"

# Block rendering
BLOCK_SELECTED_COLOR = "#FFD700"  # gold highlight for cursor
CURSOR_COLOR = "#6633AA"          # blinking insertion-point cursor
CURSOR_BLINK_INTERVAL = 0.4      # seconds
GUTTER_WIDTH = 3                  # left gutter for mode icons

# Repeat badge in gutter
REPEAT_BADGE_COLOR = "#2d9e8a"


# =============================================================================
# LINE LAYOUT
# =============================================================================

def _layout_lines(blocks: list[ProgramBlock], content_width: int) -> list[tuple[str, list[tuple[int, ProgramBlock]], int]]:
    """Pre-process blocks into display lines.

    Returns list of (gutter_icon, [(block_index, block), ...], line_repeat) tuples.
    MODE_SWITCH blocks start a new line with their icon in the gutter.
    REPEAT blocks at end of a line are extracted as line metadata.
    Lines wrap automatically at content_width.
    """
    if not blocks:
        return []

    lines: list[tuple[str, list[tuple[int, ProgramBlock]], int]] = []
    current_icon = ""
    current_line: list[tuple[int, ProgramBlock]] = []
    current_width = 0

    for i, block in enumerate(blocks):
        if block.type == ProgramBlockType.MODE_SWITCH:
            if current_line:
                lines.append(_finalize_line(current_icon, current_line))
            current_icon = ROOM_ICONS.get(target_room(block.target), "?")
            current_line = [(i, block)]
            current_width = 0  # MODE_SWITCH doesn't take content space
            continue

        block_w = min(block.display_width, content_width)

        # Check if this block would overflow
        if current_width + block_w > content_width and current_line:
            lines.append(_finalize_line(current_icon, current_line))
            current_icon = ""  # continuation line: blank gutter
            current_line = [(i, block)]
            current_width = block_w
        else:
            current_line.append((i, block))
            current_width += block_w

    if current_line:
        lines.append(_finalize_line(current_icon, current_line))

    return lines


def _finalize_line(icon: str, line_blocks: list[tuple[int, ProgramBlock]]) -> tuple[str, list[tuple[int, ProgramBlock]], int]:
    """Extract REPEAT block at end of line as line_repeat metadata."""
    line_repeat = 0
    if line_blocks and line_blocks[-1][1].type == ProgramBlockType.REPEAT:
        line_repeat = line_blocks[-1][1].repeat_count
    return (icon, line_blocks, line_repeat)


def _cursor_to_line_pos(lines: list[tuple[str, list[tuple[int, ProgramBlock]], int]], cursor: int) -> tuple[int, int]:
    """Convert insertion-point cursor to (line_index, position_in_line).

    Cursor is an insertion point (0 to len(blocks)). Position N means
    "between block N-1 and block N".
    """
    if not lines:
        return 0, 0

    for line_idx, (_, line_blocks, _) in enumerate(lines):
        if not line_blocks:
            continue
        last_block_idx = line_blocks[-1][0]

        for pos, (block_idx, _) in enumerate(line_blocks):
            if block_idx == cursor:
                return line_idx, pos

        if cursor == last_block_idx + 1:
            if line_idx + 1 < len(lines):
                next_line_blocks = lines[line_idx + 1][1]
                if next_line_blocks and next_line_blocks[0][0] == cursor:
                    continue
            return line_idx, len(line_blocks)

    if lines:
        last_line_blocks = lines[-1][1]
        return len(lines) - 1, len(last_line_blocks)
    return 0, 0


def _get_mode_context(blocks: list[ProgramBlock], cursor: int) -> str:
    """Determine the MODE_SWITCH target context at the cursor position.

    Walks backward from cursor to find the most recent MODE_SWITCH block.
    Returns the target string, or "" if no context.
    """
    for i in range(min(cursor, len(blocks)) - 1, -1, -1):
        if blocks[i].type == ProgramBlockType.MODE_SWITCH:
            return blocks[i].target
    return ""



# =============================================================================
# CODE CANVAS (UNIFORM GRID DISPLAY)
# =============================================================================

class CodeCanvas(Widget):
    """Shows the program as a uniform grid of blocks.

    Every block is BLOCK_WIDTH (5) chars wide, BLOCK_ROWS (3) rows tall.
    MODE_SWITCH blocks start new lines with target icon in gutter.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._blocks: list[ProgramBlock] = []
        self._cursor: int = 0
        self._scroll_y: int = 0
        self._lines: list[tuple[str, list[tuple[int, ProgramBlock]], int]] = []
        self._cursor_visible = True
        self._blink_timer = None
        self.add_class("caps-sensitive")
        # Compose mode for QUERY blocks
        self._composing: bool = False
        self._compose_text: str = ""
        self._playing: bool = False
        self._adjusting: bool = False

    def on_mount(self) -> None:
        self._start_blink()

    def _toggle_blink(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.refresh()

    def _start_blink(self) -> None:
        self._cursor_visible = True
        if self._blink_timer is not None:
            self._blink_timer.stop()
        self._blink_timer = self.set_interval(CURSOR_BLINK_INTERVAL, self._toggle_blink)

    def _stop_blink(self) -> None:
        if self._blink_timer is not None:
            self._blink_timer.stop()
            self._blink_timer = None
        self._cursor_visible = True

    def _reset_blink(self) -> None:
        self._start_blink()

    def set_blocks(self, blocks: list[ProgramBlock], cursor: int) -> None:
        self._blocks = blocks
        self._cursor = cursor
        self._rebuild_lines()
        self._ensure_cursor_visible()
        self.refresh()

    def _rebuild_lines(self) -> None:
        content_width = max(1, (self.size.width or 112) - GUTTER_WIDTH)
        self._lines = _layout_lines(self._blocks, content_width)

    def _ensure_cursor_visible(self) -> None:
        if not self._lines:
            self._scroll_y = 0
            return
        line_idx, _ = _cursor_to_line_pos(self._lines, self._cursor)
        cursor_row_start = line_idx * BLOCK_ROWS
        cursor_row_end = cursor_row_start + BLOCK_ROWS
        visible_height = max(1, (self.size.height or 28) - 1)  # -1 for hint row

        if cursor_row_start < self._scroll_y:
            self._scroll_y = cursor_row_start
        elif cursor_row_end > self._scroll_y + visible_height:
            self._scroll_y = cursor_row_end - visible_height

    def _get_bg(self) -> str:
        try:
            return BG_DARK if "dark" in self.app.theme else BG_LIGHT
        except Exception:
            return BG_DARK

    def render_line(self, y: int) -> Strip:
        return caps_strip(self._render_line_impl(y), self.app)

    def _render_line_impl(self, y: int) -> Strip:
        width = self.size.width
        height = self.size.height
        bg = self._get_bg()
        bg_style = Style(bgcolor=bg)

        if not self._blocks:
            return self._render_empty_line(y, width, bg, bg_style, height)

        hint_row = height - 1
        if y == hint_row:
            return self._render_hint_line(width, bg, bg_style)

        content_y = y + self._scroll_y
        line_idx = content_y // BLOCK_ROWS
        sub_row = content_y % BLOCK_ROWS

        if line_idx < 0 or line_idx >= len(self._lines):
            return Strip([Segment(" " * width, bg_style)])

        icon, line_blocks, line_repeat = self._lines[line_idx]
        content_width = width - GUTTER_WIDTH

        # Check if the MODE_SWITCH on this line is being adjusted
        gutter_adjusting = False
        if self._adjusting and line_blocks:
            for bi, blk in line_blocks:
                if bi == self._cursor - 1 and blk.type == ProgramBlockType.MODE_SWITCH:
                    gutter_adjusting = True
                    break

        gutter_segments = self._render_gutter(
            icon, sub_row, bg, bg_style, line_repeat, gutter_adjusting
        )
        block_segments = self._render_block_strip(
            line_blocks, sub_row, content_width, bg, bg_style
        )

        return Strip(gutter_segments + block_segments)

    def _render_gutter(self, icon: str, sub_row: int, bg: str,
                       bg_style: Style, line_repeat: int = 0,
                       adjusting: bool = False) -> list[Segment]:
        """Render the 3-char left gutter."""
        if not icon:
            if line_repeat > 0 and sub_row == 1:
                badge = f"x{line_repeat}"
                badge_style = Style(color=REPEAT_BADGE_COLOR, bgcolor=bg, bold=True)
                display = badge[:GUTTER_WIDTH].center(GUTTER_WIDTH)
                return [Segment(display, badge_style)]
            return [Segment(" " * GUTTER_WIDTH, bg_style)]

        # Look up room color from icon
        target_color = None
        for room, r_icon in ROOM_ICONS.items():
            if r_icon == icon:
                target_color = ROOM_COLORS[room]
                break

        if not target_color:
            return [Segment(" " * GUTTER_WIDTH, bg_style)]

        # When adjusting MODE_SWITCH, blink gutter between gold and room color
        if adjusting and self._cursor_visible:
            target_color = BLOCK_SELECTED_COLOR

        block_style = Style(bgcolor=target_color)
        if sub_row == 1:
            text_color = "#FFFFFF" if _is_dark_color(target_color) else "#1A1A1A"
            icon_style = Style(color=text_color, bgcolor=target_color, bold=True)
            display = icon[:GUTTER_WIDTH].center(GUTTER_WIDTH)
            return [Segment(display, icon_style)]
        elif sub_row == 2 and line_repeat > 0:
            badge = f"x{line_repeat}"
            text_color = "#FFFFFF" if _is_dark_color(target_color) else "#1A1A1A"
            badge_style = Style(color=text_color, bgcolor=target_color)
            display = badge[:GUTTER_WIDTH].center(GUTTER_WIDTH)
            return [Segment(display, badge_style)]
        else:
            return [Segment(" " * GUTTER_WIDTH, block_style)]

    def _render_cursor_column(self, sub_row: int, bg: str, bg_style: Style) -> list[Segment]:
        """Render a 1-char-wide blinking cursor column."""
        if self._cursor_visible:
            cursor_style = Style(bgcolor=CURSOR_COLOR)
            return [Segment(" ", cursor_style)]
        else:
            return [Segment(" ", bg_style)]

    def _render_compose_block(self, sub_row: int, available_width: int,
                              bg: str, bg_style: Style) -> list[Segment]:
        """Render the in-progress compose block at cursor position."""
        text = self._compose_text
        desired_w = max(BLOCK_WIDTH, len(text) + 2)
        actual_w = min(desired_w, available_width)
        if actual_w <= 0:
            return []

        block_bg = QUERY_COLOR
        text_color = "#FFFFFF" if _is_dark_color(block_bg) else "#1A1A1A"

        if sub_row == 0 or sub_row == 2:
            border_style = Style(color=BLOCK_SELECTED_COLOR, bgcolor=bg)
            return [Segment("\u2500" * actual_w, border_style)]

        # sub_row == 1: body with compose text and blinking cursor
        max_text = actual_w - 2  # 1 char padding each side
        if max_text <= 0:
            body_style = Style(color=text_color, bgcolor=block_bg, bold=True)
            return [Segment(" " * actual_w, body_style)]

        display_text = text
        if len(display_text) > max_text:
            if max_text > 3:
                display_text = display_text[:max_text - 3] + "..."
            else:
                display_text = display_text[:max_text]

        cursor_char = "\u2502" if self._cursor_visible else " "
        if len(display_text) < max_text:
            display_text += cursor_char
        centered = _center_text(display_text, actual_w)
        body_style = Style(color=text_color, bgcolor=block_bg, bold=True)
        return [Segment(centered, body_style)]

    def _render_block_strip(self, line_blocks: list[tuple[int, ProgramBlock]],
                            sub_row: int, content_width: int,
                            bg: str, bg_style: Style) -> list[Segment]:
        """Render a horizontal strip of blocks for one sub-row.

        Blocks use their display_width (variable for QUERY blocks).
        During compose mode, a live preview block appears at cursor position.
        """
        segments: list[Segment] = []
        x_pos = 0

        def _maybe_render_cursor_or_compose():
            nonlocal x_pos
            if x_pos >= content_width:
                return
            if self._composing:
                compose_segs = self._render_compose_block(
                    sub_row, content_width - x_pos, bg, bg_style)
                segments.extend(compose_segs)
                x_pos += sum(len(s.text) for s in compose_segs)
            else:
                segments.extend(self._render_cursor_column(sub_row, bg, bg_style))
                x_pos += 1

        # Check if cursor is before first block on this line
        if line_blocks:
            first_block_idx = line_blocks[0][0]
            if self._cursor == first_block_idx:
                _maybe_render_cursor_or_compose()

        for block_idx, block in line_blocks:
            is_before_cursor = (block_idx == self._cursor - 1)
            is_adjusting = is_before_cursor and self._adjusting

            # Skip structural blocks in the strip
            if block.type == ProgramBlockType.MODE_SWITCH:
                # After MODE_SWITCH, check cursor
                if block_idx + 1 == self._cursor:
                    if x_pos < content_width:
                        _maybe_render_cursor_or_compose()
                continue

            if x_pos >= content_width:
                break

            block_w = min(block.display_width, content_width)
            visible_w = min(block_w, content_width - x_pos)

            block_bg = block.bg_color
            text_color = "#FFFFFF" if _is_dark_color(block_bg) else "#1A1A1A"

            # When adjusting, blink the entire block between gold and normal
            if is_adjusting and self._cursor_visible:
                block_bg = BLOCK_SELECTED_COLOR
                text_color = "#1A1A1A"

            if sub_row == 0:
                # Top border
                if is_before_cursor:
                    border_style = Style(color=BLOCK_SELECTED_COLOR, bgcolor=bg)
                    segments.append(Segment("\u2500" * visible_w, border_style))
                else:
                    segments.append(Segment(" " * visible_w, bg_style))

            elif sub_row == 1:
                # Block body with icon
                icon = block.icon
                # For QUERY blocks, truncate with ellipsis if needed
                if block.type == ProgramBlockType.QUERY and len(icon) > visible_w - 2:
                    max_text = visible_w - 2
                    if max_text > 3:
                        icon = icon[:max_text - 3] + "..."
                    elif max_text > 0:
                        icon = icon[:max_text]
                    else:
                        icon = ""
                icon_text = _center_text(icon, block_w)
                body_style = Style(color=text_color, bgcolor=block_bg,
                                   bold=is_before_cursor)
                for cx in range(visible_w):
                    char = icon_text[cx] if cx < len(icon_text) else " "
                    segments.append(Segment(char, body_style))

            elif sub_row == 2:
                # Bottom border
                if is_before_cursor:
                    border_style = Style(color=BLOCK_SELECTED_COLOR, bgcolor=bg)
                    segments.append(Segment("\u2500" * visible_w, border_style))
                else:
                    segments.append(Segment(" " * visible_w, bg_style))

            x_pos += block_w

            # After this block, check if cursor falls here
            if block_idx + 1 == self._cursor:
                if x_pos < content_width:
                    _maybe_render_cursor_or_compose()

        # Fill remaining content width
        chars_used = sum(len(s.text) for s in segments)
        remaining = content_width - chars_used
        if remaining > 0:
            segments.append(Segment(" " * remaining, bg_style))

        return segments

    def _render_empty_line(self, y: int, width: int, bg: str,
                           bg_style: Style, height: int) -> Strip:
        """Render a line when no blocks are present (Watch me! prompt)."""
        mid = height // 2
        if y == mid - 1:
            title = "Watch me!"
            title_style = Style(color="#FFD700", bgcolor=bg, bold=True)
            pad = max(0, (width - len(title)) // 2)
            return Strip([
                Segment(" " * pad, bg_style),
                Segment(title, title_style),
                Segment(" " * max(0, width - pad - len(title)), bg_style),
            ])
        elif y == mid + 1:
            hint = "Press Enter to record in another room"
            return self._centered_dim_text(hint, width, bg, bg_style)
        elif y == mid + 2:
            hint = "or just start typing to add blocks"
            return self._centered_dim_text(hint, width, bg, bg_style)
        elif y == mid + 4:
            hint = "\u2190\u2192 navigate   \u2191\u2193 lines   Tab menu"
            return self._centered_dim_text(hint, width, bg, bg_style)
        return Strip([Segment(" " * width, bg_style)])

    def _render_hint_line(self, width: int, bg: str,
                          bg_style: Style) -> Strip:
        """Render context-sensitive bottom hint line."""
        if self._composing:
            hint = "Enter confirm  Bksp edit  Esc cancel"
            return self._centered_dim_text(hint, width, bg, bg_style)

        if self._playing:
            hint = "Playing...  Space or Esc to stop"
            return self._centered_dim_text(hint, width, bg, bg_style)

        # Check block before cursor for context
        if self._cursor > 0 and self._cursor <= len(self._blocks):
            block = self._blocks[self._cursor - 1]
            if block.type == ProgramBlockType.MODE_SWITCH:
                label = TARGET_LABELS.get(block.target, block.target)
                if self._adjusting:
                    hint = f"{label}  \u2191\u2193 change mode  Enter/Esc done"
                else:
                    hint = f"{label}  Enter to change  Type to add blocks"
                return self._centered_dim_text(hint, width, bg, bg_style)
            elif block.type == ProgramBlockType.PAUSE:
                if self._adjusting:
                    hint = f"Pause {block.duration}s  \u2191\u2193 adjust  Enter/Esc done"
                else:
                    hint = f"Pause {block.duration}s  Enter to adjust  \u2190\u2192 move  Bksp delete"
                return self._centered_dim_text(hint, width, bg, bg_style)
            elif block.type == ProgramBlockType.STROKE:
                if self._adjusting:
                    hint = f"Stroke {block.direction} x{block.distance}  \u2191\u2193 adjust  Enter/Esc done"
                else:
                    hint = f"Stroke {block.direction} x{block.distance}  Enter to adjust  \u2190\u2192 move  Bksp delete"
                return self._centered_dim_text(hint, width, bg, bg_style)
            elif block.type == ProgramBlockType.REPEAT:
                if self._adjusting:
                    hint = f"Repeat x{block.repeat_count}  \u2191\u2193 adjust  Enter/Esc done"
                else:
                    hint = f"Repeat x{block.repeat_count}  Enter to adjust  \u2190\u2192 move  Bksp delete"
                return self._centered_dim_text(hint, width, bg, bg_style)

        hint = "\u2190\u2192 move  \u2191\u2193 lines  Bksp delete  Space play  Tab menu"
        return self._centered_dim_text(hint, width, bg, bg_style)

    def _centered_dim_text(self, text: str, width: int, bg: str,
                           bg_style: Style) -> Strip:
        pad = max(0, (width - len(text)) // 2)
        dim_style = Style(color="#808080", bgcolor=bg)
        return Strip([
            Segment(" " * pad, bg_style),
            Segment(text[:width], dim_style),
            Segment(" " * max(0, width - pad - len(text)), bg_style),
        ])

    async def _on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()


# =============================================================================
# COMMAND MODE CONTAINER
# =============================================================================

class WatchMeRequested(Message, bubble=True):
    """Posted when user triggers Watch me! (Enter on empty canvas or Tab menu)."""
    def __init__(self, room: str = "") -> None:
        super().__init__()
        self.room = room


class CodeMode(Container, can_focus=True):
    """Code Mode: cross-mode visual programming.

    Tab opens menu modal. Space plays program. "Watch me!" captures
    keypresses in another room and inserts them as blocks.
    Mode-context aware: typing behaves differently based on MODE_SWITCH context.
    """

    DEFAULT_CSS = """
    CodeMode {
        width: 100%;
        height: 100%;
    }

    CodeCanvas {
        width: 100%;
        height: 1fr;
    }
    """

    def __init__(self, dispatch_action: Callable | None = None, **kwargs):
        super().__init__(**kwargs)
        self._dispatch_action = dispatch_action
        self._blocks: list[ProgramBlock] = []
        self._cursor: int = 0
        self._active_slot: int = 0
        self._playing: bool = False
        self._play_task: asyncio.Task | None = None
        # Compose mode state for QUERY blocks
        self._composing: bool = False
        self._compose_text: str = ""
        # Adjustment mode: Enter on adjustable block toggles this
        self._adjusting: bool = False

    def compose(self) -> ComposeResult:
        yield CodeCanvas(id="code-canvas")

    def on_mount(self) -> None:
        self._refresh_all()

    def on_show(self) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        try:
            canvas = self.query_one("#code-canvas", CodeCanvas)
            canvas._composing = self._composing
            canvas._compose_text = self._compose_text
            canvas._playing = self._playing
            canvas._adjusting = self._adjusting
            canvas.set_blocks(self._blocks, self._cursor)
            canvas._reset_blink()
        except Exception:
            pass

    def _mode_context(self) -> str:
        """Get the current MODE_SWITCH context at cursor position."""
        return _get_mode_context(self._blocks, self._cursor)

    def _mode_switch_has_content(self, block_index: int) -> bool:
        """Check if a MODE_SWITCH block has content blocks after it.

        Returns True if there are non-MODE_SWITCH blocks between this
        MODE_SWITCH and the next MODE_SWITCH (or end of program).
        """
        for i in range(block_index + 1, len(self._blocks)):
            if self._blocks[i].type == ProgramBlockType.MODE_SWITCH:
                return False
            else:
                return True
        return False

    def _ensure_default_mode(self) -> None:
        """Auto-insert a default MODE_SWITCH when canvas is empty.

        Called lazily when user starts typing on an empty canvas.
        """
        if not self._blocks:
            self._blocks.append(ProgramBlock(
                type=ProgramBlockType.MODE_SWITCH,
                target=TARGET_MUSIC_MUSIC,
            ))
            self._cursor = 1

    # ── Keyboard handling ──────────────────────────────────────────────

    async def handle_keyboard_action(self, action) -> None:
        if self._playing:
            if isinstance(action, ControlAction) and action.is_down:
                if action.action in ('space', 'escape'):
                    self._stop_playback()
                    if action.action == 'escape':
                        self.app._escape_consumed_by_mode = True
            return

        # Compose mode intercepts all input
        if self._composing:
            await self._handle_compose(action)
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
        """Left/Right navigate (exits adjustment). Up/Down adjust block or jump lines."""
        if action.direction in ('left', 'right'):
            self._adjusting = False
            if action.direction == 'left':
                if self._cursor > 0:
                    self._cursor -= 1
            elif action.direction == 'right':
                if self._cursor < len(self._blocks):
                    self._cursor += 1
            self._refresh_all()
        elif action.direction in ('up', 'down'):
            # Only adjust block values when in adjustment mode
            if self._adjusting and self._cursor > 0 and self._blocks:
                direction = 1 if action.direction == 'up' else -1
                block = self._blocks[self._cursor - 1]
                if block.type == ProgramBlockType.MODE_SWITCH:
                    if not self._mode_switch_has_content(self._cursor - 1):
                        block.cycle_target(direction)
                        self._refresh_all()
                    return
                elif block.type == ProgramBlockType.PAUSE:
                    block.cycle_pause_duration(direction)
                    self._refresh_all()
                    return
                elif block.type == ProgramBlockType.STROKE:
                    block.cycle_stroke_distance(direction)
                    self._refresh_all()
                    return
                elif block.type == ProgramBlockType.REPEAT:
                    block.cycle_repeat_count(direction)
                    self._refresh_all()
                    return
            # Line navigation
            self._jump_line(1 if action.direction == 'down' else -1)

    _ADJUSTABLE_TYPES = frozenset({
        ProgramBlockType.MODE_SWITCH,
        ProgramBlockType.PAUSE,
        ProgramBlockType.STROKE,
        ProgramBlockType.REPEAT,
    })

    async def _handle_control(self, action: ControlAction) -> None:
        if action.action == 'escape':
            if self._adjusting:
                self._adjusting = False
                self._refresh_all()
                # Set flag so app knows not to open room picker
                self.app._escape_consumed_by_mode = True
            return

        if action.action == 'backspace':
            self._adjusting = False
            self._delete_block()
        elif action.action == 'space':
            self._adjusting = False
            await self._start_playback()
        elif action.action == 'enter':
            # Empty canvas: trigger Watch me!
            if not self._blocks:
                self.post_message(WatchMeRequested())
                return
            # Toggle adjustment mode for adjustable blocks
            if self._cursor > 0:
                block = self._blocks[self._cursor - 1]
                if block.type in self._ADJUSTABLE_TYPES:
                    # Don't allow adjusting a MODE_SWITCH that has content after it
                    if block.type == ProgramBlockType.MODE_SWITCH and self._mode_switch_has_content(self._cursor - 1):
                        pass  # Fall through to compose/new-line behavior below
                    else:
                        self._adjusting = not self._adjusting
                        self._refresh_all()
                        return
            context = self._mode_context()
            if context == TARGET_PLAY:
                # Start compose mode for QUERY block
                self._composing = True
                self._compose_text = ""
                self._refresh_all()
            else:
                # Start a new line: insert a MODE_SWITCH block
                # Default to same room context, or music if none
                current_target = context or TARGET_MUSIC_MUSIC
                self._insert_block(ProgramBlock(
                    type=ProgramBlockType.MODE_SWITCH,
                    target=current_target,
                ))
                # Enter adjustment mode so user can pick room with up/down
                self._adjusting = True
                self._refresh_all()
        elif action.action == 'menu':
            # Menu key inserts an enter symbol block
            if not self._blocks:
                self._ensure_default_mode()
            self._insert_block(ProgramBlock(
                type=ProgramBlockType.KEY,
                char="enter",
                is_control=True,
            ))
        elif action.action == 'tab':
            self._adjusting = False
            await self._open_menu()

    async def _handle_character(self, action: CharacterAction) -> None:
        if action.is_repeat:
            return

        # Empty canvas: auto-insert default MODE_SWITCH first
        if not self._blocks:
            self._ensure_default_mode()

        context = self._mode_context()

        if context == TARGET_PLAY:
            # Start compose mode with this character
            self._composing = True
            self._compose_text = action.char
            self._refresh_all()
            return

        # No context: default to KEY insert (should not happen with _ensure_default_mode)
        # Music / Art text / Art paint: insert KEY block
        self._insert_block(ProgramBlock(
            type=ProgramBlockType.KEY,
            char=action.char,
        ))

    # ── Compose mode (QUERY blocks) ──────────────────────────────────

    async def _handle_compose(self, action) -> None:
        """Handle input while composing a QUERY block."""
        if isinstance(action, CharacterAction) and not action.is_repeat:
            self._compose_text += action.char
            self._refresh_all()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter' and self._compose_text:
                # Finalize QUERY block
                self._insert_block(ProgramBlock(
                    type=ProgramBlockType.QUERY,
                    query_text=self._compose_text,
                ))
                self._composing = False
                self._compose_text = ""
                self._refresh_all()
            elif action.action == 'backspace':
                if self._compose_text:
                    self._compose_text = self._compose_text[:-1]
                    self._refresh_all()
                else:
                    # Empty backspace cancels compose
                    self._composing = False
                    self._refresh_all()
            elif action.action == 'escape':
                self._composing = False
                self._compose_text = ""
                self._refresh_all()
            elif action.action == 'space':
                self._compose_text += " "
                self._refresh_all()
            return

    # ── Tab menu ─────────────────────────────────────────────────────

    async def _open_menu(self) -> None:
        from ..code_menu import CodeMenuScreen
        menu = CodeMenuScreen()
        self.app.push_screen(menu, self._on_menu_result)

    def _on_menu_result(self, result: dict | None) -> None:
        if result is None:
            return

        action = result.get("action")

        if action == "insert_mode_switch":
            target = result.get("target", TARGET_MUSIC_MUSIC)
            self._insert_block(ProgramBlock(
                type=ProgramBlockType.MODE_SWITCH,
                target=target,
            ))

        elif action == "insert_enter":
            self._insert_block(ProgramBlock(
                type=ProgramBlockType.KEY,
                char="enter",
                is_control=True,
            ))

        elif action == "insert_repeat":
            self._insert_block(ProgramBlock(type=ProgramBlockType.REPEAT))

        elif action == "insert_pause":
            self._insert_block(ProgramBlock(
                type=ProgramBlockType.PAUSE,
                duration=0.5,
            ))

        elif action == "insert_stroke":
            self._insert_block(ProgramBlock(
                type=ProgramBlockType.STROKE,
                direction="right",
                distance=1,
            ))

        elif action == "load":
            slot = result.get("slot", 1)
            self._load_from_slot(slot)

        elif action == "save":
            slot = result.get("slot", 1)
            self._save_to_slot(slot)

        elif action == "clear":
            self._blocks.clear()
            self._cursor = 0
            self._active_slot = 0
            self._composing = False
            self._compose_text = ""
            self._refresh_all()

        elif action == "watch_me":
            room = result.get("room", "")
            self.post_message(WatchMeRequested(room=room))

    # ── Public API for Watch me! ────────────────────────────────────

    def insert_watched_blocks(self, blocks: list[ProgramBlock]) -> None:
        """Insert blocks captured during Watch me! at the current cursor position."""
        for block in blocks:
            self._blocks.insert(self._cursor, block)
            self._cursor += 1
        self._refresh_all()

    # ── Block operations ───────────────────────────────────────────────

    def _jump_line(self, direction: int) -> None:
        if not self._blocks:
            return
        try:
            canvas = self.query_one("#code-canvas", CodeCanvas)
        except Exception:
            return
        lines = canvas._lines
        if not lines:
            return

        cur_line, cur_pos = _cursor_to_line_pos(lines, self._cursor)
        target_line = cur_line + direction

        if target_line < 0:
            self._cursor = 0
        elif target_line >= len(lines):
            self._cursor = len(self._blocks)
        else:
            target_blocks = lines[target_line][1]
            if not target_blocks:
                self._cursor = 0
            elif cur_pos >= len(target_blocks):
                self._cursor = target_blocks[-1][0] + 1
            else:
                self._cursor = target_blocks[cur_pos][0]

        self._refresh_all()

    def _insert_block(self, block: ProgramBlock) -> None:
        self._blocks.insert(self._cursor, block)
        self._cursor += 1
        self._refresh_all()

    def _delete_block(self) -> None:
        if self._cursor <= 0 or not self._blocks:
            return
        self._blocks.pop(self._cursor - 1)
        self._cursor -= 1
        self._refresh_all()

    # ── Playback ───────────────────────────────────────────────────────

    async def _start_playback(self) -> None:
        if not self._blocks or not self._dispatch_action:
            return

        playback_actions = blocks_to_playback_actions(self._blocks)
        if not playback_actions:
            return

        if hasattr(self.app, 'clear_all_state'):
            self.app.clear_all_state()

        self._playing = True

        from ..playback.player import PlaybackPlayer

        is_art_paint = None
        is_music_letters = None
        if hasattr(self.app, '_get_art_paint_mode_callback'):
            is_art_paint = self.app._get_art_paint_mode_callback()
        if hasattr(self.app, '_get_music_letters_mode_callback'):
            is_music_letters = self.app._get_music_letters_mode_callback()

        player = PlaybackPlayer(
            dispatch_action=self._dispatch_action,
            speed_multiplier=1.0,
            is_doodle_paint_mode=is_art_paint,
            is_play_letters_mode=is_music_letters,
        )

        async def _run_playback():
            try:
                await player.play(playback_actions)
            finally:
                self._playing = False
                from ..keyboard import RoomAction
                from ..constants import ROOM_CODE
                await self._dispatch_action(RoomAction(room=ROOM_CODE[0]))

        self._play_task = asyncio.create_task(_run_playback())

    def _stop_playback(self) -> None:
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
        self._playing = False

    # ── Save/Load ──────────────────────────────────────────────────────

    def _save_to_slot(self, slot: int) -> None:
        if not self._blocks:
            return
        source_room = "music"
        for block in self._blocks:
            if block.type == ProgramBlockType.MODE_SWITCH:
                target = block.target
                if target.startswith("music"):
                    source_room = "music"
                elif target.startswith("art"):
                    source_room = "art"
                elif target.startswith("play"):
                    source_room = "play"
                break
        save_program(self._blocks, slot, source_room)
        self._active_slot = slot
        self._refresh_all()

    def _load_from_slot(self, slot: int) -> None:
        result = load_program(slot)
        if result is not None:
            self._blocks, source_room = result
            self._cursor = len(self._blocks)
            self._active_slot = slot
            self._refresh_all()

    async def _on_key(self, event: events.Key) -> None:
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
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return True
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 128
