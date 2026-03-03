"""
Code Mode (F4): Cross-Mode Visual Programming

Records what kids do in Play and Doodle modes, shows it as colored blocks
with timing gaps, and plays it back live. A 4-year-old never sees this.
A 7-year-old discovers F4 and sees their music as colored blocks.

Blocks have a fixed icon section (4 chars) and a variable-width trailing
gap (0-12 chars) representing the pause before the next action. Up/down
arrows adjust gap length. Space plays the program back in the real mode.

Keyboard input is received via handle_keyboard_action() from the main app,
which reads directly from evdev.
"""

import asyncio
from typing import Callable, Awaitable

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
    ActionRecorder,
    gap_width,
    blocks_to_demo_actions,
    save_program,
    load_program,
    slot_occupied,
    PAUSE_LEVELS,
    NUM_PAUSE_LEVELS,
)


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

# Save bar
SAVE_BAR_HEIGHT = 2
NUM_SLOTS = 9
SLOT_FILLED_COLOR = "#9b7bc4"
SLOT_EMPTY_COLOR = "#3a2a50"
SLOT_ACTIVE_COLOR = "#FFD700"

# Hold-to-save timing
SAVE_HOLD_MS = 600  # milliseconds to hold number key for save


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
                    segments.append(Segment(f" {slot}■ ", style))
                else:
                    segments.append(Segment(f" {slot}□ ", style))
                chars_used += slot_width

            remaining = width - chars_used
            if remaining > 0:
                segments.append(Segment(" " * remaining, bg_style))

        return Strip(segments)

    async def _on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()


# =============================================================================
# CODE CANVAS (BLOCK STRIP)
# =============================================================================

