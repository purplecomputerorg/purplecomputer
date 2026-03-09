#!/usr/bin/env python3
"""
Purple Computer: Main Textual TUI Application

The calm computer for kids. Designed for 4-7 and fun for 2-8+.
A creativity device, not an entertainment device.

IMPORTANT: Requires Linux with evdev for keyboard input.
The terminal (Alacritty) is display-only; keyboard input is read
directly from evdev, bypassing the terminal. See:
  guides/keyboard-architecture.md

Keyboard controls:
- Escape (tap): Room picker (1-4 for rooms, arrows to navigate/volume)
- Escape (long hold): Parent menu
- Media keys: Volume mute/down/up
- Shift (tap): Sticky shift for one character
- Shift (double-tap): Toggle caps lock
- Caps Lock key: Remapped to Shift
"""

# Suppress ONNX runtime warnings early (before any imports that might load it)
import os
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import asyncio
import time

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.theme import Theme
from textual import events
from enum import Enum

from .constants import (
    ICON_CHAT, ICON_MUSIC, ICON_PALETTE, ICON_CODE, ICON_MENU,
    ROOM_TITLES,
    STICKY_SHIFT_GRACE, ESCAPE_HOLD_THRESHOLD,
    ICON_BATTERY_FULL, ICON_BATTERY_HIGH, ICON_BATTERY_MED,
    ICON_BATTERY_LOW, ICON_BATTERY_EMPTY, ICON_BATTERY_CHARGING,
    ICON_VOLUME_OFF, ICON_VOLUME_LOW, ICON_VOLUME_MED, ICON_VOLUME_HIGH,
    ICON_CAPS_LOCK, ICON_SHIFT,
    VOLUME_LEVELS, VOLUME_DEFAULT,
    VIEWPORT_WIDTH, VIEWPORT_HEIGHT,
    ROOM_PLAY, ROOM_MUSIC, ROOM_ART, ROOM_CODE,
    USB_UPDATE_SIGNAL_FILE,
)
from .keyboard import (
    create_keyboard_state, detect_keyboard_mode,
    KeyboardStateMachine, CharacterAction, NavigationAction,
    RoomAction, ControlAction, CapsLockAction, LongHoldAction,
)
from .input import EvdevReader, RawKeyEvent, PowerButtonReader, PowerButtonEvent, check_evdev_available
from .power_manager import get_power_manager
from .demo import DemoPlayer, get_demo_script, get_speed_multiplier
from .recording import RecordingManager
from .rooms.code_room import WatchMeRequested
from .rooms.art_room import ColorLegend, PaintModeChanged
from .rooms.parent_menu import apply_saved_display_settings
from .room_picker import RoomPickerScreen


class Room(Enum):
    """The 4 core rooms of Purple Computer"""
    PLAY = 1     # Math and emoji REPL
    MUSIC = 2    # Music and art grid
    ART = 3      # Simple drawing canvas
    CODE = 4     # Visual block programming


class View(Enum):
    """The 3 core views. Reduce screen time feeling."""
    SCREEN = 1   # 10x6" viewport
    LINE = 2     # 10" wide, 1 line height
    EARS = 3     # Screen off (blank)


