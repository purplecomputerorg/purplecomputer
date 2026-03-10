"""
Room Picker Screen: A kid-friendly modal for switching rooms.

Shows 3 room options: Play, Music, Art
Plus a separate "C: Code" option below a divider.
Arrow keys navigate (left/right for rooms, up/down for volume),
number keys 1-3 for direct room selection, C for code panel toggle,
Enter selects, Escape cancels.
Any unrecognized key dismisses the picker gracefully.

When the code panel is open, shows a pane row above the rooms:
  [Main]  [Code]
for switching focus between the viewport and code panel.
"""

from textual.screen import ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Static
from textual.app import ComposeResult

from .constants import ICON_CHAT, ICON_MUSIC, ICON_PALETTE, ICON_CODE
from .keyboard import NavigationAction, ControlAction, CharacterAction


# Room options: (id, icon, label, result)
ROOM_OPTIONS = [
    ("play", ICON_CHAT, "Play", {"room": "play"}),
    ("music", ICON_MUSIC, "Music", {"room": "music"}),
    ("art", ICON_PALETTE, "Art", {"room": "art"}),
    ("code", ICON_CODE, "Code", {"toggle_code_panel": True}),
]

# Map number keys to room indices
NUMBER_KEY_ROOMS = {'1': 0, '2': 1, '3': 2, '4': 3}

# Pane options when code panel is open
PANE_OPTIONS = [
    ("main", "Main"),
    ("code", "Code"),
]


