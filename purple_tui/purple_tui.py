#!/usr/bin/env python3
"""
Purple Computer: Main Textual TUI Application

The calm computer for kids ages 3-8.
A creativity device, not an entertainment device.

IMPORTANT: Requires Linux with evdev for keyboard input.
The terminal (Alacritty) is display-only; keyboard input is read
directly from evdev, bypassing the terminal. See:
  guides/keyboard-architecture.md

Keyboard controls:
- F1-F3: Switch modes (Ask, Play, Write)
- F9: Toggle dark/light theme
- F10: Mute/unmute, F11: Volume down, F12: Volume up
- Escape (long hold): Parent mode
- Caps Lock: Toggle big/small letters
- Sticky shift: Shift key toggles, stays active for 1 second
- Double-tap: Same symbol twice quickly = shifted version
"""

# Suppress ONNX runtime warnings early (before any imports that might load it)
import os
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, Center, Middle
from textual.widgets import Static, Footer
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.theme import Theme
from textual import events
from enum import Enum
import subprocess
import time

from .constants import (
    ICON_CHAT, ICON_MUSIC, ICON_DOCUMENT,
    ICON_MOON, ICON_SUN, MODE_TITLES,
    DOUBLE_TAP_TIME, STICKY_SHIFT_GRACE, ESCAPE_HOLD_THRESHOLD,
    ICON_BATTERY_FULL, ICON_BATTERY_HIGH, ICON_BATTERY_MED,
    ICON_BATTERY_LOW, ICON_BATTERY_EMPTY, ICON_BATTERY_CHARGING,
    ICON_VOLUME_OFF, ICON_VOLUME_LOW, ICON_VOLUME_MED, ICON_VOLUME_HIGH,
    ICON_VOLUME_DOWN, ICON_VOLUME_UP, ICON_ERASER, ICON_CAPS_LOCK,
    VOLUME_LEVELS, VOLUME_DEFAULT,
)
from .keyboard import (
    KeyboardState, create_keyboard_state, detect_keyboard_mode,
    KeyboardMode, SHIFT_MAP,
    KeyboardStateMachine, CharacterAction, NavigationAction,
    ModeAction, ControlAction, ShiftAction, CapsLockAction, LongHoldAction,
)
from .input import EvdevReader, RawKeyEvent, check_evdev_available
from .power_manager import get_power_manager


class Mode(Enum):
    """The 3 core modes of Purple Computer"""
    ASK = 1      # F1: Math and emoji REPL
    PLAY = 2     # F2: Music and art grid
    WRITE = 3    # F3: Simple text editor


class View(Enum):
    """The 3 core views. Reduce screen time feeling."""
    SCREEN = 1   # 10x6" viewport
    LINE = 2     # 10" wide, 1 line height
    EARS = 3     # Screen off (blank)


# Mode display info: F-keys for mode switching
MODE_INFO = {
    Mode.ASK: {"key": "F1", "label": "Ask", "emoji": ICON_CHAT},
    Mode.PLAY: {"key": "F2", "label": "Play", "emoji": ICON_MUSIC},
    Mode.WRITE: {"key": "F3", "label": "Write", "emoji": ICON_DOCUMENT},
}


