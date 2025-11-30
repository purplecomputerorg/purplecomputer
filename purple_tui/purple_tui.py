#!/usr/bin/env python3
"""
Purple Computer - Main Textual TUI Application

The calm computer for kids ages 3-8.
A creativity device, not an entertainment device.
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

from .constants import (
    ICON_CHAT, ICON_PALETTE, ICON_HEADPHONES, ICON_DOCUMENT,
    ICON_MOON, ICON_SUN, MODE_TITLES,
)


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


# Mode display info
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
        margin-bottom: 1;
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
    """Shows F1-F4 mode indicators as styled key badges"""

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
        margin-left: 2;
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
        # F1-F4 on the left (like on a real keyboard)
        with Horizontal(id="keys-left"):
            for mode in Mode:
                info = MODE_INFO[mode]
                badge = KeyBadge(f"{info['key']} {info['emoji']}", id=f"key-{mode.name.lower()}")
                if mode == self.current_mode:
                    badge.add_class("active")
                else:
                    badge.add_class("dim")
                yield badge

        # Spacer pushes F12 to the right
        yield Static("", id="keys-spacer")

        # F12 on the right (like on a real keyboard)
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
            badge.text = f"F12 {ICON_MOON if is_dark else ICON_SUN}"
            badge.refresh()
        except NoMatches:
            pass

    def show_escape_status(self, count: int) -> None:
        """Show escape count status - for now just refresh"""
        pass  # Could add a status badge if needed


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


class PurpleApp(App):
    """
    Purple Computer - The calm computer for kids.

    F1-F4: Switch between modes (Ask, Play, Listen, Write)
    Ctrl+V: Cycle views (Screen, Line, Ears)
    F12: Toggle dark/light mode
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

    #mode-title {
        width: 100;
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

    BINDINGS = [
        Binding("f1", "switch_mode('ask')", "Ask", show=False, priority=True),
        Binding("f2", "switch_mode('play')", "Play", show=False, priority=True),
        Binding("f3", "switch_mode('listen')", "Listen", show=False, priority=True),
        Binding("f4", "switch_mode('write')", "Write", show=False, priority=True),
        Binding("escape", "escape_pressed", "Escape", show=False, priority=True),
        Binding("f12", "toggle_theme", "Theme", show=False, priority=True),
        Binding("ctrl+d", "toggle_theme", "Theme", show=False, priority=True),  # Backup
        Binding("ctrl+v", "cycle_view", "View", show=False, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.active_mode = Mode.ASK
        self.active_view = View.SCREEN
        self.active_theme = "purple-dark"
        self.speech_enabled = False
        self.escape_count = 0  # For 3-escape clear confirmation
        self.caps_mode = False  # Track if user is typing in caps
        self._recent_letters = []  # Track recent letter keypresses
        self._pending_update = None  # Set by main() if breaking update available
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
                yield ModeTitle(id="mode-title")
                with ViewportContainer(id="viewport"):
                    yield Container(id="content-area")
            yield ModeIndicator(self.active_mode, id="mode-indicator")

    def on_mount(self) -> None:
        """Called when app starts"""
        self._apply_theme()
        self._load_mode_content()

        # Show breaking update prompt if available
        if self._pending_update:
            self._show_update_prompt()

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
                widget.query_one("#write-input").focus()
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

    def action_escape_pressed(self) -> None:
        """Handle escape key - 3 presses to clear mode"""
        self.escape_count += 1

        if self.escape_count >= 3:
            # Third press - reset mode state (not content)
            self.escape_count = 0
            self._reset_mode_state()

        # Update indicator to show escape count
        try:
            indicator = self.query_one("#mode-indicator", ModeIndicator)
            indicator.refresh()
        except NoMatches:
            pass

        # Auto-reset after timeout
        self.set_timer(2.0, self._reset_escape_count)

    def _reset_escape_count(self) -> None:
        """Reset escape count after timeout"""
        if self.escape_count > 0:
            self.escape_count = 0
            try:
                indicator = self.query_one("#mode-indicator", ModeIndicator)
                indicator.refresh()
            except NoMatches:
                pass

    def _reset_mode_state(self) -> None:
        """Reset the current mode's state without clearing content"""
        mode_id = f"mode-{self.active_mode.name.lower()}"
        try:
            content_area = self.query_one("#content-area")
            mode_widget = content_area.query_one(f"#{mode_id}")
        except NoMatches:
            return

        if self.active_mode == Mode.ASK:
            # Clear input and autocomplete, but keep history
            try:
                ask_input = mode_widget.query_one("#ask-input")
                ask_input.value = ""
                ask_input.autocomplete_matches = []
                ask_input.autocomplete_index = 0
                ask_input.last_char = None
                ask_input.last_char_time = 0
                hint = mode_widget.query_one("#autocomplete-hint")
                hint.update("")
            except Exception:
                pass

        elif self.active_mode == Mode.PLAY:
            # Reset eraser mode toggle and grid colors
            try:
                indicator = mode_widget.query_one("#eraser-indicator")
                indicator.eraser_on = False
                indicator.refresh()
                mode_widget.eraser_mode = False
                # Reset all grid colors
                grid = mode_widget.grid
                if grid:
                    for key in grid.color_state:
                        grid.color_state[key] = -1
                    grid._flash_keys.clear()
                    grid.refresh()
            except Exception:
                pass

        elif self.active_mode == Mode.WRITE:
            # Reset double-tap state
            try:
                write_area = mode_widget.query_one("#write-area")
                write_area.last_char = None
                write_area.last_char_time = 0
            except Exception:
                pass

    def on_key(self, event: events.Key) -> None:
        """Global key filter - ignore irrelevant keys app-wide"""
        # Track caps mode based on recent letter keypresses
        char = event.character
        if char and char.isalpha():
            self._recent_letters.append(char)
            # Keep only last 4 letters
            self._recent_letters = self._recent_letters[-4:]
            # If we have 4+ letters and all are uppercase, enable caps mode
            if len(self._recent_letters) >= 4:
                new_caps = all(c.isupper() for c in self._recent_letters)
                if new_caps != self.caps_mode:
                    self.caps_mode = new_caps
                    self._refresh_caps_sensitive_widgets()

        # Keys that should always be ignored (modifier-only, system keys, etc.)
        ignored_keys = {
            # Modifier keys (pressed alone)
            "shift", "ctrl", "alt", "meta", "super",
            "left_shift", "right_shift",
            "left_ctrl", "right_ctrl", "control",
            "left_alt", "right_alt", "option",
            "left_meta", "right_meta", "left_super", "right_super",
            "command", "cmd",
            # Lock keys
            "caps_lock", "num_lock", "scroll_lock",
            # Other system keys
            "print_screen", "pause", "insert",
            "home", "end", "page_up", "page_down",
            # Function keys we don't use
            "f6", "f7", "f8", "f9", "f10", "f11",
            "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20",
        }

        if event.key in ignored_keys:
            event.stop()
            event.prevent_default()
            return

        # Also ignore any ctrl+/cmd+ combos we don't explicitly handle
        # (our bindings handle ctrl+d, ctrl+v, ctrl+q)
        if event.key.startswith("ctrl+") and event.key not in {"ctrl+d", "ctrl+v", "ctrl+q", "ctrl+c"}:
            event.stop()
            event.prevent_default()
            return

    def _refresh_caps_sensitive_widgets(self) -> None:
        """Refresh all widgets that change based on caps mode"""
        # Refresh example hints and other caps-sensitive text
        widget_ids = [
            "#mode-title",         # Mode title in all modes
            "#example-hint",       # Ask and Play mode hints
            "#autocomplete-hint",  # Ask mode autocomplete
            "#write-header",       # Write mode header
            "#input-prompt",       # Ask mode "Ask:" prompt
            "#speech-indicator",   # Ask mode speech toggle
            "#eraser-indicator",   # Play mode eraser toggle
            "#coming-soon",        # Listen mode placeholder
        ]
        for widget_id in widget_ids:
            try:
                widget = self.query_one(widget_id)
                widget.refresh()
            except NoMatches:
                pass

    def caps_text(self, text: str) -> str:
        """Return text in caps if caps mode is on"""
        return text.upper() if self.caps_mode else text


def main():
    """Entry point for Purple Computer"""
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
    app.run()


if __name__ == "__main__":
    main()
