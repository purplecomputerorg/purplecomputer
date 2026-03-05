"""
Code Mode (F4): Cross-Mode Visual Programming

Shows recorded blocks in a multi-line layout with mode icons in a left gutter.
MODE_SWITCH blocks start new lines. Long sections wrap. Tab opens a menu modal.
Space plays the program. F5 (handled globally) records across modes.

Keyboard input is received via handle_keyboard_action() from the main app,
which reads directly from evdev.
"""

import asyncio
from typing import Callable

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from textual import events
from rich.segment import Segment
from rich.style import Style

from ..keyboard import CharacterAction, NavigationAction, ControlAction
from ..program import (
    ProgramBlock,
    ProgramBlockType,
    gap_width,
    blocks_to_playback_actions,
    save_program,
    load_program,
    slot_occupied,
    TARGET_ICONS,
    TARGET_COLORS,
    TARGET_PLAY_MUSIC,
    ALL_TARGETS,
)
from ..recording import RecordingManager


# =============================================================================
# CONSTANTS
# =============================================================================

# Theme colors (matching doodle mode)
BG_DARK = "#2a1845"
BG_LIGHT = "#e8daf0"
FG_DARK = "#d4c4e8"
FG_LIGHT = "#3a2a50"

# Block rendering
ICON_WIDTH = 4           # fixed character width for the icon section
BLOCK_SELECTED_COLOR = "#FFD700"  # gold highlight for cursor
GUTTER_WIDTH = 3         # left gutter for mode icons

# Repeat badge in gutter
REPEAT_BADGE_COLOR = "#2d9e8a"

# Save bar
SAVE_BAR_HEIGHT = 2
NUM_SLOTS = 9
SLOT_FILLED_COLOR = "#9b7bc4"
SLOT_EMPTY_COLOR = "#3a2a50"
SLOT_ACTIVE_COLOR = "#FFD700"

# Block strip layout rows (relative to each display line)
BLOCK_HEIGHT = 4  # border_top + body1 + body2 + border_bottom


# =============================================================================
# LINE LAYOUT
# =============================================================================

def _layout_lines(blocks: list[ProgramBlock], content_width: int) -> list[tuple[str, list[tuple[int, ProgramBlock]], int]]:
    """Pre-process blocks into display lines.

    Returns list of (icon, [(block_index, block), ...], line_repeat) tuples.
    MODE_SWITCH blocks start a new line with their icon in the gutter.
    REPEAT blocks at the end of a line are extracted as line metadata
    (line_repeat count) and not rendered in the strip.
    If a section overflows content_width, it wraps (continuation lines
    have empty gutter icon "").

    Each block in the result includes its original index in the flat blocks list.
    """
    if not blocks:
        return []

    lines: list[tuple[str, list[tuple[int, ProgramBlock]], int]] = []
    current_icon = ""
    current_line: list[tuple[int, ProgramBlock]] = []
    current_width = 0

    for i, block in enumerate(blocks):
        if block.type == ProgramBlockType.MODE_SWITCH:
            # Flush current line
            if current_line:
                lines.append(_finalize_line(current_icon, current_line))
            # Start new line with this block's icon
            current_icon = TARGET_ICONS.get(block.target, "?")
            current_line = [(i, block)]
            current_width = block.total_width
            continue

        block_w = block.total_width

        # Check if this block would overflow
        if current_width + block_w > content_width and current_line:
            # Wrap: flush current line, start continuation
            lines.append(_finalize_line(current_icon, current_line))
            current_icon = ""  # continuation line: blank gutter
            current_line = [(i, block)]
            current_width = block_w
        else:
            current_line.append((i, block))
            current_width += block_w

    # Flush last line
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
    """Convert flat cursor index to (line_index, position_in_line)."""
    for line_idx, (_, line_blocks, _) in enumerate(lines):
        for pos, (block_idx, _) in enumerate(line_blocks):
            if block_idx == cursor:
                return line_idx, pos
    return 0, 0


# =============================================================================
# SAVE BAR WIDGET
# =============================================================================