class ModeTitle(Static):
    """Shows current mode title above the viewport"""

    DEFAULT_CSS = """
    ModeTitle {
        width: 100%;
        height: 1;
        text-align: center;
        color: $primary;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = "ask"

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.refresh()

    def render(self) -> str:
        icon, label = MODE_TITLES.get(self.mode, ("", self.mode.title()))
        caps = getattr(self.app, 'caps_text', lambda x: x)
        return f"{icon}  {caps(label)}"


class KeyBadge(Static):
    """A single key badge with rounded border"""

    DEFAULT_CSS = """
    KeyBadge {
        width: auto;
        height: 3;
        padding: 0 1;
        margin: 0 1;
        border: round $primary;
        background: $surface;
        content-align: center middle;
    }

    KeyBadge.active {
        border: round $accent;
        background: $primary;
        color: $background;
        text-style: bold;
    }

    KeyBadge.dim {
        border: round $surface-darken-2;
        color: $text-muted;
    }
    """

    def __init__(self, text: str, **kwargs):
        super().__init__(**kwargs)
        self.text = text

    def render(self) -> str:
        return self.text


class ModeIndicator(Horizontal):
    """Shows mode indicators with F-keys"""

    DEFAULT_CSS = """
    ModeIndicator {
        width: 100%;
        height: 3;
        background: $background;
        padding: 0 4;
    }

    #keys-left {
        width: auto;
        height: 3;
    }

    #keys-spacer {
        width: 1fr;
        height: 3;
    }

    #keys-right {
        width: auto;
        height: 3;
        margin-right: 2;
    }
    """

    def __init__(self, current_mode: Mode, **kwargs):
        super().__init__(**kwargs)
        self.current_mode = current_mode

    def compose(self) -> ComposeResult:
        # Mode badges with F-keys
        with Horizontal(id="keys-left"):
            for mode in Mode:
                info = MODE_INFO[mode]
                badge = KeyBadge(f"{info['key']} {info['emoji']}", id=f"key-{mode.name.lower()}")
                if mode == self.current_mode:
                    badge.add_class("active")
                else:
                    badge.add_class("dim")
                yield badge

        # Spacer pushes the rest to the right
        yield Static("", id="keys-spacer")

        # Theme (F9) and Volume (F10 mute, F11 down, F12 up) on the right
        with Horizontal(id="keys-right"):
            is_dark = "dark" in getattr(self.app, 'active_theme', 'dark')
            theme_icon = ICON_MOON if is_dark else ICON_SUN
            theme_badge = KeyBadge(f"F9 {theme_icon}", id="key-theme")
            theme_badge.add_class("dim")
            yield theme_badge

            # Volume controls: F10 mute (shows current level icon), F11 down, F12 up
            volume_badge = KeyBadge(f"F10 {ICON_VOLUME_HIGH}", id="key-volume")
            volume_badge.add_class("dim")
            yield volume_badge

            vol_down_badge = KeyBadge(f"F11 {ICON_VOLUME_DOWN}", id="key-vol-down")
            vol_down_badge.add_class("dim")
            yield vol_down_badge

            vol_up_badge = KeyBadge(f"F12 {ICON_VOLUME_UP}", id="key-vol-up")
            vol_up_badge.add_class("dim")
            yield vol_up_badge

    def update_mode(self, mode: Mode) -> None:
        self.current_mode = mode
        for m in Mode:
            try:
                badge = self.query_one(f"#key-{m.name.lower()}", KeyBadge)
                badge.remove_class("active", "dim")
                if m == mode:
                    badge.add_class("active")
                else:
                    badge.add_class("dim")
            except NoMatches:
                pass

    def update_theme_icon(self) -> None:
        """Update the theme badge icon (F9)"""
        try:
            badge = self.query_one("#key-theme", KeyBadge)
            is_dark = "dark" in getattr(self.app, 'active_theme', 'dark')
            badge.text = f"F9 {ICON_MOON if is_dark else ICON_SUN}"
            badge.refresh()
        except NoMatches:
            pass

    def update_volume_indicator(self, volume_level: int) -> None:
        """Update volume indicator badge with level icon (F10)"""
        try:
            badge = self.query_one("#key-volume", KeyBadge)
            if volume_level == 0:
                icon = ICON_VOLUME_OFF
            elif volume_level <= 25:
                icon = ICON_VOLUME_LOW
            elif volume_level <= 50:
                icon = ICON_VOLUME_MED
            else:
                icon = ICON_VOLUME_HIGH
            badge.text = f"F10 {icon}"
            badge.refresh()
        except NoMatches:
            pass


class SpeechIndicator(Static):
    """Shows whether speech is on/off"""

    def __init__(self, speech_on: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.speech_on = speech_on

    def render(self) -> str:
        if self.speech_on:
            return "[bold green]🔊 Speech ON[/]"
        else:
            return "[dim]🔇 Speech off[/]"

    def toggle(self) -> bool:
        self.speech_on = not self.speech_on
        self.refresh()
        return self.speech_on


class ViewportContainer(Container):
    """
    The 10x6 inch viewport that contains all mode content.
    Centered on screen with purple border filling the rest.
    """
    pass


class BatteryIndicator(Static):
    """
    Shows battery status in the top-right corner.
    Gracefully hides if no battery is available or on error.
    """

    DEFAULT_CSS = """
    BatteryIndicator {
        width: auto;
        height: 1;
        color: $primary;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._battery_available = False
        self._battery_path = None
        self._update_timer = None

    def on_mount(self) -> None:
        """Find battery and start periodic updates"""
        self._find_battery()
        if self._battery_available:
            # Update every 30 seconds
            self._update_timer = self.set_interval(30, self._update_battery)

    def _find_battery(self) -> None:
        """Try to find a battery in /sys/class/power_supply/"""
        try:
            power_supply_path = "/sys/class/power_supply"
            if not os.path.exists(power_supply_path):
                return

            for entry in os.listdir(power_supply_path):
                entry_path = os.path.join(power_supply_path, entry)
                type_file = os.path.join(entry_path, "type")
                try:
                    with open(type_file) as f:
                        if f.read().strip() == "Battery":
                            # Found a battery. Verify we can read capacity
                            capacity_file = os.path.join(entry_path, "capacity")
                            if os.path.exists(capacity_file):
                                self._battery_path = entry_path
                                self._battery_available = True
                                return
                except (IOError, OSError, PermissionError):
                    continue
        except (IOError, OSError, PermissionError):
            pass

    def _read_battery_status(self) -> tuple[int, bool] | None:
        """Read battery percentage and charging status. Returns None on error."""
        if not self._battery_available or not self._battery_path:
            return None

        try:
            # Read capacity (percentage)
            capacity_file = os.path.join(self._battery_path, "capacity")
            with open(capacity_file) as f:
                capacity = int(f.read().strip())

            # Read charging status
            status_file = os.path.join(self._battery_path, "status")
            charging = False
            if os.path.exists(status_file):
                with open(status_file) as f:
                    status = f.read().strip().lower()
                    charging = status in ("charging", "full")

            return (capacity, charging)
        except (IOError, OSError, PermissionError, ValueError):
            return None

    def _get_battery_icon(self, capacity: int, charging: bool) -> str:
        """Get the appropriate battery icon based on level and charging status"""
        if charging:
            return ICON_BATTERY_CHARGING
        elif capacity >= 95:
            return ICON_BATTERY_FULL
        elif capacity >= 60:
            return ICON_BATTERY_HIGH
        elif capacity >= 30:
            return ICON_BATTERY_MED
        elif capacity >= 10:
            return ICON_BATTERY_LOW
        else:
            return ICON_BATTERY_EMPTY

    def _update_battery(self) -> None:
        """Periodic update callback"""
        self.refresh()

    def render(self) -> str:
        """Render the battery indicator"""
        status = self._read_battery_status()
        if status is None:
            # Dev mode: show test battery if PURPLE_TEST_BATTERY is set
            if os.environ.get("PURPLE_TEST_BATTERY"):
                return ICON_BATTERY_FULL
            return ""

        capacity, charging = status
        icon = self._get_battery_icon(capacity, charging)
        return icon


class VolumeOverlay(Static):
    """Temporary overlay showing volume level when changed.

    Shows a large speaker icon and visual bars for kids to see clearly.
    Auto-hides after a brief delay.
    """

    DEFAULT_CSS = """
    VolumeOverlay {
        width: 24;
        height: 7;
        background: $surface;
        border: heavy $primary;
        content-align: center middle;
        text-align: center;
        padding: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._level = 100
        self._hide_timer = None

    def show_volume(self, level: int) -> None:
        """Show the overlay with current volume level."""
        self._level = level
        self.refresh()

        # Show the parent container (which handles positioning)
        try:
            center = self.app.query_one("#volume-overlay-center")
            center.add_class("visible")
        except Exception:
            pass

        # Cancel any existing timer
        if self._hide_timer:
            self._hide_timer.stop()

        # Auto-hide after 1.5 seconds
        self._hide_timer = self.set_timer(1.5, self._hide)

    def _hide(self) -> None:
        """Hide the overlay."""
        try:
            center = self.app.query_one("#volume-overlay-center")
            center.remove_class("visible")
        except Exception:
            pass
        self._hide_timer = None

    def render(self) -> str:
        """Render volume icon and bars."""
        # Pick icon and label based on level
        if self._level == 0:
            icon = ICON_VOLUME_OFF
            label = "mute"
        elif self._level <= 25:
            icon = ICON_VOLUME_LOW
            label = "quiet"
        elif self._level <= 50:
            icon = ICON_VOLUME_MED
            label = "medium"
        elif self._level <= 75:
            icon = ICON_VOLUME_HIGH
            label = "loud"
        else:
            icon = ICON_VOLUME_HIGH
            label = "max"

        # Build visual bars: 4 bars for 25/50/75/100 (using wider blocks)
        bars = ""
        for threshold in [25, 50, 75, 100]:
            if self._level >= threshold:
                bars += "██"
            else:
                bars += "░░"

        return f"{icon}  {bars}\n{label}"


class PurpleApp(App):
    """
    Purple Computer: The calm computer for kids.

    F1-F3: Switch between modes (Ask, Play, Write)
    F9: Toggle dark/light theme
    F10: Mute/unmute, F11: Volume down, F12: Volume up
    Escape (long hold): Parent mode
    Caps Lock: Toggle big/small letters
    Ctrl+V: Cycle views (Screen, Line, Ears)
    """

    CSS = """
    Screen {
        background: $background;
    }

    #outer-container {
        width: 100%;
        height: 100%;
        align: center middle;
        background: $background;
    }

    #viewport-wrapper {
        width: auto;
        height: auto;
    }

    #title-row {
        width: 100;
        height: 1;
        margin-bottom: 1;
    }

    #title-spacer-left {
        width: 12;  /* Balance right side: caps (~8) + battery (~3) + margin */
    }

    #mode-title {
        width: 1fr;
        text-align: center;
    }

    #caps-indicator {
        width: auto;
        height: 1;
        margin-right: 2;
        color: $text-muted;
    }

    #caps-indicator.active {
        color: $accent;
    }

    #battery-indicator {
        width: auto;
    }

    #viewport {
        width: 100;
        height: 28;
        border: heavy $primary;
        background: $surface;
        padding: 1;
        layer: base;
    }

    #mode-indicator {
        dock: bottom;
        height: 3;
        background: $background;
    }

    #content-area {
        width: 100%;
        height: 100%;
    }

    .mode-content {
        width: 100%;
        height: 100%;
    }

    /* View-specific styles */
    .view-line #viewport {
        height: 3;
    }

    .view-ears #viewport {
        display: none;
    }

    .view-ears #mode-indicator {
        display: none;
    }

    /* Update dialog */
    #update-dialog {
        width: 60;
        height: auto;
        padding: 2 4;
        background: $surface;
        border: heavy $primary;
    }

    #update-dialog Label {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }

    #update-buttons {
        width: 100%;
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    #update-buttons Button {
        margin: 0 2;
    }

    /* Volume overlay: centered on top of viewport */
    #volume-overlay-center {
        display: none;
        layer: overlay;
        width: 100;
        height: 28;
        align: center middle;
        offset: 0 -28;
        margin-bottom: -28;
    }

    #volume-overlay-center.visible {
        display: block;
    }

    #volume-overlay-middle {
        width: auto;
        height: auto;
    }

    #viewport-wrapper {
        layers: base overlay;
    }
    """

    # Mode switching uses F-keys for robustness
    # Note: These bindings are for fallback only; evdev handles actual keyboard input
    BINDINGS = [
        Binding("f1", "switch_mode('ask')", "Ask", show=False, priority=True),
        Binding("f2", "switch_mode('play')", "Play", show=False, priority=True),
        Binding("f3", "switch_mode('write')", "Write", show=False, priority=True),
        Binding("f9", "toggle_theme", "Theme", show=False, priority=True),
        Binding("f10", "volume_mute", "Mute", show=False, priority=True),
        Binding("f11", "volume_down", "Vol-", show=False, priority=True),
        Binding("f12", "volume_up", "Vol+", show=False, priority=True),
        Binding("ctrl+v", "cycle_view", "View", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.active_mode = Mode.ASK
        self.active_view = View.SCREEN
        self.active_theme = "purple-dark"
        self.speech_enabled = False
        self.volume_level = VOLUME_DEFAULT  # 0-100, F10 mute, F11 down, F12 up
        self._volume_before_mute = VOLUME_DEFAULT  # Remember level when muting
        self._pending_update = None  # Set by main() if breaking update available

        # Power management
        self._idle_timer = None
        self._sleep_screen_active = False

        # Keyboard state for caps lock tracking and mode detection
        self.keyboard = create_keyboard_state(
            sticky_grace_period=STICKY_SHIFT_GRACE,
            double_tap_threshold=DOUBLE_TAP_TIME,
            escape_hold_threshold=ESCAPE_HOLD_THRESHOLD,
        )
        self.keyboard.mode = detect_keyboard_mode()

        # Register callback for caps lock changes
        self.keyboard.caps.on_change(self._on_caps_change)

        # Direct evdev keyboard input (replaces terminal on_key)
        self._keyboard_state_machine = KeyboardStateMachine()
        self._evdev_reader: EvdevReader | None = None
        self._escape_hold_timer = None  # Timer for detecting escape long-hold

        # Register our purple themes
        self.register_theme(
            Theme(
                name="purple-dark",
                primary="#9b7bc4",
                secondary="#7a5ca8",
                warning="#c4a060",
                error="#c46b7b",
                success="#7bc48a",
                accent="#c4a0e8",
                background="#1e1033",
                surface="#2a1845",
                panel="#2a1845",
                dark=True,
            )
        )
        self.register_theme(
            Theme(
                name="purple-light",
                primary="#7a4ca0",
                secondary="#6a3c90",
                warning="#a08040",
                error="#a04050",
                success="#40a050",
                accent="#6a3c90",
                background="#f0e8f8",
                surface="#e8daf0",
                panel="#e8daf0",
                dark=False,
            )
        )
        self.theme = "purple-dark"

    def compose(self) -> ComposeResult:
        """Create the UI layout"""
        with Container(id="outer-container"):
            with Vertical(id="viewport-wrapper"):
                with Horizontal(id="title-row"):
                    yield Static("", id="title-spacer-left")  # Balance for right elements
                    yield ModeTitle(id="mode-title")
                    yield Static(f"{ICON_CAPS_LOCK} abc", id="caps-indicator")
                    yield BatteryIndicator(id="battery-indicator")
                with ViewportContainer(id="viewport"):
                    yield Container(id="content-area")
                with Center(id="volume-overlay-center"):
                    with Middle(id="volume-overlay-middle"):
                        yield VolumeOverlay(id="volume-overlay")
            yield ModeIndicator(self.active_mode, id="mode-indicator")

    async def on_mount(self) -> None:
        """Called when app starts"""
        self._apply_theme()
        self._load_mode_content()

        # Start direct evdev keyboard reader
        # This reads keyboard events directly, bypassing the terminal
        self._evdev_reader = EvdevReader(
            callback=self._handle_raw_key_event,
            grab=True,  # Grab keyboard exclusively in kiosk mode
        )
        await self._evdev_reader.start()

        # Start idle detection timer
        # In demo mode, check every second for responsiveness
        # In normal mode, check every 5 seconds to save resources
        import os
        from .power_manager import IDLE_SLEEP_UI, IDLE_SHUTDOWN

        if os.environ.get("PURPLE_SLEEP_DEMO"):
            check_interval = 1.0
            self.notify(
                f"Demo: sleep@{IDLE_SLEEP_UI}s, off@{IDLE_SHUTDOWN}s",
                title="Sleep Demo",
                timeout=5,
            )
        else:
            check_interval = 5.0

        self._idle_timer = self.set_interval(check_interval, self._check_idle_state)

        # Show breaking update prompt if available
        if self._pending_update:
            self._show_update_prompt()

    async def on_unmount(self) -> None:
        """Called when app is shutting down"""
        # Clean up evdev reader
        if self._evdev_reader:
            await self._evdev_reader.stop()
            self._evdev_reader = None

    def suspend_with_terminal_input(self):
        """
        Context manager to suspend the TUI and allow terminal input.

        Use this instead of self.suspend() when you need to call input()
        or run interactive programs that read from stdin.

        Example:
            with self.app.suspend_with_terminal_input():
                input("Press Enter...")

        This releases the evdev keyboard grab so the terminal can receive
        input, then reacquires it when the context exits.
        """
        from contextlib import contextmanager

        @contextmanager
        def _suspend_ctx():
            # Release evdev grab so terminal can receive keyboard input
            if self._evdev_reader:
                self._evdev_reader.release_grab()

            try:
                with self.suspend():
                    yield
            finally:
                # Reacquire grab when resuming
                if self._evdev_reader:
                    self._evdev_reader.reacquire_grab()
                # Reset keyboard state to avoid stuck keys
                self._keyboard_state_machine.reset()

        return _suspend_ctx()

    async def _handle_raw_key_event(self, event: RawKeyEvent) -> None:
        """
        Handle raw keyboard events from evdev.

        This is called by EvdevReader for each key press/release.
        Events are processed through KeyboardStateMachine to produce actions.
        """
        # Record user activity for idle detection
        self._record_user_activity()

        # Process through state machine
        actions = self._keyboard_state_machine.process(event)

        for action in actions:
            await self._dispatch_keyboard_action(action)

    async def _dispatch_keyboard_action(self, action) -> None:
        """Dispatch a keyboard action to the appropriate handler."""
        if isinstance(action, ModeAction):
            if action.mode == 'ask':
                self.action_switch_mode('ask')
            elif action.mode == 'play':
                self.action_switch_mode('play')
            elif action.mode == 'write':
                self.action_switch_mode('write')
            elif action.mode == 'parent':
                self.action_parent_mode()
            return

        if isinstance(action, CapsLockAction):
            self.keyboard.handle_caps_lock_press()
            return

        if isinstance(action, LongHoldAction):
            if action.key == 'escape':
                # Long-hold escape handled via ModeAction('parent')
                pass
            return

        # Handle escape key for long-hold detection
        # Only start timer on fresh press, not on repeat events (which would restart the timer)
        if isinstance(action, ControlAction) and action.action == 'escape':
            if action.is_down and not action.is_repeat:
                self._start_escape_hold_timer()
            elif not action.is_down:
                self._cancel_escape_hold_timer()
            # Don't return - let escape events propagate to modes for other uses

        # Handle global toggles (F9 theme, F10-F12 volume)
        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'theme_toggle':
                self.action_toggle_theme()
                return
            if action.action == 'volume_mute':
                self.action_volume_mute()
                return
            if action.action == 'volume_down':
                self.action_volume_down()
                return
            if action.action == 'volume_up':
                self.action_volume_up()
                return

        # Check if a modal screen is active (e.g., ParentMenu)
        # screen_stack[0] is the base screen, anything above is a modal
        if len(self.screen_stack) > 1:
            active_screen = self.screen
            if hasattr(active_screen, 'handle_keyboard_action'):
                await active_screen.handle_keyboard_action(action)
            return

        # Dispatch to the current mode widget
        mode_id = f"mode-{self.active_mode.name.lower()}"
        try:
            content_area = self.query_one("#content-area")
            mode_widget = content_area.query_one(f"#{mode_id}")

            # Call the mode's action handler if it exists
            if hasattr(mode_widget, 'handle_keyboard_action'):
                await mode_widget.handle_keyboard_action(action)
        except NoMatches:
            pass

    def _start_escape_hold_timer(self) -> None:
        """Schedule a one-shot timer to trigger parent mode after 1s.

        Uses set_timer (not call_later) because it returns a Timer object
        that can be cancelled if escape is released before 1s.
        """
        self._cancel_escape_hold_timer()  # Cancel any existing timer
        self._escape_hold_timer = self.set_timer(ESCAPE_HOLD_THRESHOLD, self._check_escape_hold)

    def _cancel_escape_hold_timer(self) -> None:
        """Cancel the escape hold timer."""
        if self._escape_hold_timer:
            self._escape_hold_timer.stop()
            self._escape_hold_timer = None

    def _check_escape_hold(self) -> None:
        """Called by timer after 1s. Trigger parent mode if escape still held."""
        if self._keyboard_state_machine.check_escape_hold():
            self._cancel_escape_hold_timer()
            self.action_parent_mode()

    def _reset_viewport_border(self) -> None:
        """Reset viewport border to default purple."""
        try:
            from textual.color import Color
            viewport = self.query_one("#viewport")
            # Get primary color based on current theme
            primary_color = "#9b7bc4" if self.active_theme == "purple-dark" else "#7a4ca0"
            viewport.styles.border = ("heavy", Color.parse(primary_color))
        except Exception:
            pass

    def _show_update_prompt(self) -> None:
        """Show a prompt for breaking updates"""
        from textual.widgets import Button, Label
        from textual.containers import Horizontal
        from textual.screen import ModalScreen

        update_info = self._pending_update

        class UpdateScreen(ModalScreen):
            """Modal screen for update prompt"""

            BINDINGS = [("escape", "dismiss", "Cancel")]

            def compose(self):
                with Container(id="update-dialog"):
                    yield Label(f"Purple Computer {update_info['version']} is available!")
                    yield Label(update_info['message'])
                    yield Label("")
                    yield Label("This is a major update. Would you like to update now?")
                    with Horizontal(id="update-buttons"):
                        yield Button("Update", id="update-yes", variant="primary")
                        yield Button("Later", id="update-no")

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "update-yes":
                    self.dismiss(True)
                else:
                    self.dismiss(False)

            async def handle_keyboard_action(self, action) -> None:
                """Handle keyboard actions from evdev."""
                if isinstance(action, ControlAction) and action.is_down:
                    if action.action == 'enter':
                        self.dismiss(True)  # Update
                    elif action.action == 'escape':
                        self.dismiss(False)  # Later

        def handle_update_result(should_update: bool) -> None:
            if should_update:
                from .updater import apply_breaking_update
                if apply_breaking_update():
                    # Restart the app
                    import sys
                    import os
                    os.execv(sys.executable, [sys.executable] + sys.argv)

        self.push_screen(UpdateScreen(), handle_update_result)

    def _apply_theme(self) -> None:
        """Apply the current color theme"""
        self.theme = self.active_theme
        # Update mode indicator to show current theme
        try:
            indicator = self.query_one("#mode-indicator", ModeIndicator)
            indicator.refresh()
        except NoMatches:
            pass

    def _check_idle_state(self) -> None:
        """Check if we should enter sleep mode due to inactivity."""
        # Don't check if sleep screen is already showing
        if self._sleep_screen_active:
            return

        try:
            # Import threshold at runtime so demo mode env var is respected
            from .power_manager import IDLE_SLEEP_UI

            pm = get_power_manager()
            idle_seconds = pm.get_idle_seconds()

            if idle_seconds >= IDLE_SLEEP_UI:
                self._show_sleep_screen()
        except Exception as e:
            # In demo mode, show errors for debugging
            import os
            if os.environ.get("PURPLE_SLEEP_DEMO"):
                self.notify(f"Idle check error: {e}", title="Error", timeout=5)

    def _show_sleep_screen(self) -> None:
        """Show the sleep screen overlay."""
        if self._sleep_screen_active:
            return

        try:
            from .modes.sleep_screen import SleepScreen

            self._sleep_screen_active = True

            def on_sleep_screen_dismiss() -> None:
                self._sleep_screen_active = False
                # Re-enable DPMS disable (screen stays on during normal use)
                try:
                    pm = get_power_manager()
                    pm.disable_dpms()
                except Exception:
                    pass

            self.push_screen(SleepScreen(), on_sleep_screen_dismiss)
        except Exception as e:
            # If sleep screen fails, show error in demo mode
            self._sleep_screen_active = False
            import os
            if os.environ.get("PURPLE_SLEEP_DEMO"):
                self.notify(f"Sleep screen error: {e}", title="Error", timeout=5)

    def _record_user_activity(self) -> None:
        """Record that user is active. Resets idle timer."""
        try:
            pm = get_power_manager()
            pm.record_activity()
        except Exception:
            pass

    async def on_event(self, event: events.Event) -> None:
        """Record activity for any key press. Runs before widgets can stop it.

        This is called BEFORE event dispatch, so child widgets calling
        event.stop() won't prevent activity from being recorded.
        """
        if isinstance(event, events.Key):
            self._record_user_activity()
        # Always call super to continue normal event dispatch
        await super().on_event(event)

    def on_screen_resume(self, event: events.ScreenResume) -> None:
        """Restore focus when returning from overlay screens (sleep, parent menu)."""
        # Find the current mode widget and restore focus
        mode_id = f"mode-{self.active_mode.name.lower()}"
        try:
            content_area = self.query_one("#content-area")
            mode_widget = content_area.query_one(f"#{mode_id}")
            self._focus_mode(mode_widget)
        except NoMatches:
            pass

    def _create_mode_widget(self, mode: Mode):
        """Create a new mode widget"""
        if mode == Mode.ASK:
            from .modes.ask_mode import AskMode
            return AskMode(classes="mode-content")
        elif mode == Mode.PLAY:
            from .modes.play_mode import PlayMode
            return PlayMode(classes="mode-content")
        elif mode == Mode.WRITE:
            from .modes.write_mode import WriteMode
            return WriteMode(classes="mode-content")
        return None

    def _load_mode_content(self) -> None:
        """Load the content widget for the current mode"""
        content_area = self.query_one("#content-area")

        # Hide all existing mode widgets
        for child in content_area.children:
            child.display = False

        # Check if we already have this mode mounted
        mode_id = f"mode-{self.active_mode.name.lower()}"
        try:
            existing = content_area.query_one(f"#{mode_id}")
            existing.display = True
            self._focus_mode(existing)
            return
        except NoMatches:
            pass

        # Create and mount new widget
        widget = self._create_mode_widget(self.active_mode)
        if widget:
            widget.id = mode_id
            content_area.mount(widget)
            # Focus will happen in on_mount of the widget

    def _focus_mode(self, widget) -> None:
        """Focus the appropriate element in a mode widget"""
        # Each mode has a primary focusable element
        if self.active_mode == Mode.ASK:
            try:
                widget.query_one("#ask-input").focus()
            except Exception:
                pass
        elif self.active_mode == Mode.PLAY:
            widget.focus()
        elif self.active_mode == Mode.WRITE:
            try:
                widget.query_one("#art-canvas").focus()
            except Exception:
                widget.focus()
        else:
            widget.focus()

    def _update_view_class(self) -> None:
        """Update CSS class based on current view"""
        container = self.query_one("#outer-container")
        container.remove_class("view-screen", "view-line", "view-ears")

        if self.active_view == View.SCREEN:
            container.add_class("view-screen")
        elif self.active_view == View.LINE:
            container.add_class("view-line")
        elif self.active_view == View.EARS:
            container.add_class("view-ears")

    def action_switch_mode(self, mode_name: str) -> None:
        """Switch to a different mode (F1-F3)"""
        mode_map = {
            "ask": Mode.ASK,
            "play": Mode.PLAY,
            "write": Mode.WRITE,
        }
        new_mode = mode_map.get(mode_name, Mode.ASK)

        if new_mode != self.active_mode:
            # Reset viewport border when leaving write mode
            if self.active_mode == Mode.WRITE:
                self._reset_viewport_border()

            self.active_mode = new_mode
            self._load_mode_content()

            # Update title
            try:
                title = self.query_one("#mode-title", ModeTitle)
                title.set_mode(mode_name)
            except NoMatches:
                pass

            # Update mode indicator
            try:
                indicator = self.query_one("#mode-indicator", ModeIndicator)
                indicator.update_mode(new_mode)
            except NoMatches:
                pass

    def action_toggle_theme(self) -> None:
        """Toggle between dark and light mode (F9)"""
        self.active_theme = "purple-light" if self.active_theme == "purple-dark" else "purple-dark"
        self._apply_theme()
        # Update theme icon in mode indicator
        try:
            indicator = self.query_one("#mode-indicator", ModeIndicator)
            indicator.update_theme_icon()
        except NoMatches:
            pass

    def action_volume_mute(self) -> None:
        """Toggle mute on/off (F10)"""
        if self.volume_level > 0:
            # Mute: save current level and set to 0
            self._volume_before_mute = self.volume_level
            self.volume_level = 0
        else:
            # Unmute: restore previous level
            self.volume_level = self._volume_before_mute if self._volume_before_mute > 0 else VOLUME_DEFAULT
        self._apply_volume()

    def action_volume_down(self) -> None:
        """Decrease volume (F11)"""
        # Find current position in VOLUME_LEVELS and go down
        current_idx = 0
        for i, level in enumerate(VOLUME_LEVELS):
            if self.volume_level >= level:
                current_idx = i
        if current_idx > 0:
            self.volume_level = VOLUME_LEVELS[current_idx - 1]
            self._apply_volume()

    def action_volume_up(self) -> None:
        """Increase volume (F12)"""
        # Find current position in VOLUME_LEVELS and go up
        current_idx = len(VOLUME_LEVELS) - 1
        for i, level in enumerate(VOLUME_LEVELS):
            if self.volume_level <= level:
                current_idx = i
                break
        if current_idx < len(VOLUME_LEVELS) - 1:
            self.volume_level = VOLUME_LEVELS[current_idx + 1]
            self._apply_volume()

    def _apply_volume(self) -> None:
        """Apply volume level to TTS and update UI"""
        from . import tts
        tts.set_muted(self.volume_level == 0)
        # TODO: Set actual volume level when TTS supports it

        # Update volume indicator badge
        try:
            indicator = self.query_one("#mode-indicator", ModeIndicator)
            indicator.update_volume_indicator(self.volume_level)
        except NoMatches:
            pass

        # Show prominent volume overlay
        try:
            overlay = self.query_one("#volume-overlay", VolumeOverlay)
            overlay.show_volume(self.volume_level)
        except NoMatches:
            pass

    def action_cycle_view(self) -> None:
        """Cycle through views: Screen -> Line -> Ears -> Screen (Ctrl+V)"""
        views = [View.SCREEN, View.LINE, View.EARS]
        current_idx = views.index(self.active_view)
        self.active_view = views[(current_idx + 1) % len(views)]
        self._update_view_class()

    def toggle_speech(self) -> bool:
        """Toggle speech on/off, returns new state"""
        try:
            indicator = self.query_one("#speech-indicator", SpeechIndicator)
            return indicator.toggle()
        except NoMatches:
            self.speech_enabled = not self.speech_enabled
            return self.speech_enabled

    def _on_caps_change(self, caps_on: bool) -> None:
        """Called when caps lock state changes"""
        self._refresh_caps_sensitive_widgets()
        try:
            indicator = self.query_one("#caps-indicator", Static)
            if caps_on:
                indicator.update(f"{ICON_CAPS_LOCK} ABC")
                indicator.add_class("active")
            else:
                indicator.update(f"{ICON_CAPS_LOCK} abc")
                indicator.remove_class("active")
        except NoMatches:
            pass

    def action_parent_mode(self) -> None:
        """Enter parent mode. Shows admin menu for parents."""
        from .modes.parent_mode import ParentMenu
        # Cancel escape hold timer and reset state
        self._cancel_escape_hold_timer()
        self.keyboard.escape_hold.reset()
        self._keyboard_state_machine.reset()  # Clear all pressed keys state
        self.push_screen(ParentMenu())

    def on_key(self, event: events.Key) -> None:
        """
        Handle terminal key events.

        NOTE: With evdev architecture, all keyboard input is handled via
        _handle_raw_key_event(). This handler exists only to suppress
        terminal input (which we're bypassing by reading evdev directly).

        The terminal (Alacritty) is display-only; keyboard input flows:
        evdev → EvdevReader → KeyboardStateMachine → App
        """
        # Suppress all terminal keyboard events since we handle via evdev
        event.stop()
        event.prevent_default()

    def _refresh_caps_sensitive_widgets(self) -> None:
        """Refresh all widgets that change based on caps mode"""
        widget_ids = [
            "#mode-title",
            "#example-hint",
            "#autocomplete-hint",
            "#write-header",
            "#canvas-header",
            "#input-prompt",
            "#speech-indicator",
            "#eraser-indicator",
            "#coming-soon",
            "#art-canvas",
        ]
        for widget_id in widget_ids:
            try:
                widget = self.query_one(widget_id)
                widget.refresh()
            except NoMatches:
                pass

        # Refresh all HistoryLine widgets in ask mode
        try:
            from .modes.ask_mode import HistoryLine
            for widget in self.query(HistoryLine):
                widget.refresh()
        except Exception:
            pass

        # Refresh PlayGrid in play mode
        try:
            from .modes.play_mode import PlayGrid
            for widget in self.query(PlayGrid):
                widget.refresh()
        except Exception:
            pass

    @property
    def caps_mode(self) -> bool:
        """Whether caps lock is on"""
        return self.keyboard.caps.caps_lock_on

    def caps_text(self, text: str) -> str:
        """Return text in caps if caps mode is on"""
        return text.upper() if self.caps_mode else text


def main():
    """Entry point for Purple Computer"""
    import sys
    import os
    import signal
    import atexit

    # Verify evdev is available before anything else
    # Purple Computer requires Linux with evdev for keyboard input
    try:
        check_evdev_available()
    except RuntimeError as e:
        print(f"\n  Purple Computer cannot start:\n  {e}\n", file=sys.stderr)
        sys.exit(1)

    # Restore terminal state on exit (kernel auto-releases evdev grab)
    def restore_terminal():
        os.system('stty sane 2>/dev/null')

    atexit.register(restore_terminal)
    signal.signal(signal.SIGTERM, lambda s, f: (restore_terminal(), sys.exit(0)))
    signal.signal(signal.SIGINT, lambda s, f: (restore_terminal(), sys.exit(0)))

    # Note: We intentionally do NOT filter stderr here.
    # Textual renders to stderr, so any pipe redirection causes UI lag.
    # ALSA noise should be silenced at the source (see tts.py for handlers).

    # Check for updates before starting
    from .updater import auto_update_if_available
    update_result = auto_update_if_available()

    if update_result == "updated":
        # Minor update applied. Restart the app
        import os
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # If breaking update available, the app will show a prompt
    # (handled in PurpleApp.on_mount)

    try:
        app = PurpleApp()
    except RuntimeError as e:
        # Friendly error for configuration issues
        print(f"\n  Purple Computer cannot start:\n  {e}\n", file=sys.stderr)
        sys.exit(1)

    if update_result and update_result.startswith("breaking:"):
        # Pass breaking update info to app
        parts = update_result.split(":", 2)
        app._pending_update = {
            "version": parts[1],
            "message": parts[2] if len(parts) > 2 else "A new version is available"
        }
    app.run(mouse=False)  # Purple Computer is keyboard-only


if __name__ == "__main__":
    main()