class CodeCanvas(Widget):
    """Shows the program as a horizontal strip of colored blocks.

    Each block has a fixed icon section (4 chars) and a variable trailing
    gap rendered as dots in a dimmer shade of the block color.

    Layout:
      Row 0-1: save bar (rendered separately above)
      Row 2: block top borders
      Row 3-4: block bodies (icon centered)
      Row 5: block bottom borders / cursor
      Row 6: gap adjustment hints
      Rest: empty / hints
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._blocks: list[ProgramBlock] = []
        self._cursor: int = 0
        self._scroll_offset: int = 0

    def set_blocks(self, blocks: list[ProgramBlock], cursor: int) -> None:
        self._blocks = blocks
        self._cursor = cursor
        self._update_scroll()
        self.refresh()

    def _update_scroll(self) -> None:
        """Ensure the cursor block is visible."""
        if not self._blocks:
            self._scroll_offset = 0
            return

        width = self.size.width or 112

        # Calculate cumulative positions
        pos = 0
        cursor_start = 0
        cursor_end = 0
        for i, block in enumerate(self._blocks):
            if i == self._cursor:
                cursor_start = pos
                cursor_end = pos + block.total_width
            pos += block.total_width

        # Adjust scroll so cursor is visible
        if cursor_start < self._scroll_offset:
            self._scroll_offset = cursor_start
        elif cursor_end > self._scroll_offset + width:
            self._scroll_offset = cursor_end - width

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
            return self._render_empty_line(y, width, bg, bg_style)

        # Block strip layout rows (relative to widget)
        border_top = 1
        body_row_1 = 2
        body_row_2 = 3
        border_bottom = 4
        hint_row = height - 1

        if y == hint_row:
            return self._render_hint_line(width, bg, bg_style)

        if y < border_top or y > border_bottom:
            return Strip([Segment(" " * width, bg_style)])

        # Render blocks horizontally
        segments = []
        x_pos = -self._scroll_offset  # current x position

        for i, block in enumerate(self._blocks):
            is_selected = (i == self._cursor)
            icon_w = ICON_WIDTH
            gap_w = gap_width(block.gap_level)
            total_w = icon_w + gap_w

            # Skip if entirely off-screen left
            if x_pos + total_w <= 0:
                x_pos += total_w
                continue

            # Stop if past right edge
            if x_pos >= width:
                break

            # Calculate visible portion
            vis_start = max(0, -x_pos)
            vis_end = min(total_w, width - x_pos)

            block_bg = block.bg_color
            text_color = "#FFFFFF" if _is_dark_color(block_bg) else "#1A1A1A"

            # Dim gap color (mix block color toward background)
            gap_bg = _dim_color(block_bg)

            if y == border_top:
                # Top border
                if is_selected:
                    border_style = Style(color=BLOCK_SELECTED_COLOR, bgcolor=bg)
                    line = "▾" * icon_w + " " * gap_w
                else:
                    line = " " * total_w
                    border_style = bg_style
                visible = line[vis_start:vis_end]
                segments.append(Segment(visible, border_style if is_selected else bg_style))

            elif y in (body_row_1, body_row_2):
                # Block body
                if y == body_row_1:
                    # Icon row
                    icon = block.icon
                    icon_text = _center_text(icon, icon_w)
                else:
                    # Empty second row (or could show type label)
                    icon_text = " " * icon_w

                body_style = Style(color=text_color, bgcolor=block_bg,
                                   bold=is_selected)
                gap_style = Style(color="#606060", bgcolor=gap_bg)

                full_line = icon_text + ("·" * gap_w if gap_w > 0 else "")

                # Render character by character for the visible portion
                for cx in range(vis_start, vis_end):
                    if cx < icon_w:
                        char = icon_text[cx] if cx < len(icon_text) else " "
                        segments.append(Segment(char, body_style))
                    else:
                        segments.append(Segment("·", gap_style))

            elif y == border_bottom:
                # Cursor indicator
                if is_selected:
                    cursor_style = Style(color=BLOCK_SELECTED_COLOR, bgcolor=bg)
                    line = _center_text("▴", icon_w) + " " * gap_w
                else:
                    line = " " * total_w
                    cursor_style = bg_style
                visible = line[vis_start:vis_end]
                segments.append(Segment(visible, cursor_style if is_selected else bg_style))

            x_pos += total_w

        # Fill remaining width
        chars_used = sum(len(s.text) for s in segments)
        remaining = width - chars_used
        if remaining > 0:
            segments.append(Segment(" " * remaining, bg_style))

        return Strip(segments)

    def _render_empty_line(self, y: int, width: int, bg: str,
                           bg_style: Style) -> Strip:
        """Render a line when no blocks are present."""
        mid = self.size.height // 2
        if y == mid - 1:
            hint = "Play some music or draw something"
            return self._centered_dim_text(hint, width, bg, bg_style)
        elif y == mid:
            hint = "then press F4 to see it as blocks!"
            return self._centered_dim_text(hint, width, bg, bg_style)
        elif y == mid + 2:
            hint = "← → navigate   ↑↓ adjust timing   Space play"
            return self._centered_dim_text(hint, width, bg, bg_style)
        return Strip([Segment(" " * width, bg_style)])

    def _render_hint_line(self, width: int, bg: str,
                          bg_style: Style) -> Strip:
        """Render the bottom hint line."""
        hint = "← → move   ↑↓ timing   Bksp delete   Space play   1-9 load/save"
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

    Records Play/Doodle actions as colored blocks with timing gaps.
    Space plays the program back in the real mode via DemoPlayer.
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

    def __init__(self, recorder: ActionRecorder | None = None,
                 dispatch_action: Callable | None = None, **kwargs):
        super().__init__(**kwargs)
        self._recorder = recorder
        self._dispatch_action = dispatch_action
        self._blocks: list[ProgramBlock] = []
        self._cursor: int = 0
        self._active_slot: int = 0
        self._playing: bool = False
        self._play_task: asyncio.Task | None = None

        # Hold-to-save state
        self._held_digit: str | None = None
        self._hold_timer = None

    def compose(self) -> ComposeResult:
        yield SaveBar(id="save-bar")
        yield Static("─" * 80, id="code-separator")
        yield CodeCanvas(id="code-canvas")

    def on_mount(self) -> None:
        self._load_from_recorder()
        self._refresh_all()

    def _load_from_recorder(self) -> None:
        """Load blocks from the action recorder."""
        if self._recorder and self._recorder.has_events():
            self._blocks = self._recorder.get_blocks()
            self._cursor = max(0, len(self._blocks) - 1)
        # If recorder is empty and we have no blocks, that's fine (empty state)

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
        """Route keyboard actions to the appropriate handler."""
        if self._playing:
            # During playback, only Space stops it
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

        if isinstance(action, ControlAction) and not action.is_down:
            # Key release: check for hold-to-save cancel
            self._cancel_hold()
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
            self._adjust_gap(1)
        elif action.direction == 'down':
            self._adjust_gap(-1)

    async def _handle_control(self, action: ControlAction) -> None:
        if action.action == 'backspace':
            self._delete_block()
        elif action.action == 'space':
            await self._start_playback()
        elif action.action == 'enter':
            # Reload from recorder (refresh current recording)
            self._load_from_recorder()
            self._refresh_all()

    async def _handle_character(self, action: CharacterAction) -> None:
        char = action.char
        if char.isdigit() and char != '0':
            slot = int(char)
            # Start hold timer for save; if released quickly, it's a load
            self._held_digit = char
            self._cancel_hold()
            self._hold_timer = self.set_timer(
                SAVE_HOLD_MS / 1000.0,
                lambda: self._save_to_slot(slot),
            )
            # Immediate load on tap (will be cancelled if hold completes)
            self._load_from_slot(slot)

    # ── Block operations ───────────────────────────────────────────────

    def _adjust_gap(self, direction: int) -> None:
        """Adjust the trailing gap of the block at cursor."""
        if not self._blocks:
            return
        self._blocks[self._cursor].cycle_gap(direction)
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
        """Play the program in the real mode via DemoPlayer."""
        if not self._blocks or not self._dispatch_action:
            return

        # Determine target mode from blocks
        target_mode = "play"
        for block in self._blocks:
            if block.source_mode:
                target_mode = block.source_mode
                break

        demo_actions = blocks_to_demo_actions(self._blocks, target_mode)
        if not demo_actions:
            return

        self._playing = True

        # Import DemoPlayer here to avoid circular imports
        from ..demo.player import DemoPlayer

        player = DemoPlayer(
            dispatch_action=self._dispatch_action,
            speed_multiplier=1.0,
        )

        async def _run_playback():
            try:
                await player.play(demo_actions)
            finally:
                self._playing = False
                # Switch back to Code mode
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
            if block.source_mode:
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
            # Restore source_mode on all blocks
            for block in self._blocks:
                if not block.source_mode:
                    block.source_mode = source_mode
            self._cursor = 0
            self._active_slot = slot
            self._refresh_all()

    def _cancel_hold(self) -> None:
        """Cancel the hold-to-save timer."""
        if self._hold_timer:
            self._hold_timer.stop()
            self._hold_timer = None
        self._held_digit = None

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