class SaveBar(Widget):
    """Shows 9 save slots at the top of Code mode.

    Filled slots are bright, empty are dim. Active slot is highlighted.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_slot: int = 0  # 0 = none active
        self._filled: set[int] = set()

    def update_slots(self, active: int = 0) -> None:
        self._active_slot = active
        self._filled = {i for i in range(1, NUM_SLOTS + 1) if slot_occupied(i)}
        self.refresh()

    def _get_bg(self) -> str:
        try:
            return BG_DARK if "dark" in self.app.theme else BG_LIGHT
        except Exception:
            return BG_DARK

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        bg = self._get_bg()
        bg_style = Style(bgcolor=bg)

        if y >= SAVE_BAR_HEIGHT:
            return Strip([Segment(" " * width, bg_style)])

        segments = []
        # Center the slots
        slot_width = 4  # "·N· " per slot
        total_slots_width = slot_width * NUM_SLOTS
        pad = max(0, (width - total_slots_width) // 2)

        if y == 0:
            # Label row
            label = "Programs"
            label_pad = max(0, (width - len(label)) // 2)
            dim_style = Style(color="#808080", bgcolor=bg)
            segments.append(Segment(" " * label_pad, bg_style))
            segments.append(Segment(label, dim_style))
            segments.append(Segment(" " * max(0, width - label_pad - len(label)), bg_style))
        else:
            # Slot indicators
            segments.append(Segment(" " * pad, bg_style))
            chars_used = pad
            for slot in range(1, NUM_SLOTS + 1):
                if slot == self._active_slot:
                    color = SLOT_ACTIVE_COLOR
                elif slot in self._filled:
                    color = SLOT_FILLED_COLOR
                else:
                    color = SLOT_EMPTY_COLOR

                style = Style(color=color, bgcolor=bg, bold=(slot == self._active_slot))
                # Show filled slots as solid, empty as outline
                if slot in self._filled:
                    segments.append(Segment(f" {slot}\u25a0 ", style))
                else:
                    segments.append(Segment(f" {slot}\u25a1 ", style))
                chars_used += slot_width

            remaining = width - chars_used
            if remaining > 0:
                segments.append(Segment(" " * remaining, bg_style))

        return Strip(segments)

    async def _on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()


# =============================================================================
# CODE CANVAS (MULTI-LINE BLOCK DISPLAY)
# =============================================================================

class CodeCanvas(Widget):
    """Shows the program as multi-line colored blocks with mode gutter icons.

    MODE_SWITCH blocks start new lines with their target icon in a 3-char
    left gutter. Long sections wrap with blank gutter. Vertical scrolling
    when content exceeds viewport.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._blocks: list[ProgramBlock] = []
        self._cursor: int = 0
        self._scroll_y: int = 0  # vertical scroll offset in display rows
        self._lines: list[tuple[str, list[tuple[int, ProgramBlock]], int]] = []

    def set_blocks(self, blocks: list[ProgramBlock], cursor: int) -> None:
        self._blocks = blocks
        self._cursor = cursor
        self._rebuild_lines()
        self._ensure_cursor_visible()
        self.refresh()

    def _rebuild_lines(self) -> None:
        """Rebuild the line layout from blocks."""
        content_width = max(1, (self.size.width or 112) - GUTTER_WIDTH)
        self._lines = _layout_lines(self._blocks, content_width)

    def _ensure_cursor_visible(self) -> None:
        """Scroll to make the cursor line visible."""
        if not self._lines:
            self._scroll_y = 0
            return
        line_idx, _ = _cursor_to_line_pos(self._lines, self._cursor)
        # Each line occupies BLOCK_HEIGHT rows
        cursor_row_start = line_idx * BLOCK_HEIGHT
        cursor_row_end = cursor_row_start + BLOCK_HEIGHT
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
        width = self.size.width
        height = self.size.height
        bg = self._get_bg()
        bg_style = Style(bgcolor=bg)

        if not self._blocks:
            return self._render_empty_line(y, width, bg, bg_style, height)

        hint_row = height - 1
        if y == hint_row:
            return self._render_hint_line(width, bg, bg_style)

        # Map display y to content y (with vertical scrolling)
        content_y = y + self._scroll_y

        # Which line and sub-row?
        line_idx = content_y // BLOCK_HEIGHT
        sub_row = content_y % BLOCK_HEIGHT

        if line_idx < 0 or line_idx >= len(self._lines):
            return Strip([Segment(" " * width, bg_style)])

        icon, line_blocks, line_repeat = self._lines[line_idx]
        content_width = width - GUTTER_WIDTH

        # Render gutter
        gutter_segments = self._render_gutter(icon, sub_row, bg, bg_style, line_idx, line_repeat)

        # Render block strip for this line
        block_segments = self._render_block_strip(
            line_blocks, sub_row, content_width, bg, bg_style
        )

        return Strip(gutter_segments + block_segments)

    def _render_gutter(self, icon: str, sub_row: int, bg: str,
                       bg_style: Style, line_idx: int,
                       line_repeat: int = 0) -> list[Segment]:
        """Render the 3-char left gutter as a solid colored block with icon.

        Shows line_repeat count (e.g. "x3") on row 2 when a REPEAT block
        is attached to this line.
        """
        if not icon:
            # No mode icon, but still show repeat badge if present
            if line_repeat > 0 and sub_row == 2:
                badge = f"x{line_repeat}"
                badge_style = Style(color=REPEAT_BADGE_COLOR, bgcolor=bg, bold=True)
                display = badge[:GUTTER_WIDTH].center(GUTTER_WIDTH)
                return [Segment(display, badge_style)]
            return [Segment(" " * GUTTER_WIDTH, bg_style)]

        # Find the target color for this icon
        target_color = None
        for target, t_icon in TARGET_ICONS.items():
            if t_icon == icon:
                target_color = TARGET_COLORS[target]
                break

        if not target_color:
            return [Segment(" " * GUTTER_WIDTH, bg_style)]

        # Render all rows as a solid colored block
        block_style = Style(bgcolor=target_color)
        if sub_row == 1:
            # Icon row: show icon text on the colored block
            text_color = "#FFFFFF" if _is_dark_color(target_color) else "#1A1A1A"
            icon_style = Style(color=text_color, bgcolor=target_color, bold=True)
            display = icon[:GUTTER_WIDTH].center(GUTTER_WIDTH)
            return [Segment(display, icon_style)]
        elif sub_row == 2 and line_repeat > 0:
            # Show repeat badge below icon
            badge = f"x{line_repeat}"
            text_color = "#FFFFFF" if _is_dark_color(target_color) else "#1A1A1A"
            badge_style = Style(color=text_color, bgcolor=target_color)
            display = badge[:GUTTER_WIDTH].center(GUTTER_WIDTH)
            return [Segment(display, badge_style)]
        else:
            # Other rows: solid colored block
            return [Segment(" " * GUTTER_WIDTH, block_style)]

    def _render_block_strip(self, line_blocks: list[tuple[int, ProgramBlock]],
                            sub_row: int, content_width: int,
                            bg: str, bg_style: Style) -> list[Segment]:
        """Render a horizontal strip of blocks for one sub-row."""
        segments: list[Segment] = []
        x_pos = 0

        # sub_row mapping: 0=border_top, 1=body1(icon), 2=body2, 3=border_bottom
        for block_idx, block in line_blocks:
            is_selected = (block_idx == self._cursor)
            icon_w = ICON_WIDTH
            gap_w = gap_width(block.gap_level)
            total_w = icon_w + gap_w

            # Skip MODE_SWITCH blocks in the strip (they're in the gutter)
            if block.type == ProgramBlockType.MODE_SWITCH:
                continue

            if x_pos >= content_width:
                break

            # Clip to content width
            visible_w = min(total_w, content_width - x_pos)

            block_bg = block.bg_color
            text_color = "#FFFFFF" if _is_dark_color(block_bg) else "#1A1A1A"
            gap_bg = _dim_color(block_bg)

            if sub_row == 0:
                # Top border
                if is_selected:
                    border_style = Style(color=BLOCK_SELECTED_COLOR, bgcolor=bg)
                    line = "\u25be" * min(icon_w, visible_w) + " " * max(0, visible_w - icon_w)
                    segments.append(Segment(line, border_style))
                else:
                    segments.append(Segment(" " * visible_w, bg_style))

            elif sub_row in (1, 2):
                # Block body: row 1 = icon, row 2 = count badge (if count > 1)
                if sub_row == 1:
                    icon = block.icon
                    icon_text = _center_text(icon, icon_w)
                elif block.count > 1:
                    badge = f"x{block.count}"
                    icon_text = _center_text(badge, icon_w)
                else:
                    icon_text = " " * icon_w

                body_style = Style(color=text_color, bgcolor=block_bg,
                                   bold=is_selected)
                gap_style = Style(color="#606060", bgcolor=gap_bg)

                for cx in range(visible_w):
                    if cx < icon_w:
                        char = icon_text[cx] if cx < len(icon_text) else " "
                        segments.append(Segment(char, body_style))
                    else:
                        segments.append(Segment("\u00b7", gap_style))

            elif sub_row == 3:
                # Bottom border / cursor
                if is_selected:
                    cursor_style = Style(color=BLOCK_SELECTED_COLOR, bgcolor=bg)
                    line = _center_text("\u25b4", min(icon_w, visible_w)) + " " * max(0, visible_w - icon_w)
                    segments.append(Segment(line[:visible_w], cursor_style))
                else:
                    segments.append(Segment(" " * visible_w, bg_style))

            x_pos += total_w

        # Fill remaining content width
        chars_used = sum(len(s.text) for s in segments)
        remaining = content_width - chars_used
        if remaining > 0:
            segments.append(Segment(" " * remaining, bg_style))

        return segments

    def _render_empty_line(self, y: int, width: int, bg: str,
                           bg_style: Style, height: int) -> Strip:
        """Render a line when no blocks are present."""
        mid = height // 2
        if y == mid - 1:
            hint = "Type keys to add blocks"
            return self._centered_dim_text(hint, width, bg, bg_style)
        elif y == mid:
            hint = "or press F5 to record in another mode!"
            return self._centered_dim_text(hint, width, bg, bg_style)
        elif y == mid + 2:
            hint = "\u2190\u2192 navigate   \u2191\u2193 adjust   Space play   Tab menu"
            return self._centered_dim_text(hint, width, bg, bg_style)
        return Strip([Segment(" " * width, bg_style)])

    def _render_hint_line(self, width: int, bg: str,
                          bg_style: Style) -> Strip:
        """Render the bottom hint line."""
        hint = "Type to add   \u2190\u2192 move   \u2191\u2193 adjust   Bksp delete   Space play   Tab menu"
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
# BUILD MODE CONTAINER (CODE MODE)
# =============================================================================

