"""Loop Panel: dedicated bottom-docked panel for the music room loop station.

Mirrors the structure of `repl_panel.ReplPanel`: a Vertical widget docked at
the bottom that's hidden when the loop is idle and revealed when recording or
looping. The music room owns the loop state machine; this widget is purely
visual — it shows current state, a progress bar, and the next-action hint.
"""

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static


class LoopPanelToggleRequested(Message, bubble=True):
    """Posted by the music room when the loop panel opens or closes so the
    app can grow/shrink the viewport (mirrors ReplPanelToggleRequested)."""
    def __init__(self, opened: bool):
        super().__init__()
        self.opened = opened


# Number of blocks in the progress bar — mirrors music_room.PROGRESS_BLOCKS so
# both the in-panel bar and the idle hint use the same visual scale.
PROGRESS_BLOCKS = 20


class LoopPanel(Vertical):
    """Bottom panel that visualises the music room loop station.

    Hidden when closed (display: none). Open it via `open()` when the loop
    enters recording/looping; close via `close()` when it returns to idle.

    Content is updated via `set_recording(...)` and `set_looping(...)`. The
    music room calls these from its existing recording/loop progress timers.
    """

    DEFAULT_CSS = """
    LoopPanel {
        dock: bottom;
        width: 100%;
        height: auto;
        display: none;
        padding: 0 1;
        background: $surface-lighten-1;
    }

    #loop-state {
        height: 1;
        text-align: center;
    }

    #loop-bar {
        height: 1;
        text-align: center;
    }

    #loop-action {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True
        self.display = True

    def close(self) -> None:
        self._open = False
        self.display = False

    def compose(self):
        yield Static("", id="loop-state")
        yield Static("", id="loop-bar")
        yield Static("", id="loop-action")

    def set_recording(self, progress: float, remaining_secs: int) -> None:
        """Update panel content for the RECORDING state."""
        filled = int(progress * PROGRESS_BLOCKS)
        empty = PROGRESS_BLOCKS - filled
        bar = "█" * filled + "░" * empty
        self._set_lines(
            head=f"[bold red]● Recording, {remaining_secs}s left[/]",
            bar=f"[bold red]{bar}[/]",
            action="Play any keys    Hold Enter when done    Esc to cancel",
        )

    def set_looping(self, progress: float) -> None:
        """Update panel content for the LOOPING state."""
        pos = int(progress * PROGRESS_BLOCKS)
        bar_chars = list("░" * PROGRESS_BLOCKS)
        if pos < PROGRESS_BLOCKS:
            bar_chars[pos] = "█"
        bar = "".join(bar_chars)
        self._set_lines(
            head="[bold red]↻ Looping and recording[/]",
            bar=f"[bold red]{bar}[/]",
            action="Play on top    Hold Enter to stop    Tab or Esc to exit",
        )

    def _set_lines(self, *, head: str, bar: str, action: str) -> None:
        try:
            self.query_one("#loop-state", Static).update(head)
            self.query_one("#loop-bar", Static).update(bar)
            self.query_one("#loop-action", Static).update(action)
        except Exception:
            pass