class RoomOption(Static):
    """A single selectable room option with icon and label."""

    DEFAULT_CSS = """
    RoomOption {
        width: 16;
        height: 8;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 1;
        padding: 0 1;
    }

    RoomOption.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    def __init__(self, option_id: str, icon: str, label: str, number: int, **kwargs):
        super().__init__(**kwargs)
        self.option_id = option_id
        self.icon = icon
        self.label = label
        self.number = number
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        enter_hint = "\nor Enter" if self.has_class("selected") else ""
        return caps(f"\n{self.icon}  {self.label}  {self.icon}\n\nPress {self.number}{enter_hint}\n")


class PaneOption(Static):
    """A selectable pane option (Main or Code) in the pane row."""

    DEFAULT_CSS = """
    PaneOption {
        width: 16;
        height: 3;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 1;
    }

    PaneOption.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }

    PaneOption.current-pane {
        color: $accent;
    }
    """

    def __init__(self, pane_id: str, label: str, is_current: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.pane_id = pane_id
        self.label = label
        if is_current:
            self.add_class("current-pane")
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        marker = " \u25cf" if self.has_class("current-pane") else ""
        return caps(f"{self.label}{marker}")


class RoomPickerScreen(ModalScreen):
    """
    Modal screen for selecting rooms with arrow key navigation.

    Shows Play, Music, Art options with a separate Code option below.
    Left/right arrows navigate rooms, up/down adjusts volume.
    Number keys 1-3 select rooms directly, C toggles code panel.
    Any other key dismisses the picker gracefully.

    When code panel is open, shows a pane row (Main/Code) above the rooms.
    Up/down navigates between pane row and room row.
    """

    CSS = """
    RoomPickerScreen {
        align: center middle;
    }

    #picker-dialog {
        width: 100;
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

    #picker-panes {
        width: 100%;
        height: auto;
        align: center middle;
        margin-bottom: 1;
    }

    #picker-pane-divider {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin: 0 0;
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

    def __init__(self, current_room: str = "play",
                 code_panel_open: bool = False,
                 code_panel_focused: bool = False,
                 **kwargs):
        super().__init__(**kwargs)
        self._current_room = current_room
        self._code_panel_open = code_panel_open
        self._code_panel_focused = code_panel_focused
        self._selected_index = self._get_initial_index()
        # When code panel is open, start on the pane row
        self._on_pane_row = code_panel_open
        self._pane_index = 1 if code_panel_focused else 0  # 0=Main, 1=Code

    def _get_initial_index(self) -> int:
        """Get initial selection based on current room."""
        if self._current_room == "play":
            return 0
        elif self._current_room == "music":
            return 1
        elif self._current_room == "art":
            return 2
        return 0

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        with Container(id="picker-dialog"):
            if self._code_panel_open:
                yield Static(caps("Switch Pane or Room"), id="picker-title")

                with Horizontal(id="picker-panes"):
                    yield PaneOption(
                        "main", "Main",
                        is_current=not self._code_panel_focused,
                        id="pane-main",
                    )
                    yield PaneOption(
                        "code", "Code",
                        is_current=self._code_panel_focused,
                        id="pane-code",
                    )

                yield Static("\u254c" * 20, id="picker-pane-divider")
            else:
                yield Static(caps("Pick a Room"), id="picker-title")

            with Horizontal(id="picker-options"):
                for i, (opt_id, icon, label, _) in enumerate(ROOM_OPTIONS):
                    yield RoomOption(opt_id, icon, label, i + 1, id=f"opt-{opt_id}")

            if self._code_panel_open:
                yield Static(caps("\u25c0 \u25b6  to browse       \u25b2 \u25bc switch row"), id="picker-hint")
            else:
                yield Static(caps("\u25c0 \u25b6  to browse       \u25b2 \u25bc volume"), id="picker-hint")

    def on_mount(self) -> None:
        """Highlight the initially selected option."""
        self._update_selection()

    def _update_selection(self) -> None:
        """Update visual selection state for both pane row and room row."""
        # Update room row
        for i, (opt_id, _, _, _) in enumerate(ROOM_OPTIONS):
            try:
                option = self.query_one(f"#opt-{opt_id}", RoomOption)
                if not self._on_pane_row and i == self._selected_index:
                    option.add_class("selected")
                else:
                    option.remove_class("selected")
            except Exception:
                pass

        # Update pane row (if present)
        if self._code_panel_open:
            for i, (pane_id, _) in enumerate(PANE_OPTIONS):
                try:
                    option = self.query_one(f"#pane-{pane_id}", PaneOption)
                    if self._on_pane_row and i == self._pane_index:
                        option.add_class("selected")
                    else:
                        option.remove_class("selected")
                except Exception:
                    pass

    def _select_room(self, index: int) -> None:
        """Select and dismiss with the room at the given index."""
        if 0 <= index < len(ROOM_OPTIONS):
            _, _, _, result = ROOM_OPTIONS[index]
            self.dismiss(result)

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard navigation from evdev."""
        if isinstance(action, NavigationAction):
            if action.direction == 'left':
                if self._on_pane_row:
                    self._pane_index = max(0, self._pane_index - 1)
                else:
                    self._selected_index = max(0, self._selected_index - 1)
                self._update_selection()
            elif action.direction == 'right':
                if self._on_pane_row:
                    self._pane_index = min(len(PANE_OPTIONS) - 1, self._pane_index + 1)
                else:
                    self._selected_index = min(len(ROOM_OPTIONS) - 1, self._selected_index + 1)
                self._update_selection()
            elif action.direction == 'up':
                if self._code_panel_open and not self._on_pane_row:
                    # Move from room row to pane row
                    self._on_pane_row = True
                    self._update_selection()
                else:
                    # Volume up (when on pane row or no code panel)
                    self.app.action_volume_up()
            elif action.direction == 'down':
                if self._code_panel_open and self._on_pane_row:
                    # Move from pane row to room row
                    self._on_pane_row = False
                    self._update_selection()
                else:
                    # Volume down (when on room row or no code panel)
                    self.app.action_volume_down()
            return

        if isinstance(action, CharacterAction) and not action.is_repeat:
            if action.char in NUMBER_KEY_ROOMS:
                self._select_room(NUMBER_KEY_ROOMS[action.char])
            elif action.char.lower() == 'c':
                self._select_room(3)  # Code is index 3
            else:
                # Any other character key: graceful escape (dismiss picker)
                self.dismiss(None)
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                if self._on_pane_row:
                    # Select the pane
                    pane_id, _ = PANE_OPTIONS[self._pane_index]
                    self.dismiss({"focus_pane": pane_id})
                else:
                    # Select the room
                    _, _, _, result = ROOM_OPTIONS[self._selected_index]
                    self.dismiss(result)
            elif action.action == 'escape':
                # Cancel, return None
                self.dismiss(None)
            elif action.action == 'volume_mute':
                self.app.action_volume_mute()
            elif action.action == 'volume_down':
                self.app.action_volume_down()
            elif action.action == 'volume_up':
                self.app.action_volume_up()

    async def _on_key(self, event) -> None:
        """Suppress terminal key events. All input comes via evdev."""
        event.stop()
        event.prevent_default()
