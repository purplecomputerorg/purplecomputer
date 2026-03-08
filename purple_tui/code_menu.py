"""
Command Menu: Tab-activated modal menu for Command mode (F4).

Flat 7-item menu:
  Pause, Stroke, Repeat, Mode... (insert items)
  ---------
  Load..., Save..., Clear (program items)

Navigation via arrow keys, Enter to select, Tab/Esc to close.
Follows the ModePickerScreen pattern for evdev-based input.
"""

from textual.screen import ModalScreen
from textual.containers import Container
from textual.widgets import Static
from textual.app import ComposeResult
from textual import events

from .keyboard import NavigationAction, ControlAction, CharacterAction
from .program import (
    ROOM_ORDER,
    ROOMS,
    ROOM_ICONS,
    slot_occupied,
)


# Menu item definitions: (id, label, selectable)
MENU_ITEMS = [
    ("watch_me", "  Watch me!", True),
    ("insert_pause", "  Pause \u23f8", True),
    ("insert_stroke", "  Stroke \u25b6", True),
    ("insert_repeat", "  Repeat x2", True),
    ("insert_room_switch", "  Room...", True),
    ("separator", "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", False),
    ("load", "  Load...", True),
    ("save", "  Save...", True),
    ("clear", "  Clear", True),
]

# Indices of selectable items for navigation
_SELECTABLE_INDICES = [i for i, (_, _, sel) in enumerate(MENU_ITEMS) if sel]


