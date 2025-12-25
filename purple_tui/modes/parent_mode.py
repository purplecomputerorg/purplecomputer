"""
Parent Mode - Admin menu for parents/guardians

Accessed by holding Escape for ~1 second.
Provides access to system settings, bash shell, etc.
"""

from textual.widgets import Static, Button
from textual.containers import Container, Vertical, Center, Middle
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.binding import Binding
import subprocess
import os
import sys
from pathlib import Path


class ParentMenuItem(Button):
    """A menu item button with consistent styling"""

    DEFAULT_CSS = """
    ParentMenuItem {
        width: 40;
        height: 3;
        margin: 1 0;
    }
    """


class ParentMenu(ModalScreen):
    """
    Parent Mode - Admin menu for parents/guardians.

    Provides access to:
    - Bash shell (exit to return to Purple)
    - Future: Settings, content packs, updates, etc.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Back to Purple"),
    ]

    DEFAULT_CSS = """
    ParentMenu {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #parent-dialog {
        width: 60;
        height: auto;
        padding: 2 4;
        background: $surface;
        border: heavy $primary;
    }

    #parent-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 2;
    }

    #parent-items {
        width: 100%;
        align: center middle;
    }

    #parent-hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="parent-dialog"):
            yield Static("Parent Menu", id="parent-title")
            with Center(id="parent-items"):
                with Vertical():
                    yield ParentMenuItem("Open Terminal", id="menu-shell")
                    yield ParentMenuItem("Recalibrate Keyboard", id="menu-keyboard")
            yield Static("Press Escape to return", id="parent-hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle menu item selection"""
        if event.button.id == "menu-shell":
            self._open_shell()
        elif event.button.id == "menu-keyboard":
            self._recalibrate_keyboard()

    def _open_shell(self) -> None:
        """Open a bash shell, suspending the TUI"""
        # Dismiss the modal first
        self.dismiss()

        # Schedule the shell to open after the modal is closed
        self.app.call_later(self._run_shell)

    def _run_shell(self) -> None:
        """Actually run the shell - called after modal dismissed"""
        # Suspend the Textual app to give control to the terminal
        with self.app.suspend():
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

            # When shell exits, the Textual app resumes automatically
            print()
            print("Returning to Purple Computer...")
            sys.stdout.flush()

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

        with self.app.suspend():
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
