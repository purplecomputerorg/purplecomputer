"""
Write Mode - Simple Text Editor for Kids

A blank screen with large font for typing:
- Letters, numbers, symbols only
- Sticky shift (toggle, don't hold)
- Caps lock works as expected
- Backspace works
- Enter creates new line
- Arrow keys and other modifiers do nothing
"""

from textual.widgets import Static, TextArea
from textual.containers import Container
from textual.app import ComposeResult
from textual import events


class KidTextArea(TextArea):
    """
    Simple text area with kid-safe key handling.

    Only allows:
    - Letters, numbers, standard symbols
    - Backspace (delete)
    - Enter (new line)
    - Caps Lock (toggle case)
    - Sticky Shift (toggle, not hold)
    """

    DEFAULT_CSS = """
    KidTextArea {
        width: 100%;
        height: 100%;
        border: none;
        background: transparent;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sticky_shift = False

    def on_key(self, event: events.Key) -> None:
        """Filter keys for kid-safe editing"""
        key = event.key

        # Allow: backspace, enter
        if key in ("backspace", "enter"):
            return  # Let default handling work

        # Block: arrows, ctrl combos, function keys, etc.
        blocked_keys = [
            "up", "down", "left", "right",
            "home", "end", "pageup", "pagedown",
            "insert", "delete", "escape", "tab",
        ]

        if key in blocked_keys:
            event.stop()
            event.prevent_default()
            return

        # Block non-printable keys (except allowed ones above)
        if not event.is_printable and key not in ("backspace", "enter"):
            event.stop()
            event.prevent_default()
            return


class WriteMode(Container):
    """
    Write Mode - Simple text editor for small kids.

    A blank screen where kids can type freely.
    No distractions, no complex features.
    """

    DEFAULT_CSS = """
    WriteMode {
        width: 100%;
        height: 100%;
        padding: 1;
    }

    #write-header {
        height: 1;
        dock: top;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #write-area {
        width: 100%;
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[dim]Type anything you want![/]", id="write-header")
        yield KidTextArea(id="write-area")

    def on_mount(self) -> None:
        """Focus the text area when mode loads"""
        self.query_one("#write-area").focus()
