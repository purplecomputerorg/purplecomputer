"""
Room Picker Screen: A kid-friendly modal for switching rooms.

Shows 3 rooms (Play, Music, Art) at the top, then Volume + Clear Room
side by side. Arrow keys navigate, number keys 1-3 for direct room
selection, V opens volume, C clears a room, Enter selects, Escape cancels.
Any unrecognized key dismisses gracefully.
"""

from .modal import PurpleModal, PickerModal
from textual.containers import Container, Horizontal
from textual.widgets import Static
from textual.app import ComposeResult
from textual.message import Message

from .constants import (
    ICON_CHAT, ICON_MUSIC, ICON_PALETTE, ICON_VOLUME_HIGH, ICON_VOLUME_OFF,
    ICON_VOLUME_LOW, ICON_VOLUME_MED, ICON_BROOM, ICON_CODE,
)
from .keyboard import NavigationAction, ControlAction, CharacterAction
from .hints import arrow_keys_text


# Room options: (id, icon, label, result)
ROOM_OPTIONS = [
    ("play", ICON_CHAT, "Play", {"room": "play"}),
    ("music", ICON_MUSIC, "Music", {"room": "music"}),
    ("art", ICON_PALETTE, "Art", {"room": "art"}),
]

ROOM_DISPLAY_NAMES = {opt_id: label for opt_id, _, label, _ in ROOM_OPTIONS}

# Map number keys to room indices
NUMBER_KEY_ROOMS = {'1': 0, '2': 1, '3': 2}

# Navigation rows
ROW_ROOMS = 0
ROW_EXTRAS = 1
ROW_CODE = 2

# Extras columns: 0 = volume, 1 = clear room
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

    def render(self) -> str:
        enter_hint = "\nor Enter" if self.has_class("selected") else ""
        return f"\n{self.icon}  {self.label}  {self.icon}\n\nPress {self.number}{enter_hint}\n"


