"""
Room Picker Screen: A kid-friendly modal for switching rooms.

Shows 3 rooms (Play, Music, Art) at the top, then a code space toggle
(full width) with On/Off indicator, and Volume + Clear Rooms side by side.
Arrow keys navigate, number keys 1-3 for direct room selection,
Space toggles code space, V opens volume, C clears rooms,
Enter selects, Escape cancels. Any unrecognized key dismisses gracefully.
"""

from textual.screen import ModalScreen
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static
from textual.app import ComposeResult
from textual.message import Message

from .constants import (
    ICON_CHAT, ICON_MUSIC, ICON_PALETTE, ICON_VOLUME_HIGH,
    ICON_BROOM, ICON_CODE,
)
from .keyboard import NavigationAction, ControlAction, CharacterAction


# Room options: (id, icon, label, result)
ROOM_OPTIONS = [
    ("play", ICON_CHAT, "Play", {"room": "play"}),
    ("music", ICON_MUSIC, "Music", {"room": "music"}),
    ("art", ICON_PALETTE, "Art", {"room": "art"}),
]

# Map number keys to room indices
NUMBER_KEY_ROOMS = {'1': 0, '2': 1, '3': 2}

# Navigation rows
ROW_ROOMS = 0
ROW_CODE = 1
ROW_EXTRAS = 2
NUM_ROWS = 3

# Extras columns: 0 = volume, 1 = clear rooms
COL_VOLUME = 0
COL_CLEAR = 1
NUM_EXTRA_COLS = 2


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


class CodeToggleOption(Static):
    """Wide toggle button for code space, spanning the width of 3 room boxes."""

    DEFAULT_CSS = """
    CodeToggleOption {
        width: 52;
        height: 7;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 1;
    }

    CodeToggleOption.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }

    CodeToggleOption.code-active {
        border: round $accent;
    }
    """

    def __init__(self, code_on: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._code_on = code_on
        if code_on:
            self.add_class("code-active")
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        # Line 1: robots on either side of "Code Space"
        title_line = f"{ICON_CODE}  Code Space  {ICON_CODE}"
        # Line 2: radio-style indicator, filled circle marks current state
        if self._code_on:
            status_line = "\u25cb Off  \u25cf On"
        else:
            status_line = "\u25cf Off  \u25cb On"
        # Line 3: Turn On / Turn Off hint
        action = "Turn Off" if self._code_on else "Turn On"
        enter_hint = " or Enter" if self.has_class("selected") else ""
        hint = f"Press Space{enter_hint}: {action}"
        return caps(f"\n{title_line}\n{status_line}\n{hint}")


class ExtraOption(Static):
    """Half-width action button for the extras row (volume, clear rooms)."""

    DEFAULT_CSS = """
    ExtraOption {
        width: 25;
        height: 5;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 1;
    }

    ExtraOption.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    def __init__(self, icon: str, label: str, key_hint: str, **kwargs):
        super().__init__(**kwargs)
        self._icon = icon
        self._label = label
        self._key_hint = key_hint
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        hint = f"Press {self._key_hint} or Enter" if self.has_class("selected") else f"Press {self._key_hint}"
        return caps(f"\n{self._icon}  {self._label}  {self._icon}\n{hint}")


class ConfirmFreshScreen(ModalScreen):
    """Are you sure? confirmation for Clear Rooms.

    Uses vertical layout (up/down navigation) consistent with
    the brightness/contrast adjustment dialogs.
    """

    CSS = """
    ConfirmFreshScreen {
        align: center middle;
    }

    #confirm-dialog {
        width: 50;
        height: auto;
        max-height: 22;
        padding: 2 3;
        background: $surface;
        border: heavy $warning;
    }

    #confirm-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #confirm-subtitle {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    .confirm-btn {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 1 1 0 1;
    }

    .confirm-btn.selected {
        border: heavy $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }

    #confirm-hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected = 1  # Default to "No, go back" (safer)

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        with Container(id="confirm-dialog"):
            yield Static(caps("Are you sure?"), id="confirm-title")
            yield Static(caps("This will clear everything."), id="confirm-subtitle")
            with Vertical(id="confirm-buttons"):
                yield Static(caps("Yes, clear rooms"), id="btn-yes", classes="confirm-btn")
                yield Static(caps("No, go back"), id="btn-no", classes="confirm-btn selected")
            yield Static(caps("\u25b2 \u25bc to choose       Enter to confirm       Escape to cancel"), id="confirm-hint")

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction in ('up', 'down'):
                self._selected = 1 - self._selected
                self._update_selection()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                self.dismiss(self._selected == 0)
            elif action.action == 'escape':
                self.dismiss(False)
            return

        if isinstance(action, CharacterAction):
            self.dismiss(False)

    def _update_selection(self) -> None:
        try:
            yes_btn = self.query_one("#btn-yes")
            no_btn = self.query_one("#btn-no")
            if self._selected == 0:
                yes_btn.add_class("selected")
                no_btn.remove_class("selected")
            else:
                yes_btn.remove_class("selected")
                no_btn.add_class("selected")
        except Exception:
            pass

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()


