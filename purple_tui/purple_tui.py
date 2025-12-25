#!/usr/bin/env python3
"""
Purple Computer - Main Textual TUI Application

The calm computer for kids ages 3-8.
A creativity device, not an entertainment device.

Keyboard controls:
- F1-F4: Switch modes (Ask, Play, Listen, Write)
- F12: Toggle dark/light theme
- Escape (long hold): Parent mode
- Caps Lock: Toggle big/small letters
- Sticky shift: Shift key toggles, stays active for 1 second
- Double-tap: Same symbol twice quickly = shifted version
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, Center, Middle
from textual.widgets import Static, Footer
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.theme import Theme
from textual import events
from enum import Enum
import subprocess
import os
import time

from .constants import (
    ICON_CHAT, ICON_PALETTE, ICON_HEADPHONES, ICON_DOCUMENT,
    ICON_MOON, ICON_SUN, MODE_TITLES,
    DOUBLE_TAP_TIME, STICKY_SHIFT_GRACE, ESCAPE_HOLD_THRESHOLD,
    ICON_BATTERY_FULL, ICON_BATTERY_HIGH, ICON_BATTERY_MED,
    ICON_BATTERY_LOW, ICON_BATTERY_EMPTY, ICON_BATTERY_CHARGING,
)
from .keyboard import (
    KeyboardState, create_keyboard_state, detect_keyboard_mode,
    KeyboardMode, SHIFT_MAP,
    launch_keyboard_normalizer, stop_keyboard_normalizer,
)
from .power_manager import get_power_manager
from .modes.write_mode import BorderColorChanged


class Mode(Enum):
    """The 4 core modes of Purple Computer"""
    ASK = 1      # F1 - Math and emoji REPL
    PLAY = 2     # F2 - Music and art grid
    LISTEN = 3   # F3 - Stories and songs (future)
    WRITE = 4    # F4 - Simple text editor


class View(Enum):
    """The 3 core views - reduce screen time feeling"""
    SCREEN = 1   # 10x6" viewport
    LINE = 2     # 10" wide, 1 line height
    EARS = 3     # Screen off (blank)


# Mode display info - F-keys for mode switching
MODE_INFO = {
    Mode.ASK: {"key": "F1", "label": "Ask", "emoji": ICON_CHAT},
    Mode.PLAY: {"key": "F2", "label": "Play", "emoji": ICON_PALETTE},
    Mode.LISTEN: {"key": "F3", "label": "Listen", "emoji": ICON_HEADPHONES},
    Mode.WRITE: {"key": "F4", "label": "Write", "emoji": ICON_DOCUMENT},
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

    #caps-indicator {
        width: auto;
        height: 3;
        padding: 0 1;
        content-align: center middle;
        color: $text-muted;
    }

    #caps-indicator.active {
        color: $accent;
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

        # Spacer pushes theme to the right
        yield Static("", id="keys-spacer")

        # Caps indicator (starts as lowercase since caps starts off)
        yield Static("abc", id="caps-indicator")

        # Theme toggle on the right (F12)
        with Horizontal(id="keys-right"):
            is_dark = "dark" in getattr(self.app, 'active_theme', 'dark')
            theme_icon = ICON_MOON if is_dark else ICON_SUN
            theme_badge = KeyBadge(f"F12 {theme_icon}", id="key-theme")
            theme_badge.add_class("dim")
            yield theme_badge

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
        """Update the theme badge icon"""
        try:
            badge = self.query_one("#key-theme", KeyBadge)
            is_dark = "dark" in getattr(self.app, 'active_theme', 'dark')
            badge.text = f"0 {ICON_MOON if is_dark else ICON_SUN}"
            badge.refresh()
        except NoMatches:
            pass

    def update_caps_indicator(self, caps_on: bool) -> None:
        """Update caps lock indicator"""
        try:
            indicator = self.query_one("#caps-indicator", Static)
            if caps_on:
                indicator.update("ABC")
                indicator.add_class("active")
            else:
                indicator.update("abc")
                indicator.remove_class("active")
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
                            # Found a battery - verify we can read capacity
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
    Purple Computer - The calm computer for kids.

    F1-F4: Switch between modes (Ask, Play, Listen, Write)
    F12: Toggle dark/light mode
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

    #mode-title {
        width: 1fr;
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
    """

    # Mode switching uses F-keys for robustness
    BINDINGS = [
        Binding("f1", "switch_mode('ask')", "Ask", show=False, priority=True),
        Binding("f2", "switch_mode('play')", "Play", show=False, priority=True),
        Binding("f3", "switch_mode('listen')", "Listen", show=False, priority=True),
        Binding("f4", "switch_mode('write')", "Write", show=False, priority=True),
        Binding("f12", "toggle_theme", "Theme", show=False, priority=True),
        Binding("ctrl+v", "cycle_view", "View", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.active_mode = Mode.ASK
        self.active_view = View.SCREEN
        self.active_theme = "purple-dark"
        self.speech_enabled = False
        self._pending_update = None  # Set by main() if breaking update available

        # Power management
        self._idle_timer = None
        self._sleep_screen_active = False

        # Unified keyboard state
        self.keyboard = create_keyboard_state(
            sticky_grace_period=STICKY_SHIFT_GRACE,
            double_tap_threshold=DOUBLE_TAP_TIME,
            escape_hold_threshold=ESCAPE_HOLD_THRESHOLD,
        )
        self.keyboard.mode = detect_keyboard_mode()

        # Register callback for caps lock changes
        self.keyboard.caps.on_change(self._on_caps_change)

        # Keyboard normalizer subprocess (Linux only)
        self._keyboard_normalizer_process = None

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
                    yield ModeTitle(id="mode-title")
                    yield BatteryIndicator(id="battery-indicator")
                with ViewportContainer(id="viewport"):
                    yield Container(id="content-area")
            yield ModeIndicator(self.active_mode, id="mode-indicator")

    def on_mount(self) -> None:
        """Called when app starts"""
        self._apply_theme()
        self._load_mode_content()

        # Launch keyboard normalizer on Linux (provides tap-shift, long-press, etc.)
        # This fails gracefully if not on Linux or missing permissions
        self._keyboard_normalizer_process = launch_keyboard_normalizer()

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

    def on_unmount(self) -> None:
        """Called when app is shutting down"""
        # Clean up keyboard normalizer subprocess
        stop_keyboard_normalizer(self._keyboard_normalizer_process)
        self._keyboard_normalizer_process = None

    def on_border_color_changed(self, event: BorderColorChanged) -> None:
        """Handle border color change from write mode."""
        try:
            from textual.color import Color
            viewport = self.query_one("#viewport")
            viewport.styles.border = ("heavy", Color.parse(event.color))
        except Exception:
            pass

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
        """Record that user is active - resets idle timer."""
        try:
            pm = get_power_manager()
            pm.record_activity()
        except Exception:
            pass

    async def on_event(self, event: events.Event) -> None:
        """Record activity for any key press - before widgets can stop it.

        This is called BEFORE event dispatch, so child widgets calling
        event.stop() won't prevent activity from being recorded.
        """
        if isinstance(event, events.Key):
            self._record_user_activity()
        # Always call super to continue normal event dispatch
        await super().on_event(event)

    def _create_mode_widget(self, mode: Mode):
        """Create a new mode widget"""
        if mode == Mode.ASK:
            from .modes.ask_mode import AskMode
            return AskMode(classes="mode-content")
        elif mode == Mode.PLAY:
            from .modes.play_mode import PlayMode
            return PlayMode(classes="mode-content")
        elif mode == Mode.LISTEN:
            from .modes.listen_mode import ListenMode
            return ListenMode(classes="mode-content")
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
                widget.query_one("#write-area").focus()
                # Restore border color when re-entering write mode
                widget.restore_border_color()
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
        """Switch to a different mode (F1-F4)"""
        mode_map = {
            "ask": Mode.ASK,
            "play": Mode.PLAY,
            "listen": Mode.LISTEN,
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
        """Toggle between dark and light mode (F12)"""
        self.active_theme = "purple-light" if self.active_theme == "purple-dark" else "purple-dark"
        self._apply_theme()
        # Update theme icon in mode indicator
        try:
            indicator = self.query_one("#mode-indicator", ModeIndicator)
            indicator.update_theme_icon()
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
            indicator = self.query_one("#mode-indicator", ModeIndicator)
            indicator.update_caps_indicator(caps_on)
        except NoMatches:
            pass

    def action_parent_mode(self) -> None:
        """Enter parent mode - shows admin menu for parents"""
        from .modes.parent_mode import ParentMenu
        # Reset escape hold state so it can be triggered again after returning
        self.keyboard.escape_hold.reset()
        self.push_screen(ParentMenu())

    def on_key(self, event: events.Key) -> None:
        """Handle key events at app level"""
        # Note: Activity recording moved to on_event() so it can't be bypassed
        # by child widgets calling event.stop()

        key = event.key

        # Handle F24 from hardware keyboard normalizer (long-press escape signal)
        if key == "f24":
            self.action_parent_mode()
            event.stop()
            event.prevent_default()
            return

        # Handle Escape for long-hold parent mode (fallback for Mac/terminal)
        if key == "escape":
            if self.keyboard.handle_escape_repeat():
                # Long hold threshold reached - enter parent mode
                self.action_parent_mode()
                event.stop()
                event.prevent_default()
                return
            # First press - start tracking
            self.keyboard.handle_escape_press()
            event.stop()
            event.prevent_default()
            return

        # Handle Caps Lock toggle
        if key == "caps_lock":
            self.keyboard.handle_caps_lock_press()
            event.stop()
            event.prevent_default()
            return

        # Handle Shift key for sticky shift
        if key in ("shift", "left_shift", "right_shift"):
            self.keyboard.handle_sticky_shift_press()
            event.stop()
            event.prevent_default()
            return

        # Keys that should always be ignored (modifier-only, system keys, etc.)
        ignored_keys = {
            # Modifier keys (pressed alone) - except shift which we handle above
            "ctrl", "alt", "meta", "super",
            "left_ctrl", "right_ctrl", "control",
            "left_alt", "right_alt", "option",
            "left_meta", "right_meta", "left_super", "right_super",
            "command", "cmd",
            # Lock keys (except caps_lock which we handle above)
            "num_lock", "scroll_lock",
            # Other system keys
            "print_screen", "pause", "insert",
            "home", "end", "page_up", "page_down",
            # F-keys not used for modes (F5-F11, F13-F23)
            # Note: F24 is handled above for parent mode
            "f5", "f6", "f7", "f8", "f9", "f10", "f11",
            "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20",
            "f21", "f22", "f23",
        }

        if key in ignored_keys:
            event.stop()
            event.prevent_default()
            return

        # Also ignore any ctrl+/cmd+ combos we don't explicitly handle
        if key.startswith("ctrl+") and key not in {"ctrl+v", "ctrl+c"}:
            event.stop()
            event.prevent_default()
            return

    def _refresh_caps_sensitive_widgets(self) -> None:
        """Refresh all widgets that change based on caps mode"""
        widget_ids = [
            "#mode-title",
            "#example-hint",
            "#autocomplete-hint",
            "#write-header",
            "#input-prompt",
            "#speech-indicator",
            "#eraser-indicator",
            "#coming-soon",
        ]
        for widget_id in widget_ids:
            try:
                widget = self.query_one(widget_id)
                widget.refresh()
            except NoMatches:
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
    # Note: We intentionally do NOT filter stderr here.
    # Textual renders to stderr, so any pipe redirection causes UI lag.
    # ALSA noise should be silenced at the source (see tts.py for handlers).

    # Check for updates before starting
    from .updater import auto_update_if_available
    update_result = auto_update_if_available()

    if update_result == "updated":
        # Minor update applied - restart the app
        import sys
        import os
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # If breaking update available, the app will show a prompt
    # (handled in PurpleApp.on_mount)

    app = PurpleApp()
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
