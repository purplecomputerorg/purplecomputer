"""
Write Mode: Text Canvas with Playful Painting

A text-focused canvas with paint-by-key features:
- Normal typing writes readable text (left-to-right, wrapping at edges)
- Each key tints the background based on keyboard row
- Arrow keys move the cursor (no drawing)
- Hold Space + arrows to paint colored trails
- Backspace erases glyph and fades background
- Hold Backspace to clear the entire canvas

Keyboard input is received via handle_keyboard_action() from the main app,
which reads directly from evdev. This gives us true key release detection.
"""

import colorsys
import time

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from textual.message import Message
from textual import events
from rich.segment import Segment
from rich.style import Style

from ..color_mixing import mix_colors_paint, hex_to_rgb, rgb_to_hex
from ..keyboard import (
    CharacterAction, NavigationAction, ControlAction, ShiftAction,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# Grayscale values (selected by number keys: 1=white, 0=black)
GRAYSCALE = {
    "1": "#FFFFFF",  # White
    "2": "#E0E0E0",
    "3": "#C0C0C0",
    "4": "#A0A0A0",
    "5": "#808080",  # Middle gray
    "6": "#606060",
    "7": "#404040",
    "8": "#202020",
    "9": "#101010",
    "0": "#000000",  # Black
}

# Brush character for painting
BRUSH_CHAR = "█"

# Box-drawing characters for cursor border
BOX_CHARS = {
    (-1, -1): "┌",  # top-left
    (0, -1): "─",   # top-center
    (1, -1): "┐",   # top-right
    (-1, 0): "│",   # middle-left
    (1, 0): "│",    # middle-right
    (-1, 1): "└",   # bottom-left
    (0, 1): "─",    # bottom-center
    (1, 1): "┘",    # bottom-right
}

# Keyboard rows for colors (letter rows only)
QWERTY_ROW = list("qwertyuiop")    # Red family
ASDF_ROW = list("asdfghjkl")       # Yellow family
ZXCV_ROW = list("zxcvbnm")         # Blue family

# Color legend: representative colors for each keyboard row (medium brightness)
# Ordered top-to-bottom to mirror keyboard layout (QWERTY at top, ZXCV at bottom)
ROW_LEGEND_COLORS = [
    "#BF4040",  # Red (QWERTY row)
    "#BFA040",  # Yellow/gold (ASDF row)
    "#4060BF",  # Blue (ZXCV row)
]

# Legend positioning
LEGEND_WIDTH = 2  # Characters wide (block + space)
LEGEND_MARGIN_RIGHT = 1  # From right edge
LEGEND_MARGIN_BOTTOM = 0  # From bottom edge

# Default backgrounds (dark and light themes)
DEFAULT_BG_DARK = "#2a1845"
DEFAULT_BG_LIGHT = "#e8daf0"

# Readable text foreground colors (dark and light themes)
TEXT_FG_DARK = "#FFFFFF"
TEXT_FG_LIGHT = "#1e1033"

# Cursor colors
CURSOR_BG_NORMAL = "#6633AA"
CURSOR_BG_PAINT = "#FF6600"

# Background tint strength (0.0 = no tint, 1.0 = full color)
# Keep low so text stays readable
BG_TINT_STRENGTH = 0.15

# Paint color strength when holding space
PAINT_STRENGTH = 0.7

# Fade factor for backspace (how much background fades toward default)
FADE_FACTOR = 0.5

# Hold duration for backspace clear (in seconds)
BACKSPACE_HOLD_CLEAR_TIME = 1.0


# =============================================================================
# COLOR UTILITIES
# =============================================================================

def hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convert HSL to hex color string."""
    r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Linear interpolation between two colors."""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return rgb_to_hex(r, g, b)


def generate_row_gradient(hue: float, keys: list[str]) -> dict[str, str]:
    """Generate a light-to-dark gradient for a row of keys."""
    result = {}
    count = len(keys)
    for i, key in enumerate(keys):
        lightness = 0.65 - (i / max(count - 1, 1)) * 0.35
        result[key] = hsl_to_hex(hue, 0.75, lightness)
    return result


# Build key-to-color mapping (primary colors by row)
KEY_COLORS: dict[str, str] = {}
KEY_COLORS.update(generate_row_gradient(0, QWERTY_ROW))     # Red family (top letter row)
KEY_COLORS.update(generate_row_gradient(50, ASDF_ROW))      # Yellow family (home row)
KEY_COLORS.update(generate_row_gradient(220, ZXCV_ROW))     # Blue family (bottom row)


def get_key_color(char: str) -> str:
    """Get the color for a key, or white if not mapped."""
    return KEY_COLORS.get(char.lower(), "#AAAAAA")


def get_row_tint_color(char: str) -> str | None:
    """Get a tint color based on which keyboard row a character is on."""
    lower = char.lower()
    if lower in QWERTY_ROW:
        return hsl_to_hex(0, 0.5, 0.35)      # Red family
    elif lower in ASDF_ROW:
        return hsl_to_hex(50, 0.5, 0.40)     # Yellow family
    elif lower in ZXCV_ROW:
        return hsl_to_hex(220, 0.5, 0.35)    # Blue family
    else:
        return None  # No tint for unmapped keys


def is_text_tint_bg(color: str) -> bool:
    """Check if a color is a text tint (close to default bg) vs a paint color.

    Text tints are subtle blends with the default background.
    Paint colors are more saturated/vibrant.
    """
    r, g, b = hex_to_rgb(color)

    # Check distance from dark default bg
    dr, dg, db = hex_to_rgb(DEFAULT_BG_DARK)
    dark_dist = abs(r - dr) + abs(g - dg) + abs(b - db)

    # Check distance from light default bg
    lr, lg, lb = hex_to_rgb(DEFAULT_BG_LIGHT)
    light_dist = abs(r - lr) + abs(g - lg) + abs(b - lb)

    # If close to either default, it's a text tint
    # Threshold of ~100 covers the 15% tint strength
    return dark_dist < 100 or light_dist < 100


# =============================================================================
# MESSAGES
# =============================================================================

class PaintModeChanged(Message):
    """Message sent when paint mode changes."""

    def __init__(self, is_painting: bool, last_color: str) -> None:
        self.is_painting = is_painting
        self.last_color = last_color
        super().__init__()


# =============================================================================
# CANVAS WIDGET
# =============================================================================

class ArtCanvas(Widget, can_focus=True):
    """
    Custom canvas widget with text typing and Space-held painting.

    Uses render_line() for full control over rendering.
    Cell structure: (char, fg_color, bg_color)
    """

    DEFAULT_CSS = """
    ArtCanvas {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Grid: dict[(x, y)] = (char, fg_color, bg_color)
        self._grid: dict[tuple[int, int], tuple[str, str, str]] = {}
        self._cursor_x = 0
        self._cursor_y = 0

        # Paint mode toggle
        self._paint_mode = False
        self._last_key_color = "#FFFFFF"  # Color from last key in paint mode
        self._last_key_char = ""  # Last key pressed

        # Double-tap detection for Space to toggle paint mode
        self._last_space_time: float = 0.0
        self._double_tap_threshold = 0.4  # seconds

        # Space-hold for drawing lines in paint mode
        # With evdev, we get true key release events
        self._space_down = False

        # Cursor blink state
        self._cursor_visible = True
        self._blink_timer = None

        # Backspace hold state
        self._backspace_start_time: float | None = None
        self._clear_animation_active = False

    def _get_default_bg(self) -> str:
        """Get default background based on current theme."""
        try:
            is_dark = "dark" in self.app.theme
            return DEFAULT_BG_DARK if is_dark else DEFAULT_BG_LIGHT
        except Exception:
            return DEFAULT_BG_DARK

    def _is_dark_theme(self) -> bool:
        """Check if using dark theme."""
        try:
            return "dark" in self.app.theme
        except Exception:
            return True

    def _get_text_fg(self) -> str:
        """Get text foreground color based on current theme."""
        return TEXT_FG_DARK if self._is_dark_theme() else TEXT_FG_LIGHT

    def _toggle_paint_mode(self) -> None:
        """Toggle between paint mode and text mode."""
        self._paint_mode = not self._paint_mode
        self._space_down = False  # Reset brush state on mode change

        # Start or stop cursor blinking
        if self._paint_mode:
            self._start_blink()
        else:
            self._stop_blink()

        self.post_message(PaintModeChanged(self._paint_mode, self._last_key_color))
        self.refresh()

    def _toggle_blink(self) -> None:
        """Toggle cursor visibility for blink effect."""
        self._cursor_visible = not self._cursor_visible
        self.refresh()

    def _start_blink(self) -> None:
        """Start cursor blinking."""
        self._cursor_visible = True
        if self._blink_timer is not None:
            self._blink_timer.stop()
        self._blink_timer = self.set_interval(0.4, self._toggle_blink)

    def _stop_blink(self) -> None:
        """Stop cursor blinking."""
        if self._blink_timer is not None:
            self._blink_timer.stop()
            self._blink_timer = None
        self._cursor_visible = True

    def _release_space_down(self) -> None:
        """Release brush-down state (called on space key release)."""
        self._space_down = False
        self.refresh()

    def _start_space_down(self) -> None:
        """Start brush-down state for line drawing."""
        self._space_down = True

    @property
    def canvas_width(self) -> int:
        """Width of the canvas in characters."""
        return max(1, self.size.width)

    @property
    def canvas_height(self) -> int:
        """Height of the canvas in characters."""
        return max(1, self.size.height)

    @property
    def is_painting(self) -> bool:
        """Whether paint mode is active."""
        return self._paint_mode

    def _is_in_brush_ring(self, x: int, y: int) -> bool:
        """Check if position is in the 3x3 ring around cursor (not center)."""
        dx = x - self._cursor_x
        dy = y - self._cursor_y
        # In the 3x3 area but not the center
        return abs(dx) <= 1 and abs(dy) <= 1 and not (dx == 0 and dy == 0)

    def _get_legend_row(self, x: int, y: int) -> int | None:
        """Check if position is part of the color legend.

        Returns the row index (0=red, 1=yellow, 2=blue) if this position
        should show a legend block, or None if not part of the legend.
        """
        height = self.canvas_height
        width = self.canvas_width

        # Legend is 3 rows tall, positioned at bottom-right
        legend_start_y = height - LEGEND_MARGIN_BOTTOM - 3
        legend_x = width - LEGEND_MARGIN_RIGHT - LEGEND_WIDTH

        # Check if in legend area
        if x >= legend_x and x < legend_x + LEGEND_WIDTH:
            if y >= legend_start_y and y < legend_start_y + 3:
                return y - legend_start_y
        return None

    def _caps_char(self, char: str) -> str:
        """Transform character based on caps mode."""
        if hasattr(self.app, 'caps_mode') and self.app.caps_mode and char.isalpha():
            return char.upper()
        return char

    def render_line(self, y: int) -> Strip:
        """Render a single line of the canvas."""
        width = self.size.width

        if width <= 0:
            return Strip([])

        segments = []
        default_bg = self._get_default_bg()

        for x in range(width):
            pos = (x, y)
            cell = self._grid.get(pos)

            is_cursor_center = (x == self._cursor_x and y == self._cursor_y)
            is_brush_ring = self._paint_mode and self._is_in_brush_ring(x, y)

            # Check if this is a legend position (only show in paint mode)
            legend_row = self._get_legend_row(x, y) if self._paint_mode else None
            if legend_row is not None:
                # Calculate position within the 2-char wide legend
                legend_x_start = width - LEGEND_MARGIN_RIGHT - LEGEND_WIDTH
                legend_offset = x - legend_x_start
                legend_color = ROW_LEGEND_COLORS[legend_row]

                if legend_offset == 0:
                    # First char: colored block
                    legend_style = Style(color=legend_color, bgcolor=legend_color)
                    segments.append(Segment("█", legend_style))
                else:
                    # Second char: space (padding)
                    segments.append(Segment(" ", Style(bgcolor=default_bg)))
                continue

            if is_cursor_center:
                if self._paint_mode:
                    # Paint mode: center always shows underlying (the "hole")
                    if cell:
                        char, fg_color, bg_color = cell
                        # Apply theme to text cells
                        if char != BRUSH_CHAR:
                            fg_color = self._get_text_fg()
                            if is_text_tint_bg(bg_color):
                                bg_color = default_bg
                        segments.append(Segment(self._caps_char(char), Style(color=fg_color, bgcolor=bg_color)))
                    else:
                        segments.append(Segment(" ", Style(bgcolor=default_bg)))
                else:
                    # Text mode cursor
                    cursor_style = Style(color="#FFFFFF", bgcolor=CURSOR_BG_NORMAL, bold=True)
                    segments.append(Segment("▌", cursor_style))
            elif is_brush_ring:
                # 3x3 ring around cursor: blinks on/off with box-drawing chars
                if self._cursor_visible:
                    dx = x - self._cursor_x
                    dy = y - self._cursor_y
                    box_char = BOX_CHARS.get((dx, dy), "·")

                    if cell:
                        char, fg_color, bg_color = cell
                        # Apply theme to text cell backgrounds
                        if char != BRUSH_CHAR and is_text_tint_bg(bg_color):
                            bg_color = default_bg
                        # Check if cell has real text (not empty/space/block)
                        if char not in (" ", BRUSH_CHAR, ""):
                            # Text cell: keep the character, tint it with cursor color
                            ring_style = Style(color=self._last_key_color, bgcolor=bg_color)
                            segments.append(Segment(self._caps_char(char), ring_style))
                        else:
                            # Painted/empty cell: show box char with underlying bg
                            ring_style = Style(color=self._last_key_color, bgcolor=bg_color)
                            segments.append(Segment(box_char, ring_style))
                    else:
                        # Empty cell: show box char on default bg
                        ring_style = Style(color=self._last_key_color, bgcolor=default_bg)
                        segments.append(Segment(box_char, ring_style))
                else:
                    # Blink off: show underlying cell
                    if cell:
                        char, fg_color, bg_color = cell
                        # Apply theme to text cells
                        if char != BRUSH_CHAR:
                            fg_color = self._get_text_fg()
                            if is_text_tint_bg(bg_color):
                                bg_color = default_bg
                        segments.append(Segment(self._caps_char(char), Style(color=fg_color, bgcolor=bg_color)))
                    else:
                        segments.append(Segment(" ", Style(bgcolor=default_bg)))
            elif cell:
                char, fg_color, bg_color = cell
                # Paint cells (BRUSH_CHAR): keep stored colors
                # Text cells: adapt to theme
                if char == BRUSH_CHAR:
                    char_style = Style(color=fg_color, bgcolor=bg_color)
                else:
                    # Text cell: use theme-appropriate fg
                    # If bg is a text tint, use theme's default_bg
                    # If bg is a paint color (text typed over paint), keep it
                    text_fg = self._get_text_fg()
                    if is_text_tint_bg(bg_color):
                        char_style = Style(color=text_fg, bgcolor=default_bg)
                    else:
                        char_style = Style(color=text_fg, bgcolor=bg_color)
                segments.append(Segment(self._caps_char(char), char_style))
            else:
                # Empty cell
                segments.append(Segment(" ", Style(bgcolor=default_bg)))

        return Strip(segments)

    def _move_cursor_right(self) -> bool:
        """Move cursor right, return False if at edge."""
        if self._cursor_x < self.canvas_width - 1:
            self._cursor_x += 1
            return True
        return False

    def _move_cursor_left(self) -> bool:
        """Move cursor left, return False if at edge."""
        if self._cursor_x > 0:
            self._cursor_x -= 1
            return True
        return False

    def _move_cursor_up(self) -> bool:
        """Move cursor up, return False if at edge."""
        if self._cursor_y > 0:
            self._cursor_y -= 1
            return True
        return False

    def _move_cursor_down(self) -> bool:
        """Move cursor down, return False if at edge."""
        if self._cursor_y < self.canvas_height - 1:
            self._cursor_y += 1
            return True
        return False

    def _move_in_direction(self, direction: str) -> bool:
        """Move cursor in the given direction. Returns True if moved."""
        if direction == 'up':
            return self._move_cursor_up()
        elif direction == 'down':
            return self._move_cursor_down()
        elif direction == 'left':
            return self._move_cursor_left()
        elif direction == 'right':
            return self._move_cursor_right()
        return False

    def _carriage_return(self) -> None:
        """Move to start of next line."""
        self._cursor_x = 0
        if self._cursor_y < self.canvas_height - 1:
            self._cursor_y += 1

    def _get_cell_bg(self, pos: tuple[int, int]) -> str:
        """Get background color of a cell, or default if empty."""
        cell = self._grid.get(pos)
        if cell:
            return cell[2]
        return self._get_default_bg()

    def _set_cell(self, pos: tuple[int, int], char: str, fg: str, bg: str) -> None:
        """Set a cell's content."""
        self._grid[pos] = (char, fg, bg)

    def _paint_at_cursor(self) -> None:
        """Paint at current cursor position using current color."""
        pos = (self._cursor_x, self._cursor_y)
        existing_bg = self._get_cell_bg(pos)
        default_bg = self._get_default_bg()

        # Blend paint color with existing background using spectral mixing
        if existing_bg != default_bg:
            # Mix existing color with new paint color
            new_bg = mix_colors_paint([existing_bg, self._last_key_color])
        else:
            # Blend paint color with default background
            new_bg = lerp_color(default_bg, self._last_key_color, PAINT_STRENGTH)

        # Paint uses solid block character
        self._set_cell(pos, BRUSH_CHAR, new_bg, new_bg)

    def type_char(self, char: str) -> None:
        """Type a character at cursor with row-based background tint."""
        pos = (self._cursor_x, self._cursor_y)

        # Update last key color (for painting)
        self._last_key_char = char
        self._last_key_color = get_key_color(char)

        # Get tint color based on keyboard row
        tint = get_row_tint_color(char)
        default_bg = self._get_default_bg()

        # Get existing background or start from default
        existing_bg = self._get_cell_bg(pos)

        # Blend tint with existing background (subtle tint)
        if tint is None:
            new_bg = existing_bg
        elif existing_bg == default_bg:
            new_bg = lerp_color(default_bg, tint, BG_TINT_STRENGTH)
        else:
            # Blend new tint into existing
            new_bg = lerp_color(existing_bg, tint, BG_TINT_STRENGTH * 0.5)

        # Text always uses readable foreground
        self._set_cell(pos, char, self._get_text_fg(), new_bg)

        # Move cursor right (with wrapping to next line)
        if not self._move_cursor_right():
            # At right edge, wrap to next line
            self._carriage_return()

        self.refresh()

    def _backspace(self) -> None:
        """Delete character at cursor and fade background."""
        # Move cursor back first
        if self._cursor_x > 0:
            self._cursor_x -= 1
        elif self._cursor_y > 0:
            # Wrap to end of previous line
            self._cursor_y -= 1
            self._cursor_x = self.canvas_width - 1

        pos = (self._cursor_x, self._cursor_y)
        cell = self._grid.get(pos)
        default_bg = self._get_default_bg()

        if cell:
            _, _, bg = cell
            # Fade background toward default
            faded_bg = lerp_color(bg, default_bg, FADE_FACTOR)
            # Clear the glyph but keep faded background
            if faded_bg != default_bg:
                self._set_cell(pos, " ", self._get_text_fg(), faded_bg)
            else:
                # Fully faded, remove cell entirely
                del self._grid[pos]
        # If cell was empty, nothing to do

        self.refresh()

    def _clear_canvas(self) -> None:
        """Clear the entire canvas with animation."""
        self._clear_animation_active = True

        # Simple clear (animation could be added via set_interval)
        self._grid.clear()
        self._cursor_x = 0
        self._cursor_y = 0

        self._clear_animation_active = False
        self.refresh()

    def _on_edge_hit(self) -> None:
        """Provide feedback when cursor hits an edge."""
        # Could add visual flash or sound here
        # For now, the cursor just stops
        pass

    async def handle_keyboard_action(self, action) -> None:
        """
        Handle keyboard actions from the main app's KeyboardStateMachine.

        This receives high-level actions (CharacterAction, NavigationAction, etc.)
        instead of raw key events. Key up/down detection works reliably via evdev.
        """
        # Handle control actions (space, tab, backspace, enter, escape)
        if isinstance(action, ControlAction):
            if action.action == 'space':
                if action.is_down:
                    # Space press
                    if self._paint_mode:
                        # In paint mode: stamp and enable "pen down" for line drawing
                        self._paint_at_cursor()
                        self._start_space_down()
                        # If an arrow key is held, advance in that direction after stamping
                        if action.arrow_held:
                            self._move_in_direction(action.arrow_held)
                        self.refresh()
                    else:
                        # In text mode: check for double-tap to toggle, else type space
                        current_time = time.time()
                        if (current_time - self._last_space_time) < self._double_tap_threshold:
                            # Double-tap detected: toggle paint mode
                            self._toggle_paint_mode()
                            self._last_space_time = 0.0
                        else:
                            # Type a space
                            pos = (self._cursor_x, self._cursor_y)
                            existing_bg = self._get_cell_bg(pos)
                            self._set_cell(pos, " ", self._get_text_fg(), existing_bg)
                            if not self._move_cursor_right():
                                self._carriage_return()
                            self._last_space_time = current_time
                            self.refresh()
                else:
                    # Space release: stop line drawing
                    if self._paint_mode:
                        self._release_space_down()
                return

            if action.action == 'tab' and action.is_down:
                self._toggle_paint_mode()
                return

            if action.action == 'enter' and action.is_down:
                # Move down one line, keeping column position (for vertical drawing)
                self._move_cursor_down()
                self.refresh()
                return

            if action.action == 'backspace':
                if action.is_down:
                    current_time = time.time()

                    if self._backspace_start_time is None:
                        self._backspace_start_time = current_time

                    # Check for hold-to-clear
                    hold_duration = current_time - self._backspace_start_time
                    if hold_duration >= BACKSPACE_HOLD_CLEAR_TIME:
                        self._clear_canvas()
                        self._backspace_start_time = None
                    else:
                        self._backspace()
                else:
                    # Backspace release: reset timer
                    self._backspace_start_time = None
                return

            # Escape is handled by the main app (parent mode)
            return

        # Handle navigation actions (arrow keys)
        if isinstance(action, NavigationAction):
            # Collect all directions to move (primary + any other held arrows)
            directions_to_move = [action.direction]
            if action.other_arrows_held:
                directions_to_move.extend(action.other_arrows_held)

            any_moved = False
            for direction in directions_to_move:
                moved = self._move_in_direction(direction)
                if moved:
                    any_moved = True

            if not any_moved:
                self._on_edge_hit()

            # In paint mode with pen down: draw line
            # action.space_held comes from KeyboardStateMachine
            if self._paint_mode and (self._space_down or action.space_held):
                self._paint_at_cursor()

            self.refresh()
            return

        # Handle character actions (printable characters)
        if isinstance(action, CharacterAction):
            # Reset backspace timer on character input
            self._backspace_start_time = None

            char = action.char
            if self._paint_mode:
                # In paint mode:
                # - Lowercase letters: select color, stamp, advance right
                # - Uppercase (shift) letters: just select color (no stamp, no advance)
                # - Number keys: select grayscale, stamp, advance right
                if char in GRAYSCALE:
                    self._last_key_char = char
                    self._last_key_color = GRAYSCALE[char]
                    self._paint_at_cursor()
                    self._move_cursor_right()  # Advance after stamp
                    self.post_message(PaintModeChanged(True, self._last_key_color))
                    self.refresh()
                elif char.isalpha():
                    lower = char.lower()
                    color = get_key_color(lower)
                    if color != "#AAAAAA":  # Only if it's a mapped color
                        self._last_key_char = lower
                        self._last_key_color = color
                        self.post_message(PaintModeChanged(True, self._last_key_color))
                        if not action.shift_held:
                            # No shift: stamp and advance (works with caps lock and double-tap)
                            self._paint_at_cursor()
                            self._move_cursor_right()
                        # Shift held: just select brush, no stamp
                        self.refresh()
            else:
                # In text mode: type the character
                self.type_char(char)
            return

    def on_blur(self, event: events.Blur) -> None:
        """Reset state when losing focus."""
        pass  # Paint mode persists across focus changes


# =============================================================================
# HEADER WIDGET
# =============================================================================

class CanvasHeader(Static):
    """Shows current mode and hints."""

    DEFAULT_CSS = """
    CanvasHeader {
        height: 1;
        dock: top;
        text-align: center;
        color: $text-muted;
        background: $surface;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._is_painting = False
        self._last_color = "#FFFFFF"

    def update_state(self, is_painting: bool, last_color: str) -> None:
        """Update displayed state."""
        self._is_painting = is_painting
        self._last_color = last_color
        self.refresh()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)

        if self._is_painting:
            # Show paint mode with color indicator
            mode_styled = f"[bold {self._last_color}]{caps('Paint')}[/]"
            hint = caps("type=stamp, SHIFT=select, Space+arrows=line")
        else:
            mode_styled = f"[bold]{caps('Write')}[/]"
            hint = caps("Tab = paint")

        return f"{mode_styled}  [dim]({hint})[/]"


# =============================================================================
# WRITE MODE CONTAINER
# =============================================================================

class WriteMode(Container):
    """
    Write Mode: Text canvas with playful painting.

    Normal typing writes readable text with subtle background tinting.
    Holding Space while pressing arrows paints colorful trails.
    """

    DEFAULT_CSS = """
    WriteMode {
        width: 100%;
        height: 100%;
        padding: 0;
        background: $surface;
    }

    #canvas-header {
        height: 1;
        dock: top;
        margin-bottom: 1;
    }

    #art-canvas {
        width: 100%;
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield CanvasHeader(id="canvas-header")
        yield ArtCanvas(id="art-canvas")

    def on_mount(self) -> None:
        """Focus the canvas when mode loads."""
        canvas = self.query_one("#art-canvas", ArtCanvas)
        canvas.focus()
        # Initialize header
        header = self.query_one("#canvas-header", CanvasHeader)
        header.update_state(False, "#FFFFFF")

    def on_paint_mode_changed(self, event: PaintModeChanged) -> None:
        """Update header when paint mode changes."""
        header = self.query_one("#canvas-header", CanvasHeader)
        header.update_state(event.is_painting, event.last_color)

    async def handle_keyboard_action(self, action) -> None:
        """Delegate keyboard actions to the canvas."""
        canvas = self.query_one("#art-canvas", ArtCanvas)
        await canvas.handle_keyboard_action(action)