class RoomPickerScreen(ModalScreen):
    """
    Modal screen for selecting rooms with arrow key navigation.

    Layout (3 navigable rows):
      [1 Play]  [2 Music]  [3 Art]          <- room row
      [Code Space  ● / ○    Press Space]     <- code toggle (full width)
      [Volume  V]  [Clear Rooms  C]          <- extras row (50/50)
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

    #picker-options {
        width: 100%;
        height: auto;
        align: center middle;
        margin-bottom: 1;
    }

    #picker-toggle-row {
        width: 100%;
        height: auto;
        align: center middle;
        margin-bottom: 1;
    }

    #picker-extras {
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

    class RoomSelected(Message, bubble=True):
        """Posted when a room is selected, before the picker is dismissed.

        The app should handle this by switching rooms, then dismissing the picker.
        This avoids a flicker frame where the old room is visible between
        picker dismiss and room switch.
        """
        def __init__(self, result: dict):
            super().__init__()
            self.result = result

    def __init__(self, current_room: str = "play",
                 code_space_open: bool = False,
                 code_space_available: bool = True,
                 **kwargs):
        super().__init__(**kwargs)
        self._current_room = current_room
        self._code_space_open = code_space_open
        self._code_space_available = code_space_available
        # If code space is active, start focused on code space row
        if code_space_open and code_space_available:
            self._active_row = ROW_CODE
        else:
            self._active_row = ROW_ROOMS
        self._room_index = self._get_initial_room_index()
        self._extra_index = COL_VOLUME

    def _get_initial_room_index(self) -> int:
        for i, (opt_id, _, _, _) in enumerate(ROOM_OPTIONS):
            if opt_id == self._current_room:
                return i
        return 0

    @property
    def _visible_rows(self) -> list[int]:
        """Row indices that are navigable (skips code row when unavailable)."""
        rows = [ROW_ROOMS]
        if self._code_space_available:
            rows.append(ROW_CODE)
        rows.append(ROW_EXTRAS)
        return rows

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, 'caps_text', lambda x: x)

        with Container(id="picker-dialog"):
            yield Static(caps("Pick a Room"), id="picker-title")

            with Horizontal(id="picker-options"):
                for i, (opt_id, icon, label, _) in enumerate(ROOM_OPTIONS):
                    yield RoomOption(opt_id, icon, label, i + 1, id=f"opt-{opt_id}")

            if self._code_space_available:
                with Horizontal(id="picker-toggle-row"):
                    yield CodeToggleOption(
                        code_on=self._code_space_open,
                        id="opt-code-toggle",
                    )

            with Horizontal(id="picker-extras"):
                yield ExtraOption(ICON_VOLUME_HIGH, "Volume", "V", id="opt-volume")
                yield ExtraOption(ICON_BROOM, "Clear Rooms", "C", id="opt-clear-rooms")

            yield Static(caps("Arrow keys to move    Enter to pick"), id="picker-hint")

    def on_mount(self) -> None:
        self._update_selection()

    def _update_selection(self) -> None:
        """Update visual selection state."""
        # Room row
        for i, (opt_id, _, _, _) in enumerate(ROOM_OPTIONS):
            try:
                option = self.query_one(f"#opt-{opt_id}", RoomOption)
                if self._active_row == ROW_ROOMS and i == self._room_index:
                    option.add_class("selected")
                else:
                    option.remove_class("selected")
            except Exception:
                pass

        # Code toggle
        try:
            toggle = self.query_one("#opt-code-toggle", CodeToggleOption)
            if self._active_row == ROW_CODE:
                toggle.add_class("selected")
            else:
                toggle.remove_class("selected")
        except Exception:
            pass

        # Extras row
        extra_ids = ["#opt-volume", "#opt-clear-rooms"]
        for i, eid in enumerate(extra_ids):
            try:
                widget = self.query_one(eid, ExtraOption)
                if self._active_row == ROW_EXTRAS and i == self._extra_index:
                    widget.add_class("selected")
                else:
                    widget.remove_class("selected")
            except Exception:
                pass

    def _select_room(self, index: int) -> None:
        if 0 <= index < len(ROOM_OPTIONS):
            _, _, _, result = ROOM_OPTIONS[index]
            self.post_message(self.RoomSelected(result))

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard navigation from evdev."""
        if isinstance(action, NavigationAction):
            visible = self._visible_rows
            if action.direction == 'left':
                if self._active_row == ROW_ROOMS:
                    self._room_index = max(0, self._room_index - 1)
                elif self._active_row == ROW_EXTRAS:
                    self._extra_index = max(0, self._extra_index - 1)
                # ROW_CODE: single item, no left/right
                self._update_selection()
            elif action.direction == 'right':
                if self._active_row == ROW_ROOMS:
                    self._room_index = min(len(ROOM_OPTIONS) - 1, self._room_index + 1)
                elif self._active_row == ROW_EXTRAS:
                    self._extra_index = min(NUM_EXTRA_COLS - 1, self._extra_index + 1)
                self._update_selection()
            elif action.direction == 'up':
                cur = visible.index(self._active_row) if self._active_row in visible else 0
                if cur > 0:
                    self._active_row = visible[cur - 1]
                    self._update_selection()
            elif action.direction == 'down':
                cur = visible.index(self._active_row) if self._active_row in visible else 0
                if cur < len(visible) - 1:
                    self._active_row = visible[cur + 1]
                    self._update_selection()
            return

        if isinstance(action, CharacterAction) and not action.is_repeat:
            if action.char in NUMBER_KEY_ROOMS:
                self._select_room(NUMBER_KEY_ROOMS[action.char])
            elif action.char.lower() == 'v':
                # Jump to volume and activate
                self._active_row = ROW_EXTRAS
                self._extra_index = COL_VOLUME
                self._update_selection()
                self._open_volume()
            elif action.char.lower() == 'c':
                # Jump to clear rooms and activate
                self._active_row = ROW_EXTRAS
                self._extra_index = COL_CLEAR
                self._update_selection()
                self._confirm_clear_rooms()
            else:
                # Any other character key: dismiss picker
                self.dismiss(None)
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                if self._active_row == ROW_ROOMS:
                    self._select_room(self._room_index)
                elif self._active_row == ROW_CODE:
                    self.dismiss({"toggle_code_space": True})
                elif self._active_row == ROW_EXTRAS:
                    if self._extra_index == COL_VOLUME:
                        self._open_volume()
                    elif self._extra_index == COL_CLEAR:
                        self._confirm_clear_rooms()
            elif action.action == 'escape':
                self.dismiss(None)
            elif action.action == 'space':
                # Space toggles code space from any row (if available)
                if self._code_space_available:
                    self.dismiss({"toggle_code_space": True})
            elif action.action == 'volume_mute':
                self.app.action_volume_mute()
            elif action.action == 'volume_down':
                self.app.action_volume_down()
            elif action.action == 'volume_up':
                self.app.action_volume_up()

    def _confirm_clear_rooms(self) -> None:
        """Show confirmation before clearing all rooms."""
        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self.dismiss({"start_fresh": True})

        self.app.push_screen(ConfirmFreshScreen(), on_confirm)

    def _open_volume(self) -> None:
        """Open the volume modal."""
        self.app.push_screen(VolumeModal())

    async def _on_key(self, event) -> None:
        """Suppress terminal key events. All input comes via evdev."""
        event.stop()
        event.prevent_default()


