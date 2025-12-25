"""
Sketch Mode - Freeform keyboard scribbling

A canvas where keystrokes place glyphs, not text.
Each key produces a specific glyph - rows have themes.
No goals, no prompts, no instructions - pure freeplay.
"""

from textual.widget import Widget
from textual.containers import Container
from textual.app import ComposeResult
from textual.strip import Strip
from textual import events
from rich.segment import Segment
from rich.style import Style
import random
import time


# Each key maps to a specific glyph
# Rows have themes: dots → lines → shapes → decorative
GLYPH_MAP = {
    # Number row: small dots and particles
    '1': '·', '2': '•', '3': '●', '4': '○', '5': '◦',
    '6': '◘', '7': '◙', '8': '◎', '9': '◉', '0': '⊙',
    # QWERTY row: lines and connectors
    'q': '─', 'w': '│', 'e': '╱', 'r': '╲', 't': '┼',
    'y': '╳', 'u': '═', 'i': '║', 'o': '┃', 'p': '━',
    # ASDF row: shapes and blocks
    'a': '■', 's': '□', 'd': '▪', 'f': '▫', 'g': '◆',
    'h': '◇', 'j': '▲', 'k': '△', 'l': '▼', ';': '▽',
    # ZXCV row: decorative symbols
    'z': '★', 'x': '☆', 'c': '✦', 'v': '✧', 'b': '♦',
    'n': '♢', 'm': '◈', ',': '✶', '.': '✴', '/': '✿',
}

# Default backgrounds (dark and light themes)
DEFAULT_BG_DARK = "#2a1845"
DEFAULT_BG_LIGHT = "#e8daf0"
DEFAULT_FG_DARK = "#9b7bc4"
DEFAULT_FG_LIGHT = "#7a4ca0"

# Cursor appearance
CURSOR_CHAR = "▌"


class SketchCanvas(Widget, can_focus=True):
    """
    A canvas for freeform keyboard scribbling.

    Uses render_line() to bypass Textual's compositor for immediate updates.
    Each cell stores a glyph or None (empty).
    """

    DEFAULT_CSS = """
    SketchCanvas {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        # Canvas data: dict[(x, y)] -> glyph character
        self._canvas: dict[tuple[int, int], str] = {}
        # Cursor position
        self._cursor_x = 0
        self._cursor_y = 0
        # Random state for movement drift
        self._rng = random.Random(time.time())
        # Direction bias from arrow keys: (dx, dy)
        self._direction_bias = (1, 0)  # Default: right

    def on_mount(self) -> None:
        """Center cursor on mount."""
        self._cursor_x = self.size.width // 2
        self._cursor_y = self.size.height // 2
        self.focus()

    def on_resize(self, event: events.Resize) -> None:
        """Recenter cursor if canvas resizes."""
        # Keep cursor in bounds
        self._cursor_x = max(0, min(self._cursor_x, event.size.width - 1))
        self._cursor_y = max(0, min(self._cursor_y, event.size.height - 1))

    def _get_theme_colors(self) -> tuple[str, str]:
        """Get (background, foreground) colors based on current theme."""
        try:
            is_dark = "dark" in self.app.theme
            if is_dark:
                return DEFAULT_BG_DARK, DEFAULT_FG_DARK
            else:
                return DEFAULT_BG_LIGHT, DEFAULT_FG_LIGHT
        except Exception:
            return DEFAULT_BG_DARK, DEFAULT_FG_DARK

    def _move_cursor(self) -> None:
        """
        Move cursor after placing a glyph.

        Uses direction bias from arrow keys, with small random drift.
        """
        dx, dy = self._direction_bias

        # Add small random drift (low amplitude for coherence)
        # 20% chance to drift perpendicular, 5% chance to drift opposite
        drift = self._rng.random()
        if drift < 0.05:
            # Rare: move opposite (creates density)
            dx, dy = -dx, -dy
        elif drift < 0.20:
            # Sometimes: drift perpendicular
            if dx != 0:
                dy = self._rng.choice([-1, 1])
            else:
                dx = self._rng.choice([-1, 1])
        # else: move in biased direction

        # Apply movement
        new_x = self._cursor_x + dx
        new_y = self._cursor_y + dy

        # Wrap around edges
        width, height = self.size.width, self.size.height
        if width > 0 and height > 0:
            self._cursor_x = new_x % width
            self._cursor_y = new_y % height

    def place_glyph(self, key: str) -> None:
        """Place a glyph at the current cursor position based on the key pressed."""
        glyph = GLYPH_MAP.get(key.lower())
        if glyph:
            self._canvas[(self._cursor_x, self._cursor_y)] = glyph
            self._move_cursor()
            self.refresh()

    def erase(self) -> None:
        """Erase at current cursor position (spacebar)."""
        pos = (self._cursor_x, self._cursor_y)
        if pos in self._canvas:
            del self._canvas[pos]
        self._move_cursor()
        self.refresh()

    def clear_canvas(self) -> None:
        """Clear the entire canvas."""
        self._canvas.clear()
        # Re-center cursor
        self._cursor_x = self.size.width // 2
        self._cursor_y = self.size.height // 2
        self.refresh()

    def set_direction(self, dx: int, dy: int) -> None:
        """Set direction bias from arrow keys."""
        self._direction_bias = (dx, dy)

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        key = event.key
        char = event.character

        # Clear canvas: Ctrl+L
        if key == "ctrl+l":
            self.clear_canvas()
            event.stop()
            return

        # Arrow keys: change direction bias (don't place marks)
        if key == "up":
            self.set_direction(0, -1)
            event.stop()
            return
        if key == "down":
            self.set_direction(0, 1)
            event.stop()
            return
        if key == "left":
            self.set_direction(-1, 0)
            event.stop()
            return
        if key == "right":
            self.set_direction(1, 0)
            event.stop()
            return

        # Spacebar: erase
        if key == "space":
            self.erase()
            event.stop()
            return

        # Backspace: do nothing (avoid text-editing affordances)
        if key == "backspace":
            event.stop()
            return

        # Check if this key has a mapped glyph
        if char and char.lower() in GLYPH_MAP:
            self.place_glyph(char)
            event.stop()
            return

    def render_line(self, y: int) -> Strip:
        """Render a single line of the canvas."""
        width = self.size.width
        bg_color, fg_color = self._get_theme_colors()

        bg_style = Style(bgcolor=bg_color)
        glyph_style = Style(bgcolor=bg_color, color=fg_color)
        cursor_style = Style(bgcolor=bg_color, color=fg_color, blink=True)

        segments = []

        for x in range(width):
            is_cursor = (x == self._cursor_x and y == self._cursor_y)
            glyph = self._canvas.get((x, y))

            if is_cursor:
                # Show cursor (blinks)
                segments.append(Segment(CURSOR_CHAR, cursor_style))
            elif glyph:
                segments.append(Segment(glyph, glyph_style))
            else:
                segments.append(Segment(" ", bg_style))

        return Strip(segments)


class SketchMode(Container):
    """Sketch Mode - freeform keyboard scribbling."""

    DEFAULT_CSS = """
    SketchMode {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.canvas: SketchCanvas | None = None

    def compose(self) -> ComposeResult:
        self.canvas = SketchCanvas()
        yield self.canvas

    def on_mount(self) -> None:
        if self.canvas:
            self.canvas.focus()
