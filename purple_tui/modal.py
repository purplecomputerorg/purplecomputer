"""Base modal for Purple Computer dialogs."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from .constants import SUPPORT_EMAIL


class PurpleModal(ModalScreen):
    """Base class for Purple Computer modal dialogs. Provides shared styling.

    Subclasses should use these standard IDs:
    - #modal-dialog: the main dialog container
    - #modal-title: the dialog title
    - #modal-hint: the bottom hint line
    Content-specific widgets use their own IDs.
    """

    DEFAULT_CSS = """
    PurpleModal {
        align: center middle;
    }

    #modal-dialog {
        height: auto;
        background: $surface;
        border: heavy $primary;
    }

    #modal-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #modal-hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """


class AudioUnavailableModal(PurpleModal):
    """Shown once per session if pygame's audio mixer fails to initialize."""

    CSS = """
    #modal-dialog {
        width: 60;
        padding: 2 3;
    }
    #modal-body {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, "caps_text", lambda x: x)
        with Container(id="modal-dialog"):
            yield Static(caps("Sound isn't working"), id="modal-title")
            yield Static(
                caps(
                    "Music will still open, but you won't hear anything.\n"
                    "If this keeps happening, ask a grown-up to email\n"
                    f"{SUPPORT_EMAIL}"
                ),
                id="modal-body",
            )
            yield Static(caps("Press any key to continue"), id="modal-hint")

    async def handle_keyboard_action(self, action) -> None:
        self.dismiss()
