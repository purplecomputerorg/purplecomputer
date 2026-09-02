"""Time Travel bar: slim bottom scrubber for stepping a room back through time.

Mirrors LoopPanel's structure: a bottom-docked panel the app mounts into the
active room while scrubbing. Left/right arrows preview earlier steps full-size
above; Enter keeps what's shown, Escape puts the room back the way it was.
"""

from textual.containers import Vertical
from textual.widgets import Static

from .constants import ICON_TIME_TRAVEL

MAX_DOTS = 24  # dots shown 1:1 for the newest steps; ⋯ marks more beyond


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
        # Initial content comes from values stored by set_position() before
        # mounting completes, so the bar never flashes blank.
        yield Static(f"[bold]{ICON_TIME_TRAVEL} Time Travel[/]", id="tt-head")
        yield Static(self._dots_markup(), id="tt-dots")
        yield Static("Enter: keep this    Esc: never mind", id="tt-action")

    def set_position(self, index: int, total: int) -> None:
        """Show step `index` (0-based) of `total` on the dot track."""
        self._index = index
        self._total = total
        try:
            self.query_one("#tt-dots", Static).update(self._dots_markup())
        except Exception:
            pass  # not composed yet; compose() will use the stored values

    def _dots_markup(self) -> str:
        """One dot per step over a window of the newest MAX_DOTS steps, so each
        arrow press moves exactly one dot. A dim ⋯ says more steps lie beyond."""
        index, total = self._index, self._total
        count = min(total, MAX_DOTS)
        start = min(max(0, total - count), index)
        filled = index - start + 1 if total else 0
        track = ("● " * filled + "○ " * (count - filled)).rstrip()
        if start > 0:
            track = f"[dim]⋯[/] {track}"
        if start + count < total:
            track = f"{track} [dim]⋯[/]"
        left = "◀ back in time"
        right = "forward ▶"
        if index <= 0:
            left = f"[dim]{left}[/]"
        if index >= total - 1:
            right = f"[dim]{right}[/]"
        return f"{left}   {track}   {right}"
