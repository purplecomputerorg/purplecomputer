"""
Code Menu: Tab-activated modal menu for Code mode (F4).

Provides:
  Record: "Record in Play (music)", "Record in Play (letters)", etc.
  Insert: "Mode switch...", "Repeat ×2"
  Program: "Load...", "Save...", "Clear all blocks"

Navigation via arrow keys, Enter to select, Tab/Esc to close.
Follows the ModePickerScreen pattern for evdev-based input.
"""

from textual.screen import ModalScreen
from textual.containers import Container, Vertical
from textual.widgets import Static
from textual.app import ComposeResult
from textual import events

from .keyboard import NavigationAction, ControlAction, CharacterAction
from .program import (
    ALL_TARGETS,
    TARGET_ICONS,
    TARGET_LABELS,
    TARGET_COLORS,
    slot_occupied,
    NUM_PAUSE_LEVELS,
)


# Menu item definitions: (id, label, section)
# Section headers are rendered but not selectable
MENU_ITEMS = [
    # Record section
    ("record_play_music", f"{TARGET_ICONS['play.music']}  Record in Play (music)", "record"),
    ("record_play_letters", f"{TARGET_ICONS['play.letters']}  Record in Play (letters)", "record"),
    ("record_doodle_text", f"{TARGET_ICONS['doodle.text']}  Record in Doodle (text)", "record"),
    ("record_doodle_paint", f"{TARGET_ICONS['doodle.paint']}  Record in Doodle (paint)", "record"),
    ("record_explore", f"{TARGET_ICONS['explore']}  Record in Explore", "record"),
    # Insert section
    ("insert_mode_switch", "   Mode switch...", "insert"),
    ("insert_repeat", "   Repeat ×2", "insert"),
    # Adjust section
    ("timing_up", "   Longer pause ↑", "adjust"),
    ("timing_down", "   Shorter pause ↓", "adjust"),
    ("cycle_up", "   Cycle value ↑", "adjust"),
    # Program section
    ("load", "   Load...", "program"),
    ("save", "   Save...", "program"),
    ("clear", "   Clear all blocks", "program"),
]

# Target map for record items
RECORD_TARGETS = {
    "record_play_music": "play.music",
    "record_play_letters": "play.letters",
    "record_doodle_text": "doodle.text",
    "record_doodle_paint": "doodle.paint",
    "record_explore": "explore",
}


