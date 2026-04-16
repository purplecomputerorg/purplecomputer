"""Support info screen: version, device summary, and scrollable deep dives.

Opened from the parent menu. Shows Purple version, hardware model, and
audio status at a glance. Two buttons drop into scrollable Device info
and Audio info sub-screens for diagnostics.
"""

from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Static

from ..constants import SUPPORT_EMAIL
from ..keyboard import NavigationAction, ControlAction, CharacterAction
from ..modal import PurpleModal
from ..scrolling import scroll_widget
from .. import diagnostics


class _ScrollablePage(PurpleModal):
    """Base class for the Device info / Audio info sub-screens.

    Subclasses set TITLE and implement _collect_text(). Up/down arrow keys
    scroll, Escape returns to the Support info screen.
    """

    TITLE = "Info"

    DEFAULT_CSS = """
    _ScrollablePage #modal-dialog {
        width: 80%;
        height: 80%;
        padding: 1 2;
    }

    _ScrollablePage #info-scroll {
        width: 100%;
        height: 1fr;
        border: round $surface-lighten-2;
        padding: 0 1;
    }

    _ScrollablePage #info-body {
        width: 100%;
        height: auto;
    }
    """

    def _collect_text(self) -> str:
        raise NotImplementedError

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, "caps_text", lambda x: x)
        with Vertical(id="modal-dialog"):
            yield Static(caps(self.TITLE), id="modal-title")
            with ScrollableContainer(id="info-scroll"):
                yield Static(self._collect_text(), id="info-body")
            yield Static(caps("\u25b2 \u25bc scroll   Esc back"), id="modal-hint")

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction) and action.direction in ("up", "down"):
            try:
                scroll_widget(self.query_one("#info-scroll"), -1 if action.direction == "up" else 1)
            except Exception:
                pass
            return
        if isinstance(action, ControlAction) and action.is_down and action.action == "escape":
            self.dismiss()
            return
        if isinstance(action, CharacterAction):
            # Any character dismisses; parents can always press Esc intentionally too.
            return


class DeviceInfoScreen(_ScrollablePage):
    TITLE = "Device info"

    def _collect_text(self) -> str:
        return diagnostics.collect_device_info()


class AudioInfoScreen(_ScrollablePage):
    TITLE = "Audio info"

    def _collect_text(self) -> str:
        return diagnostics.collect_audio_info(getattr(self.app, "audio_ok", None))


# Registry of sub-screen buttons. Add new (id, label, screen_class) tuples
# here to grow the Support info screen without touching any other code.
_SUB_SCREENS = [
    ("btn-device-info", "Device info", DeviceInfoScreen),
    ("btn-audio-info", "Audio info", AudioInfoScreen),
]


class SupportInfoScreen(PurpleModal):
    """Top-level Support info modal shown from the parent menu."""

    CSS = """
    #modal-dialog {
        width: 64;
        padding: 1 2;
        max-height: 26;
    }

    #support-summary {
        width: 100%;
        text-align: center;
        margin: 1 0;
    }

    #support-email {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    .support-btn {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 0 1 0;
    }

    .support-btn.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected = 0

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, "caps_text", lambda x: x)
        with Vertical(id="modal-dialog"):
            yield Static(caps("Support info"), id="modal-title")
            yield Static(caps(self._summary_text()), id="support-summary")
            for i, (btn_id, label, _) in enumerate(_SUB_SCREENS):
                classes = "support-btn" + (" selected" if i == self._selected else "")
                yield Static(caps(label), id=btn_id, classes=classes)
            yield Static(caps(f"Contact: {SUPPORT_EMAIL}"), id="support-email")
            yield Static(caps("\u25b2 \u25bc choose   Enter open   Esc back"), id="modal-hint")

    def _summary_text(self) -> str:
        version = diagnostics.get_version_label() or "Dev build"
        model = diagnostics.get_product_name()
        audio = diagnostics.get_audio_status_line(getattr(self.app, "audio_ok", None))
        return f"{version}\n{model}\n{audio}"

    def _update_buttons(self) -> None:
        for i, (btn_id, _, _) in enumerate(_SUB_SCREENS):
            try:
                w = self.query_one(f"#{btn_id}")
                if i == self._selected:
                    w.add_class("selected")
                else:
                    w.remove_class("selected")
            except Exception:
                pass

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction) and action.direction in ("up", "down"):
            if action.direction == "up":
                self._selected = (self._selected - 1) % len(_SUB_SCREENS)
            else:
                self._selected = (self._selected + 1) % len(_SUB_SCREENS)
            self._update_buttons()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == "enter":
                _, _, screen_cls = _SUB_SCREENS[self._selected]
                self.app.push_screen(screen_cls())
            elif action.action == "escape":
                self.dismiss()
            return

        if isinstance(action, CharacterAction):
            return
