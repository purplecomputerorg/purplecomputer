"""
Write Mode: Art Canvas

A directional typing canvas for creative expression:
- Arrow keys change typing direction (up/down/left/right)
- Cursor shows direction as an arrow
- Tab toggles between text mode and dot mode
- In dot mode, all keys paint colored dots (⬤)
- Dot colors follow keyboard row gradients (purple, red, yellow, blue)
- Painting dots over dots mixes colors
- Edges wrap around (Pac-Man style)
"""

from enum import Enum
import colorsys

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from textual.message import Message
from textual import events
from rich.segment import Segment
from rich.style import Style

from ..color_mixing import mix_colors_paint


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class Direction(Enum):
    """Typing direction on the canvas."""
    RIGHT = "right"
    LEFT = "left"
    UP = "up"
    DOWN = "down"


class CanvasMode(Enum):
    """Canvas input mode."""
    TEXT = "text"
    DOT = "dot"


# Direction arrows for cursor display
DIRECTION_ARROWS = {
    Direction.RIGHT: "▶",
    Direction.LEFT: "◀",
    Direction.UP: "▲",
    Direction.DOWN: "▼",
}

# The dot character (solid block, reliably 1 char wide)
DOT_CHAR = "█"

# Keyboard rows (left to right order for gradient)
NUMBER_ROW = list("1234567890")
QWERTY_ROW = list("qwertyuiop[]\\")
ASDF_ROW = list("asdfghjkl;'")
ZXCV_ROW = list("zxcvbnm,./")

# Default background color
DEFAULT_BG = "#2a1845"


# =============================================================================
# COLOR GRADIENT GENERATION
# =============================================================================

def hsl_to_hex(h: float, s: float, l: float) -> str:
    """
    Convert HSL to hex color string.

    Args:
        h: Hue (0-360)
        s: Saturation (0-1)
        l: Lightness (0-1)

    Returns:
        Hex color string like "#FF0000"
    """
    # colorsys uses h in 0-1 range
    r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def generate_row_gradient(hue: float, keys: list[str]) -> dict[str, str]:
    """
    Generate a light-to-dark gradient for a row of keys.

    Args:
        hue: Base hue (0-360)
        keys: List of keys in order

    Returns:
        Dict mapping each key to its hex color
    """
    result = {}
    count = len(keys)
    for i, key in enumerate(keys):
        # Lightness goes from 0.70 (light) to 0.30 (dark)
        lightness = 0.70 - (i / max(count - 1, 1)) * 0.40
        result[key] = hsl_to_hex(hue, 0.80, lightness)
    return result


# Build the complete key-to-color mapping
DOT_COLORS: dict[str, str] = {}
DOT_COLORS.update(generate_row_gradient(300, NUMBER_ROW))   # Purple/pink
DOT_COLORS.update(generate_row_gradient(0, QWERTY_ROW))     # Red
DOT_COLORS.update(generate_row_gradient(50, ASDF_ROW))      # Yellow
DOT_COLORS.update(generate_row_gradient(220, ZXCV_ROW))     # Blue


def get_dot_color(char: str) -> str:
    """Get the dot color for a character, or white if not in a row."""
    return DOT_COLORS.get(char.lower(), "#FFFFFF")


# =============================================================================
# MESSAGES
# =============================================================================

class CanvasModeChanged(Message):
    """Message sent when canvas mode or direction changes."""

    def __init__(self, mode: "CanvasMode", direction: "Direction") -> None:
        self.mode = mode
        self.direction = direction
        super().__init__()


# =============================================================================
# CANVAS WIDGET
# =============================================================================

