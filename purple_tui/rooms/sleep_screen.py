"""
Purple Computer - Sleep Screen, Shutdown Confirm Screen, Bye Screen,
Live Boot Splash, and First Boot Welcome

Kid-friendly screens for sleep (idle timeout), shutdown confirmation
(power button tap), shutdown (power button hold, lid close timeout),
live boot welcome message, and first-boot-after-install welcome.

Two power states: awake and sleep face. No DPMS screen-off state.
Timers adapt to charger status and lid position.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual import events

from ..power_manager import get_power_manager, LID_SHUTDOWN_DELAY
from ..constants import is_live_boot


def _friendly_time(seconds: float) -> str:
    """Format remaining seconds as friendly, rounded text for parents.

    45+ min: 'about 1 hr', 10-44 min: 'about NN min',
    1-9 min: 'N min', under 1 min: 'soon'.
    """
    minutes = int(seconds / 60)
    if minutes >= 45:
        return "about 1 hr"
    if minutes >= 10:
        return f"about {minutes} min"
    if minutes >= 1:
        return f"{minutes} min"
    return "soon"

# All lines SAME WIDTH for consistent bounding box
_SLEEP_FACE = "\n".join([
    "---     ---",
    "           ",
    "   \\___/   ",
    "           ",
    "   z z z   ",
])


class SleepFace(Static):
    """Sleeping face widget - centered as a single block."""

    def render(self) -> str:
        return _SLEEP_FACE


class SleepScreen(Screen):
    """
    Sleep screen shown when computer is idle or lid is closed.

    Press any key to wake up and return to normal operation.
    Shuts down after extended idle or lid-closed timeout.
    """

    DEFAULT_CSS = """
    SleepScreen {
        align: center middle;
        background: #140a22;
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

        lid_close_time = getattr(self.app, '_lid_close_time', None)
        lid_was_closed_for = getattr(self.app, '_lid_was_closed_for', 0)

        lines = []
        if lid_close_time is not None:
            closed_min = int((time.time() - lid_close_time) / 60)
            lines.append(f"💻 Lid closed{f' {closed_min} min' if closed_min >= 1 else ''}.")
        elif lid_was_closed_for > 0:
            closed_min = int(lid_was_closed_for / 60)
            lines.append(f"💻 Lid open{f' (closed {closed_min} min)' if closed_min >= 1 else ''}.")

        if live:
            lines.append("💾 USB. Need it to restart.")

        if lid_close_time is not None:
            remaining = max(0, LID_SHUTDOWN_DELAY - (time.time() - lid_close_time))
            lines.append(f"⏳ Shuts off in {_friendly_time(remaining)}.")
        else:
            idle = pm.get_idle_seconds()
            remaining = max(0, pm.get_idle_shutdown_threshold() - idle)
            power_icon = "🔌 Plugged in." if on_charger is True else "🔋 Battery."
            lines.append(f"{power_icon} Shuts off in {_friendly_time(remaining)}.")

        try:
            self.query_one("#sleep-status", Static).update("\n".join(lines))
        except Exception:
            pass

    def _check_idle_shutdown(self) -> None:
        """Check if idle time has reached shutdown threshold."""
        from ..power_manager import _power_log
        pm = get_power_manager()

        charger = pm.is_on_charger()
        idle = pm.get_idle_seconds()
        shutdown_threshold = pm.get_idle_shutdown_threshold()
        if int(idle) % 30 == 0:
            _power_log(f"SLEEP_SCREEN TICK: idle={idle:.0f}s, shutdown_threshold={shutdown_threshold}, charger={charger}")
        if idle >= shutdown_threshold:
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
        yield Static(_SLEEP_FACE, id="shutdown-face")
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
        """Show goodbye and shut down immediately.

        The user already confirmed (held power 3s or tapped twice).
        No reason to delay.
        """
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
    after shutdown unless installed. When audio is detected as broken,
    appends a one-line warning pointing at Support info + USB adapter.
    Dismissed by any key press.
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

    #splash-audio-warning {
        content-align: center middle;
        color: $warning;
        margin-bottom: 2;
    }

    #splash-hint {
        content-align: center middle;
        color: $text-muted;
    }
    """

    _BASE_MESSAGE = (
        "Purple Computer is running from USB.\n"
        "\n"
        "You can keep using it, but if the computer\n"
        "turns off, you'll need the USB to start\n"
        "Purple again.\n"
        "\n"
        "Purple uses just the keyboard, on purpose.\n"
        "No mouse, trackpad, or touch needed.\n"
        "\n"
        "To install Purple permanently,\n"
        "visit the Parent Menu."
    )

    _AUDIO_WARNING = (
        "\U0001f507 Sound is not working on this computer.\n"
        "Plug in a USB audio adapter, or open the\n"
        "Parent Menu to see Support info."
    )

    def compose(self) -> ComposeResult:
        yield Static(self._BASE_MESSAGE, id="splash-message")
        yield Static("", id="splash-audio-warning")
        yield Static("Press any key to start", id="splash-hint")

    def on_mount(self) -> None:
        # Audio probe runs on a background thread started from on_mount
        # of PurpleApp. By the time the user finishes reading the splash,
        # app.audio_ok is almost always set. Poll briefly in case it isn't.
        self._refresh_audio_warning()
        self.set_interval(0.25, self._refresh_audio_warning)

    def _refresh_audio_warning(self) -> None:
        audio_ok = getattr(self.app, "audio_ok", None)
        try:
            warning = self.query_one("#splash-audio-warning", Static)
        except Exception:
            return
        warning.update(self._AUDIO_WARNING if audio_ok is False else "")

    def on_key(self, event: events.Key) -> None:
        """Any key dismisses the splash."""
        event.stop()
        event.prevent_default()
        self.dismiss()

    async def handle_keyboard_action(self, action) -> None:
        """Any key dismisses the splash."""
        self.dismiss()
