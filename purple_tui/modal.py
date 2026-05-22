"""Base modal for Purple Computer dialogs."""

from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Static
from textual.app import ComposeResult
from textual import events

from .keyboard import NavigationAction, ControlAction


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
        background: $background;
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


class PickerModal(PurpleModal):
    """Base class for modal option pickers with up/down navigation.

    Subclasses set TITLE, OPTIONS, and default_selected. Each option is
    (value, label) or (value, label, description). Enter dismisses with the
    selected value, Escape dismisses with escape_value.
    """

    CSS = """
    #modal-dialog {
        width: 50;
        padding: 1 2;
    }

    #modal-title {
        color: $primary;
    }

    #modal-desc {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    .picker-option {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 1;
    }

    .picker-option.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    TITLE: str = ""
    DESCRIPTION: str = ""
    OPTIONS: list = []
    default_selected: int = 0
    escape_value = None  # What to dismiss with on Escape

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected = self.default_selected

    def _option_label(self, option) -> str:
        if len(option) == 3:
            return f"{option[1]}\n{option[2]}"
        return option[1]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Static(self.TITLE, id="modal-title")
            if self.DESCRIPTION:
                yield Static(self.DESCRIPTION, id="modal-desc")
            for i, opt in enumerate(self.OPTIONS):
                yield Static(
                    self._option_label(opt),
                    id=f"picker-opt-{i}",
                    classes="picker-option",
                )
            yield Static("▲ ▼ choose   Enter confirm   Esc cancel", id="modal-hint")

    def on_mount(self) -> None:
        self._update_selection()

    def _update_selection(self) -> None:
        for i in range(len(self.OPTIONS)):
            try:
                widget = self.query_one(f"#picker-opt-{i}", Static)
                widget.set_class(i == self._selected, "selected")
            except Exception:
                pass

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._selected = (self._selected - 1) % len(self.OPTIONS)
                self._update_selection()
            elif action.direction == 'down':
                self._selected = (self._selected + 1) % len(self.OPTIONS)
                self._update_selection()
            return

        if isinstance(action, ControlAction) and action.is_down and not action.is_repeat:
            if action.action == 'enter':
                self._on_confirm(self.OPTIONS[self._selected][0])
            elif action.action == 'escape':
                self.dismiss(self.escape_value)

    def _on_confirm(self, value):
        self.dismiss(value)
