"""Base modal for Purple Computer dialogs."""

from textual.screen import ModalScreen


class PurpleModal(ModalScreen):
    """Base class for Purple Computer modal dialogs. Provides shared styling.

    Subclasses should use these standard IDs:
    - #modal-dialog: the main dialog container
    - #modal-title: the dialog title
    - #modal-hint: the bottom hint line
    Content-specific widgets use their own IDs.
    """

    CSS = """
    PurpleModal {
        align: center middle;
    }

    #modal-dialog {
        height: auto;
        background: $surface;
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
