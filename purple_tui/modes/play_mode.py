"""
Play Mode - Music and Art Grid

A rectangular grid mapped to QWERTY keyboard:
- Letter keys (A-Z): Toggle grid cells on/off, play notes, cycle colors
- Number keys (0-9): Play fun silly sounds (boing, drum, pop, giggle, etc.)
- Simple kid-friendly rules: letters = music + art, numbers = silly sounds
"""

from textual.widgets import Static
from textual.containers import Container
from textual.app import ComposeResult
from textual import events
from textual.reactive import reactive
import subprocess
import os
from pathlib import Path


# QWERTY keyboard layout for the grid
QWERTY_ROWS = [
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M'],
]

# Number keys for silly sounds
NUMBER_KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']

# Rainbow colors for cycling
RAINBOW_COLORS = [
    "#ff6b6b",  # Red
    "#ffa94d",  # Orange
    "#ffd43b",  # Yellow
    "#69db7c",  # Green
    "#4dabf7",  # Blue
    "#9775fa",  # Purple
    "#f783ac",  # Pink
]


def get_sounds_path() -> Path:
    """Get path to the sounds pack"""
    # Try different locations
    locations = [
        # Development: project root
        Path(__file__).parent.parent.parent / "packs" / "core-sounds" / "content",
        # Installed: home directory
        Path.home() / ".purple" / "packs" / "core-sounds" / "content",
    ]
    for loc in locations:
        if loc.exists():
            return loc
    return locations[0]  # Default to first even if not found


class GridCell(Static):
    """A single cell in the play grid"""

    active = reactive(False)
    color_index = reactive(0)

    def __init__(self, letter: str, **kwargs):
        super().__init__(**kwargs)
        self.letter = letter

    def render(self) -> str:
        if self.active:
            color = RAINBOW_COLORS[self.color_index % len(RAINBOW_COLORS)]
            return f"[bold {color}]{self.letter}[/]"
        else:
            return f"[dim]{self.letter}[/]"

    def toggle(self) -> bool:
        """Toggle the cell state, cycle color if already on"""
        if self.active:
            # Already on, cycle to next color
            self.color_index = (self.color_index + 1) % len(RAINBOW_COLORS)
        else:
            # Turn on
            self.active = True
        return self.active


class PlayMode(Container):
    """
    Play Mode - Music and art grid.

    Press letter keys to toggle cells and play notes.
    Each letter has its own color state (cycles through rainbow).
    Number keys play silly sounds (boing, drum, pop, etc.)
    """

    DEFAULT_CSS = """
    PlayMode {
        width: 100%;
        height: 100%;
        align: center middle;
        layout: vertical;
    }

    #play-title {
        width: 100%;
        height: 1;
        text-align: center;
        margin-bottom: 1;
    }

    #grid-container {
        width: auto;
        height: auto;
        align: center middle;
    }

    .grid-row {
        width: auto;
        height: 3;
        align: center middle;
        layout: horizontal;
    }

    GridCell {
        width: 5;
        height: 3;
        border: round $accent;
        text-align: center;
        content-align: center middle;
    }

    #number-row {
        margin-top: 1;
    }

    #instructions {
        width: 100%;
        height: 1;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cells: dict[str, GridCell] = {}
        self.sounds_path = get_sounds_path()

    def compose(self) -> ComposeResult:
        yield Static("[bold]🎵 Play Mode 🎵[/]", id="play-title")

        with Container(id="grid-container"):
            # QWERTY letter rows
            for row in QWERTY_ROWS:
                with Container(classes="grid-row"):
                    for letter in row:
                        cell = GridCell(letter)
                        self.cells[letter] = cell
                        yield cell

            # Number row for silly sounds
            with Container(classes="grid-row", id="number-row"):
                for num in NUMBER_KEYS:
                    cell = GridCell(num)
                    self.cells[num] = cell
                    yield cell

        yield Static(
            "[dim]Letters = music + color! Numbers = silly sounds![/]",
            id="instructions"
        )

    def on_mount(self) -> None:
        """Focus when mode loads"""
        self.focus()

    def _get_sound_file(self, key: str) -> str | None:
        """Get the path to a pre-generated sound file"""
        wav_path = self.sounds_path / f"{key.lower()}.wav"
        if wav_path.exists():
            return str(wav_path)
        return None

    def _play_sound(self, wav_path: str) -> None:
        """Play a WAV file"""
        import platform
        system = platform.system()

        try:
            if system == 'Darwin':
                subprocess.Popen(['afplay', wav_path],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            elif system == 'Linux':
                subprocess.Popen(['aplay', '-q', wav_path],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        except (FileNotFoundError, OSError):
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key presses"""
        # Get the character from the key event
        key = event.character or event.key
        if key:
            key = key.upper()

        # Check if it's a letter or number we care about
        if key and key in self.cells:
            event.stop()
            event.prevent_default()
            cell = self.cells[key]

            # Letters toggle cells, numbers just play
            if key.isalpha():
                cell.toggle()

            # Play the pre-generated sound
            wav_path = self._get_sound_file(key)
            if wav_path:
                self._play_sound(wav_path)
