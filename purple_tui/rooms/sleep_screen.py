"""
Purple Computer - Sleep Screen, Shutdown Confirm Screen, and Bye Screen

Kid-friendly screens for sleep (idle timeout), shutdown confirmation
(power button tap), and shutdown (power button hold, lid close timeout).
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual import events
import time

from ..power_manager import (
    get_power_manager,
    IDLE_SCREEN_OFF,
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


class SleepScreen(Screen):
    """
    Sleep screen shown when computer is idle or power button is tapped.

    Press any key to wake up and return to normal operation.
    Turns screen off after extended idle and shuts down eventually.
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
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._status_timer = None
        self._lid_close_time: float | None = None
        self._screen_off = False
        self._shutdown_initiated = False

    def compose(self) -> ComposeResult:
        yield SleepFace()
        yield Static("Press any key to wake", id="sleep-hint")

    def on_mount(self) -> None:
        """Start update timer when screen is shown."""
        self._status_timer = self.set_interval(1.0, self._update_status)
        self._update_status()

    def on_unmount(self) -> None:
        """Clean up timer when screen is hidden."""
        if self._status_timer:
            self._status_timer.stop()

    def _update_status(self) -> None:
        """Check idle time and lid state, act accordingly."""
        pm = get_power_manager()
        idle = pm.get_idle_seconds()
        lid_open = pm.get_lid_state()

        # Lid close edge detection (use _lid_close_time as the state flag)
        if lid_open is False and self._lid_close_time is None:
            self._lid_close_time = time.time()
            pm.set_screen_brightness("off")
            self._screen_off = True
        elif lid_open is not False and self._lid_close_time is not None:
            self._lid_close_time = None
            if self._screen_off:
                pm.set_screen_brightness("on")
                self._screen_off = False

        # Lid shutdown
        if self._lid_close_time is not None:
            if time.time() - self._lid_close_time >= LID_SHUTDOWN_DELAY:
                self._do_shutdown()
            return

        # Idle shutdown
        if idle >= IDLE_SHUTDOWN:
            self._do_shutdown()
            return

        # Idle screen off
        if idle >= IDLE_SCREEN_OFF:
            if not self._screen_off:
                pm.set_screen_brightness("off")
                self._screen_off = True

    def _do_shutdown(self) -> None:
        """Execute shutdown (only once, further calls are no-ops)."""
        if self._shutdown_initiated:
            return
        self._shutdown_initiated = True
        pm = get_power_manager()
        pm.set_screen_brightness("on")
        if not pm.shutdown():
            try:
                self.query_one("#sleep-hint", Static).update("Please turn off")
            except Exception:
                pass

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
        self.dismiss()

    def on_key(self, event: events.Key) -> None:
        """Any key press wakes up the computer (terminal fallback)"""
        event.stop()
        event.prevent_default()
        self._wake_up()

    async def handle_keyboard_action(self, action) -> None:
        """Any key action wakes up the computer (evdev)"""
        self._wake_up()


class ShutdownConfirmScreen(Screen):
    """
    Confirmation screen shown when power button is tapped.

    Shows "Press power button again to shut down". Any other key
    dismisses back to normal operation.
    """

    DEFAULT_CSS = """
    ShutdownConfirmScreen {
        align: center middle;
        background: $background;
    }

    #shutdown-face {
        content-align: center middle;
        color: $primary;
    }

    #shutdown-hint {
        content-align: center middle;
        color: $text-muted;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "\n".join([
                "---     ---",
                "           ",
                "   \\___/   ",
                "           ",
                "   z z z   ",
            ]),
            id="shutdown-face",
        )
        yield Static("Press power button again to shut down", id="shutdown-hint")

    def _cancel(self) -> None:
        """Cancel shutdown and return to normal operation."""
        pm = get_power_manager()
        pm.record_activity()
        self.dismiss()

    def on_key(self, event: events.Key) -> None:
        """Any non-power key cancels (terminal fallback)."""
        event.stop()
        event.prevent_default()
        self._cancel()

    async def handle_keyboard_action(self, action) -> None:
        """Any non-power key cancels (evdev)."""
        self._cancel()


class ByeScreen(Screen):
    """
    Friendly shutdown screen shown when power button is held for 3 seconds.

    Shows a brief goodbye message, then powers off. No cancel option
    since the 3-second hold was already a deliberate action.
    """

    DEFAULT_CSS = """
    ByeScreen {
        align: center middle;
        background: $background;
    }

    #bye-face {
        content-align: center middle;
        color: $primary;
    }

    #bye-text {
        content-align: center middle;
        color: $text-muted;
        margin-top: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "\n".join([
                "---     ---",
                "           ",
                "   \\___/   ",
                "           ",
                "    Bye!   ",
            ]),
            id="bye-face",
        )
        yield Static("Turning off...", id="bye-text")

    def on_mount(self) -> None:
        """Show goodbye briefly, then shut down."""
        self.set_timer(2.0, self._do_shutdown)
        # Fallback: if normal shutdown hangs (common on live ISOs),
        # force power off after 10 seconds
        self.set_timer(10.0, self._force_shutdown)

    def _do_shutdown(self) -> None:
        """Execute shutdown"""
        pm = get_power_manager()
        pm.set_screen_brightness("on")
        if not pm.shutdown():
            try:
                self.query_one("#bye-text", Static).update("Please turn off")
            except Exception:
                pass

    def _force_shutdown(self) -> None:
        """Force power off if normal shutdown is stuck."""
        pm = get_power_manager()
        pm.force_shutdown()

    def on_key(self, event: events.Key) -> None:
        """Suppress all keys during shutdown."""
        event.stop()
        event.prevent_default()

    async def handle_keyboard_action(self, action) -> None:
        """Suppress all keys during shutdown."""
        pass
