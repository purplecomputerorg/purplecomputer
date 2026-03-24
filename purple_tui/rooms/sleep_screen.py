"""
Purple Computer - Sleep Screen, Shutdown Confirm Screen, Bye Screen,
and Live Boot Splash

Kid-friendly screens for sleep (idle timeout), shutdown confirmation
(power button tap), shutdown (power button hold, lid close timeout),
and live boot welcome message.

Two power states: awake and sleep face. No DPMS screen-off state.
Timers adapt to charger status and lid position.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual import events
import time

from ..power_manager import (
    get_power_manager,
    LID_SHUTDOWN_DELAY,
)
from ..constants import is_live_boot

# Live boot message shown on the sleep face screen
_LIVE_BOOT_HINT = (
    "Purple is running from USB.\n"
    "If the computer turns off,\n"
    "you'll need the USB to start it again."
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
    Sleep screen shown when computer is idle or lid is closed.

    Press any key to wake up and return to normal operation.
    Shuts down after extended idle (battery) or lid-closed timeout.
    On charger with lid open, stays on sleep face indefinitely.
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

    #sleep-live-hint {
        content-align: center middle;
        color: $text-muted;
        margin-top: 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._status_timer = None
        self._lid_close_time: float | None = None
        self._shutdown_initiated = False

    def compose(self) -> ComposeResult:
        yield SleepFace()
        yield Static("Press any key to wake", id="sleep-hint")
        if is_live_boot():
            yield Static(_LIVE_BOOT_HINT, id="sleep-live-hint")

    def on_mount(self) -> None:
        """Start update timer when screen is shown."""
        self._status_timer = self.set_interval(1.0, self._update_status)
        self._update_status()

    def on_unmount(self) -> None:
        """Clean up timer when screen is hidden."""
        if self._status_timer:
            self._status_timer.stop()

    def _update_status(self) -> None:
        """Check idle time, lid state, and charger. Act accordingly."""
        pm = get_power_manager()
        idle = pm.get_idle_seconds()
        lid_open = pm.get_lid_state()

        # Refresh charger state each tick
        pm.is_on_charger()

        # Lid close edge detection
        if lid_open is False and self._lid_close_time is None:
            self._lid_close_time = time.time()
        elif lid_open is not False and self._lid_close_time is not None:
            self._lid_close_time = None

        # Lid-closed shutdown: 10 min after lid close, regardless of charger
        if self._lid_close_time is not None:
            if time.time() - self._lid_close_time >= LID_SHUTDOWN_DELAY:
                self._do_shutdown()
            return

        # Idle shutdown (only on battery, never on charger with lid open)
        shutdown_threshold = pm.get_idle_shutdown_threshold()
        if shutdown_threshold is not None and idle >= shutdown_threshold:
            self._do_shutdown()
            return

    def _do_shutdown(self) -> None:
        """Execute shutdown (only once, further calls are no-ops)."""
        if self._shutdown_initiated:
            return
        self._shutdown_initiated = True
        pm = get_power_manager()
        if not pm.shutdown():
            try:
                self.query_one("#sleep-hint", Static).update("Please turn off")
            except Exception:
                pass

    def _wake_up(self) -> None:
        """Wake up and return to normal operation"""
        pm = get_power_manager()
        pm.record_activity()

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


class LiveBootSplash(Screen):
    """
    Welcome screen shown once on first launch during live boot (USB).

    Tells the parent that Purple is running from USB and will be gone
    after shutdown unless installed. Dismissed by any key press.
    """

    DEFAULT_CSS = """
    LiveBootSplash {
        align: center middle;
        background: $background;
    }

    #splash-message {
        content-align: center middle;
        color: $primary;
        margin-bottom: 2;
    }

    #splash-hint {
        content-align: center middle;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "Purple Computer is running from USB.\n"
            "\n"
            "You can keep using it, but if the computer\n"
            "turns off, you'll need the USB to start\n"
            "Purple again.\n"
            "\n"
            "To install Purple permanently,\n"
            "visit the Parent Menu.",
            id="splash-message",
        )
        yield Static("Press any key to start", id="splash-hint")

    def on_key(self, event: events.Key) -> None:
        """Any key dismisses the splash."""
        event.stop()
        event.prevent_default()
        self.dismiss()

    async def handle_keyboard_action(self, action) -> None:
        """Any key dismisses the splash."""
        self.dismiss()