class ExtraOption(Static):
    """Half-width action button for the extras row (volume, clear room)."""

    DEFAULT_CSS = """
    ExtraOption {
        width: 25;
        height: 6;
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

    ExtraOption.disabled {
        color: $text-muted;
        border: round $surface-darken-1;
    }

    ExtraOption.disabled.selected {
        background: $surface-lighten-1;
        color: $text-muted;
        border: heavy $accent-darken-2;
    }
    """

    def __init__(self, icon: str, label: str, key_hint: str, disabled: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._icon = icon
        self._label = label
        self._key_hint = key_hint
        if disabled:
            self.add_class("disabled")

    def render(self) -> str:
        if self.has_class("disabled"):
            return f"\n{self._icon}  {self._label}  {self._icon}\n"
        hint = f"Press {self._key_hint} or Enter" if self.has_class("selected") else f"Press {self._key_hint}"
        return f"\n{self._icon}  {self._label}  {self._icon}\n{hint}"


class ConfirmFreshScreen(PickerModal):
    """Clear-room chooser: go back (default, on top), this room, or all rooms.

    Dismisses with the id of the room to clear ("play"/"music"/"art"), "all",
    or None to cancel. Go Back is on top and pre-selected so a stray Enter
    never wipes a kid's work, while the likely action is one press away.
    """

    TITLE = "Clear a Room"
    DESCRIPTION = "Pick what to clear."

    def __init__(self, current_room: str = "play", **kwargs):
        room_name = ROOM_DISPLAY_NAMES.get(current_room, "This")
        self.OPTIONS = [
            (None, "Go Back"),
            (current_room, f"Clear {room_name} Room"),
            ("all", "Clear All Rooms"),
        ]
        super().__init__(**kwargs)


class RoomPickerScreen(PurpleModal):
    """
    Modal screen for selecting rooms with arrow key navigation.

    Layout (2 navigable rows):
      [1 Play]  [2 Music]  [3 Art]          <- room row
      [Volume  V]  [Clear Room  C]          <- extras row (50/50)
    """

    CSS = """
    #modal-dialog {
        width: 100;
        padding: 2 3;
    }

    #picker-options {
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

    #picker-code-row {
        width: 100%;
        height: auto;
        align: center middle;
        margin-bottom: 1;
    }

    #opt-code-toggle {
        width: 52;
    }

    #picker-arrows {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    #picker-arrow-hint {
        width: auto;
        height: auto;
        color: $text-muted;
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

    def __init__(self, current_room: str = "play", code_panel_open: bool = False, code_panel_enabled: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._current_room = current_room
        self._code_panel_open = code_panel_open
        self._code_panel_enabled = code_panel_enabled
        self._show_code_row = current_room in ("music", "art") and (code_panel_open or code_panel_enabled)
        # Always start on the room row, highlighting the current room
        self._active_row = ROW_ROOMS
        self._room_index = self._get_initial_room_index()
        self._extra_index = COL_VOLUME

    def _get_initial_room_index(self) -> int:
        for i, (opt_id, _, _, _) in enumerate(ROOM_OPTIONS):
            if opt_id == self._current_room:
                return i
        return 0

    def compose(self) -> ComposeResult:
        with Container(id="modal-dialog"):
            yield Static("Pick a Room", id="modal-title")

            with Horizontal(id="picker-options"):
                for i, (opt_id, icon, label, _) in enumerate(ROOM_OPTIONS):
                    yield RoomOption(opt_id, icon, label, i + 1, id=f"opt-{opt_id}")

            with Horizontal(id="picker-extras"):
                if getattr(self.app, "volume_locked", False):
                    icon, label = self._locked_volume_badge()
                    yield ExtraOption(icon, label, "", disabled=True, id="opt-volume")
                else:
                    yield ExtraOption(ICON_VOLUME_HIGH, "Volume", "V", id="opt-volume")
                yield ExtraOption(ICON_BROOM, "Clear Room", "C", id="opt-clear-rooms")

            if self._show_code_row:
                with Horizontal(id="picker-code-row"):
                    if self._code_panel_open:
                        yield ExtraOption(ICON_CODE, "Close Code", "Space", id="opt-code-toggle")
                    else:
                        yield ExtraOption(ICON_CODE, "Open Code", "Space", id="opt-code-toggle")

            yield Static("Enter pick   Hold Esc for grown-ups", id="modal-hint")
            with Container(id="picker-arrows"):
                yield Static(arrow_keys_text(), id="picker-arrow-hint")

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

        # Code row (present when code panel is open or enabled in music/art)
        if self._show_code_row:
            try:
                code_opt = self.query_one("#opt-code-toggle", ExtraOption)
                if self._active_row == ROW_CODE:
                    code_opt.add_class("selected")
                else:
                    code_opt.remove_class("selected")
            except Exception:
                pass

    def _select_room(self, index: int) -> None:
        if 0 <= index < len(ROOM_OPTIONS):
            _, _, _, result = ROOM_OPTIONS[index]
            self.post_message(self.RoomSelected(result))

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard navigation from evdev."""
        if isinstance(action, NavigationAction):
            if action.direction == 'left':
                if self._active_row == ROW_ROOMS:
                    self._room_index = max(0, self._room_index - 1)
                elif self._active_row == ROW_EXTRAS:
                    self._extra_index = max(0, self._extra_index - 1)
                self._update_selection()
            elif action.direction == 'right':
                if self._active_row == ROW_ROOMS:
                    self._room_index = min(len(ROOM_OPTIONS) - 1, self._room_index + 1)
                elif self._active_row == ROW_EXTRAS:
                    self._extra_index = min(NUM_EXTRA_COLS - 1, self._extra_index + 1)
                self._update_selection()
            elif action.direction == 'up':
                if self._active_row == ROW_CODE:
                    self._active_row = ROW_EXTRAS
                    self._update_selection()
                elif self._active_row == ROW_EXTRAS:
                    self._active_row = ROW_ROOMS
                    # Map extras column back to nearest room:
                    # extras 0 -> room 0, extras 1 -> room 2
                    self._room_index = 0 if self._extra_index == 0 else 2
                    self._update_selection()
            elif action.direction == 'down':
                if self._active_row == ROW_ROOMS:
                    self._active_row = ROW_EXTRAS
                    # Map room column to closest extras column:
                    # rooms 0,1 (left/center) -> extras 0, room 2 (right) -> extras 1
                    self._extra_index = 0 if self._room_index <= 1 else 1
                    self._update_selection()
                elif self._active_row == ROW_EXTRAS and self._show_code_row:
                    self._active_row = ROW_CODE
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
                # Jump to clear room and activate
                self._active_row = ROW_EXTRAS
                self._extra_index = COL_CLEAR
                self._update_selection()
                self._confirm_clear_rooms()
            else:
                # Any other character key: dismiss picker
                self.dismiss(None)
            return

        # Escape dismisses on release, not press. The app runs a 1s long-hold
        # timer on every escape press; if we dismissed on press the picker
        # would close instantly, leaving the long-hold timer to open the
        # parent menu 1s later (visible flicker / two-step transition).
        # Releasing-side dismiss means a tap closes the picker, while a hold
        # leaves the picker up until the timer fires and dismisses it itself
        # in _check_escape_hold().
        if isinstance(action, ControlAction) and action.action == 'escape' and not action.is_down:
            self.dismiss(None)
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                if self._active_row == ROW_ROOMS:
                    self._select_room(self._room_index)
                elif self._active_row == ROW_EXTRAS:
                    if self._extra_index == COL_VOLUME:
                        self._open_volume()
                    elif self._extra_index == COL_CLEAR:
                        self._confirm_clear_rooms()
                elif self._active_row == ROW_CODE:
                    if self._code_panel_open:
                        self.dismiss({"close_code": True})
                    else:
                        self.dismiss({"open_code": True})
            elif action.action == 'space' and self._show_code_row:
                if self._code_panel_open:
                    self.dismiss({"close_code": True})
                else:
                    self.dismiss({"open_code": True})
            elif action.action == 'volume_mute':
                self.app.action_volume_mute()
            elif action.action == 'volume_down':
                self.app.action_volume_down()
            elif action.action == 'volume_up':
                self.app.action_volume_up()

    def _confirm_clear_rooms(self) -> None:
        """Let the parent choose to clear just this room or all rooms."""
        def on_confirm(result: str | None) -> None:
            if result == "all":
                self.dismiss({"start_fresh": True})
            elif result:
                self.dismiss({"clear_room": result})

        self.app.push_screen(ConfirmFreshScreen(self._current_room), on_confirm)

    def _locked_volume_badge(self) -> tuple[str, str]:
        """Pick the icon + label for the Volume slot when it's locked."""
        lock = getattr(self.app, "_volume_lock", None)
        if lock == 0:
            return ICON_VOLUME_OFF, "Silent"
        if lock is not None:
            if lock <= 35:
                icon = ICON_VOLUME_LOW
            elif lock <= 60:
                icon = ICON_VOLUME_MED
            else:
                icon = ICON_VOLUME_HIGH
            return icon, "Locked"
        return ICON_VOLUME_OFF, "No Sound"

    def _open_volume(self) -> None:
        """Open the kid's volume modal (skip when audio is off or a parent lock is on)."""
        if getattr(self.app, "volume_locked", False):
            return
        self.app.push_screen(VolumeModal())

    async def _on_key(self, event) -> None:
        """Suppress terminal key events. All input comes via evdev."""
        event.stop()
        event.prevent_default()


class VolumeModal(PurpleModal):
    """Simple volume adjustment modal.

    Shows current volume level. Up/down arrows adjust. Enter/Esc to close.
    """

    CSS = """
    #modal-dialog {
        width: 50;
        padding: 2 3;
    }

    #volume-display {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    #modal-hint {
        margin-top: 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="modal-dialog"):
            yield Static("Volume", id="modal-title")
            yield Static("", id="volume-display")
            yield Static("\u25c0 \u25b6 \u25b2 \u25bc adjust   Enter close", id="modal-hint")

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        level = self.app.volume_level
        from .constants import (
            ICON_VOLUME_OFF, ICON_VOLUME_LOW, ICON_VOLUME_MED, ICON_VOLUME_HIGH,
        )
        if level == 0:
            icon = ICON_VOLUME_OFF
            label = "Sound Off"
            bars = "░░░░░░░░░░"
        elif level <= 15:
            icon = ICON_VOLUME_LOW
            label = "Whisper"
            bars = "██░░░░░░░░"
        elif level <= 35:
            icon = ICON_VOLUME_LOW
            label = "Quiet"
            bars = "████░░░░░░"
        elif level <= 60:
            icon = ICON_VOLUME_MED
            label = "Medium"
            bars = "██████░░░░"
        elif level <= 85:
            icon = ICON_VOLUME_HIGH
            label = "Loud"
            bars = "████████░░"
        else:
            icon = ICON_VOLUME_HIGH
            label = "Full"
            bars = "██████████"

        try:
            display = self.query_one("#volume-display", Static)
            display.update(f"{icon}  {bars}  {label}")
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
