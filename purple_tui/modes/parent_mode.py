"""
Parent Mode - Admin menu for parents/guardians

Accessed by holding Escape for ~1 second.
Provides access to system settings, bash shell, etc.

Navigation is handled explicitly via on_key (no focus system).
Up/Down arrows move selection, Enter activates, Escape exits.
"""

from textual.widgets import Static
from textual.containers import Container, Vertical, Horizontal, Center
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual import events
import subprocess
import os
import sys
import termios
import json
from pathlib import Path

from ..keyboard import NavigationAction, ControlAction


# =============================================================================
# Display Settings
# =============================================================================
#
# Uses xrandr for software-level display adjustment. This works consistently
# across all X11 systems regardless of laptop hardware (ThinkPad, Dell, HP,
# Surface, MacBook, etc.) because it adjusts gamma at the GPU level, not the
# actual backlight.
#
# Brightness: xrandr --brightness (multiplier, 0.5-1.0)
# Contrast: xrandr --gamma (gamma curve, 0.7-1.3 applied uniformly to R:G:B)

DISPLAY_SETTINGS_FILE = Path.home() / ".config" / "purple" / "display.json"

# Brightness: how bright the screen appears (software gamma multiplier)
BRIGHTNESS_MIN = 0.5
BRIGHTNESS_MAX = 1.0
BRIGHTNESS_STEP = 0.1
BRIGHTNESS_DEFAULT = 1.0

# Contrast: gamma curve adjustment (lower = washed out, higher = punchy)
# 1.0 is default, <1.0 increases perceived contrast, >1.0 decreases it
# We invert the scale for UX: user sees "higher = more contrast"
CONTRAST_MIN = 0.7
CONTRAST_MAX = 1.3
CONTRAST_STEP = 0.1
CONTRAST_DEFAULT = 1.0


def load_display_settings() -> dict:
    """Load display settings from disk."""
    try:
        if DISPLAY_SETTINGS_FILE.exists():
            data = json.loads(DISPLAY_SETTINGS_FILE.read_text())
            return {
                "brightness": float(data.get("brightness", BRIGHTNESS_DEFAULT)),
                "contrast": float(data.get("contrast", CONTRAST_DEFAULT)),
            }
    except Exception:
        pass
    return {"brightness": BRIGHTNESS_DEFAULT, "contrast": CONTRAST_DEFAULT}


def save_display_settings(settings: dict) -> bool:
    """Save display settings to disk."""
    try:
        DISPLAY_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        DISPLAY_SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
        return True
    except Exception:
        return False


def _get_xrandr_outputs() -> list:
    """Get list of connected display outputs. Returns empty list on failure."""
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return []

        outputs = []
        for line in result.stdout.splitlines():
            if " connected" in line:
                output_name = line.split()[0]
                outputs.append(output_name)
        return outputs
    except Exception:
        return []


def apply_display_settings(brightness: float, contrast: float) -> bool:
    """
    Apply brightness and contrast using xrandr.

    brightness: 0.5-1.0 (software gamma multiplier)
    contrast: 0.7-1.3 (gamma curve, inverted for UX)

    Returns True on success.
    """
    brightness = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, brightness))
    contrast = max(CONTRAST_MIN, min(CONTRAST_MAX, contrast))

    outputs = _get_xrandr_outputs()
    if not outputs:
        return False

    # Contrast uses gamma: we invert so higher value = more contrast
    # gamma < 1.0 = more contrast (darker darks, brighter brights)
    # gamma > 1.0 = less contrast (washed out)
    # User slider: 0.7 (low) to 1.3 (high contrast)
    # We map: user 0.7 -> gamma 1.3, user 1.3 -> gamma 0.7
    gamma = 2.0 - contrast  # Invert: 0.7->1.3, 1.0->1.0, 1.3->0.7
    gamma_str = f"{gamma:.1f}:{gamma:.1f}:{gamma:.1f}"

    try:
        for output in outputs:
            subprocess.run(
                ["xrandr", "--output", output,
                 "--brightness", str(brightness),
                 "--gamma", gamma_str],
                capture_output=True,
                timeout=5
            )
        return True
    except Exception:
        return False