class RoomTitle(Static):
    """Shows current mode title above the viewport"""

    DEFAULT_CSS = """
    RoomTitle {
        width: 100%;
        height: 1;
        text-align: center;
        color: $primary;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = ROOM_PLAY[0]
        self._recording_indicator = ""
        self.add_class("caps-sensitive")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.refresh()

    def set_recording_indicator(self, indicator: str) -> None:
        self._recording_indicator = indicator
        self.refresh()

    def render(self) -> str:
        icon, label = ROOM_TITLES.get(self.mode, ("", self.mode.title()))
        caps = getattr(self.app, 'caps_text', lambda x: x)
        title = f"{icon}  {caps(label)}"
        if self._recording_indicator:
            title = f"{self._recording_indicator}   {title}"
        return title


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


class RoomBadge(KeyBadge):
    """A room badge that shows icon + room name, responds to caps lock"""

    DEFAULT_CSS = """
    RoomBadge {
        width: 11;
    }
    """

    def __init__(self, icon: str, room_name: str, **kwargs):
        super().__init__(text="", **kwargs)
        self._icon = icon
        self._room_name = room_name
        self.add_class("caps-sensitive")

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        return f"{self._icon} {caps(self._room_name)}"


class RoomIndicator(Horizontal):
    """Shows mode indicators (icons + names) and mute indicator, centered"""

    DEFAULT_CSS = """
    RoomIndicator {
        width: 100%;
        height: 3;
        background: $background;
    }

    #keys-spacer-left {
        width: 1fr;
        height: 3;
    }

    #keys-center {
        width: auto;
        height: 3;
    }

    #keys-spacer-right {
        width: 1fr;
        height: 3;
    }

    #keys-right {
        width: auto;
        height: 3;
        margin-right: 2;
    }
    """

    def __init__(self, current_room: Room, **kwargs):
        super().__init__(**kwargs)
        self.current_room = current_room

    def compose(self) -> ComposeResult:
        yield Static("", id="keys-spacer-left")

        with Horizontal(id="keys-center"):
            # Esc badge for mode picker
            esc_badge = KeyBadge(f"Esc {ICON_MENU}", id="key-esc")
            esc_badge.add_class("dim")
            yield esc_badge

            # Room badges with icon + name
            room_info = {
                Room.PLAY: (ICON_CHAT, "Play"),
                Room.MUSIC: (ICON_MUSIC, "Music"),
                Room.ART: (ICON_PALETTE, "Art"),
                Room.CODE: (ICON_CODE, "Code"),
            }
            for room in Room:
                icon, name = room_info[room]
                badge = RoomBadge(icon, name, id=f"key-{room.name.lower()}")
                if room == self.current_room:
                    badge.add_class("active")
                else:
                    badge.add_class("dim")
                yield badge

        yield Static("", id="keys-spacer-right")

        # Mute indicator on the right (only visible when muted)
        with Horizontal(id="keys-right"):
            mute_badge = KeyBadge(ICON_VOLUME_OFF, id="key-mute")
            mute_badge.add_class("dim")
            mute_badge.display = False
            yield mute_badge

    def update_room(self, room: Room) -> None:
        self.current_room = room
        for m in Room:
            try:
                badge = self.query_one(f"#key-{m.name.lower()}", RoomBadge)
                badge.remove_class("active", "dim")
                if m == room:
                    badge.add_class("active")
                else:
                    badge.add_class("dim")
            except NoMatches:
                pass

    def update_volume_indicator(self, volume_level: int) -> None:
        """Show/hide mute indicator based on volume level."""
        try:
            badge = self.query_one("#key-mute", KeyBadge)
            badge.display = (volume_level == 0)
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


class PurpleApp(App):
    """
    Purple Computer: The calm computer for kids.

    Escape (tap): Room picker
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

    #viewport-row {
        width: auto;
        height: auto;
    }

    #paint-legend {
        width: 4;
        height: 4;
        margin-left: 1;
        margin-top: __LEGEND_TOP_MARGIN__;
    }

    #title-row {
        width: __VIEWPORT_WIDTH__;
        height: 1;
        margin-bottom: 1;
    }

    #title-spacer-left {
        width: 12;  /* Balance right side: caps (~8) + battery (~3) + margin */
    }

    #room-title {
        width: 1fr;
        text-align: center;
    }

    #shift-indicator {
        width: auto;
        height: 1;
        margin-right: 1;
        color: $accent;
        display: none;
    }

    #shift-indicator.active {
        display: block;
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
        width: __VIEWPORT_WIDTH__;
        height: __VIEWPORT_HEIGHT__;
        border: heavy $primary;
        background: $surface;
    }

    #room-indicator {
        dock: bottom;
        height: 3;
        margin-top: 1;
        background: $background;
    }

    #content-area {
        width: 100%;
        height: 100%;
    }

    .room-content {
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

    .view-ears #room-indicator {
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
    """.replace("__VIEWPORT_WIDTH__", str(VIEWPORT_WIDTH)).replace("__VIEWPORT_HEIGHT__", str(VIEWPORT_HEIGHT)).replace("__LEGEND_TOP_MARGIN__", str(VIEWPORT_HEIGHT - 5))  # align legend 1 row above viewport bottom

    # Note: These bindings are for fallback only; evdev handles actual keyboard input
    BINDINGS = [
        Binding("f8", "take_screenshot", "Screenshot", show=False, priority=True),
        Binding("ctrl+v", "cycle_view", "View", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.active_room = Room.PLAY
        self.active_view = View.SCREEN
        self.active_theme = "purple-dark"
        self.speech_enabled = False
        self.volume_level = VOLUME_DEFAULT  # 0-100
        self._volume_before_mute = VOLUME_DEFAULT  # Remember level when muting
        self._pending_update = None  # Set by main() if breaking update available

        # Power management
        self._idle_timer = None
        self._sleep_screen_active = False
        self._power_button_reader: PowerButtonReader | None = None
        self._bye_screen_active = False
        self._app_suspended = False  # True while shell is open via parent menu
        self._lid_close_time: float | None = None  # App-level lid tracking (fallback)

        # Keyboard state for caps lock tracking and mode detection
        self.keyboard = create_keyboard_state(
            sticky_grace_period=STICKY_SHIFT_GRACE,
            escape_hold_threshold=ESCAPE_HOLD_THRESHOLD,
        )
        self.keyboard.mode = detect_keyboard_mode()

        # Register callback for caps lock changes
        self.keyboard.caps.on_change(self._on_caps_change)

        # Direct evdev keyboard input (replaces terminal on_key)
        self._keyboard_state_machine = KeyboardStateMachine()
        self._keyboard_state_machine.on_sticky_shift_change(self._on_sticky_shift_change)
        self._sticky_shift_timer = None
        self._evdev_reader: EvdevReader | None = None
        self._escape_hold_timer = None  # Timer for detecting escape long-hold
        self._escape_triggered_long_hold = False  # True if long-hold fired (avoid showing picker)
        self._modal_open_at_escape_press = False  # True if modal was open when ESC was pressed

        # Recording manager for Watch me! capture
        self._recording_manager = RecordingManager()
        self._watch_me_active: bool = False
        self._watch_me_room: str = ""
        self._watch_me_timer: asyncio.TimerHandle | None = None

        # Demo playback (dev mode only)
        self._demo_player: DemoPlayer | None = None
        self._demo_task = None

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
                background="#dcc8e8",
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
                    yield RoomTitle(id="room-title")
                    yield Static(ICON_SHIFT, id="shift-indicator")
                    yield Static(f"{ICON_CAPS_LOCK} abc", id="caps-indicator")
                    yield BatteryIndicator(id="battery-indicator")
                with Horizontal(id="viewport-row"):
                    with ViewportContainer(id="viewport"):
                        yield Container(id="content-area")
                    yield ColorLegend(id="paint-legend")
            yield RoomIndicator(self.active_room, id="room-indicator")

    async def on_mount(self) -> None:
        """Called when app starts"""
        self._apply_theme()
        apply_saved_display_settings()
        self._load_room_content()

        # Initialize color legend (visible in play mode, hidden otherwise)
        try:
            legend = self.query_one("#paint-legend", ColorLegend)
            if self.active_room == Room.PLAY:
                legend.set_visible(True)
                legend.set_active_row(-1)
            else:
                legend.set_visible(False)
        except NoMatches:
            pass

        # Start direct evdev keyboard reader (unless disabled for AI tools)
        # This reads keyboard events directly, bypassing the terminal
        if os.environ.get("PURPLE_NO_EVDEV") != "1":
            self._evdev_reader = EvdevReader(
                callback=self._handle_raw_key_event,
                grab=True,  # Grab keyboard exclusively in kiosk mode
            )
            await self._evdev_reader.start()
        else:
            self._evdev_reader = None

        # Start power button reader (separate device from keyboard)
        if os.environ.get("PURPLE_NO_EVDEV") != "1":
            from .power_manager import POWER_HOLD_SHUTDOWN
            self._power_button_reader = PowerButtonReader(
                callback=self._handle_power_button_event,
                hold_seconds=POWER_HOLD_SHUTDOWN,
            )
            try:
                await self._power_button_reader.start()
            except Exception:
                self._power_button_reader = None

        # Start idle detection timer (disabled in dev mode for AI training)
        # In demo mode, check every second for responsiveness
        # In normal mode, check every 5 seconds to save resources
        if os.environ.get("PURPLE_DEV_MODE") == "1":
            # Dev mode: no sleep screen (for AI training)
            self._idle_timer = None
        else:
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

        # Poll for USB update signal file (written by systemd usb_updater service)
        self._usb_update_timer = self.set_interval(2.0, self._check_usb_update_signal)

        # Show breaking update prompt if available
        if self._pending_update:
            self._show_update_prompt()

        # Auto-start demo if requested (for recording)
        if os.environ.get("PURPLE_DEMO_AUTOSTART"):
            # Wait 2 seconds for FFmpeg to stabilize (trimmed from final video)
            self.set_timer(2.0, self.start_demo)

        # In dev mode, check for screenshot and command trigger files (for AI tools)
        if os.environ.get("PURPLE_DEV_MODE") == "1":
            self._dev_log("[Mount] Starting dev mode timers...")
            self._screenshot_timer = self.set_interval(0.2, self._check_screenshot_trigger)
            self._command_timer = self.set_interval(0.1, self._check_command_trigger)
            self._dev_log("[Mount] Dev mode timers started")

    async def on_unmount(self) -> None:
        """Called when app is shutting down"""
        # Clean up evdev reader
        if self._evdev_reader:
            await self._evdev_reader.stop()
            self._evdev_reader = None

        # Clean up power button reader
        if self._power_button_reader:
            await self._power_button_reader.stop()
            self._power_button_reader = None

    def on_paint_mode_changed(self, event: PaintModeChanged) -> None:
        """Show/hide paint legend and update active row when paint mode changes."""
        try:
            legend = self.query_one("#paint-legend", ColorLegend)
            legend.set_visible(event.is_painting)
            legend.set_active_color(event.last_color)
        except NoMatches:
            pass

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
            self._app_suspended = True

            # Release evdev grab so terminal can receive keyboard input
            if self._evdev_reader:
                self._evdev_reader.release_grab()

            # Let logind handle power button directly while shell is open
            from .power_manager import set_logind_power_key
            logind_switched = set_logind_power_key("poweroff")

            try:
                with self.suspend():
                    yield
            finally:
                # Restore TUI control of power button
                if logind_switched:
                    set_logind_power_key("ignore")
                # Reacquire grab when resuming
                if self._evdev_reader:
                    self._evdev_reader.reacquire_grab()
                # Reset keyboard state to avoid stuck keys
                self._keyboard_state_machine.reset()
                self._app_suspended = False

        return _suspend_ctx()

    async def _handle_raw_key_event(self, event: RawKeyEvent) -> None:
        """
        Handle raw keyboard events from evdev.

        This is called by EvdevReader for each key press/release.
        Events are processed through KeyboardStateMachine to produce actions.
        """
        # Log evdev events in dev mode to debug mode switching
        if os.environ.get("PURPLE_DEV_MODE") == "1":
            self._dev_log(f"[Evdev] keycode={event.keycode} is_down={event.is_down}")

        # Record user activity for idle detection
        self._record_user_activity()

        # Flush stale TTS audio after long gaps (e.g., VM suspend/resume)
        now = time.monotonic()
        if now - getattr(self, '_last_evdev_time', now) > 5.0:
            from . import tts
            tts.stop()
        self._last_evdev_time = now

        # Process through state machine
        actions = self._keyboard_state_machine.process(event)

        for action in actions:
            if os.environ.get("PURPLE_DEV_MODE") == "1":
                self._dev_log(f"[Evdev] action={action} (current_room={self.active_room.name})")
            await self._dispatch_keyboard_action(action)

    async def _dispatch_keyboard_action(self, action) -> None:
        """Dispatch a keyboard action to the appropriate handler."""
        # During Watch me!, record events and restrict room switching
        if self._watch_me_active:
            if isinstance(action, RoomAction):
                if action.room == ROOM_CODE[0]:
                    # Switching to Code ends Watch me!: stop recording, insert blocks
                    await self._end_watch_me()
                # Other room switches blocked during Watch me!
                return

            # Esc ends Watch me! (same as pressing F4 to return to Code)
            if isinstance(action, ControlAction) and action.action == 'escape' and action.is_down:
                await self._end_watch_me()
                self._escape_consumed_by_mode = True
                return
            # Space ends Watch me! in Music room (space = "play", so it's a natural stop)
            if (isinstance(action, ControlAction) and action.action == 'space'
                    and action.is_down and self.active_room == Room.MUSIC):
                await self._end_watch_me()
                return
            if isinstance(action, ControlAction) and action.action == 'escape':
                return
            # Long-hold escape: end Watch me! and fall through to open parent menu
            if isinstance(action, LongHoldAction) and action.key == 'escape':
                await self._end_watch_me()

            # Record the event and reset inactivity timer
            if not (self._demo_player and self._demo_player.is_running):
                mode = self._get_current_mode()
                self._recording_manager.record_event(
                    action, self.active_room.name.lower(), mode
                )
                self._reset_watch_me_timer()

            # Still dispatch to the active room for live feedback
            # (fall through to mode dispatch below)

        # During code playback, space/escape stop playback regardless of active room
        # (playback switches rooms, so the code room may not be the active one)
        try:
            content_area = self.query_one("#content-area")
            code_room = content_area.query_one("#room-code")
            if code_room._playing:
                if isinstance(action, ControlAction) and action.is_down:
                    if action.action in ('space', 'escape'):
                        code_room._stop_playback()
                        if action.action == 'escape':
                            self._escape_consumed_by_mode = True
                        return
        except NoMatches:
            pass

        if isinstance(action, RoomAction):
            # Dismiss any open modal (like mode picker) when switching rooms
            if len(self.screen_stack) > 1:
                self.screen.dismiss(None)
            if action.room == ROOM_PLAY[0]:
                self.action_switch_room(ROOM_PLAY[0])
            elif action.room == ROOM_MUSIC[0]:
                self.action_switch_room(ROOM_MUSIC[0])
            elif action.room == ROOM_ART[0]:
                self.action_switch_room(ROOM_ART[0])
            elif action.room == ROOM_CODE[0]:
                self.action_switch_room(ROOM_CODE[0])
            elif action.room == 'parent':
                self.action_parent_menu()
            return

        if isinstance(action, CapsLockAction):
            self.keyboard.handle_caps_lock_press()
            return

        if isinstance(action, LongHoldAction):
            if action.key == 'escape':
                # Long-hold escape handled via RoomAction('parent')
                pass
            return

        # Handle escape key for long-hold detection and tap-to-pick
        # Only start timer on fresh press, not on repeat events (which would restart the timer)
        if isinstance(action, ControlAction) and action.action == 'escape':
            if action.is_down and not action.is_repeat:
                self._escape_triggered_long_hold = False  # Reset on fresh press
                # Track if modal was open when ESC pressed (for toggle behavior)
                self._modal_open_at_escape_press = len(self.screen_stack) > 1
                self._start_escape_hold_timer()
            elif not action.is_down:
                self._cancel_escape_hold_timer()
                # If long hold wasn't triggered, this was a tap: toggle mode picker
                # Only OPEN picker if no modal was open when ESC was pressed
                # If modal was open, it handles its own ESC (closes itself)
                # Also skip if the active mode consumed the escape (e.g. exiting adjustment)
                consumed = getattr(self, '_escape_consumed_by_mode', False)
                self._escape_consumed_by_mode = False
                if not self._escape_triggered_long_hold and not self._modal_open_at_escape_press and not consumed:
                    if len(self.screen_stack) == 1:
                        self._show_room_picker()
                        return
            # Don't return - let escape events propagate to modes for other uses

        # Handle global volume controls (media keys or room picker)
        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'volume_mute':
                self.action_volume_mute()
                return
            if action.action == 'volume_down':
                self.action_volume_down()
                return
            if action.action == 'volume_up':
                self.action_volume_up()
                return

        # Remap = key to + (more useful for kids: math, color mixing, emoji combining)
        if isinstance(action, CharacterAction) and action.char == '=':
            action = CharacterAction(
                char='+', shifted=action.shifted, shift_held=action.shift_held,
                is_repeat=action.is_repeat, arrow_held=action.arrow_held,
            )

        # Check if a modal screen is active (e.g., ParentMenu)
        # screen_stack[0] is the base screen, anything above is a modal
        if len(self.screen_stack) > 1:
            active_screen = self.screen
            if hasattr(active_screen, 'handle_keyboard_action'):
                await active_screen.handle_keyboard_action(action)
            return

        # Dispatch to the current mode widget
        room_id = f"room-{self.active_room.name.lower()}"
        try:
            content_area = self.query_one("#content-area")
            room_widget = content_area.query_one(f"#{room_id}")

            # Call the mode's action handler if it exists
            if hasattr(room_widget, 'handle_keyboard_action'):
                await room_widget.handle_keyboard_action(action)
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
            self._escape_triggered_long_hold = True  # Prevent picker on release
            self._cancel_escape_hold_timer()
            self.action_parent_menu()

    def _show_room_picker(self) -> None:
        """Show the mode picker modal."""
        self.clear_notifications()
        current_room = self.active_room.name.lower()
        picker = RoomPickerScreen(current_room=current_room)
        self.push_screen(picker, self._on_room_picked)

    def _on_room_picked(self, result: dict | None) -> None:
        """Handle mode picker result."""
        if result is None:
            # Cancelled, do nothing
            return

        room_name = result.get("room")

        # Switch to the selected mode
        if room_name == "play":
            self.action_switch_room(ROOM_PLAY[0])
        elif room_name == "music":
            self.action_switch_room(ROOM_MUSIC[0])
        elif room_name == "art":
            self.action_switch_room(ROOM_ART[0])
        elif room_name == "code":
            self.action_switch_room(ROOM_CODE[0])

    # ── Watch me! flow ─────────────────────────────────────────────

    def on_watch_me_requested(self, message: WatchMeRequested) -> None:
        """Handle WatchMeRequested from CodeMode: show room picker or start directly."""
        if message.room:
            # Room already chosen (from Tab menu with room picker)
            self._on_watch_me_room_picked(message.room)
        else:
            # Show room picker (Enter on empty canvas)
            picker = RoomPickerScreen(current_room="code")
            self.push_screen(picker, self._on_watch_me_room_picked)

    def _on_watch_me_room_picked(self, result) -> None:
        """Room picked for Watch me!: start recording and switch."""
        if result is None:
            return
        # Result is either a string (from Tab menu) or a dict (from room picker)
        if isinstance(result, dict):
            room_name = result.get("room", "")
        else:
            room_name = result
        if not room_name or room_name == "code":
            return

        # Map room picker names to internal room IDs
        # Room picker uses "explore"/"play"/"doodle", internal uses "play"/"music"/"art"
        picker_to_internal = {
            "explore": "play", "play": "music", "doodle": "art",
            "music": "music", "art": "art",
        }
        internal_name = picker_to_internal.get(room_name, room_name)

        self._recording_manager.start_recording(internal_name)
        self._watch_me_active = True
        self._watch_me_room = internal_name
        self._reset_watch_me_timer()

        # Show "Watching..." in title bar
        try:
            title = self.query_one("#room-title", RoomTitle)
            title.set_recording_indicator("\u23fa Watching... Esc when done")
        except Exception:
            pass

        # Switch to target room
        room_id_map = {"play": ROOM_PLAY[0], "music": ROOM_MUSIC[0], "art": ROOM_ART[0]}
        room_id = room_id_map.get(internal_name)
        if room_id:
            self.action_switch_room(room_id)

    async def _end_watch_me(self) -> None:
        """End Watch me! session: stop recording, switch to Code, insert blocks."""
        self._watch_me_active = False
        self._cancel_watch_me_timer()
        recording = self._recording_manager.stop_recording()

        # Clear title bar indicator
        try:
            title = self.query_one("#room-title", RoomTitle)
            title.set_recording_indicator("")
        except Exception:
            pass

        # Switch to Code mode
        self.action_switch_room(ROOM_CODE[0])

        # Insert blocks if recording was non-empty
        if recording is not None:
            from .program import default_target_for_room
            target = default_target_for_room(self._watch_me_room)
            # Capture current instrument if recording in music room
            instrument = ""
            if self._watch_me_room == "music":
                try:
                    from .music_constants import INSTRUMENTS
                    content_area = self.query_one("#content-area")
                    music = content_area.query_one("#room-music")
                    instrument = INSTRUMENTS[music._instrument_index][0]
                except Exception:
                    pass
            blocks = recording.to_blocks(target, instrument=instrument)
            if blocks:
                try:
                    content_area = self.query_one("#content-area")
                    command_widget = content_area.query_one("#room-code")
                    command_widget.insert_watched_blocks(blocks)
                except Exception:
                    pass

    WATCH_ME_TIMEOUT = 15  # seconds of inactivity before auto-ending Watch me!

    def _reset_watch_me_timer(self) -> None:
        """Reset the Watch me! inactivity timer."""
        self._cancel_watch_me_timer()
        loop = asyncio.get_event_loop()
        self._watch_me_timer = loop.call_later(
            self.WATCH_ME_TIMEOUT, self._watch_me_timed_out
        )

    def _cancel_watch_me_timer(self) -> None:
        """Cancel the Watch me! inactivity timer if running."""
        if self._watch_me_timer is not None:
            self._watch_me_timer.cancel()
            self._watch_me_timer = None

    def _watch_me_timed_out(self) -> None:
        """Called when Watch me! inactivity timeout expires."""
        if self._watch_me_active:
            asyncio.ensure_future(self._end_watch_me())

    def _get_current_mode(self) -> str:
        """Get the current sub-mode string for the active mode."""
        room_name = self.active_room.name.lower()
        try:
            content_area = self.query_one("#content-area")
            if room_name == "music":
                music_widget = content_area.query_one("#room-music")
                if hasattr(music_widget, '_letters_mode') and music_widget._letters_mode:
                    return "letters"
                return "music"
            elif room_name == "art":
                art_widget = content_area.query_one("#room-art")
                canvas = art_widget.query_one("#art-canvas")
                if hasattr(canvas, 'is_painting') and canvas.is_painting:
                    return "paint"
                return "text"
        except Exception:
            pass
        return ""

    def _get_art_paint_mode_callback(self):
        """Get a callback for checking art paint mode."""
        def check():
            try:
                content_area = self.query_one("#content-area")
                art = content_area.query_one("#room-art")
                canvas = art.query_one("#art-canvas")
                return hasattr(canvas, 'is_painting') and canvas.is_painting
            except Exception:
                return False
        return check

    def _get_music_letters_mode_callback(self):
        """Get a callback for checking music letters mode."""
        def check():
            try:
                content_area = self.query_one("#content-area")
                music = content_area.query_one("#room-music")
                return hasattr(music, '_letters_mode') and music._letters_mode
            except Exception:
                return False
        return check

    def _get_set_instrument_callback(self):
        """Get a callback for setting the music room instrument."""
        def set_inst(instrument_id: str):
            try:
                from .music_constants import INSTRUMENTS
                content_area = self.query_one("#content-area")
                music = content_area.query_one("#room-music")
                inst_ids = [inst_id for inst_id, _ in INSTRUMENTS]
                if instrument_id in inst_ids:
                    idx = inst_ids.index(instrument_id)
                    music._instrument_index = idx
                    if music.grid:
                        music.grid.set_instrument(idx)
                    if music._header:
                        music._header.update_instrument(INSTRUMENTS[idx][1])
            except Exception:
                pass
        return set_inst

    def _update_recording_indicator(self) -> None:
        """Update the title bar with Watch me! recording state."""
        if self._watch_me_active:
            indicator = "\u23fa Watching... Esc when done"
        else:
            indicator = ""
        try:
            title = self.query_one("#room-title", RoomTitle)
            title.set_recording_indicator(indicator)
        except Exception:
            pass

    def _reset_viewport_border(self) -> None:
        """Reset viewport outline to default purple."""
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

    def _check_usb_update_signal(self) -> None:
        """Poll for USB update signal file. Written by the systemd usb_updater service."""
        if not os.path.exists(USB_UPDATE_SIGNAL_FILE):
            return

        # Remove signal file so we don't prompt again
        try:
            os.unlink(USB_UPDATE_SIGNAL_FILE)
        except OSError:
            pass

        # Stop polling
        if self._usb_update_timer:
            self._usb_update_timer.stop()

        self._show_usb_update_restart()

    def _show_usb_update_restart(self) -> None:
        """Show a friendly modal prompting for restart after USB update."""
        from textual.widgets import Label
        from textual.screen import ModalScreen

        class UsbUpdateScreen(ModalScreen):
            """Modal screen for USB update restart prompt."""

            def compose(self):
                with Container(id="update-dialog"):
                    yield Label("New update ready!")
                    yield Label("")
                    yield Label("Press Enter to restart.")

            async def handle_keyboard_action(self, action) -> None:
                """Handle keyboard actions from evdev."""
                if isinstance(action, ControlAction) and action.is_down:
                    if action.action == 'enter':
                        self.dismiss(True)

        def handle_restart(should_restart: bool) -> None:
            if should_restart:
                import sys
                os.execv(sys.executable, [sys.executable] + sys.argv)

        self.push_screen(UsbUpdateScreen(), handle_restart)

    def _apply_theme(self) -> None:
        """Apply the current color theme"""
        self.theme = self.active_theme
        # Update mode indicator to show current theme
        try:
            indicator = self.query_one("#room-indicator", RoomIndicator)
            indicator.refresh()
        except NoMatches:
            pass

    def _check_idle_state(self) -> None:
        """Check if we should enter sleep mode due to inactivity or lid close."""
        try:
            # Import threshold at runtime so demo mode env var is respected
            from .power_manager import IDLE_SLEEP_UI, LID_SHUTDOWN_DELAY

            pm = get_power_manager()
            lid_open = pm.get_lid_state()

            # Track lid close time at app level (fallback for sleep screen bugs)
            if lid_open is False:
                if self._lid_close_time is None:
                    self._lid_close_time = time.time()
            else:
                self._lid_close_time = None

            # Safety: if _sleep_screen_active flag is stuck but screen isn't
            # actually showing, reset it so we don't block forever
            if self._sleep_screen_active:
                from .rooms.sleep_screen import SleepScreen
                actually_showing = any(
                    isinstance(s, SleepScreen) for s in self.screen_stack
                )
                if not actually_showing:
                    self._sleep_screen_active = False

            if self._sleep_screen_active:
                # Sleep screen handles its own lid countdown and idle timers.
                # But as a last resort: if lid has been closed way past the
                # shutdown delay and we're still alive, force shutdown directly.
                if (self._lid_close_time is not None
                        and time.time() - self._lid_close_time > LID_SHUTDOWN_DELAY + 30):
                    self._show_bye_screen()
                return

            # Lid closed: immediately show sleep screen (which handles shutdown countdown)
            if lid_open is False:
                self._show_sleep_screen()
                return

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
            from .rooms.sleep_screen import SleepScreen

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
        self._lid_close_time = None  # User is active, reset lid tracking
        try:
            pm = get_power_manager()
            pm.record_activity()
        except Exception:
            pass

    # ── Power Button ──────────────────────────────────────────────────

    async def _handle_power_button_event(self, event: PowerButtonEvent) -> None:
        """Handle power button tap/hold from PowerButtonReader.

        Tap: show sleep screen (cute, not scary)
        Hold (3s): show bye screen and shut down
        """
        if self._app_suspended or self._bye_screen_active:
            return

        if event.action == "tap":
            if self._sleep_screen_active:
                # Already sleeping: second tap means shut down.
                # (Many laptops send tap-only for power, hold never fires.)
                self._show_bye_screen()
            else:
                self._show_sleep_screen()
        elif event.action == "hold":
            self._show_bye_screen()

    def _show_bye_screen(self) -> None:
        """Show the goodbye screen and shut down."""
        if self._bye_screen_active:
            return

        from .rooms.sleep_screen import ByeScreen, SleepScreen

        # Dismiss sleep screen first if it's showing (avoid stacking)
        if self._sleep_screen_active:
            for screen in list(self.screen_stack):
                if isinstance(screen, SleepScreen):
                    screen.dismiss()
                    break

        self._bye_screen_active = True
        self.push_screen(ByeScreen())

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
        room_id = f"room-{self.active_room.name.lower()}"
        try:
            content_area = self.query_one("#content-area")
            room_widget = content_area.query_one(f"#{room_id}")
            self._focus_room(room_widget)
        except NoMatches:
            pass

    def _create_room_widget(self, room: Room):
        """Create a new room widget"""
        if room == Room.PLAY:
            from .rooms.play_room import PlayMode
            return PlayMode(classes="room-content")
        elif room == Room.MUSIC:
            from .rooms.music_room import MusicMode
            return MusicMode(classes="room-content")
        elif room == Room.ART:
            from .rooms.art_room import ArtMode
            return ArtMode(classes="room-content")
        elif room == Room.CODE:
            from .rooms.code_room import CodeMode
            return CodeMode(
                dispatch_action=self._dispatch_keyboard_action,
                classes="room-content",
            )
        return None

    def _load_room_content(self) -> None:
        """Load the content widget for the current mode"""
        content_area = self.query_one("#content-area")

        # Hide all existing mode widgets
        for child in content_area.children:
            child.display = False

        # Check if we already have this mode mounted
        room_id = f"room-{self.active_room.name.lower()}"
        try:
            existing = content_area.query_one(f"#{room_id}")
            existing.display = True
            self._focus_room(existing)
            return
        except NoMatches:
            pass

        # Create and mount new widget
        widget = self._create_room_widget(self.active_room)
        if widget:
            widget.id = room_id
            content_area.mount(widget)
            # Focus will happen in on_mount of the widget

    def _focus_room(self, widget) -> None:
        """Focus the appropriate element in a mode widget"""
        # Each mode has a primary focusable element
        if self.active_room == Room.PLAY:
            try:
                widget.query_one("#play-input").focus()
            except Exception:
                pass
        elif self.active_room == Room.MUSIC:
            widget.focus()
        elif self.active_room == Room.ART:
            try:
                widget.query_one("#art-canvas").focus()
            except Exception:
                widget.focus()
        elif self.active_room == Room.CODE:
            widget.focus()
            # Refresh blocks when re-entering Code mode
            if hasattr(widget, 'on_show'):
                widget.on_show()
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

    def action_switch_room(self, room_name: str) -> None:
        """Switch to a different room"""
        from .rooms.art_room import ArtPromptScreen

        # Debug: log who is calling mode switch
        if os.environ.get("PURPLE_DEV_MODE") == "1":
            import traceback
            self._dev_log(f"[ModeSwitch] action_switch_room({room_name}) called from:")
            for line in traceback.format_stack()[-5:-1]:
                self._dev_log(line.strip())

        room_map = {
            ROOM_PLAY[0]: Room.PLAY,
            ROOM_MUSIC[0]: Room.MUSIC,
            ROOM_ART[0]: Room.ART,
            ROOM_CODE[0]: Room.CODE,
        }
        new_room = room_map.get(room_name, Room.PLAY)

        # If ArtPromptScreen is showing and we're switching to a different mode,
        # dismiss it (keeping the drawing) and proceed with the switch
        if len(self.screen_stack) > 1:
            active_screen = self.screen
            if isinstance(active_screen, ArtPromptScreen):
                # Dismiss without callback action (we're switching modes anyway)
                self.pop_screen()
                # If switching back to art, we're already there, just return
                if new_room == Room.ART:
                    return

        if new_room != self.active_room:
            # Reset viewport border when leaving art mode
            if self.active_room == Room.ART:
                self._reset_viewport_border()

            # Auto-clear music mode when leaving (ephemeral mode)
            if self.active_room == Room.MUSIC:
                try:
                    content_area = self.query_one("#content-area")
                    music_widget = content_area.query_one(f"#room-{ROOM_MUSIC[0]}")
                    if hasattr(music_widget, 'reset_state'):
                        music_widget.reset_state()
                except NoMatches:
                    pass

            # Check if entering art mode with existing content
            if new_room == Room.ART:
                try:
                    content_area = self.query_one("#content-area")
                    art_widget = content_area.query_one(f"#room-{ROOM_ART[0]}")
                    if hasattr(art_widget, 'has_content') and art_widget.has_content() and not self.demo_running:
                        # Switch first (shows drawing), then prompt on top
                        self._complete_room_switch(new_room)
                        self._show_art_prompt()
                        return
                except NoMatches:
                    pass  # First time entering, no content yet

            self._complete_room_switch(new_room)

    def _complete_room_switch(self, new_room: Room) -> None:
        """Complete the mode switch (updates UI, loads content)."""
        self.clear_notifications()
        self.active_room = new_room
        self._load_room_content()

        # Update title
        room_names = {Room.PLAY: ROOM_PLAY[0], Room.MUSIC: ROOM_MUSIC[0], Room.ART: ROOM_ART[0], Room.CODE: ROOM_CODE[0]}
        try:
            title = self.query_one("#room-title", RoomTitle)
            title.set_mode(room_names.get(new_room, ROOM_PLAY[0]))
        except NoMatches:
            pass

        # Update mode indicator
        try:
            indicator = self.query_one("#room-indicator", RoomIndicator)
            indicator.update_room(new_room)
        except NoMatches:
            pass

        # Show color legend in play mode (always visible, no active row)
        # Hide it when leaving both art and play modes
        if new_room == Room.PLAY:
            try:
                legend = self.query_one("#paint-legend", ColorLegend)
                legend.set_visible(True)
                legend.set_active_row(-1)  # No active row initially
            except NoMatches:
                pass
        elif new_room != Room.ART:
            try:
                legend = self.query_one("#paint-legend", ColorLegend)
                legend.set_visible(False)
            except NoMatches:
                pass

    def _show_art_prompt(self) -> None:
        """Show prompt when entering Art mode with existing content."""
        from .rooms.art_room import ArtPromptScreen

        def handle_prompt_result(should_clear: bool) -> None:
            # Clear canvas if user chose "New drawing"
            if should_clear:
                try:
                    content_area = self.query_one("#content-area")
                    art_widget = content_area.query_one(f"#room-{ROOM_ART[0]}")
                    if hasattr(art_widget, 'clear_canvas'):
                        art_widget.clear_canvas()
                except NoMatches:
                    pass

        self.push_screen(ArtPromptScreen(), handle_prompt_result)

    def action_volume_mute(self) -> None:
        """Toggle mute on/off"""
        if self.volume_level > 0:
            # Mute: save current level and set to 0
            self._volume_before_mute = self.volume_level
            self.volume_level = 0
        else:
            # Unmute: restore previous level
            self.volume_level = self._volume_before_mute if self._volume_before_mute > 0 else VOLUME_DEFAULT
        self._apply_volume()

    def action_volume_down(self) -> None:
        """Decrease volume"""
        # Find current position in VOLUME_LEVELS and go down
        current_idx = 0
        for i, level in enumerate(VOLUME_LEVELS):
            if self.volume_level >= level:
                current_idx = i
        if current_idx > 0:
            self.volume_level = VOLUME_LEVELS[current_idx - 1]
        self._apply_volume()  # Always show feedback, even at min

    def action_volume_up(self) -> None:
        """Increase volume"""
        # Find current position in VOLUME_LEVELS and go up
        current_idx = len(VOLUME_LEVELS) - 1
        for i, level in enumerate(VOLUME_LEVELS):
            if self.volume_level <= level:
                current_idx = i
                break
        if current_idx < len(VOLUME_LEVELS) - 1:
            self.volume_level = VOLUME_LEVELS[current_idx + 1]
        self._apply_volume()  # Always show feedback, even at max

    def action_take_screenshot(self) -> None:
        """Take a screenshot (F8). Used by AI training tools.

        Only works when PURPLE_DEV_MODE=1 is set.
        Set PURPLE_SCREENSHOT_DIR to specify output directory.
        Screenshots are saved as SVG files with incrementing numbers.
        """
        # Only allow in dev mode
        if os.environ.get("PURPLE_DEV_MODE") != "1":
            return

        self._do_screenshot()

    _screenshot_counter = -1  # Monotonic counter, first screenshot is 0

    def _do_screenshot(self) -> None:
        """Actually take the screenshot."""
        screenshot_dir = os.environ.get("PURPLE_SCREENSHOT_DIR", "screenshots")

        os.makedirs(screenshot_dir, exist_ok=True)

        # Use monotonic counter so renames of previous files don't cause collisions
        PurpleApp._screenshot_counter += 1
        next_num = PurpleApp._screenshot_counter

        filename = os.path.join(screenshot_dir, f"screenshot_{next_num:04d}.svg")
        self.save_screenshot(filename)

        # Also save path to a "latest" file for easy access
        latest_path = os.path.join(screenshot_dir, "latest.txt")
        with open(latest_path, "w") as f:
            f.write(filename)

    def _check_screenshot_trigger(self) -> None:
        """Check for file-based screenshot trigger (for AI tools).

        The AI tool creates a 'trigger' file, we take a screenshot and delete it.
        This works around evdev keyboard input not coming through PTY.
        """
        if os.environ.get("PURPLE_DEV_MODE") != "1":
            return

        screenshot_dir = os.environ.get("PURPLE_SCREENSHOT_DIR")
        if not screenshot_dir:
            return

        trigger_path = os.path.join(screenshot_dir, "trigger")
        if os.path.exists(trigger_path):
            self._dev_log("[Trigger] Found screenshot trigger, taking screenshot...")
            try:
                os.unlink(trigger_path)
                self._do_screenshot()
                self._dev_log("[Trigger] Screenshot done")
            except Exception as e:
                self._dev_log(f"[Trigger] Screenshot error: {e}")

    def _check_command_trigger(self) -> None:
        """Check for file-based command trigger (for AI tools).

        The AI tool writes commands to a 'command' file, we execute them.
        This works around evdev keyboard input not coming through PTY.

        Command file format (JSON, one command per line):
            {"action": "mode", "value": "art"}
            {"action": "key", "value": "a"}
            {"action": "key", "value": "up"}
            {"action": "key", "value": "enter"}

        Supported actions:
            - mode: Switch to a mode (play, music, art)
            - key: Send a keypress (letters, arrows, enter, escape, space, backspace)
        """
        import asyncio

        if os.environ.get("PURPLE_DEV_MODE") != "1":
            return

        screenshot_dir = os.environ.get("PURPLE_SCREENSHOT_DIR")
        if not screenshot_dir:
            return

        command_path = os.path.join(screenshot_dir, "command")
        if not os.path.exists(command_path):
            return

        try:
            with open(command_path, "r") as f:
                content = f.read()
            os.unlink(command_path)

            import json
            cmd_count = 0
            for line in content.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    cmd = json.loads(line)
                    asyncio.create_task(self._execute_dev_command(cmd))
                    cmd_count += 1
                except json.JSONDecodeError:
                    pass

            # Write response with count of commands processed
            response_path = os.path.join(screenshot_dir, "command_response")
            with open(response_path, "w") as f:
                f.write(f"{cmd_count}\n")
        except Exception:
            pass

    def _dev_log(self, msg: str) -> None:
        """Write to dev mode log file."""
        screenshot_dir = os.environ.get("PURPLE_SCREENSHOT_DIR")
        if screenshot_dir:
            log_path = os.path.join(screenshot_dir, "dev_commands.log")
            with open(log_path, "a") as f:
                f.write(f"{msg}\n")

    async def _execute_dev_command(self, cmd: dict) -> None:
        """Execute a dev command from the command file."""
        action = cmd.get("action")
        value = cmd.get("value", "")

        self._dev_log(f"[DevCmd] action={action} value={value} (current_room={self.active_room.name})")

        if action == "mode":
            # Switch mode: play, music, art
            room_map = {
                "play": ROOM_PLAY[0],
                "music": ROOM_MUSIC[0],
                "art": ROOM_ART[0],
            }
            room_name = room_map.get(value.lower())
            self._dev_log(f"[DevCmd] room_name={room_name} (from {value.lower()})")
            if room_name:
                self.action_switch_room(room_name)
                self._dev_log(f"[DevCmd] Switched to {room_name}")

        elif action == "key":
            # Send a keypress through the keyboard state machine
            try:
                key_action = self._create_action_from_key(value)
                self._dev_log(f"[DevCmd] key={value} -> action={key_action}")
                if key_action:
                    # Await the dispatch to ensure it completes before next command
                    await self._dispatch_keyboard_action(key_action)
                    self._dev_log(f"[DevCmd] key={value} dispatched, mode now={self.active_room.name}")

                    # For control keys (especially space), also send key-up event
                    # Without this, _space_down stays True and arrow movements paint
                    if isinstance(key_action, ControlAction):
                        key_up_action = ControlAction(action=key_action.action, is_down=False)
                        await self._dispatch_keyboard_action(key_up_action)
                        self._dev_log(f"[DevCmd] key={value} release dispatched")
                else:
                    self._dev_log(f"[DevCmd] WARNING: Unknown key '{value}'")
            except Exception as e:
                import traceback
                self._dev_log(f"[DevCmd] ERROR: key={value} exception={e}\n{traceback.format_exc()}")

        elif action == "clear":
            # Clear the art canvas
            from .rooms.art_room import ArtMode, ArtCanvas
            try:
                # Query by type, not ID (ArtMode has no ID)
                art = self.query_one(ArtMode)
                art.clear_canvas()
                # Also directly access and refresh the canvas to ensure clear takes effect
                try:
                    canvas = art.query_one(ArtCanvas)
                    canvas.refresh()
                    self._dev_log(f"[DevCmd] Canvas cleared, grid size={len(canvas._grid)}")
                except Exception:
                    pass
                self._dev_log("[DevCmd] Canvas cleared")
            except Exception as e:
                import traceback
                self._dev_log(f"[DevCmd] ERROR: clear failed: {e}\n{traceback.format_exc()}")

        elif action == "set_position":
            # Set cursor position directly (fast alternative to arrow keys)
            from .rooms.art_room import ArtMode, ArtCanvas
            try:
                x = int(cmd.get("x", 0))
                y = int(cmd.get("y", 0))
                art = self.query_one(ArtMode)
                canvas = art.query_one(ArtCanvas)
                canvas.set_cursor_position(x, y)
                self._dev_log(f"[DevCmd] set_position x={x} y={y}")
            except Exception as e:
                self._dev_log(f"[DevCmd] ERROR: set_position failed: {e}")

        elif action == "paint_at":
            # Paint a color at specific position (combines move + select + stamp)
            from .rooms.art_room import ArtMode, ArtCanvas
            try:
                x = int(cmd.get("x", 0))
                y = int(cmd.get("y", 0))
                color_key = cmd.get("color", "f")
                art = self.query_one(ArtMode)
                canvas = art.query_one(ArtCanvas)
                canvas.paint_at(x, y, color_key)
                self._dev_log(f"[DevCmd] paint_at x={x} y={y} color={color_key}")
            except Exception as e:
                self._dev_log(f"[DevCmd] ERROR: paint_at failed: {e}")

    def _create_action_from_key(self, key: str):
        """Create a keyboard action from a key name."""
        key_lower = key.lower()

        # Navigation keys
        nav_keys = {
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
        }
        if key_lower in nav_keys:
            return NavigationAction(direction=nav_keys[key_lower])

        # Control keys
        ctrl_keys = {
            "enter": "enter",
            "return": "enter",
            "escape": "escape",
            "esc": "escape",
            "backspace": "backspace",
            "delete": "delete",
            "tab": "tab",
            "space": "space",
        }
        if key_lower in ctrl_keys:
            return ControlAction(action=ctrl_keys[key_lower], is_down=True)

        # Single character (preserve case for shift+letter)
        if len(key) == 1:
            return CharacterAction(char=key)

        return None

    def _apply_volume(self) -> None:
        """Apply volume level to TTS and update UI"""
        from . import tts
        tts.set_muted(self.volume_level == 0)
        # TODO: Set actual volume level when TTS supports it

        # Update volume indicator badge
        try:
            indicator = self.query_one("#room-indicator", RoomIndicator)
            indicator.update_volume_indicator(self.volume_level)
        except NoMatches:
            pass

        # Build volume feedback message
        if self.volume_level == 0:
            icon = ICON_VOLUME_OFF
            label = "Sound Off"
            bars = "░░░░░░░░"
        elif self.volume_level <= 25:
            icon = ICON_VOLUME_LOW
            label = "Quiet Sound"
            bars = "██░░░░░░"
        elif self.volume_level <= 50:
            icon = ICON_VOLUME_MED
            label = "Low Sound"
            bars = "████░░░░"
        elif self.volume_level <= 75:
            icon = ICON_VOLUME_HIGH
            label = "Medium Sound"
            bars = "██████░░"
        else:
            icon = ICON_VOLUME_HIGH
            label = "High Sound"
            bars = "████████"

        self.clear_notifications()
        self.notify(f"{icon}  {bars}  {label}", timeout=1.5)

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

    def _on_sticky_shift_change(self, active: bool) -> None:
        """Called when sticky shift state changes."""
        if self._sticky_shift_timer:
            self._sticky_shift_timer.stop()
            self._sticky_shift_timer = None
        try:
            indicator = self.query_one("#shift-indicator", Static)
            if active:
                indicator.add_class("active")
                self._sticky_shift_timer = self.set_timer(
                    STICKY_SHIFT_GRACE, self._expire_sticky_shift_indicator
                )
            else:
                indicator.remove_class("active")
        except NoMatches:
            pass

    def _expire_sticky_shift_indicator(self) -> None:
        """Hide sticky shift indicator after grace period."""
        self._sticky_shift_timer = None
        try:
            indicator = self.query_one("#shift-indicator", Static)
            indicator.remove_class("active")
        except NoMatches:
            pass

    def action_parent_menu(self) -> None:
        """Enter parent mode. Shows admin menu for parents."""
        from .rooms.parent_menu import ParentMenu
        # Cancel escape hold timer and reset state
        self._cancel_escape_hold_timer()
        self.keyboard.escape_hold.reset()
        self._keyboard_state_machine.reset()  # Clear all pressed keys state
        self.clear_notifications()
        self.push_screen(ParentMenu(), callback=lambda _: self.clear_notifications())

    def clear_all_state(self) -> None:
        """Clear all state across all modes. Used at start of demo."""
        from .rooms.play_room import PlayMode
        from .rooms.music_room import MusicMode
        from .rooms.art_room import ArtMode

        # Clear play mode history
        try:
            play = self.query_one(PlayMode)
            play.clear_history()
        except Exception:
            pass

        # Reset music mode colors
        try:
            music = self.query_one(MusicMode)
            music.reset_state()
        except Exception:
            pass

        # Clear art mode canvas
        try:
            art = self.query_one(ArtMode)
            art.clear_canvas()
        except Exception:
            pass

    def _set_music_key_color(self, key: str, color_index: int) -> None:
        """Set a Music mode key's color directly. Used by demo player for flash effects."""
        from .rooms.music_room import MusicMode, MusicGrid

        try:
            music = self.query_one(MusicMode)
            grid = music.query_one(MusicGrid)
            grid.set_color_index(key, color_index)
        except Exception:
            pass

    def _get_cursor_position(self) -> tuple[float, float] | None:
        """Get cursor position as viewport fractions (x_frac, y_frac).

        Returns (x, y) where 0.0=top-left, 1.0=bottom-right of the viewport,
        or None if cursor position cannot be determined.
        """
        try:
            viewport = self.query_one("#viewport")
            vp = viewport.region
        except Exception:
            return None

        if self.active_room == Room.PLAY:
            from .rooms.play_room import InlineInput
            try:
                inp = self.query_one("#play-input", InlineInput)
                inp_region = inp.region
                cursor_x = inp_region.x - vp.x + inp.cursor_position
                cursor_y = inp_region.y - vp.y
                return (cursor_x / vp.width, cursor_y / vp.height)
            except Exception:
                # Fallback: left side of input line, near bottom of viewport
                return (0.07, 0.9)

        elif self.active_room == Room.ART:
            from .rooms.art_room import ArtMode, ArtCanvas
            try:
                art = self.query_one(ArtMode)
                canvas = art.query_one(ArtCanvas)
                canvas_region = canvas.region
                cursor_x = canvas_region.x - vp.x + 1 + canvas._cursor_x
                cursor_y = canvas_region.y - vp.y + 1 + canvas._cursor_y
                return (cursor_x / vp.width, cursor_y / vp.height)
            except Exception:
                return None

        return None

    def _is_art_paint_mode(self) -> bool:
        """Check if Art mode is in paint mode (vs text mode)."""
        from .rooms.art_room import ArtMode, ArtCanvas

        try:
            art = self.query_one(ArtMode)
            canvas = art.query_one(ArtCanvas)
            return canvas.is_painting
        except Exception:
            return False

    def _clear_art(self) -> None:
        """Clear only the art canvas and reset cursor to (0,0)."""
        from .rooms.art_room import ArtMode

        try:
            art = self.query_one(ArtMode)
            art.clear_canvas()
        except Exception:
            pass

    def start_demo(self) -> None:
        """Start demo playback (dev mode only).

        The demo player dispatches synthetic keyboard actions at human pace,
        showcasing all modes and features. Called from ParentMenu.
        """
        import asyncio

        # Cancel any running demo
        self.cancel_demo()

        # Create player that dispatches actions through our normal handler
        # If PURPLE_ZOOM_EVENTS env var is set, zoom events will be written there
        zoom_events_file = os.environ.get("PURPLE_ZOOM_EVENTS")
        self._demo_player = DemoPlayer(
            dispatch_action=self._dispatch_keyboard_action,
            speed_multiplier=get_speed_multiplier(),
            clear_all=self.clear_all_state,
            clear_art=self._clear_art,
            set_music_key_color=self._set_music_key_color,
            is_art_paint_mode=self._is_art_paint_mode,
            get_cursor_position=self._get_cursor_position,
            zoom_events_file=zoom_events_file,
        )

        # Check if we should exit after demo (for recording)
        exit_after = os.environ.get("PURPLE_DEMO_AUTOSTART")

        # Run the demo as a background task
        async def run_demo():
            demo_script = get_demo_script()  # Uses PURPLE_DEMO_NAME env var
            await self._demo_player.play(demo_script)
            self._demo_player = None
            self._demo_task = None
            # Exit app if this was an auto-started demo (for recording)
            if exit_after:
                # Wait 2 seconds before exit (trimmed from final video)
                await asyncio.sleep(2.0)
                self.exit()

        self._demo_task = asyncio.create_task(run_demo())

    def cancel_demo(self) -> None:
        """Cancel any running demo playback."""
        if self._demo_player:
            self._demo_player.cancel()
            self._demo_player = None
        if self._demo_task:
            self._demo_task.cancel()
            self._demo_task = None

    @property
    def demo_running(self) -> bool:
        """Check if a demo is currently playing."""
        return self._demo_player is not None and self._demo_player.is_running

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
        """Refresh all widgets that change based on caps mode.

        Widgets opt-in by adding the 'caps-sensitive' CSS class.
        """
        for widget in self.query(".caps-sensitive"):
            widget.refresh()

    @property
    def caps_mode(self) -> bool:
        """Whether caps lock is on"""
        return self.keyboard.caps.caps_lock_on

    def caps_text(self, text: str) -> str:
        """Return text in caps if caps mode is on.

        Only uppercases text outside Rich markup tags (e.g. [bold], [on #hex]),
        since Rich tags are case-sensitive and .upper() breaks them.
        """
        if not self.caps_mode:
            return text
        result = []
        i = 0
        while i < len(text):
            if text[i] == '[':
                # Find closing bracket, preserve tag as-is
                end = text.find(']', i)
                if end != -1:
                    result.append(text[i:end + 1])
                    i = end + 1
                    continue
            result.append(text[i].upper())
            i += 1
        return ''.join(result)


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

    # Auto-size Alacritty font to fit the required terminal grid.
    # Measures actual terminal dimensions and adjusts empirically.
    # Shows "Loading..." if adjustment is needed (usually <1 second).
    from .font_sizer import ensure_terminal_size
    ensure_terminal_size()

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