class ArtCanvas(Widget, can_focus=True):
    """
    Custom canvas widget with directional typing and dot painting.

    Uses render_line() for full control over rendering.
    """

    DEFAULT_CSS = """
    ArtCanvas {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Grid: dict[(x, y)] = (char, color)
        self._grid: dict[tuple[int, int], tuple[str, str]] = {}
        self._cursor_x = 0
        self._cursor_y = 0
        self._direction = Direction.RIGHT
        self._mode = CanvasMode.TEXT
        self._default_text_color = "#FFFFFF"

    @property
    def canvas_width(self) -> int:
        """Width of the canvas in characters."""
        return max(1, self.size.width)

    @property
    def canvas_height(self) -> int:
        """Height of the canvas in characters."""
        return max(1, self.size.height)

    @property
    def direction(self) -> Direction:
        """Current typing direction."""
        return self._direction

    @property
    def mode(self) -> CanvasMode:
        """Current canvas mode."""
        return self._mode

    def render_line(self, y: int) -> Strip:
        """Render a single line of the canvas."""
        width = self.size.width

        if width <= 0:
            return Strip([])

        segments = []
        bg_style = Style(bgcolor=DEFAULT_BG)

        for x in range(width):
            pos = (x, y)
            cell = self._grid.get(pos)

            # Is this the cursor position?
            is_cursor = (x == self._cursor_x and y == self._cursor_y)

            if is_cursor:
                # Draw cursor as direction arrow
                arrow = DIRECTION_ARROWS[self._direction]
                # Cursor style: bright on dark
                cursor_style = Style(color="#FFFFFF", bgcolor="#6633AA", bold=True)
                segments.append(Segment(arrow, cursor_style))
            elif cell:
                char, color = cell
                # Draw the character with its color
                char_style = Style(color=color, bgcolor=DEFAULT_BG)
                segments.append(Segment(char, char_style))
            else:
                # Empty cell
                segments.append(Segment(" ", bg_style))

        return Strip(segments)

    def _move_cursor(self) -> None:
        """Move cursor in current direction with Pac-Man wrap."""
        if self._direction == Direction.RIGHT:
            self._cursor_x = (self._cursor_x + 1) % self.canvas_width
        elif self._direction == Direction.LEFT:
            self._cursor_x = (self._cursor_x - 1) % self.canvas_width
        elif self._direction == Direction.DOWN:
            self._cursor_y = (self._cursor_y + 1) % self.canvas_height
        elif self._direction == Direction.UP:
            self._cursor_y = (self._cursor_y - 1) % self.canvas_height

    def _move_cursor_back(self) -> None:
        """Move cursor opposite to current direction (for backspace)."""
        if self._direction == Direction.RIGHT:
            self._cursor_x = (self._cursor_x - 1) % self.canvas_width
        elif self._direction == Direction.LEFT:
            self._cursor_x = (self._cursor_x + 1) % self.canvas_width
        elif self._direction == Direction.DOWN:
            self._cursor_y = (self._cursor_y - 1) % self.canvas_height
        elif self._direction == Direction.UP:
            self._cursor_y = (self._cursor_y + 1) % self.canvas_height

    def _carriage_return(self) -> None:
        """Move to start of next line (relative to typing direction)."""
        if self._direction == Direction.RIGHT:
            self._cursor_x = 0
            self._cursor_y = (self._cursor_y + 1) % self.canvas_height
        elif self._direction == Direction.LEFT:
            self._cursor_x = self.canvas_width - 1
            self._cursor_y = (self._cursor_y + 1) % self.canvas_height
        elif self._direction == Direction.DOWN:
            self._cursor_y = 0
            self._cursor_x = (self._cursor_x + 1) % self.canvas_width
        elif self._direction == Direction.UP:
            self._cursor_y = self.canvas_height - 1
            self._cursor_x = (self._cursor_x + 1) % self.canvas_width

    def type_char(self, char: str, color: str) -> None:
        """Type a character or dot at cursor, then move cursor."""
        pos = (self._cursor_x, self._cursor_y)

        if self._mode == CanvasMode.DOT:
            existing = self._grid.get(pos)
            if existing and existing[0] == DOT_CHAR:
                # Mix colors when painting over existing dot
                new_color = mix_colors_paint([existing[1], color])
                self._grid[pos] = (DOT_CHAR, new_color)
            else:
                self._grid[pos] = (DOT_CHAR, color)
        else:
            # Text mode: just place character
            self._grid[pos] = (char, color)

        self._move_cursor()
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        """Handle keyboard input."""
        key = event.key
        char = event.character

        # Arrow keys change direction
        if key == "up":
            self._direction = Direction.UP
            self.post_message(CanvasModeChanged(self._mode, self._direction))
            self.refresh()
            event.stop()
            event.prevent_default()
            return

        if key == "down":
            self._direction = Direction.DOWN
            self.post_message(CanvasModeChanged(self._mode, self._direction))
            self.refresh()
            event.stop()
            event.prevent_default()
            return

        if key == "left":
            self._direction = Direction.LEFT
            self.post_message(CanvasModeChanged(self._mode, self._direction))
            self.refresh()
            event.stop()
            event.prevent_default()
            return

        if key == "right":
            self._direction = Direction.RIGHT
            self.post_message(CanvasModeChanged(self._mode, self._direction))
            self.refresh()
            event.stop()
            event.prevent_default()
            return

        # Tab toggles mode
        if key == "tab":
            if self._mode == CanvasMode.TEXT:
                self._mode = CanvasMode.DOT
            else:
                self._mode = CanvasMode.TEXT
            # Post message to update header
            self.post_message(CanvasModeChanged(self._mode, self._direction))
            self.refresh()
            event.stop()
            event.prevent_default()
            return

        # Enter: carriage return
        if key == "enter":
            self._carriage_return()
            self.refresh()
            event.stop()
            event.prevent_default()
            return

        # Backspace: move back, clear cell
        if key == "backspace":
            self._move_cursor_back()
            pos = (self._cursor_x, self._cursor_y)
            if pos in self._grid:
                del self._grid[pos]
            self.refresh()
            event.stop()
            event.prevent_default()
            return

        # Let escape bubble up for parent menu
        if key == "escape":
            return

        # Block other non-printable keys
        if not event.is_printable:
            event.stop()
            event.prevent_default()
            return

        # Printable character
        if char:
            if self._mode == CanvasMode.DOT:
                color = get_dot_color(char)
                self.type_char(DOT_CHAR, color)
            else:
                self.type_char(char, self._default_text_color)
            event.stop()
            event.prevent_default()


# =============================================================================
# HEADER WIDGET
# =============================================================================

class CanvasHeader(Static):
    """Shows current mode and direction."""

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
        self._mode = CanvasMode.TEXT
        self._direction = Direction.RIGHT

    def update_state(self, mode: CanvasMode, direction: Direction) -> None:
        """Update displayed mode and direction."""
        self._mode = mode
        self._direction = direction
        self.refresh()

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        mode_text = "Dot" if self._mode == CanvasMode.DOT else "Text"
        arrow = DIRECTION_ARROWS[self._direction]

        # Color the mode indicator based on mode
        if self._mode == CanvasMode.DOT:
            mode_styled = f"[bold #da77f2]{caps(mode_text)}[/]"
        else:
            mode_styled = f"[bold]{caps(mode_text)}[/]"

        hint = caps("Tab: switch mode, Arrows: direction")
        return f"{mode_styled} {arrow}  [dim]({hint})[/]"


# =============================================================================
# WRITE MODE CONTAINER
# =============================================================================

class WriteMode(Container):
    """
    Art Canvas mode.

    Ephemeral canvas for creative expression with directional typing,
    dot painting, and color mixing.
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
        # Initialize header with canvas state
        header = self.query_one("#canvas-header", CanvasHeader)
        header.update_state(canvas.mode, canvas.direction)

    def on_canvas_mode_changed(self, event: CanvasModeChanged) -> None:
        """Update header when canvas mode/direction changes."""
        header = self.query_one("#canvas-header", CanvasHeader)
        header.update_state(event.mode, event.direction)