def apply_saved_display_settings() -> None:
    """Apply saved display settings. Call on app startup."""
    settings = load_display_settings()
    apply_display_settings(settings["brightness"], settings["contrast"])


class DisplaySettingsScreen(ModalScreen):
    """
    Modal for adjusting display brightness and contrast.

    Simple +/- interface with visual bars for each setting.
    Parent-friendly design.
    """

    CSS = """
    DisplaySettingsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #display-dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $primary;
    }

    #display-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .setting-row {
        width: 100%;
        height: 1;
        margin: 1 0;
    }

    .setting-label {
        width: 12;
        text-align: right;
        padding-right: 1;
    }

    .setting-bar {
        width: 20;
    }

    .setting-value {
        width: 8;
        text-align: left;
        padding-left: 1;
    }

    #button-row {
        width: 100%;
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    #display-hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    # Focus areas: brightness, contrast, buttons
    FOCUS_AREAS = ["brightness", "contrast", "buttons"]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        settings = load_display_settings()
        self._brightness = settings["brightness"]
        self._contrast = settings["contrast"]
        self._original_brightness = self._brightness
        self._original_contrast = self._contrast
        self._selected_button = 0  # 0=Save, 1=Cancel
        self._focus_index = 0  # Index into FOCUS_AREAS

    @property
    def _focus_area(self) -> str:
        return self.FOCUS_AREAS[self._focus_index]

    def compose(self) -> ComposeResult:
        with Vertical(id="display-dialog"):
            yield Static("Display Settings", id="display-title")
            with Horizontal(classes="setting-row"):
                yield Static("Brightness:", classes="setting-label")
                yield Static("", id="brightness-bar", classes="setting-bar")
                yield Static("", id="brightness-value", classes="setting-value")
            with Horizontal(classes="setting-row"):
                yield Static("Contrast:", classes="setting-label")
                yield Static("", id="contrast-bar", classes="setting-bar")
                yield Static("", id="contrast-value", classes="setting-value")
            with Horizontal(id="button-row"):
                yield Static("  Save  ", id="btn-save")
                yield Static(" Cancel ", id="btn-cancel")
            yield Static("← → adjust   ↑ ↓ move   Enter confirm", id="display-hint")

    def on_mount(self) -> None:
        self._update_display()

    def _render_bar(self, value: float, min_val: float, max_val: float, focused: bool) -> str:
        """Render a setting bar with optional focus highlight."""
        segments = 7
        filled = round((value - min_val) / (max_val - min_val) * segments)
        bar = "█" * filled + "░" * (segments - filled)
        if focused:
            return f"[bold cyan]◀ {bar} ▶[/]"
        return f"  {bar}  "

    def _update_display(self) -> None:
        """Update all display elements."""
        # Brightness bar
        bright_bar = self.query_one("#brightness-bar", Static)
        bright_val = self.query_one("#brightness-value", Static)
        bright_bar.update(self._render_bar(
            self._brightness, BRIGHTNESS_MIN, BRIGHTNESS_MAX,
            self._focus_area == "brightness"
        ))
        bright_val.update(f"{int(self._brightness * 100)}%")

        # Contrast bar
        contrast_bar = self.query_one("#contrast-bar", Static)
        contrast_val = self.query_one("#contrast-value", Static)
        contrast_bar.update(self._render_bar(
            self._contrast, CONTRAST_MIN, CONTRAST_MAX,
            self._focus_area == "contrast"
        ))
        # Show contrast as a relative scale: 1.0 = "Normal"
        if abs(self._contrast - 1.0) < 0.05:
            contrast_text = "Normal"
        elif self._contrast < 1.0:
            contrast_text = "Low"
        else:
            contrast_text = "High"
        contrast_val.update(contrast_text)

        # Buttons
        save_btn = self.query_one("#btn-save", Static)
        cancel_btn = self.query_one("#btn-cancel", Static)

        if self._focus_area == "buttons":
            if self._selected_button == 0:
                save_btn.update("[bold reverse]  Save  [/]")
                cancel_btn.update(" Cancel ")
            else:
                save_btn.update("  Save  ")
                cancel_btn.update("[bold reverse] Cancel [/]")
        else:
            save_btn.update("  Save  ")
            cancel_btn.update(" Cancel ")

    def _apply_current_settings(self) -> None:
        """Apply current brightness and contrast to display."""
        apply_display_settings(self._brightness, self._contrast)

    def on_key(self, event: events.Key) -> None:
        """Suppress terminal key events."""
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        """Handle keyboard input."""
        if isinstance(action, NavigationAction):
            if self._focus_area == "brightness":
                if action.direction == 'left':
                    self._brightness = max(BRIGHTNESS_MIN, self._brightness - BRIGHTNESS_STEP)
                    self._apply_current_settings()
                elif action.direction == 'right':
                    self._brightness = min(BRIGHTNESS_MAX, self._brightness + BRIGHTNESS_STEP)
                    self._apply_current_settings()
                elif action.direction == 'down':
                    self._focus_index = 1  # contrast
                self._update_display()

            elif self._focus_area == "contrast":
                if action.direction == 'left':
                    self._contrast = max(CONTRAST_MIN, self._contrast - CONTRAST_STEP)
                    self._apply_current_settings()
                elif action.direction == 'right':
                    self._contrast = min(CONTRAST_MAX, self._contrast + CONTRAST_STEP)
                    self._apply_current_settings()
                elif action.direction == 'up':
                    self._focus_index = 0  # brightness
                elif action.direction == 'down':
                    self._focus_index = 2  # buttons
                self._update_display()

            else:  # buttons
                if action.direction == 'up':
                    self._focus_index = 1  # contrast
                    self._update_display()
                elif action.direction in ('left', 'right'):
                    self._selected_button = 1 - self._selected_button
                    self._update_display()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                if self._focus_area == "buttons":
                    if self._selected_button == 0:  # Save
                        save_display_settings({
                            "brightness": self._brightness,
                            "contrast": self._contrast,
                        })
                        self.dismiss(True)
                    else:  # Cancel
                        apply_display_settings(self._original_brightness, self._original_contrast)
                        self.dismiss(False)
                else:
                    # Enter on sliders moves to buttons
                    self._focus_index = 2
                    self._update_display()
            elif action.action == 'escape':
                # Restore original settings and exit
                apply_display_settings(self._original_brightness, self._original_contrast)
                self.dismiss(False)


def _flush_terminal_input() -> None:
    """Flush any buffered terminal input to prevent stray characters."""
    try:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (termios.error, OSError):
        pass  # Not a TTY or other error, ignore


def _is_dev_environment() -> bool:
    """Check if running in a development environment.

    Returns True if:
    - PURPLE_TEST_BATTERY env var is set (set by `make run`), OR
    - .git directory exists in project root (git checkout, not installed)

    In production, Purple is installed to /opt/purple without .git,
    and PURPLE_TEST_BATTERY is not set.
    """
    if os.environ.get("PURPLE_TEST_BATTERY"):
        return True
    project_root = Path(__file__).parent.parent.parent
    return (project_root / ".git").is_dir()


def _get_menu_items() -> list:
    """Get menu items, including dev-only items when appropriate."""
    items = [
        ("menu-display", "Adjust Display"),
        ("menu-shell", "Open Terminal"),
        ("menu-keyboard", "Recalibrate Keyboard"),
    ]
    if _is_dev_environment():
        items.append(("menu-demo", "Start Demo"))
        items.append(("menu-update", "Git Pull & Exit"))
    items.append(("menu-exit", "Exit"))
    return items


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
        self._menu_items = _get_menu_items()
        self._selected_index = 0
        # Escape is always "tainted" since user held it to open this menu
        self._ignore_until_released = {'escape'}

    def compose(self) -> ComposeResult:
        with Vertical(id="parent-dialog"):
            yield Static("Parent Menu", id="parent-title")
            with Vertical(id="parent-items"):
                for item_id, label in self._menu_items:
                    yield ParentMenuItem(label, item_id)
            yield Static("↑↓ Enter Esc", id="parent-hint")

    def on_mount(self) -> None:
        """Highlight the first menu item"""
        self._update_selection()

    def _update_selection(self) -> None:
        """Update visual selection state"""
        for i, (item_id, _) in enumerate(self._menu_items):
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
                self._selected_index = (self._selected_index - 1) % len(self._menu_items)
                self._update_selection()
            elif action.direction == 'down':
                self._selected_index = (self._selected_index + 1) % len(self._menu_items)
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
        item_id = self._menu_items[self._selected_index][0]
        if item_id == "menu-display":
            self._open_display_settings()
        elif item_id == "menu-shell":
            self._open_shell()
        elif item_id == "menu-keyboard":
            self._recalibrate_keyboard()
        elif item_id == "menu-demo":
            self._start_demo()
        elif item_id == "menu-update":
            self._update_and_restart()
        elif item_id == "menu-exit":
            self.dismiss()

    def _open_display_settings(self) -> None:
        """Open the display settings modal."""
        self.app.push_screen(DisplaySettingsScreen())

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

        # Force redraw after returning from suspend
        self.app.refresh(repaint=True)

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

        # Force redraw after returning from suspend
        self.app.refresh(repaint=True)

    def _start_demo(self) -> None:
        """Start the demo playback (dev mode only)."""
        self.dismiss()
        # Tell the app to start demo after modal is closed
        self.app.call_later(self.app.start_demo)

    def _update_and_restart(self) -> None:
        """Git pull and restart the app (dev mode only)."""
        self.dismiss()
        self.app.call_later(self._run_update_and_restart)

    def _run_update_and_restart(self) -> None:
        """Actually run the update - called after modal dismissed."""
        project_root = Path(__file__).parent.parent.parent

        with self.app.suspend_with_terminal_input():
            os.system('stty sane')
            os.system('clear')

            print("=" * 60)
            print("Purple Computer - Update & Restart")
            print("=" * 60)
            print()

            # Git pull
            print("Pulling latest changes...")
            result = subprocess.run(
                ["git", "pull"],
                cwd=project_root,
            )

            if result.returncode != 0:
                print()
                print("Git pull failed. Check the error above.")
                print("Press Enter to return to Purple Computer...")
                input()
                _flush_terminal_input()
                os.system('stty sane')
                return

            # Pip install (in case dependencies changed)
            print()
            print("Updating dependencies...")
            venv_pip = project_root / ".venv" / "bin" / "pip"
            if venv_pip.exists():
                subprocess.run(
                    [str(venv_pip), "install", "-q", "-r", "requirements.txt"],
                    cwd=project_root,
                )

            print()
            print("Update complete!")
            print("Press Enter to exit. Then run 'make run' to restart.")
            print()

            input()

            # Restore terminal and exit.
            # We use os._exit(0) instead of sys.exit(0) because we're inside
            # Textual's suspend context. sys.exit() would try to unwind through
            # Textual's cleanup code, which can leave the terminal in a broken
            # state (blank screen, no echo). os._exit() exits immediately while
            # the terminal is still in the clean state from suspend().
            _flush_terminal_input()
            os.system('stty sane')
            os.system('clear')
            print("Run 'make run' to start Purple Computer.")
            print()
            os._exit(0)
