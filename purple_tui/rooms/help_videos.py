"""Help & Videos screen: a scannable QR plus the plain video-guide URL.

Opened from the parent menu. The QR is pre-baked (purple_tui/qr_data.py) and
drawn with half-block characters so two module rows fit per terminal row,
keeping the whole code inside the viewport. Dark modules render black, light
ones white, so the baked quiet-zone border gives a scannable frame even on the
purple dialog.
"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from rich.text import Text

from ..constants import SUPPORT_EMAIL
from ..keyboard import ControlAction, CharacterAction
from ..modal import PurpleModal
from ..qr_data import VIDEO_QR_MATRIX, VIDEO_QR_URL

_UPPER_HALF = "▀"  # ▀ : foreground paints top module, background the bottom one

# Brand-purple QR. Keep the dark/light luminance gap wide so phones still scan it.
_QR_DARK = "#3a1d63"
_QR_LIGHT = "#f3eefb"


def _render_qr() -> Text:
    rows = [[c == "1" for c in row] for row in VIDEO_QR_MATRIX]
    blank = [False] * len(rows[0])
    text = Text(no_wrap=True)
    for top in range(0, len(rows), 2):
        top_row = rows[top]
        bot_row = rows[top + 1] if top + 1 < len(rows) else blank
        for x in range(len(top_row)):
            fg = _QR_DARK if top_row[x] else _QR_LIGHT
            bg = _QR_DARK if bot_row[x] else _QR_LIGHT
            text.append(_UPPER_HALF, style=f"{fg} on {bg}")
        if top + 2 < len(rows):
            text.append("\n")
    return text


class HelpVideosScreen(PurpleModal):
    """Show video-guide QR and URL for parents."""

    CSS = """
    #modal-dialog {
        width: auto;
        padding: 1 3;
    }

    #help-intro {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    #help-qr {
        width: auto;
        margin: 0 1;
    }

    #help-url {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static("Help & Videos", id="modal-title")
            yield Static("Scan to watch video guides:", id="help-intro")
            yield Static(_render_qr(), id="help-qr")
            yield Static(VIDEO_QR_URL.split("://", 1)[-1], id="help-url")
            yield Static(f"Questions? {SUPPORT_EMAIL}", id="modal-hint")

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, ControlAction) and action.is_down and action.action == "escape":
            self.dismiss()
            return
        if isinstance(action, CharacterAction):
            return