class VolumeModal(ModalScreen):
    """Simple volume adjustment modal.

    Shows current volume level. Up/down arrows adjust. Enter/Esc to close.
    """

    CSS = """
    VolumeModal {
        align: center middle;
    }

    #volume-dialog {
        width: 50;
        height: auto;
        padding: 2 3;
        background: $surface;
        border: heavy $primary;
    }

    #volume-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #volume-display {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    #volume-hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        with Container(id="volume-dialog"):
            yield Static(caps("Volume"), id="volume-title")
            yield Static("", id="volume-display")
            yield Static(caps("\u25c0 \u25b6 \u25b2 \u25bc  to adjust       Enter to close"), id="volume-hint")

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        level = self.app.volume_level
        from .constants import (
            ICON_VOLUME_OFF, ICON_VOLUME_LOW, ICON_VOLUME_MED, ICON_VOLUME_HIGH,
        )
        if level == 0:
            icon = ICON_VOLUME_OFF
            bars = "\u2591" * 8
        elif level <= 25:
            icon = ICON_VOLUME_LOW
            bars = "\u2588\u2588\u2591\u2591\u2591\u2591\u2591\u2591"
        elif level <= 50:
            icon = ICON_VOLUME_MED
            bars = "\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591"
        elif level <= 75:
            icon = ICON_VOLUME_HIGH
            bars = "\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591"
        else:
            icon = ICON_VOLUME_HIGH
            bars = "\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588"

        try:
            display = self.query_one("#volume-display", Static)
            display.update(f"{icon}  {bars}  {level}%")
        except Exception:
            pass

    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction in ('up', 'right'):
                self.app.action_volume_up()
                self._update_display()
            elif action.direction in ('down', 'left'):
                self.app.action_volume_down()
                self._update_display()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action in ('enter', 'escape', 'tab'):
                self.dismiss(None)
            elif action.action == 'volume_mute':
                self.app.action_volume_mute()
                self._update_display()
            elif action.action == 'volume_down':
                self.app.action_volume_down()
                self._update_display()
            elif action.action == 'volume_up':
                self.app.action_volume_up()
                self._update_display()
            return

        if isinstance(action, CharacterAction):
            # Any character key dismisses
            self.dismiss(None)

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()