class CodeMenuScreen(ModalScreen):
    """Modal menu for Code mode, opened with Tab.

    Returns a result dict on selection:
      {"action": "record", "target": "play.music"}
      {"action": "insert_mode_switch"}
      {"action": "insert_repeat"}
      {"action": "load"}
      {"action": "save"}
      {"action": "clear"}
    Or None if cancelled.
    """

    CSS = """
    CodeMenuScreen {
        align: center middle;
    }

    #code-menu-dialog {
        width: 42;
        height: auto;
        max-height: 24;
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

    .menu-section-header {
        width: 100%;
        color: $text-muted;
        margin-top: 1;
    }

    .menu-item {
        width: 100%;
        height: 1;
        padding: 0 1;
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
        self._selected_index = 0
        self._sub_view: str | None = None  # "target_picker" or "slot_picker"
        self._sub_action: str = ""  # "load" or "save" (for slot picker)
        self._sub_selected: int = 0  # index in sub-view

    def compose(self) -> ComposeResult:
        with Container(id="code-menu-dialog"):
            yield Static("Code Menu", id="code-menu-title")

            # Section headers and items
            current_section = ""
            for i, (item_id, label, section) in enumerate(MENU_ITEMS):
                if section != current_section:
                    header_text = section.title()
                    yield Static(f"  {header_text}", classes="menu-section-header")
                    current_section = section
                yield Static(label, id=f"menu-{item_id}", classes="menu-item")

            yield Static("↑↓ select  Enter confirm  Tab/Esc close", id="code-menu-hint")

    def on_mount(self) -> None:
        self._update_selection()

    def _update_selection(self) -> None:
        """Highlight the selected item."""
        for i, (item_id, _, _) in enumerate(MENU_ITEMS):
            try:
                item = self.query_one(f"#menu-{item_id}", Static)
                if i == self._selected_index:
                    item.add_class("selected")
                else:
                    item.remove_class("selected")
            except Exception:
                pass

    async def handle_keyboard_action(self, action) -> None:
        """Handle evdev keyboard input."""
        if self._sub_view == "target_picker":
            await self._handle_target_picker(action)
            return
        if self._sub_view == "slot_picker":
            await self._handle_slot_picker(action)
            return

        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._selected_index = max(0, self._selected_index - 1)
                self._update_selection()
            elif action.direction == 'down':
                self._selected_index = min(len(MENU_ITEMS) - 1, self._selected_index + 1)
                self._update_selection()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                self._activate_item()
            elif action.action in ('tab', 'escape'):
                self.dismiss(None)
            return

    def _activate_item(self) -> None:
        """Handle Enter on the selected item."""
        item_id = MENU_ITEMS[self._selected_index][0]

        if item_id in RECORD_TARGETS:
            target = RECORD_TARGETS[item_id]
            self.dismiss({"action": "record", "target": target})

        elif item_id == "insert_mode_switch":
            # Show target sub-picker
            self._sub_view = "target_picker"
            self._sub_selected = 0
            self._show_sub_picker_targets()

        elif item_id == "insert_repeat":
            self.dismiss({"action": "insert_repeat"})

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

        elif item_id == "timing_up":
            self.dismiss({"action": "adjust", "direction": 1})

        elif item_id == "timing_down":
            self.dismiss({"action": "adjust", "direction": -1})

        elif item_id == "cycle_up":
            self.dismiss({"action": "adjust", "direction": 1})

        elif item_id == "clear":
            self.dismiss({"action": "clear"})

    # ── Target sub-picker ─────────────────────────────────────────────

    def _show_sub_picker_targets(self) -> None:
        """Replace menu content with target picker."""
        try:
            dialog = self.query_one("#code-menu-dialog", Container)
            title = self.query_one("#code-menu-title", Static)
            title.update("Pick target mode")

            # Hide menu items and section headers, show target list
            for child in dialog.children:
                if child.has_class("menu-item") or child.has_class("menu-section-header"):
                    child.display = False

            # Update hint
            hint = self.query_one("#code-menu-hint", Static)
            hint.update("↑↓ select  Enter confirm  Esc back")

            # Mount target items
            for i, target in enumerate(ALL_TARGETS):
                icon = TARGET_ICONS[target]
                label = TARGET_LABELS[target]
                item = Static(f"  {icon}  {label}", id=f"target-{i}", classes="menu-item")
                dialog.mount(item, before=hint)

            self._update_target_selection()
        except Exception:
            pass

    def _update_target_selection(self) -> None:
        """Highlight selected target."""
        for i in range(len(ALL_TARGETS)):
            try:
                item = self.query_one(f"#target-{i}", Static)
                if i == self._sub_selected:
                    item.add_class("selected")
                else:
                    item.remove_class("selected")
            except Exception:
                pass

    async def _handle_target_picker(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._sub_selected = max(0, self._sub_selected - 1)
                self._update_target_selection()
            elif action.direction == 'down':
                self._sub_selected = min(len(ALL_TARGETS) - 1, self._sub_selected + 1)
                self._update_target_selection()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                target = ALL_TARGETS[self._sub_selected]
                self.dismiss({"action": "insert_mode_switch", "target": target})
            elif action.action in ('escape', 'tab'):
                self._exit_sub_view()
            return

    # ── Slot sub-picker ───────────────────────────────────────────────

    def _show_sub_picker_slots(self) -> None:
        """Replace menu content with slot picker."""
        try:
            dialog = self.query_one("#code-menu-dialog", Container)
            title = self.query_one("#code-menu-title", Static)
            action_label = "Load from" if self._sub_action == "load" else "Save to"
            title.update(f"{action_label} slot")

            # Hide menu items and section headers
            for child in dialog.children:
                if child.has_class("menu-item") or child.has_class("menu-section-header"):
                    child.display = False

            # Update hint
            hint = self.query_one("#code-menu-hint", Static)
            hint.update("↑↓ select  Enter confirm  Esc back")

            # Mount slot items
            for slot in range(1, 10):
                filled = slot_occupied(slot)
                marker = "■" if filled else "□"
                label = f"  {slot} {marker}"
                item = Static(label, id=f"slot-{slot}", classes="menu-item")
                dialog.mount(item, before=hint)

            self._update_slot_selection()
        except Exception:
            pass

    def _update_slot_selection(self) -> None:
        """Highlight selected slot."""
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

        # Allow direct number key presses for quick slot selection
        if isinstance(action, CharacterAction) and not action.is_repeat:
            if action.char.isdigit() and action.char != '0':
                slot = int(action.char)
                self.dismiss({"action": self._sub_action, "slot": slot})
            return

    def _exit_sub_view(self) -> None:
        """Return from sub-picker to main menu."""
        self._sub_view = None
        self._sub_selected = 0

        try:
            dialog = self.query_one("#code-menu-dialog", Container)
            title = self.query_one("#code-menu-title", Static)
            title.update("Code Menu")

            # Remove sub-picker items
            for child in list(dialog.children):
                child_id = child.id or ""
                if child_id.startswith("target-") or child_id.startswith("slot-"):
                    child.remove()

            # Show main menu items and section headers
            for child in dialog.children:
                if child.has_class("menu-item") or child.has_class("menu-section-header"):
                    child.display = True

            # Reset hint
            hint = self.query_one("#code-menu-hint", Static)
            hint.update("↑↓ select  Enter confirm  Tab/Esc close")
        except Exception:
            pass

        self._update_selection()

    async def _on_key(self, event) -> None:
        """Suppress terminal key events. All input comes via evdev."""
        event.stop()
        event.prevent_default()