class BuildMode(Container, can_focus=True):
    """Code Mode: cross-mode visual programming.

    Tab opens menu modal. Space plays program. F5 recording handled globally.
    Enter inserts newline control block. Up/down adjusts gaps, repeat count,
    or MODE_SWITCH target.
    """

    DEFAULT_CSS = """
    BuildMode {
        width: 100%;
        height: 100%;
    }

    SaveBar {
        width: 100%;
        height: 2;
    }

    #code-separator {
        width: 100%;
        height: 1;
        color: $primary;
        text-align: center;
    }

    CodeCanvas {
        width: 100%;
        height: 1fr;
    }
    """

    def __init__(self, recording_manager: RecordingManager | None = None,
                 dispatch_action: Callable | None = None, **kwargs):
        super().__init__(**kwargs)
        self._recording_manager = recording_manager
        self._dispatch_action = dispatch_action
        self._blocks: list[ProgramBlock] = []
        self._cursor: int = 0
        self._active_slot: int = 0
        self._playing: bool = False
        self._play_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield SaveBar(id="save-bar")
        yield Static("\u2500" * 80, id="code-separator")
        yield CodeCanvas(id="code-canvas")

    def on_mount(self) -> None:
        self._import_from_recording()
        self._refresh_all()

    def on_show(self) -> None:
        """Refresh every time Code mode becomes visible.

        Auto-imports from recording manager if we have no blocks yet.
        """
        if not self._blocks:
            self._import_from_recording()
        self._refresh_all()

    def _import_from_recording(self) -> None:
        """Import blocks from the recording manager."""
        if self._recording_manager and self._recording_manager.has_recording():
            self._blocks = self._recording_manager.to_blocks()
            self._cursor = max(0, len(self._blocks) - 1)

    def _refresh_all(self) -> None:
        """Update both save bar and code canvas."""
        try:
            save_bar = self.query_one("#save-bar", SaveBar)
            save_bar.update_slots(self._active_slot)
        except Exception:
            pass

        try:
            canvas = self.query_one("#code-canvas", CodeCanvas)
            canvas.set_blocks(self._blocks, self._cursor)
        except Exception:
            pass

    # ── Keyboard handling ──────────────────────────────────────────────

    async def handle_keyboard_action(self, action) -> None:
        """Route keyboard actions.

        Characters insert blocks, arrows navigate/adjust, Space plays,
        Backspace deletes, Tab opens menu, Enter inserts newline block.
        """
        if self._playing:
            if isinstance(action, ControlAction) and action.is_down:
                if action.action == 'space':
                    self._stop_playback()
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
                self._cursor -= 1
                self._refresh_all()
        elif action.direction == 'right':
            if self._blocks and self._cursor < len(self._blocks) - 1:
                self._cursor += 1
                self._refresh_all()
        elif action.direction == 'up':
            self._adjust_block(1)
        elif action.direction == 'down':
            self._adjust_block(-1)

    async def _handle_control(self, action: ControlAction) -> None:
        if action.action == 'backspace':
            self._delete_block()
        elif action.action == 'space':
            await self._start_playback()
        elif action.action == 'enter':
            new_block = ProgramBlock(
                type=ProgramBlockType.CONTROL, control="enter",
            )
            if not self._try_auto_collapse(new_block):
                self._insert_block(new_block)
        elif action.action == 'tab':
            await self._open_menu()

    async def _handle_character(self, action: CharacterAction) -> None:
        if action.is_repeat:
            return
        new_block = ProgramBlock(
            type=ProgramBlockType.KEY, char=action.char,
        )
        if not self._try_auto_collapse(new_block):
            self._insert_block(new_block)

    # ── Tab menu ─────────────────────────────────────────────────────

    async def _open_menu(self) -> None:
        """Open the Code menu modal."""
        from ..code_menu import CodeMenuScreen
        menu = CodeMenuScreen()
        self.app.push_screen(menu, self._on_menu_result)

    def _on_menu_result(self, result: dict | None) -> None:
        """Handle menu modal result."""
        if result is None:
            return

        action = result.get("action")

        if action == "record":
            # Start recording in the specified mode/sub-mode
            target = result.get("target", TARGET_PLAY_MUSIC)
            self._start_record_in(target)

        elif action == "insert_mode_switch":
            target = result.get("target", TARGET_PLAY_MUSIC)
            self._insert_block(ProgramBlock(
                type=ProgramBlockType.MODE_SWITCH,
                target=target,
            ))

        elif action == "insert_repeat":
            self._insert_block(ProgramBlock(type=ProgramBlockType.REPEAT))

        elif action == "load":
            slot = result.get("slot", 1)
            self._load_from_slot(slot)

        elif action == "save":
            slot = result.get("slot", 1)
            self._save_to_slot(slot)

        elif action == "adjust":
            direction = result.get("direction", 1)
            self._adjust_block(direction)

        elif action == "clear":
            self._blocks.clear()
            self._cursor = 0
            self._active_slot = 0
            self._refresh_all()

    def _start_record_in(self, target: str) -> None:
        """Start recording and switch to the target mode/sub-mode."""
        if not self._recording_manager or not self._dispatch_action:
            return

        self._recording_manager.start_recording()

        # Parse target to get mode and sub-mode
        parts = target.split(".", 1)
        main_mode = parts[0]

        # Switch to the target mode (this will exit Code mode)
        from ..keyboard import ModeAction
        asyncio.create_task(self._dispatch_action(ModeAction(mode=main_mode)))

        # Sub-mode toggle will be handled after mode switch via a small delay
        if len(parts) > 1:
            sub_mode = parts[1]
            asyncio.create_task(self._toggle_sub_mode_after_switch(main_mode, sub_mode))

    async def _toggle_sub_mode_after_switch(self, mode: str, sub_mode: str) -> None:
        """Toggle sub-mode after a mode switch (needs short delay for mount)."""
        await asyncio.sleep(0.2)
        if not self._dispatch_action:
            return

        needs_tab = False
        if mode == "play" and sub_mode == "letters":
            # Play mode starts in music, need tab for letters
            needs_tab = True
        elif mode == "doodle" and sub_mode == "paint":
            # Doodle mode starts in text, need tab for paint
            needs_tab = True

        if needs_tab:
            await self._dispatch_action(ControlAction(action='tab', is_down=True))

    # ── Block operations ───────────────────────────────────────────────

    def _try_auto_collapse(self, new_block: ProgramBlock) -> bool:
        """Try to auto-collapse new_block into the current block.

        If the current block matches, increment its count and return True.
        Otherwise return False (caller should insert normally).
        """
        if not self._blocks:
            return False
        current = self._blocks[self._cursor]
        if current.matches(new_block):
            current.count += 1
            self._refresh_all()
            return True
        return False

    def _jump_line(self, direction: int) -> None:
        """Jump cursor to the previous (-1) or next (+1) line."""
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
            # Already on first line: jump to first block
            self._cursor = 0
        elif target_line >= len(lines):
            # Already on last line: jump to last block
            self._cursor = len(self._blocks) - 1
        else:
            # Jump to same position on target line (or last block if shorter)
            target_blocks = lines[target_line][1]
            pos = min(cur_pos, len(target_blocks) - 1)
            self._cursor = target_blocks[pos][0]

        self._refresh_all()

    def _adjust_block(self, direction: int) -> None:
        """Adjust the current block: count, gap, repeat count, or cycle target.

        For blocks with count > 1, up/down adjusts the count. When count
        reaches 1 via down, further down adjusts gap. For single blocks
        (count=1), up/down adjusts gap as before.
        """
        if not self._blocks:
            return
        block = self._blocks[self._cursor]
        if block.type == ProgramBlockType.REPEAT:
            block.cycle_repeat_count(direction)
        elif block.type == ProgramBlockType.MODE_SWITCH:
            block.cycle_target(direction)
        elif block.count > 1:
            block.cycle_count(direction)
        else:
            block.cycle_gap(direction)
        self._refresh_all()

    def _insert_block(self, block: ProgramBlock) -> None:
        """Insert a block after the cursor."""
        if self._blocks:
            self._blocks.insert(self._cursor + 1, block)
            self._cursor += 1
        else:
            self._blocks.append(block)
            self._cursor = 0
        self._refresh_all()

    def _delete_block(self) -> None:
        """Delete the block at cursor."""
        if not self._blocks:
            return
        self._blocks.pop(self._cursor)
        if self._cursor >= len(self._blocks) and self._cursor > 0:
            self._cursor -= 1
        self._refresh_all()

    # ── Playback ───────────────────────────────────────────────────────

    async def _start_playback(self) -> None:
        """Play the program: clear target mode state, then replay actions."""
        if not self._blocks or not self._dispatch_action:
            return

        playback_actions = blocks_to_playback_actions(self._blocks)
        if not playback_actions:
            return

        # Clear target mode state so playback starts fresh
        if hasattr(self.app, 'clear_all_state'):
            self.app.clear_all_state()

        self._playing = True

        from ..playback.player import PlaybackPlayer

        # Get sub-mode callbacks from app if available
        is_doodle_paint = None
        is_play_letters = None
        if hasattr(self.app, '_get_doodle_paint_mode_callback'):
            is_doodle_paint = self.app._get_doodle_paint_mode_callback()
        if hasattr(self.app, '_get_play_letters_mode_callback'):
            is_play_letters = self.app._get_play_letters_mode_callback()

        player = PlaybackPlayer(
            dispatch_action=self._dispatch_action,
            speed_multiplier=1.0,
            is_doodle_paint_mode=is_doodle_paint,
            is_play_letters_mode=is_play_letters,
        )

        async def _run_playback():
            try:
                await player.play(playback_actions)
            finally:
                self._playing = False
                from ..keyboard import ModeAction
                from ..constants import MODE_BUILD
                await self._dispatch_action(ModeAction(mode=MODE_BUILD[0]))

        self._play_task = asyncio.create_task(_run_playback())

    def _stop_playback(self) -> None:
        """Stop current playback."""
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
        self._playing = False

    # ── Save/Load ──────────────────────────────────────────────────────

    def _save_to_slot(self, slot: int) -> None:
        """Save the current program to a slot."""
        if not self._blocks:
            return
        source_mode = "play"
        for block in self._blocks:
            if block.source_mode in ("play", "doodle", "explore"):
                source_mode = block.source_mode
                break
        save_program(self._blocks, slot, source_mode)
        self._active_slot = slot
        self._refresh_all()

    def _load_from_slot(self, slot: int) -> None:
        """Load a program from a slot."""
        result = load_program(slot)
        if result is not None:
            self._blocks, source_mode = result
            for block in self._blocks:
                if not block.source_mode:
                    block.source_mode = source_mode
            self._cursor = 0
            self._active_slot = slot
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
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 128


def _dim_color(hex_color: str, factor: float = 0.5) -> str:
    """Darken a hex color by blending toward black."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "#1a1a1a"
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)
    return f"#{r:02x}{g:02x}{b:02x}"
