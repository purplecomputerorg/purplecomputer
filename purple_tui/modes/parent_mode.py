"""
Parent Mode - Admin menu for parents/guardians

Accessed by holding Escape for ~1 second.
Provides access to system settings, bash shell, etc.

Navigation is handled explicitly via on_key (no focus system).
Up/Down arrows move selection, Enter activates, Escape exits.
"""

from textual.widgets import Static
from textual.containers import Container, Vertical, Center
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual import events
import subprocess
import os
import sys
import termios
from pathlib import Path

from ..keyboard import NavigationAction, ControlAction


def _flush_terminal_input() -> None:
    """Flush any buffered terminal input to prevent stray characters."""
    try:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (termios.error, OSError):
        pass  # Not a TTY or other error, ignore


# Menu items: (id, label)
MENU_ITEMS = [
    ("menu-shell", "Open Terminal"),
    ("menu-keyboard", "Recalibrate Keyboard"),
    ("menu-exit", "Exit"),
]


class ParentMenuItem(Static):
    """A menu item that shows selected state via styling"""

    DEFAULT_CSS = """
    ParentMenuItem {
        width: 100%;
        height: 1;
        text-align: left;
        padding: 0 2;
        margin: 0;
    }

    ParentMenuItem.selected {
        background: $primary;
        color: $text;
        text-style: bold;
    }
    """

    def __init__(self, label: str, item_id: str, **kwargs):
        super().__init__(label, id=item_id, **kwargs)
        self.label = label


class ParentMenu(ModalScreen):
    """
    Parent Mode - Admin menu for parents/guardians.

    Provides access to:
    - Bash shell (exit to return to Purple)
    - Future: Settings, content packs, updates, etc.

    Navigation: Up/Down to move, Enter to select, Escape to exit.
    No focus system used (keyboard-only design).
    """

    DEFAULT_CSS = """
    ParentMenu {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #parent-dialog {
        width: 36;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $primary;
    }

    #parent-title {
        width: 100%;
        height: 1;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #parent-items {
        width: 100%;
        height: auto;
    }

    #parent-hint {
        width: 100%;
        height: 1;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_index = 0
        # Escape is always "tainted" since user held it to open this menu
        # Other keys could be added here if needed
        self._ignore_until_released = {'escape'}

    def compose(self) -> ComposeResult:
        with Vertical(id="parent-dialog"):
            yield Static("Parent Menu", id="parent-title")
            with Vertical(id="parent-items"):
                for item_id, label in MENU_ITEMS:
                    yield ParentMenuItem(label, item_id)
            yield Static("↑↓ Enter Esc", id="parent-hint")

    def on_mount(self) -> None:
        """Highlight the first menu item"""
        self._update_selection()

    def _update_selection(self) -> None:
        """Update visual selection state"""
        for i, (item_id, _) in enumerate(MENU_ITEMS):
            item = self.query_one(f"#{item_id}", ParentMenuItem)
            if i == self._selected_index:
                item.add_class("selected")
            else:
                item.remove_class("selected")

    def on_key(self, event: events.Key) -> None:
        """Suppress terminal key events - we use evdev exclusively."""
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard actions from evdev."""
        # Navigation always works immediately
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._selected_index = (self._selected_index - 1) % len(MENU_ITEMS)
                self._update_selection()
            elif action.direction == 'down':
                self._selected_index = (self._selected_index + 1) % len(MENU_ITEMS)
                self._update_selection()
            return

        if isinstance(action, ControlAction):
            key = action.action

            # Track key releases to clear "tainted" keys
            if not action.is_down and key in self._ignore_until_released:
                self._ignore_until_released.discard(key)
                return

            # Ignore tainted keys until released
            if key in self._ignore_until_released:
                return

            # Handle key presses
            if action.is_down:
                if key == 'enter':
                    self._activate_selected()
                elif key == 'escape':
                    self.dismiss()
            return

    def _activate_selected(self) -> None:
        """Activate the currently selected menu item"""
        item_id = MENU_ITEMS[self._selected_index][0]
        if item_id == "menu-shell":
            self._open_shell()
        elif item_id == "menu-keyboard":
            self._recalibrate_keyboard()
        elif item_id == "menu-exit":
            self.dismiss()

    def _open_shell(self) -> None:
        """Open a bash shell, suspending the TUI"""
        # Dismiss the modal first
        self.dismiss()

        # Schedule the shell to open after the modal is closed
        self.app.call_later(self._run_shell)

    def _run_shell(self) -> None:
        """Actually run the shell - called after modal dismissed"""
        # Suspend the Textual app and release evdev grab for terminal input
        with self.app.suspend_with_terminal_input():
            # Reset terminal to sane state (ensures echo is on, etc.)
            os.system('stty sane')
            # Clear screen and show message
            os.system('clear')
            print("=" * 60)
            print("Purple Computer - Terminal Mode")
            print("=" * 60)
            print()
            print("You are now in a bash shell.")
            print("Type 'exit' to return to Purple Computer.")
            print()
            print("-" * 60)
            print()
            sys.stdout.flush()

            # Get the user's default shell or fall back to bash
            shell = os.environ.get('SHELL', '/bin/bash')

            # Run the shell interactively
            subprocess.run([shell, '-i'])

            # When shell exits, clean up before resuming
            print()
            print("Returning to Purple Computer...")
            sys.stdout.flush()

            # Flush any buffered input to prevent stray characters
            _flush_terminal_input()
            os.system('stty sane')

    def _recalibrate_keyboard(self) -> None:
        """Run keyboard calibration"""
        self.dismiss()
        self.app.call_later(self._run_keyboard_calibration)

    def _run_keyboard_calibration(self) -> None:
        """Actually run calibration - called after modal dismissed"""
        # Find the keyboard_normalizer.py script
        this_dir = Path(__file__).parent
        candidates = [
            this_dir.parent.parent / "keyboard_normalizer.py",  # Project root
            Path("/opt/purple/keyboard_normalizer.py"),  # Installed location
        ]

        script_path = None
        for path in candidates:
            if path.exists():
                script_path = path
                break

        if not script_path:
            self.app.notify("Could not find keyboard calibration script", severity="error")
            return

        with self.app.suspend_with_terminal_input():
            os.system('stty sane')
            os.system('clear')

            # Run the calibration
            result = subprocess.run([sys.executable, str(script_path), "--calibrate"])

            if result.returncode == 0:
                print()
                print("Keyboard calibration complete!")
                print("Press Enter to return to Purple Computer...")
            else:
                print()
                print("Keyboard calibration failed or was cancelled.")
                print("Press Enter to return to Purple Computer...")

            input()  # Wait for user to press Enter

            # Flush any buffered input to prevent stray characters
            _flush_terminal_input()
            os.system('stty sane')
