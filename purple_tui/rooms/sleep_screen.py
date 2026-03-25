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

from ..power_manager import get_power_manager
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
        self._shutdown_initiated = False

    def compose(self) -> ComposeResult:
        yield SleepFace()
        yield Static("Press any key to wake", id="sleep-hint")
        if is_live_boot():
            yield Static(_LIVE_BOOT_HINT, id="sleep-live-hint")

    def on_mount(self) -> None:
        """Start update timer when screen is shown."""
        # Check for idle shutdown periodically.
        # Lid detection and lid-close shutdown are handled by
        # LidSwitchReader and the app's _check_idle_state timer.
        self._status_timer = self.set_interval(5.0, self._check_idle_shutdown)

    def on_unmount(self) -> None:
        """Clean up timer when screen is hidden."""
        if self._status_timer:
            self._status_timer.stop()

    def _check_idle_shutdown(self) -> None:
        """Check if idle time has reached shutdown threshold (battery only)."""
        from ..power_manager import _power_log
        pm = get_power_manager()

        # Refresh charger state
        charger = pm.is_on_charger()

        idle = pm.get_idle_seconds()
        shutdown_threshold = pm.get_idle_shutdown_threshold()
        if int(idle) % 30 == 0:
            _power_log(f"SLEEP_SCREEN TICK: idle={idle:.0f}s, shutdown_threshold={shutdown_threshold}, charger={charger}")
        if shutdown_threshold is not None and idle >= shutdown_threshold:
            _power_log(f"SLEEP_SCREEN SHUTDOWN: idle {idle:.0f}s >= {shutdown_threshold}s")
            self._do_shutdown()

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
        """Wake up and return to normal operation."""
        from ..power_manager import _power_log
        _power_log("WAKE UP: key pressed on sleep screen")
        pm = get_power_manager()
        pm.record_activity()
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

    Shows "Press power button again to shut down" with a 3-second
    countdown. Auto-dismisses when the countdown expires. Any other
    key also dismisses back to normal operation.
    """

    COUNTDOWN_SECONDS = 3

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
        yield Static(
            f"Press power button again to shut down ({self.COUNTDOWN_SECONDS})",
            id="shutdown-hint",
        )

    def on_mount(self) -> None:
        self._remaining = self.COUNTDOWN_SECONDS
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._cancel()
            return
        hint = self.query_one("#shutdown-hint", Static)
        hint.update(f"Press power button again to shut down ({self._remaining})")

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
