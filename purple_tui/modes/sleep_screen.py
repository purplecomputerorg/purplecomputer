"""
Purple Computer - Sleep Screen

Kid-friendly sleep screen shown after idle timeout.
Features a cute sleeping face and clear instructions.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Container, Vertical, Center, Middle
from textual import events
import time

from ..power_manager import (
    get_power_manager,
    IDLE_SCREEN_OFF,
    IDLE_SHUTDOWN_WARN,
    IDLE_SHUTDOWN,
    LID_SHUTDOWN_DELAY,
)


class SleepFace(Static):
    """Sleeping face widget - centered as a single block."""

    def render(self) -> str:
        # All lines SAME WIDTH for consistent bounding box
        return "\n".join([
            "---     ---",
            "           ",
            "   \\___/   ",
            "           ",
            "   z z z   ",
        ])


class SleepStatus(Static):
    """Shows current sleep status and countdown"""

    DEFAULT_CSS = """
    SleepStatus {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        margin-top: 2;
    }

    SleepStatus.warning {
        color: $warning;
    }

    SleepStatus.danger {
        color: $error;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._message = ""
        self._style_class = ""

    def set_status(self, message: str, style: str = "") -> None:
        """Update the status message and style"""
        self._message = message
        self._style_class = style
        self.remove_class("warning", "danger")
        if style:
            self.add_class(style)
        self.refresh()

    def render(self) -> str:
        return self._message


class SleepScreen(Screen):
    """
    Sleep screen shown when computer is idle.

    Press any key to wake up and return to normal operation.
    Shows countdown warnings before screen off and shutdown.
    """

    DEFAULT_CSS = """
    SleepScreen {
        align: center middle;
        background: $background;
    }

    SleepFace {
        content-align: center middle;
        color: $primary;
    }

    #sleep-hint {
        content-align: center middle;
        color: $text-muted;
        margin-top: 2;
    }

    #sleep-status {
        content-align: center middle;
        color: $text-muted;
        margin-top: 1;
    }

    #lid-warning {
        content-align: center middle;
        color: $error;
        text-style: bold;
        margin-top: 1;
        display: none;
    }

    #lid-warning.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._status_timer = None
        self._lid_close_time: float | None = None
        self._last_lid_state: bool | None = None
        self._screen_off = False

    def compose(self) -> ComposeResult:
        yield SleepFace()
        yield Static("press any key to wake", id="sleep-hint")
        yield SleepStatus(id="sleep-status")
        yield Static("Lid closed!", id="lid-warning")

    def on_mount(self) -> None:
        """Start update timer when screen is shown"""
        self._status_timer = self.set_interval(1.0, self._update_status)
        self._update_status()

    def on_unmount(self) -> None:
        """Clean up timer when screen is hidden"""
        if self._status_timer:
            self._status_timer.stop()

    def _update_status(self) -> None:
        """Update the status display based on idle time and lid state"""
        pm = get_power_manager()
        idle = pm.get_idle_seconds()

        # Check lid state
        lid_open = pm.get_lid_state()
        if lid_open is not None:
            if not lid_open and self._last_lid_state:
                # Lid just closed
                self._lid_close_time = time.time()
            elif lid_open and not self._last_lid_state:
                # Lid just opened
                self._lid_close_time = None
            self._last_lid_state = lid_open

        # Handle lid close countdown
        lid_warning = self.query_one("#lid-warning", Static)
        if self._lid_close_time is not None:
            elapsed = time.time() - self._lid_close_time
            remaining = max(0, LID_SHUTDOWN_DELAY - int(elapsed))

            if remaining <= 0:
                lid_warning.update("turning off...")
                lid_warning.add_class("visible")
                self.call_later(self._do_shutdown)
                return
            else:
                lid_warning.update(f"lid closed ({remaining}s)")
                lid_warning.add_class("visible")
        else:
            lid_warning.remove_class("visible")

        # Update status based on idle time
        status = self.query_one("#sleep-status", SleepStatus)
        hint = self.query_one("#sleep-hint", Static)

        if idle >= IDLE_SHUTDOWN:
            status.set_status("turning off...", "danger")
            hint.update("")
            self.call_later(self._do_shutdown)
        elif idle >= IDLE_SHUTDOWN_WARN:
            remaining = int(IDLE_SHUTDOWN - idle)
            mins = remaining // 60
            secs = remaining % 60
            if mins > 0:
                status.set_status(f"turning off in {mins} minutes", "danger")
            else:
                status.set_status(f"turning off in {secs} seconds", "danger")
            hint.update("press any key to stay on")
        elif idle >= IDLE_SCREEN_OFF:
            if not self._screen_off:
                pm.set_screen_brightness("off")
                self._screen_off = True
            remaining = int(IDLE_SHUTDOWN_WARN - idle)
            mins = remaining // 60
            status.set_status(f"screen off, turning off in {mins} minutes", "warning")
            hint.update("press any key to wake")
        else:
            remaining = int(IDLE_SCREEN_OFF - idle)
            mins = remaining // 60
            if mins > 0:
                status.set_status(f"screen dims in {mins} minutes", "")
            else:
                status.set_status("", "")
            hint.update("press any key to wake")

    def _do_shutdown(self) -> None:
        """Execute shutdown"""
        pm = get_power_manager()
        pm.set_screen_brightness("on")
        if not pm.shutdown():
            status = self.query_one("#sleep-status", SleepStatus)
            status.set_status("please turn off", "danger")

    def _wake_up(self) -> None:
        """Wake up and return to normal operation"""
        pm = get_power_manager()
        pm.record_activity()

        # Turn screen back on if it was off
        if self._screen_off:
            pm.set_screen_brightness("on")
            self._screen_off = False

        # Reset lid close tracking
        self._lid_close_time = None

        # Dismiss this screen and return to normal
        self.app.pop_screen()

    def on_key(self, event: events.Key) -> None:
        """Any key press wakes up the computer"""
        event.stop()
        event.prevent_default()
        self._wake_up()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Mouse movement wakes up"""
        event.stop()
        self._wake_up()

    def on_click(self, event: events.Click) -> None:
        """Click wakes up"""
        event.stop()
        self._wake_up()