class CodeMenuScreen(ModalScreen):
    """Modal menu for Command mode, opened with Tab.

    Returns a result dict on selection, or None if cancelled.
    """

    CSS = """
    CodeMenuScreen {
        align: center middle;
    }

    #code-menu-dialog {
        width: 32;
        height: auto;
        max-height: 18;
        padding: 1 2;
        background: $surface;
        border: heavy $primary;
    }

    #code-menu-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .menu-item {
        width: 100%;
        height: 1;
        padding: 0 1;
    }

    .menu-separator {
        width: 100%;
        height: 1;
        color: $text-muted;
        text-align: center;
    }

    .menu-item.selected {
        background: $primary;
        color: $background;
        text-style: bold;
    }

    #code-menu-hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sel_pos = 0  # position within _SELECTABLE_INDICES
        self._sub_view: str | None = None  # "target_picker" or "slot_picker"
        self._sub_action: str = ""
        self._sub_selected: int = 0

    def compose(self) -> ComposeResult:
        with Container(id="code-menu-dialog"):
            yield Static("Command Menu", id="code-menu-title")

            for i, (item_id, label, selectable) in enumerate(MENU_ITEMS):
                if not selectable:
                    yield Static(label, classes="menu-separator")
                else:
                    yield Static(label, id=f"menu-{item_id}", classes="menu-item")

            yield Static("\u2191\u2193 select  Enter confirm  Tab/Esc close", id="code-menu-hint")

    def on_mount(self) -> None:
        self._update_selection()

    def _update_selection(self) -> None:
        selected_idx = _SELECTABLE_INDICES[self._sel_pos]
        for i, (item_id, _, selectable) in enumerate(MENU_ITEMS):
            if not selectable:
                continue
            try:
                item = self.query_one(f"#menu-{item_id}", Static)
                if i == selected_idx:
                    item.add_class("selected")
                else:
                    item.remove_class("selected")
            except Exception:
                pass

    async def handle_keyboard_action(self, action) -> None:
        if self._sub_view in ("room_picker", "watch_me_picker"):
            await self._handle_room_picker(action)
            return
        if self._sub_view == "slot_picker":
            await self._handle_slot_picker(action)
            return

        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._sel_pos = max(0, self._sel_pos - 1)
                self._update_selection()
            elif action.direction == 'down':
                self._sel_pos = min(len(_SELECTABLE_INDICES) - 1, self._sel_pos + 1)
                self._update_selection()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                self._activate_item()
            elif action.action in ('tab', 'escape'):
                self.dismiss(None)
            return

    def _activate_item(self) -> None:
        menu_idx = _SELECTABLE_INDICES[self._sel_pos]
        item_id = MENU_ITEMS[menu_idx][0]

        if item_id == "watch_me":
            self._sub_view = "watch_me_picker"
            self._sub_selected = 0
            self._show_sub_picker_rooms(title="Watch me in...")

        elif item_id == "insert_room_switch":
            self._sub_view = "room_picker"
            self._sub_selected = 0
            self._show_sub_picker_rooms()

        elif item_id == "insert_repeat":
            self.dismiss({"action": "insert_repeat"})

        elif item_id == "insert_pause":
            self.dismiss({"action": "insert_pause"})

        elif item_id == "insert_stroke":
            self.dismiss({"action": "insert_stroke"})

        elif item_id == "load":
            self._sub_view = "slot_picker"
            self._sub_action = "load"
            self._sub_selected = 0
            self._show_sub_picker_slots()

        elif item_id == "save":
            self._sub_view = "slot_picker"
            self._sub_action = "save"
            self._sub_selected = 0
            self._show_sub_picker_slots()

        elif item_id == "clear":
            self.dismiss({"action": "clear"})

    # ── Room sub-picker ──────────────────────────────────────────────

    def _show_sub_picker_rooms(self, title: str = "Pick a room") -> None:
        try:
            dialog = self.query_one("#code-menu-dialog", Container)
            title_widget = self.query_one("#code-menu-title", Static)
            title_widget.update(title)

            for child in dialog.children:
                if child.has_class("menu-item") or child.has_class("menu-separator"):
                    child.display = False

            hint = self.query_one("#code-menu-hint", Static)
            hint.update("\u2191\u2193 select  Enter confirm  Esc back")

            for i, room in enumerate(ROOM_ORDER):
                icon = ROOM_ICONS[room]
                label = ROOMS[room]["label"]
                item = Static(f"  {icon}  {label}", id=f"room-{i}", classes="menu-item")
                dialog.mount(item, before=hint)

            self._update_room_selection()
        except Exception:
            pass

    def _update_room_selection(self) -> None:
        for i in range(len(ROOM_ORDER)):
            try:
                item = self.query_one(f"#room-{i}", Static)
                if i == self._sub_selected:
                    item.add_class("selected")
                else:
                    item.remove_class("selected")
            except Exception:
                pass

    async def _handle_room_picker(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._sub_selected = max(0, self._sub_selected - 1)
                self._update_room_selection()
            elif action.direction == 'down':
                self._sub_selected = min(len(ROOM_ORDER) - 1, self._sub_selected + 1)
                self._update_room_selection()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                room = ROOM_ORDER[self._sub_selected]
                if self._sub_view == "watch_me_picker":
                    self.dismiss({"action": "watch_me", "room": room})
                else:
                    target = ROOMS[room]["default"]
                    self.dismiss({"action": "insert_mode_switch", "target": target})
            elif action.action in ('escape', 'tab'):
                self._exit_sub_view()
            return

    # ── Slot sub-picker ───────────────────────────────────────────────

    def _show_sub_picker_slots(self) -> None:
        try:
            dialog = self.query_one("#code-menu-dialog", Container)
            title = self.query_one("#code-menu-title", Static)
            action_label = "Load from" if self._sub_action == "load" else "Save to"
            title.update(f"{action_label} slot")

            for child in dialog.children:
                if child.has_class("menu-item") or child.has_class("menu-separator"):
                    child.display = False

            hint = self.query_one("#code-menu-hint", Static)
            hint.update("\u2191\u2193 select  Enter confirm  Esc back")

            for slot in range(1, 10):
                filled = slot_occupied(slot)
                marker = "\u25a0" if filled else "\u25a1"
                label = f"  {slot} {marker}"
                item = Static(label, id=f"slot-{slot}", classes="menu-item")
                dialog.mount(item, before=hint)

            self._update_slot_selection()
        except Exception:
            pass

    def _update_slot_selection(self) -> None:
        for slot in range(1, 10):
            try:
                item = self.query_one(f"#slot-{slot}", Static)
                if slot - 1 == self._sub_selected:
                    item.add_class("selected")
                else:
                    item.remove_class("selected")
            except Exception:
                pass

    async def _handle_slot_picker(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._sub_selected = max(0, self._sub_selected - 1)
                self._update_slot_selection()
            elif action.direction == 'down':
                self._sub_selected = min(8, self._sub_selected + 1)
                self._update_slot_selection()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                slot = self._sub_selected + 1
                self.dismiss({"action": self._sub_action, "slot": slot})
            elif action.action in ('escape', 'tab'):
                self._exit_sub_view()
            return

        if isinstance(action, CharacterAction) and not action.is_repeat:
            if action.char.isdigit() and action.char != '0':
                slot = int(action.char)
                self.dismiss({"action": self._sub_action, "slot": slot})
            return

    def _exit_sub_view(self) -> None:
        self._sub_view = None
        self._sub_selected = 0

        try:
            dialog = self.query_one("#code-menu-dialog", Container)
            title = self.query_one("#code-menu-title", Static)
            title.update("Command Menu")

            for child in list(dialog.children):
                child_id = child.id or ""
                if child_id.startswith("room-") or child_id.startswith("slot-"):
                    child.remove()

            for child in dialog.children:
                if child.has_class("menu-item") or child.has_class("menu-separator"):
                    child.display = True

            hint = self.query_one("#code-menu-hint", Static)
            hint.update("\u2191\u2193 select  Enter confirm  Tab/Esc close")
        except Exception:
            pass

        self._update_selection()

    async def _on_key(self, event) -> None:
        event.stop()
        event.prevent_default()
