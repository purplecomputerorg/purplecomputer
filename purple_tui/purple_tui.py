#!/usr/bin/env python3
"""
Purple Computer - Main Textual TUI Application

The calm computer for kids ages 3-8.
A creativity device, not an entertainment device.
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, Center, Middle
from textual.widgets import Static, Footer
from textual.binding import Binding
from textual.css.query import NoMatches
from textual import events
from enum import Enum
import subprocess
import os


class Mode(Enum):
    """The 4 core modes of Purple Computer"""
    ASK = 1      # F1 - Math and emoji REPL
    PLAY = 2     # F2 - Music and art grid
    LISTEN = 3   # F3 - Stories and songs (future)
    WRITE = 4    # F4 - Simple text editor


class View(Enum):
    """The 3 core views - reduce screen time feeling"""
    SCREEN = 1   # 10x6" viewport
    LINE = 2     # 10" wide, 1 line height
    EARS = 3     # Screen off (blank)


# Color themes - calming purple tones
THEMES = {
    "dark": {
        "background": "#2d1b4e",      # Soft deep purple
        "foreground": "#f5f3ff",      # Soft white
        "border": "#2d1b4e",          # Same as background for border area
        "accent": "#c4b5fd",          # Light purple accent
        "muted": "#6b5b7a",           # Muted purple for secondary text
    },
    "light": {
        "background": "#f5f3ff",      # Soft white
        "foreground": "#2d1b4e",      # Deep purple text
        "border": "#e9e4f5",          # Slightly darker than background
        "accent": "#7c3aed",          # Vibrant purple accent
        "muted": "#a89cc4",           # Muted purple for secondary text
    }
}

# Mode display info
MODE_INFO = {
    Mode.ASK: {"key": "F1", "label": "Ask", "emoji": "💭"},
    Mode.PLAY: {"key": "F2", "label": "Play", "emoji": "🎵"},
    Mode.LISTEN: {"key": "F3", "label": "Listen", "emoji": "👂"},
    Mode.WRITE: {"key": "F4", "label": "Write", "emoji": "✏️"},
}


class ModeIndicator(Static):
    """Shows F1-F4 mode indicators in the border area"""

    def __init__(self, current_mode: Mode, **kwargs):
        super().__init__(**kwargs)
        self.current_mode = current_mode

    def render(self) -> str:
        parts = []
        for mode in Mode:
            info = MODE_INFO[mode]
            if mode == self.current_mode:
                parts.append(f"[bold reverse] {info['key']} {info['emoji']} [/]")
            else:
                parts.append(f"[dim]{info['key']} {info['emoji']}[/]")
        # Show sun/moon based on current theme
        is_dark = self.app.dark if hasattr(self.app, 'dark') else True
        theme_icon = "🌙" if is_dark else "☀️"
        return "  ".join(parts) + f"  [dim]F12 {theme_icon}[/]"

    def update_mode(self, mode: Mode) -> None:
        self.current_mode = mode
        self.refresh()


class SpeechIndicator(Static):
    """Shows whether speech is on/off"""

    def __init__(self, speech_on: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.speech_on = speech_on

    def render(self) -> str:
        if self.speech_on:
            return "[bold green]🔊 Speech ON[/]"
        else:
            return "[dim]🔇 Speech off[/]"

    def toggle(self) -> bool:
        self.speech_on = not self.speech_on
        self.refresh()
        return self.speech_on


class ViewportContainer(Container):
    """
    The 10x6 inch viewport that contains all mode content.
    Centered on screen with purple border filling the rest.
    """
    pass


class PurpleApp(App):
    """
    Purple Computer - The calm computer for kids.

    F1-F4: Switch between modes (Ask, Play, Listen, Write)
    Ctrl+V: Cycle views (Screen, Line, Ears)
    F12: Toggle dark/light mode
    """

    CSS = """
    Screen {
        background: $background;
    }

    #outer-container {
        width: 100%;
        height: 100%;
        align: center middle;
        background: $background;
    }

    #viewport {
        width: 100;
        height: 28;
        border: heavy $accent;
        background: $surface;
        padding: 1;
    }

    #mode-indicator {
        dock: bottom;
        height: 1;
        text-align: center;
        background: $background;
        color: $text;
        padding: 0 2;
    }

    #speech-indicator {
        dock: top;
        height: 1;
        text-align: right;
        background: $background;
        color: $text;
        padding: 0 2;
    }

    #content-area {
        width: 100%;
        height: 100%;
    }

    .mode-content {
        width: 100%;
        height: 100%;
    }

    /* View-specific styles */
    .view-line #viewport {
        height: 3;
    }

    .view-ears #viewport {
        display: none;
    }

    .view-ears #mode-indicator {
        display: none;
    }
    """

    BINDINGS = [
        Binding("f1", "switch_mode('ask')", "Ask", show=False, priority=True),
        Binding("f2", "switch_mode('play')", "Play", show=False, priority=True),
        Binding("f3", "switch_mode('listen')", "Listen", show=False, priority=True),
        Binding("f4", "switch_mode('write')", "Write", show=False, priority=True),
        Binding("f12", "toggle_theme", "Theme", show=False, priority=True),
        Binding("ctrl+d", "toggle_theme", "Theme", show=False, priority=True),  # Backup
        Binding("ctrl+v", "cycle_view", "View", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.active_mode = Mode.ASK
        self.active_view = View.SCREEN
        self.active_theme = "dark"
        self.speech_enabled = False

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        with Container(id="outer-container"):
            yield SpeechIndicator(self.speech_enabled, id="speech-indicator")
            with ViewportContainer(id="viewport"):
                yield Container(id="content-area")
            yield ModeIndicator(self.active_mode, id="mode-indicator")

    def on_mount(self) -> None:
        """Called when app starts"""
        self._apply_theme()
        self._load_mode_content()

    def _apply_theme(self) -> None:
        """Apply the current color theme"""
        self.dark = self.active_theme == "dark"
        # Update mode indicator to show current theme
        try:
            indicator = self.query_one("#mode-indicator", ModeIndicator)
            indicator.refresh()
        except NoMatches:
            pass

    def _load_mode_content(self) -> None:
        """Load the content widget for the current mode"""
        content_area = self.query_one("#content-area")
        content_area.remove_children()

        # Import and create the appropriate mode widget
        # Modes are Python modules (curated code), not purplepacks
        if self.active_mode == Mode.ASK:
            from .modes.ask_mode import AskMode
            content_area.mount(AskMode(classes="mode-content"))
        elif self.active_mode == Mode.PLAY:
            from .modes.play_mode import PlayMode
            content_area.mount(PlayMode(classes="mode-content"))
        elif self.active_mode == Mode.LISTEN:
            from .modes.listen_mode import ListenMode
            content_area.mount(ListenMode(classes="mode-content"))
        elif self.active_mode == Mode.WRITE:
            from .modes.write_mode import WriteMode
            content_area.mount(WriteMode(classes="mode-content"))

    def _update_view_class(self) -> None:
        """Update CSS class based on current view"""
        container = self.query_one("#outer-container")
        container.remove_class("view-screen", "view-line", "view-ears")

        if self.active_view == View.SCREEN:
            container.add_class("view-screen")
        elif self.active_view == View.LINE:
            container.add_class("view-line")
        elif self.active_view == View.EARS:
            container.add_class("view-ears")

    def action_switch_mode(self, mode_name: str) -> None:
        """Switch to a different mode (F1-F4)"""
        mode_map = {
            "ask": Mode.ASK,
            "play": Mode.PLAY,
            "listen": Mode.LISTEN,
            "write": Mode.WRITE,
        }
        new_mode = mode_map.get(mode_name, Mode.ASK)

        if new_mode != self.active_mode:
            self.active_mode = new_mode
            self._load_mode_content()

            try:
                indicator = self.query_one("#mode-indicator", ModeIndicator)
                indicator.update_mode(new_mode)
            except NoMatches:
                pass

    def action_toggle_theme(self) -> None:
        """Toggle between dark and light mode (F12)"""
        self.active_theme = "light" if self.active_theme == "dark" else "dark"
        self._apply_theme()

    def action_cycle_view(self) -> None:
        """Cycle through views: Screen -> Line -> Ears -> Screen (Ctrl+V)"""
        views = [View.SCREEN, View.LINE, View.EARS]
        current_idx = views.index(self.active_view)
        self.active_view = views[(current_idx + 1) % len(views)]
        self._update_view_class()

    def toggle_speech(self) -> bool:
        """Toggle speech on/off, returns new state"""
        try:
            indicator = self.query_one("#speech-indicator", SpeechIndicator)
            return indicator.toggle()
        except NoMatches:
            self.speech_enabled = not self.speech_enabled
            return self.speech_enabled


def main():
    """Entry point for Purple Computer"""
    app = PurpleApp()
    app.run()


if __name__ == "__main__":
    main()
