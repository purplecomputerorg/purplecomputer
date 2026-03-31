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

from ..power_manager import get_power_manager, LID_SHUTDOWN_DELAY, BATTERY_IDLE_SHUTDOWN
from ..constants import is_live_boot


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

    #sleep-status {
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
        yield Static("", id="sleep-status")

    def on_mount(self) -> None:
        """Start update timer when screen is shown."""
        self._update_status()
        self._status_timer = self.set_interval(5.0, self._tick)

    def on_unmount(self) -> None:
        """Clean up timer when screen is hidden."""
        if self._status_timer:
            self._status_timer.stop()

    def _tick(self) -> None:
        """Update status text and check for idle shutdown."""
        self._update_status()
        self._check_idle_shutdown()

    def _update_status(self) -> None:
        """Update the power status hint based on current state."""
        import time
        pm = get_power_manager()
        on_charger = pm.is_on_charger()
        live = is_live_boot()

        # Lid state: currently closed, or was closed and now reopened
        lid_close_time = getattr(self.app, '_lid_close_time', None)
        lid_was_closed_for = getattr(self.app, '_lid_was_closed_for', 0)
        lid_involved = lid_close_time is not None or lid_was_closed_for > 0

        lines = []
        if lid_close_time is not None:
            closed_min = int((time.time() - lid_close_time) / 60)
            if closed_min < 1:
                lines.append("Lid is closed.")
            else:
                lines.append(f"Lid has been closed for {closed_min} min.")
        elif lid_was_closed_for > 0:
            closed_min = int(lid_was_closed_for / 60)
            if closed_min < 1:
                lines.append("Lid was closed briefly.")
            else:
                lines.append(f"Lid was closed for {closed_min} min.")

        if live:
            lines.append("Running from USB.")
            lines.append("If it turns off, you'll need the USB to restart.")

        shutdown_min = LID_SHUTDOWN_DELAY // 60 if lid_involved else BATTERY_IDLE_SHUTDOWN // 60
        if on_charger is True:
            lines.append("Plugged in. Won't turn off automatically.")
        else:
            lines.append(f"On battery. Turns off after {shutdown_min} min to save power.")

        try:
            self.query_one("#sleep-status", Static).update("\n".join(lines))
        except Exception:
            pass

    def _check_idle_shutdown(self) -> None:
        """Check if idle time has reached shutdown threshold (battery only)."""
        from ..power_manager import _power_log
        pm = get_power_manager()

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
        # Spawn a watchdog in case shutdown hangs (same as ByeScreen)
        import subprocess
        try:
            subprocess.Popen(
                ["sh", "-c",
                 "sleep 5 && "
                 "systemctl poweroff --force --force 2>/dev/null || "
                 "sudo systemctl poweroff --force --force 2>/dev/null"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
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
        # Clear the "was closed for" so it doesn't linger into next sleep
        self.app._lid_was_closed_for = 0
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
        """Show goodbye and shut down immediately."""
        # Spawn a detached watchdog process FIRST. This runs independently
        # of the TUI, so even if systemd kills the X11 session (and thus
        # the Textual event loop), the watchdog will still force power off.
        self._spawn_shutdown_watchdog()
        # Shut down immediately. The user already confirmed (held power 3s
        # or tapped twice). No reason to delay.
        self._do_shutdown()

    def _spawn_shutdown_watchdog(self) -> None:
        """Spawn a background process that force-powers-off after 5 seconds.

        Independent of the TUI event loop: survives X11/Textual being killed.
        Normal --force shutdown is near-instant, so 5s is generous.
        """
        import subprocess
        try:
            subprocess.Popen(
                ["sh", "-c",
                 "sleep 5 && "
                 "systemctl poweroff --force --force 2>/dev/null || "
                 "sudo systemctl poweroff --force --force 2>/dev/null"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from TUI's process group
            )
        except Exception:
            pass

    def _do_shutdown(self) -> None:
        """Execute shutdown."""
        pm = get_power_manager()
        if not pm.shutdown():
            try:
                self.query_one("#bye-text", Static).update("Please turn off")
            except Exception:
                pass

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
