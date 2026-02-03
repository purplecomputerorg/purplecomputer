"""
Mode Picker Screen: A kid-friendly modal for switching modes.

Shows 3 options: Explore, Play, Doodle
Arrow keys navigate, Enter selects, Escape cancels.
"""

from textual.screen import ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Static
from textual.app import ComposeResult

from .constants import ICON_CHAT, ICON_MUSIC, ICON_PALETTE
from .keyboard import NavigationAction, ControlAction


# Mode options: (id, icon, label, result)
# result is what gets returned when selected
MODE_OPTIONS = [
    ("explore", ICON_CHAT, "Explore", {"mode": "explore"}),
    ("play", ICON_MUSIC, "Play", {"mode": "play"}),
    ("doodle", ICON_PALETTE, "Doodle", {"mode": "doodle"}),
]


class ModeOption(Static):
    """A single selectable mode option with icon and label."""

    DEFAULT_CSS = """
    ModeOption {
        width: 14;
        height: 5;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 1;
        padding: 0 1;
    }

    ModeOption.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    def __init__(self, option_id: str, icon: str, label: str, **kwargs):
        super().__init__(**kwargs)
        self.option_id = option_id
        self.icon = icon
        self.label = label

    def render(self) -> str:
        return f"{self.icon}\n{self.label}"


class ModePickerScreen(ModalScreen):
    """
    Modal screen for selecting modes with arrow key navigation.

    Shows Explore, Play, and Doodle (Write/Paint) options.
    Returns the selected mode info or None if cancelled.
    """

    CSS = """
    ModePickerScreen {
        align: center middle;
    }

    #picker-dialog {
        width: 58;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: heavy $primary;
    }

    #picker-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #picker-options {
        width: 100%;
        height: auto;
        align: center middle;
        margin-bottom: 1;
    }

    #picker-hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, current_mode: str = "explore", **kwargs):
        super().__init__(**kwargs)
        self._current_mode = current_mode
        self._selected_index = self._get_initial_index()

    def _get_initial_index(self) -> int:
        """Get initial selection based on current mode."""
        if self._current_mode == "explore":
            return 0
        elif self._current_mode == "play":
            return 1
        elif self._current_mode == "doodle":
            return 2
        return 0

    def compose(self) -> ComposeResult:
        with Container(id="picker-dialog"):
            yield Static("Pick a Mode", id="picker-title")

            with Horizontal(id="picker-options"):
                for opt_id, icon, label, _ in MODE_OPTIONS:
                    yield ModeOption(opt_id, icon, label, id=f"opt-{opt_id}")

            yield Static("◀ ▶", id="picker-hint")

    def on_mount(self) -> None:
        """Highlight the initially selected option."""
        self._update_selection()

    def _update_selection(self) -> None:
        """Update visual selection state."""
        for i, (opt_id, _, _, _) in enumerate(MODE_OPTIONS):
            try:
                option = self.query_one(f"#opt-{opt_id}", ModeOption)
                if i == self._selected_index:
                    option.add_class("selected")
                else:
                    option.remove_class("selected")
            except Exception:
                pass

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard navigation from evdev."""
        if isinstance(action, NavigationAction):
            if action.direction == 'left':
                self._selected_index = max(0, self._selected_index - 1)
                self._update_selection()
            elif action.direction == 'right':
                self._selected_index = min(len(MODE_OPTIONS) - 1, self._selected_index + 1)
                self._update_selection()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                # Return the selected mode info
                _, _, _, result = MODE_OPTIONS[self._selected_index]
                self.dismiss(result)
            elif action.action == 'escape':
                # Cancel, return None
                self.dismiss(None)

    async def _on_key(self, event) -> None:
        """Suppress terminal key events. All input comes via evdev."""
        event.stop()
        event.prevent_default()
