"""
Play Mode - Music and Art Grid

A rectangular grid mapped to QWERTY keyboard.
Press keys to play sounds and cycle colors.
"""

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual.widget import Widget
from textual.strip import Strip
from textual import events
from rich.segment import Segment
from rich.style import Style
import subprocess
from pathlib import Path


# 10x4 grid matching keyboard layout
GRID_KEYS = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';'],
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/'],
]

# Rainbow colors to cycle through (no light purple)
# Red, Orange, Yellow, Green, Blue, Indigo, Violet + None (back to default)
COLORS = ["#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#4dabf7", "#748ffc", "#da77f2", None]

# Default background (None in COLORS means use this)
DEFAULT_BG = "#2a1845"

# Light colors need dark text
LIGHT_COLORS = {"#ffd43b", "#69db7c", "#ffa94d"}


class GridCell(Widget):
    """A single grid cell - uses render_line to bypass compositor bug."""

    DEFAULT_CSS = """
    GridCell {
        width: 1fr;
        height: 1fr;
    }
    """

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key
        self.color_idx = -1
        self._bg_color = DEFAULT_BG

    def next_color(self) -> None:
        """Cycle to the next color."""
        self.color_idx += 1
        color = COLORS[self.color_idx % len(COLORS)]
        self._bg_color = color if color else DEFAULT_BG
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render each line manually - bypasses compositor."""
        width = self.size.width
        height = self.size.height

        # Use dark text on light backgrounds
        text_color = "#1e1033" if self._bg_color in LIGHT_COLORS else "white"
        bg_style = Style(bgcolor=self._bg_color)
        text_style = Style(bgcolor=self._bg_color, color=text_color, bold=True)

        # Center the key vertically and horizontally
        mid_y = height // 2
        if y == mid_y:
            # Line with the key character centered
            pad_left = (width - 1) // 2
            pad_right = width - pad_left - 1
            segments = [
                Segment(" " * pad_left, bg_style),
                Segment(self.key, text_style),
                Segment(" " * pad_right, bg_style),
            ]
        else:
            # Empty line with background
            segments = [Segment(" " * width, bg_style)]

        return Strip(segments)


class PlayMode(Container, can_focus=True):
    """Play Mode - press keys to make sounds and colors."""

    DEFAULT_CSS = """
    PlayMode {
        width: 100%;
        height: 100%;
    }

    #grid {
        width: 100%;
        height: 1fr;
        layout: grid;
        grid-size: 10 4;
        grid-rows: 1fr 1fr 1fr 1fr;
        grid-columns: 1fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr 1fr;
    }

    #hint {
        dock: bottom;
        width: 100%;
        height: 1;
        text-align: center;
        color: #6b5b8a;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cells: dict[str, GridCell] = {}
        self.sounds_path = self._get_sounds_path()

    # Block all mouse events
    def on_click(self, event) -> None:
        event.stop()

    def on_mouse_down(self, event) -> None:
        event.stop()

    def on_mouse_up(self, event) -> None:
        event.stop()

    def on_mouse_scroll_down(self, event) -> None:
        event.stop()

    def on_mouse_scroll_up(self, event) -> None:
        event.stop()

    def _get_sounds_path(self) -> Path:
        """Find the sounds directory."""
        paths = [
            Path(__file__).parent.parent.parent / "packs" / "core-sounds" / "content",
            Path.home() / ".purple" / "packs" / "core-sounds" / "content",
        ]
        for p in paths:
            if p.exists():
                return p
        return paths[0]

    def compose(self) -> ComposeResult:
        with Container(id="grid"):
            for row in GRID_KEYS:
                for key in row:
                    cell = GridCell(key)
                    # Store by uppercase for letters, as-is for others
                    self.cells[key.upper() if key.isalpha() else key] = cell
                    yield cell
        yield Static("[dim]Press keys to play![/]", id="hint")

    def on_mount(self) -> None:
        self.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key press."""
        char = event.character or event.key
        if not char:
            return

        lookup = char.upper() if char.isalpha() else char

        if lookup in self.cells:
            event.stop()
            self.cells[lookup].next_color()
            self._play_sound(lookup)

    def _play_sound(self, key: str) -> None:
        """Play sound for a key."""
        # Map special chars to filenames
        names = {';': 'semicolon', ',': 'comma', '.': 'period', '/': 'slash'}
        name = names.get(key, key.lower())
        path = self.sounds_path / f"{name}.wav"

        if path.exists():
            try:
                subprocess.Popen(
                    ['afplay', str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except OSError:
                pass
