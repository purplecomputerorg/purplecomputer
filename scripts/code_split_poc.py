"""
Proof of concept: split-screen code mode via font resizing.

Press 'c' to toggle code mode (shrinks font to 2/3, shows split layout).
Press 'q' to quit.

Run with: just python scripts/code_split_poc.py
(Must be inside Alacritty with PURPLE_ALACRITTY_CONFIG set)
"""

import os
import re
import time

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal, Vertical
from textual.strip import Strip
from textual import events
from rich.segment import Segment
from rich.style import Style


# Alacritty config handling (copied minimal version from font_sizer)
def _get_config_path() -> str | None:
    path = os.environ.get("PURPLE_ALACRITTY_CONFIG", "/etc/purple/alacritty.toml")
    if os.path.isfile(path):
        return path
    return None


def _read_font_size(config_path: str) -> float | None:
    try:
        with open(config_path) as f:
            content = f.read()
        m = re.search(r'^size\s*=\s*([\d.]+)', content, re.MULTILINE)
        if m:
            return float(m.group(1))
    except (OSError, ValueError):
        pass
    return None


def _write_font_size(config_path: str, new_size: float) -> bool:
    try:
        with open(config_path) as f:
            content = f.read()
        new_content = re.sub(
            r'^(size\s*=\s*)[\d.]+',
            f'\\g<1>{new_size:.1f}',
            content, count=1, flags=re.MULTILINE,
        )
        if new_content == content:
            return False
        with open(config_path, 'w') as f:
            f.write(new_content)
        return True
    except OSError:
        return False


class ColorPanel(Widget):
    """A panel that fills with a solid color and label."""

    def __init__(self, label: str, bg_color: str, **kwargs):
        super().__init__(**kwargs)
        self._label = label
        self._bg_color = bg_color

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        style = Style(bgcolor=self._bg_color, color="white", bold=True)
        if y == self.size.height // 2:
            text = self._label.center(width)[:width]
            return Strip([Segment(text, style)])
        return Strip([Segment(" " * width, style)])


class CodeSplitApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #normal-layout {
        height: 1fr;
    }

    #split-top {
        height: 2fr;
        layout: horizontal;
    }

    #split-bottom {
        height: 1fr;
    }

    #room-panel {
        width: 2fr;
    }

    #side-panel {
        width: 1fr;
    }

    #status {
        dock: bottom;
        height: 1;
        background: #4a3866;
        color: #f5f3ff;
        text-align: center;
    }
    """

    def __init__(self):
        super().__init__()
        self._code_mode = False
        self._config_path = _get_config_path()
        self._original_font: float | None = None
        if self._config_path:
            self._original_font = _read_font_size(self._config_path)

    def compose(self) -> ComposeResult:
        yield ColorPanel("Room (Play / Music / Art)", "#2a1845", id="normal-layout")
        yield Static("Press 'c' to toggle code mode | 'q' to quit", id="status")

    def _rebuild_layout(self) -> None:
        """Swap between normal and split layouts."""
        # Remove existing content (not the status bar)
        for widget in list(self.query("ColorPanel, #split-top, #split-bottom")):
            widget.remove()

        status = self.query_one("#status")

        if self._code_mode:
            top = Horizontal(
                ColorPanel("Room", "#2a1845", id="room-panel"),
                ColorPanel("Toolbox / Preview", "#1a2a1a", id="side-panel"),
                id="split-top",
            )
            bottom = ColorPanel("Code Editor", "#1a1a2a", id="split-bottom")
            self.mount(top, before=status)
            self.mount(bottom, before=status)
            cols, rows = os.get_terminal_size()
            status.update(
                f"CODE MODE | {cols}x{rows} cells | Press 'c' to exit code mode | 'q' to quit"
            )
        else:
            panel = ColorPanel("Room (Play / Music / Art)", "#2a1845", id="normal-layout")
            self.mount(panel, before=status)
            cols, rows = os.get_terminal_size()
            status.update(
                f"NORMAL MODE | {cols}x{rows} cells | Press 'c' for code mode | 'q' to quit"
            )

    def _toggle_code_mode(self) -> None:
        if not self._config_path or not self._original_font:
            self.query_one("#status").update("No Alacritty config found!")
            return

        self._code_mode = not self._code_mode

        if self._code_mode:
            new_font = round(self._original_font * 2 / 3 * 2) / 2  # floor to 0.5
            _write_font_size(self._config_path, new_font)
        else:
            _write_font_size(self._config_path, self._original_font)

        # Give Alacritty a moment to reload, then rebuild
        self.set_timer(0.3, self._rebuild_layout)

    async def on_key(self, event: events.Key) -> None:
        if event.key == "c":
            self._toggle_code_mode()
        elif event.key == "q":
            # Restore font before quitting
            if self._config_path and self._original_font:
                _write_font_size(self._config_path, self._original_font)
            self.exit()

    def on_resize(self, event: events.Resize) -> None:
        """Update status with current terminal size."""
        status = self.query_one("#status", Static)
        mode = "CODE" if self._code_mode else "NORMAL"
        status.update(
            f"{mode} MODE | {event.size.width}x{event.size.height} cells | Press 'c' to toggle | 'q' to quit"
        )


if __name__ == "__main__":
    app = CodeSplitApp()
    app.run()
