"""Time Travel bar: slim bottom scrubber for stepping a room back through time.

Mirrors LoopPanel's structure: a bottom-docked panel the app mounts into the
active room while scrubbing. Left/right arrows preview earlier steps full-size
above; Enter keeps what's shown, Escape puts the room back the way it was.
"""

from textual.containers import Vertical
from textual.widgets import Static

from .constants import ICON_TIME_TRAVEL

MAX_DOTS = 24  # dot track length; longer histories map onto it proportionally


class TimeTravelBar(Vertical):
    DEFAULT_CSS = """
    TimeTravelBar {
        dock: bottom;
        width: 100%;
        height: auto;
        padding: 0 1;
        background: $surface-lighten-1;
    }

    #tt-head {
        height: 1;
        text-align: center;
    }

    #tt-dots {
        height: 1;
        text-align: center;
        margin-top: 1;
        margin-bottom: 1;
    }

    #tt-action {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._index = 0
        self._total = 0

    def compose(self):
        yield Static(f"[bold]{ICON_TIME_TRAVEL} Time Travel[/]", id="tt-head")
        yield Static("", id="tt-dots")
        yield Static("", id="tt-action")

    def on_mount(self) -> None:
        self._render_lines()

    def set_position(self, index: int, total: int) -> None:
        """Show step `index` (0-based) of `total` as a filled-dots track."""
        self._index = index
        self._total = total
        self._render_lines()

    def _render_lines(self) -> None:
        if not self.is_mounted:
            return
        index, total = self._index, self._total
        dots = min(total, MAX_DOTS)
        filled = max(1, round((index + 1) / total * dots)) if total else 0
        track = ("● " * filled + "○ " * (dots - filled)).rstrip()
        left = "[dim]◀[/]" if index <= 0 else "◀"
        right = "[dim]▶[/]" if index >= total - 1 else "▶"
        self.query_one("#tt-dots", Static).update(f"{left}   {track}   {right}")
        self.query_one("#tt-action", Static).update(
            "◀ ▶ go back and forth    Enter: keep this    Esc: put it back"
        )
