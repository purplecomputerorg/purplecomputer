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
- Escape (tap): Room picker (1-3 for rooms, arrows to navigate/volume)
- Escape (long hold): Parent menu
- Media keys: Volume mute/down/up
- Shift (tap): Sticky shift for one character
- Shift (double-tap): Toggle caps lock
- Caps Lock key: Remapped to Shift
"""

# Boot log heartbeat + startup watchdog. Imported FIRST, before anything else,
# so we have timestamps and a deadlocked-thread dumper armed from the earliest
# possible moment if a later import hangs. See purple_tui/boot_log.py.
from . import boot_log
boot_log.heartbeat("purple_tui entry: beginning stdlib imports")

# Suppress ONNX runtime warnings early (before any imports that might load it)
import os
from pathlib import Path
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import asyncio
import time
boot_log.heartbeat("stdlib imports done; importing textual")

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static
from textual.widget import Widget
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.theme import Theme
from textual.strip import Strip
from textual import events
from rich.segment import Segment
from rich.style import Style
from enum import Enum
boot_log.heartbeat("textual/rich imports done; importing purple_tui.constants")

from .constants import (
    ICON_CHAT, ICON_MUSIC, ICON_PALETTE, ICON_MENU,
    ROOM_TITLES,
    STICKY_SHIFT_GRACE, ESCAPE_HOLD_THRESHOLD,
    ICON_BATTERY_FULL, ICON_BATTERY_HIGH, ICON_BATTERY_MED,
    ICON_BATTERY_LOW, ICON_BATTERY_EMPTY, ICON_BATTERY_CHARGING,
    ICON_VOLUME_OFF, ICON_VOLUME_LOW, ICON_VOLUME_MED, ICON_VOLUME_HIGH,
    ICON_SHIFT,
    ICON_USB, ICON_SIGN_OUT, ICON_HARDDISK, ICON_ROBOT, display_len,
    is_usb_cached, is_usb_present,
    VOLUME_LEVELS, VOLUME_DEFAULT,
    VIEWPORT_WIDTH, VIEWPORT_HEIGHT, WRAPPER_REFERENCE_ROWS,
    ROOM_PLAY, ROOM_MUSIC, ROOM_ART,
    is_live_boot, is_debug,
)
boot_log.heartbeat("constants imported; importing keyboard + input")
from .keyboard import (
    create_keyboard_state, detect_keyboard_mode,
    KeyboardStateMachine, CharacterAction, NavigationAction,
    RoomAction, ControlAction,
    InputFloodGuard,
)
from .input import EvdevReader, RawKeyEvent, PowerButtonReader, PowerButtonEvent, LidSwitchReader, LidSwitchEvent, check_evdev_available
from . import caps as _caps_chokepoint  # noqa: F401  # side-effect: installs Strip render-time uppercase patch
boot_log.heartbeat("keyboard + input imported; importing power_manager")
from .power_manager import get_power_manager
boot_log.heartbeat("power_manager imported; importing .demo")
from .demo import DemoPlayer, get_demo_script, get_speed_multiplier
boot_log.heartbeat(".demo imported; importing rooms.art_room")
from .rooms.art_room import ColorLegend, PaintModeChanged
boot_log.heartbeat("rooms.art_room imported; importing rooms.parent_menu")
from .rooms.parent_menu import apply_saved_display_settings
boot_log.heartbeat("rooms.parent_menu imported; importing room_picker")
from .room_picker import RoomPickerScreen
boot_log.heartbeat("room_picker imported; importing repl_panel")
from .repl_panel import ReplCommandSubmitted, ReplPanelClosed, ReplPanelToggleRequested, ReplPanel
from .loop_panel import LoopPanelToggleRequested
boot_log.heartbeat("all purple_tui imports done")


def _border_bar_color(active_theme: str) -> str:
    """Hex of the viewport border colour for the active theme. Used to tint
    the heavy-line spacers inside the bottom-border subtitle so the border
    looks visually continuous between the left- and right-anchored hints."""
    return "#9b7bc4" if active_theme == "purple-dark" else "#7a4ca0"


def _spanning_subtitle(left: str | None, right: str | None, active_theme: str) -> str:
    """Build a left-aligned bottom-border subtitle that spans the border.

    Gaps are filled with `━` characters tinted to match the border, so the
    border line keeps reading as continuous between the visible hints. The
    viewport CSS sets `border-subtitle-align: left` so the string anchors
    at the left edge.
    """
    bar_color = _border_bar_color(active_theme)
    # Textual draws: corner(1) + pad(1) + subtitle + pad(1) + corner(1) on
    # each row, leaving (width - 4) Rich-cells for the subtitle. We size
    # the string to *exactly* fill that slot in Rich-cell terms (== char
    # count, since Rich measures every PUA glyph as 1 cell). That makes
    # the rightmost icon sit at the last subtitle column, so its 2nd
    # painted cell lands on the trailing pad — same place the rightmost
    # icon sits in the single-hint right-align case. If we under-filled
    # in Rich cells (e.g. by reasoning in display cells), Textual would
    # add native ━ filler at the right end and visually shove the right
    # hint away from the corner.
    #
    # Pad a literal space between every hint edge and the ━ filler. The
    # 2nd painted cell of a trailing/leading icon would otherwise overlap
    # the adjacent ━ — a dash slicing through the icon — because Rich
    # placed the next character one cell after the icon while the
    # terminal painted the icon two cells wide.
    interior = VIEWPORT_WIDTH - 6
    parts: list[str] = []
    used = 0
    if left:
        parts.append(left + " ")
        used += len(left) + 1
    if right:
        right_w = len(right) + 1  # leading space
        gap = max(1, interior - used - right_w)
        parts.append(f"[{bar_color}]{'━' * gap}[/]")
        parts.append(" " + right)
    elif left:
        gap = max(1, interior - used)
        parts.append(f"[{bar_color}]{'━' * gap}[/]")
    return "".join(parts)


def _set_viewport_hints(viewport, *, left: str | None, right: str | None, active_theme: str) -> None:
    """Apply bottom-border hints, picking alignment so single-hint cases let
    Textual fill the rest of the border naturally (no visible color seam)."""
    if left and right:
        viewport.styles.border_subtitle_align = "left"
        viewport.border_subtitle = _spanning_subtitle(left, right, active_theme)
    elif left:
        viewport.styles.border_subtitle_align = "left"
        # Trailing space stops the trailing icon's 2nd painted cell from
        # overlapping Textual's native ━ filler.
        viewport.border_subtitle = left + " "
    elif right:
        viewport.styles.border_subtitle_align = "right"
        # No leading space: the right hint's first icon paints rightward
        # into its own next char, never backward into Textual's ━ filler,
        # so a leading buffer would just show as an empty cell where the
        # border line should continue.
        viewport.border_subtitle = right
    else:
        viewport.border_subtitle = ""


def _apply_room_subtitle(viewport, room: 'Room', code_panel_enabled: bool, active_theme: str, music_looping_enabled: bool = True) -> None:
    """Idle (no panel open) bottom-border hints for music/art rooms."""
    right = None
    left = None
    if room in (Room.MUSIC, Room.ART) and code_panel_enabled:
        right = f"{ICON_ROBOT} Hold Space: write code! {ICON_ROBOT}"
    if room == Room.MUSIC and music_looping_enabled:
        left = f"{ICON_MUSIC} Hold Enter: record a loop {ICON_MUSIC}"
    _set_viewport_hints(viewport, left=left, right=right, active_theme=active_theme)


class Room(Enum):
    """The 3 core rooms of Purple Computer"""
    PLAY = 1     # Math and emoji REPL
    MUSIC = 2    # Music and art grid
    ART = 3      # Simple drawing canvas


class View(Enum):
    """The 3 core views. Reduce screen time feeling."""
    SCREEN = 1   # 10x6" viewport
    LINE = 2     # 10" wide, 1 line height
    EARS = 3     # Screen off (blank)


class TitleBar(Widget):
    """Renders centered room title with right-aligned status indicators.

    Uses render_line for pixel-perfect positioning: title is centered within
    the full width regardless of indicator widths. Indicators are always
    right-aligned 1 cell from the right edge.
    """

    DEFAULT_CSS = """
    TitleBar {
        width: 100%;
        height: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = ROOM_PLAY[0]
        self._shift_text = ""
        self._shift_active = False
        self._battery_text = ""
        self._boot_text = ""
        self._boot_color = ""

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.refresh()

    def set_shift(self, text: str, active: bool) -> None:
        self._shift_text = text
        self._shift_active = active
        self.refresh()

    def set_battery(self, text: str) -> None:
        self._battery_text = text
        self.refresh()

    def set_boot_mode(self, text: str, color: str) -> None:
        self._boot_text = text
        self._boot_color = color
        self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if width <= 0 or y != 0:
            return Strip([])

        # Left indicator (boot mode: USB or Installed), aligned with viewport border
        left_text = f"       {self._boot_text}" if self._boot_text else ""
        left_len = display_len(left_text)

        # Title (centered within full width)
        icon, label = ROOM_TITLES.get(self.mode, ("", self.mode.title()))
        title = f"{icon}  {label}"
        title_start = max(0, (width - display_len(title)) // 2)

        # Right indicator segments (right-aligned)
        primary = "#9b7bc4"
        accent = "#6a3c90"
        muted = "#6a5a80"
        indicator_parts: list[tuple[str, str]] = []
        if self._shift_text:
            indicator_parts.append((self._shift_text + " ", accent if self._shift_active else muted))
        if self._battery_text:
            indicator_parts.append((" " + self._battery_text, primary))

        indicator_total = sum(display_len(t) for t, _ in indicator_parts)
        indicator_start = max(0, width - indicator_total - 4)

        # Build segments left to right
        title_style = Style(color=primary, bold=True)
        title_end = min(width, title_start + display_len(title))
        # Clamp title to not overlap left or right indicators
        effective_title_start = max(title_start, left_len)
        effective_title_end = min(title_end, indicator_start)

        segments: list[Segment] = []
        pos = 0

        # Left indicator (boot mode)
        if left_text:
            segments.append(Segment(left_text, Style(color=self._boot_color)))
            pos = left_len

        # Gap between left indicator and title
        if effective_title_start > pos:
            segments.append(Segment(" " * (effective_title_start - pos)))
            pos = effective_title_start

        # Title text (possibly truncated)
        if effective_title_end > pos:
            title_offset = pos - title_start
            segments.append(Segment(title[title_offset:title_offset + (effective_title_end - pos)], title_style))
            pos = effective_title_end

        # Gap between title and right indicators
        if indicator_start > pos:
            segments.append(Segment(" " * (indicator_start - pos)))
            pos = indicator_start

        # Right indicators
        for text, color in indicator_parts:
            segments.append(Segment(text, Style(color=color)))
            pos += display_len(text)

        # Trailing space
        if pos < width:
            segments.append(Segment(" " * (width - pos)))

        return Strip(segments)


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

    def render(self) -> str:
        return f"{self._icon} {self._room_name}"


class RoomIndicator(Horizontal):
    """Shows mode indicators (icons + names) and mute indicator."""

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
            esc_badge = KeyBadge(f"Esc {ICON_MENU}", id="key-esc")
            esc_badge.add_class("dim")
            yield esc_badge

            room_info = {
                Room.PLAY: (ICON_CHAT, "Play"),
                Room.MUSIC: (ICON_MUSIC, "Music"),
                Room.ART: (ICON_PALETTE, "Art"),
            }
            for room in [Room.PLAY, Room.MUSIC, Room.ART]:
                icon, name = room_info[room]
                badge = RoomBadge(icon, name, id=f"key-{room.name.lower()}")
                if room == self.current_room:
                    badge.add_class("active")
                else:
                    badge.add_class("dim")
                yield badge

        yield Static("", id="keys-spacer-right")

        with Horizontal(id="keys-right"):
            mute_badge = KeyBadge(ICON_VOLUME_OFF, id="key-mute")
            mute_badge.add_class("dim")
            mute_badge.display = False
            yield mute_badge

    def update_room(self, room: Room) -> None:
        self.current_room = room
        for m in [Room.PLAY, Room.MUSIC, Room.ART]:
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


class CompactRoomIndicator(Static):
    """Compact 1-row room indicator shown when REPL panel is open."""

    DEFAULT_CSS = """
    CompactRoomIndicator {
        dock: bottom;
        width: 100%;
        height: 1;
        text-align: center;
        color: $text-muted;
        background: $background;
        display: none;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_room = Room.PLAY

    def update_room(self, room: Room) -> None:
        self._current_room = room
        self.refresh()

    def render(self) -> str:
        rooms = [
            (Room.PLAY, ICON_CHAT, "Play"),
            (Room.MUSIC, ICON_MUSIC, "Music"),
            (Room.ART, ICON_PALETTE, "Art"),
        ]
        parts = []
        for room, icon, name in rooms:
            if room == self._current_room:
                parts.append(f"[bold $accent]{icon} {name}[/]")
            else:
                parts.append(f"[dim]{icon} {name}[/]")
        return f"Esc {ICON_MENU}  " + "  ".join(parts)


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
            self._update_battery()  # Push initial state
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
        """Periodic update callback: push battery text to TitleBar."""
        status = self._read_battery_status()
        if status is None:
            text = ICON_BATTERY_FULL if os.environ.get("PURPLE_TEST_BATTERY") else ""
        else:
            capacity, charging = status
            text = self._get_battery_icon(capacity, charging)
        try:
            title_bar = self.screen.query_one("#title-bar")
            title_bar.set_battery(text)
        except Exception:
            pass

    def render(self) -> str:
        return ""


DEFAULT_COMPUTER_NAME = "My Purple Computer"

_COMPUTER_NAME_CACHE: str | None = None
_COMPUTER_NAME_LOADED = False

# User-writable override for the computer name. Lets the parent rename without
# sudo after install. install.sh seeds /opt/purple/computer_name.txt; the
# override wins if present (even if empty, meaning "no name").
_COMPUTER_NAME_USER_PATH = Path.home() / ".purple" / "computer_name.txt"
_COMPUTER_NAME_SYSTEM_PATH = Path("/opt/purple/computer_name.txt")


def _read_computer_name() -> str | None:
    """Return the computer name, or None. User override wins over install-time value."""
    global _COMPUTER_NAME_CACHE, _COMPUTER_NAME_LOADED
    if _COMPUTER_NAME_LOADED:
        return _COMPUTER_NAME_CACHE
    _COMPUTER_NAME_LOADED = True
    for path in (_COMPUTER_NAME_USER_PATH, _COMPUTER_NAME_SYSTEM_PATH):
        try:
            name = path.read_text().strip()
            _COMPUTER_NAME_CACHE = name or None
            return _COMPUTER_NAME_CACHE
        except OSError:
            continue
    _COMPUTER_NAME_CACHE = None
    return _COMPUTER_NAME_CACHE


def write_computer_name(name: str) -> None:
    """Persist a user-supplied computer name and refresh the cached value."""
    global _COMPUTER_NAME_CACHE, _COMPUTER_NAME_LOADED
    _COMPUTER_NAME_USER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _COMPUTER_NAME_USER_PATH.write_text(name)
    _COMPUTER_NAME_CACHE = name.strip() or None
    _COMPUTER_NAME_LOADED = True


class BootModeIndicator(Static):
    """Shows boot mode in title bar: USB (with eject status) or Installed.

    Uses is_live_boot() (checks /proc/cmdline) rather than squashfs file
    existence, since /cdrom may be unmounted after caching on some machines.
    """

    DEFAULT_CSS = """
    BootModeIndicator {
        width: auto;
        height: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._is_live = False
        self._is_cached = False
        self._usb_removed = False
        self._blink_state = True

    def on_mount(self) -> None:
        self._is_live = is_live_boot()
        self._push_to_title_bar()
        if not self._is_live:
            return

        if is_usb_cached():
            self._is_cached = True
            self._usb_removed = not is_usb_present()
            self._push_to_title_bar()
            self.set_interval(5.0, self._check_usb_removed)
            return

        self.set_interval(5.0, self._check_cache_done)
        self.set_interval(1.0, self._toggle_blink)

    def _check_cache_done(self) -> None:
        if is_usb_cached():
            self._is_cached = True
            self._blink_state = True
            self._push_to_title_bar()
            self.set_interval(5.0, self._check_usb_removed)

    def _check_usb_removed(self) -> None:
        removed = not is_usb_present()
        if removed != self._usb_removed:
            self._usb_removed = removed
            self._push_to_title_bar()

    def _toggle_blink(self) -> None:
        if self._is_cached:
            return
        self._blink_state = not self._blink_state
        self._push_to_title_bar()

    def _push_to_title_bar(self) -> None:
        muted = "#6a5a80"
        if not self._is_live:
            label = _read_computer_name() or DEFAULT_COMPUTER_NAME
            text, color = f"{ICON_HARDDISK} {label}", muted
        elif self._is_cached and self._usb_removed:
            text, color = f"{ICON_USB} USB {ICON_SIGN_OUT} If restart, reinsert", muted
        elif self._is_cached:
            text, color = (
                f"{ICON_USB} USB {ICON_SIGN_OUT} OK to remove \u2022 If restart, reinsert",
                muted,
            )
        elif self._blink_state:
            text, color = f"{ICON_USB} USB", muted
        else:
            text, color = "  USB", muted
        try:
            title_bar = self.screen.query_one("#title-bar")
            title_bar.set_boot_mode(text, color)
        except Exception:
            pass

    def render(self) -> str:
        return ""


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
        align: center top;
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

    #legend-spacer {
        width: 5;
    }

    #paint-legend {
        width: 4;
        height: 4;
        margin-left: 1;
        margin-top: __LEGEND_TOP_MARGIN__;
    }

    #title-bar {
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }

    #battery-indicator, #boot-mode-indicator {
        display: none;
    }

    #viewport {
        width: __VIEWPORT_WIDTH__;
        height: __VIEWPORT_HEIGHT__;
        border: heavy $primary;
        background: $surface;
        border-subtitle-align: left;
    }

    #room-indicator {
        dock: bottom;
        height: 3;
        margin-top: 1;
        background: $background;
    }

    #littles-hint {
        display: none;
        dock: bottom;
        height: 3;
        margin-top: 1;
        background: $background;
        content-align: center middle;
        text-align: center;
        color: $text-muted;
    }

    #content-area {
        width: 100%;
        height: 100%;
    }

    .room-content {
        width: 100%;
        height: 100%;
    }

    Toast {
        width: 32;
        max-width: 32;
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

    """.replace("__VIEWPORT_WIDTH__", str(VIEWPORT_WIDTH)).replace("__VIEWPORT_BORDER_WIDTH__", str(VIEWPORT_WIDTH + 2)).replace("__VIEWPORT_HEIGHT__", str(VIEWPORT_HEIGHT)).replace("__LEGEND_TOP_MARGIN__", str(VIEWPORT_HEIGHT - 5))  # align legend near viewport bottom

    # Note: These bindings are for fallback only; evdev handles actual keyboard input
    BINDINGS = [
        Binding("f8", "take_screenshot", "Screenshot", show=False, priority=True),
        Binding("ctrl+v", "cycle_view", "View", show=False, priority=True),
    ]


    def __init__(self):
        boot_log.heartbeat("PurpleApp.__init__ begin")
        super().__init__()
        boot_log.heartbeat("PurpleApp.__init__ after App.__init__")
        self.active_room = Room.PLAY
        self.active_view = View.SCREEN
        self.active_theme = "purple-dark"
        self.speech_enabled = False
        self.volume_level = VOLUME_DEFAULT  # 0-100
        self._volume_before_mute = VOLUME_DEFAULT  # Remember level when muting
        self._silent_mode = False  # Parent silence lock; volume keys disabled while True
        self._brightness_hint_showing = False  # Prevent layering brightness toasts

        # Power management
        self._idle_timer = None
        self._power_button_reader: PowerButtonReader | None = None
        self._lid_switch_reader: LidSwitchReader | None = None
        self._lid_close_time: float | None = None  # When lid was closed (for shutdown timer)
        self._lid_was_closed_for: float = 0  # How long lid was closed (for sleep screen status)
        self._bye_screen_active = False
        self._app_suspended = False  # True while shell is open via parent menu
        self._idle_inhibitors: set[str] = set()  # Reasons currently suppressing idle sleep/shutdown

        # Keyboard state for caps lock tracking and mode detection
        self.keyboard = create_keyboard_state(
            sticky_grace_period=STICKY_SHIFT_GRACE,
            escape_hold_threshold=ESCAPE_HOLD_THRESHOLD,
        )
        if os.environ.get("PURPLE_NO_EVDEV") != "1":
            self.keyboard.mode = detect_keyboard_mode()

        # Direct evdev keyboard input (replaces terminal on_key)
        self._keyboard_state_machine = KeyboardStateMachine()
        self._keyboard_state_machine.on_sticky_shift_change(self._on_sticky_shift_change)
        self._input_flood_guard = InputFloodGuard()
        self._sticky_shift_timer = None
        self._evdev_reader: EvdevReader | None = None
        self._escape_hold_timer = None  # Timer for detecting escape long-hold
        self._escape_triggered_long_hold = False  # True if long-hold fired (avoid showing picker)
        self._modal_open_at_escape_press = False  # True if modal was open when ESC was pressed

        # Littles Mode: locks into a single room with no switching
        self._littles_mode: str | None = None  # None, "music", or "art"
        self._code_panel_enabled: bool = True
        self._code_panel_active: bool = False  # True when code panel mode is on (persists across rooms)
        self._music_looping_enabled: bool = True
        self._music_key_switching_enabled: bool = True

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
                yield TitleBar(id="title-bar")
                with Horizontal(id="viewport-row"):
                    yield Static("", id="legend-spacer")
                    with ViewportContainer(id="viewport"):
                        yield Container(id="content-area")
                    yield ColorLegend(id="paint-legend")
            yield RoomIndicator(self.active_room, id="room-indicator")
            yield Static("🎈 Littles Mode  ·  Hold Esc to exit", id="littles-hint")
            yield CompactRoomIndicator(id="compact-room-indicator")
            # Hidden state-tracking widgets (push updates to TitleBar)
            yield BatteryIndicator(id="battery-indicator")
            yield BootModeIndicator(id="boot-mode-indicator")

    async def on_mount(self) -> None:
        """Called when app starts"""
        boot_log.heartbeat("PurpleApp.on_mount begin")
        self._apply_theme()
        # Pin wrapper top so code/loop mode growth doesn't shift the border 1 row on odd-height terminals.
        self.query_one("#viewport-wrapper").styles.margin = (max(0, (self.size.height - WRAPPER_REFERENCE_ROWS) // 2), 0, 0, 0)

        # Ensure logind ignores power button (TUI handles it).
        # Defensive: a previous crash or logind-mediated shutdown during a
        # shell session can leave the config stuck on "poweroff".
        from .power_manager import set_logind_power_key
        set_logind_power_key("ignore")

        from .settings import (get_littles_mode, get_code_panel, get_music_looping,
                               get_music_key_switching, get_all_caps, get_volume_level, get_silent_mode)
        from . import caps as caps_module
        caps_module.set_enabled(get_all_caps())
        self.volume_level = get_volume_level()
        self._silent_mode = get_silent_mode()
        saved_littles = get_littles_mode()
        if saved_littles:
            self._littles_mode = saved_littles
            self._code_panel_enabled = False
            self._music_looping_enabled = False
            self._music_key_switching_enabled = False
            room_map = {"music": Room.MUSIC, "music_noscreen": Room.MUSIC, "art": Room.ART}
            self.active_room = room_map.get(saved_littles, Room.MUSIC)
        else:
            self._code_panel_enabled = get_code_panel()
            self._music_looping_enabled = get_music_looping()
            self._music_key_switching_enabled = get_music_key_switching()

        self._load_room_content()

        # Set system volume to match the effective volume (0 while silent mode is locked on)
        self._apply_volume_system()
        from . import tts
        tts.set_muted(self._effective_volume() == 0)

        # Set viewport border subtitle for music/art rooms
        try:
            viewport = self.query_one("#viewport")
            _apply_room_subtitle(viewport, self.active_room, self._code_panel_enabled, self.active_theme, self._music_looping_enabled)
        except NoMatches:
            pass

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

        # Hide room indicator in Littles Mode, show hint instead
        if self._littles_mode:
            try:
                self.query_one("#room-indicator", RoomIndicator).display = False
                self.query_one("#littles-hint", Static).display = True
            except NoMatches:
                pass

        # Start direct evdev keyboard reader (unless disabled for AI tools)
        # This reads keyboard events directly, bypassing the terminal
        if os.environ.get("PURPLE_NO_EVDEV") != "1":
            self._evdev_reader = EvdevReader(
                callback=self._handle_raw_key_event,
                grab=not is_debug(),  # No grab in debug: allows kernel VT switch
            )
            await self._evdev_reader.start()
        else:
            self._evdev_reader = None

        # Start power button reader (separate device from keyboard)
        if os.environ.get("PURPLE_NO_EVDEV") != "1":
            from .power_manager import POWER_HOLD_SHUTDOWN, _power_log
            self._power_button_reader = PowerButtonReader(
                callback=self._handle_power_button_event,
                hold_seconds=POWER_HOLD_SHUTDOWN,
            )
            try:
                await self._power_button_reader.start()
                if not self._power_button_reader._devices:
                    _power_log("POWER BUTTON INIT: no device found")
                else:
                    for dev in self._power_button_reader._devices:
                        _power_log(f"POWER BUTTON INIT: listening on {dev.path} ({dev.name})")
            except Exception as e:
                _power_log(f"POWER BUTTON INIT: start failed: {e}")
                self._power_button_reader = None

        # Start lid switch reader (instant lid open/close detection via evdev)
        if os.environ.get("PURPLE_NO_EVDEV") != "1":
            self._lid_switch_reader = LidSwitchReader(
                callback=self._handle_lid_switch_event,
            )
            try:
                await self._lid_switch_reader.start()
            except Exception:
                self._lid_switch_reader = None

        # Start idle detection timer (disabled in dev mode for AI training)
        # In demo mode, check every second for responsiveness
        # In normal mode, check every 5 seconds to save resources
        if os.environ.get("PURPLE_DEV_MODE") == "1":
            # Dev mode: no sleep screen (for AI training)
            self._idle_timer = None
        else:
            from .power_manager import (
                CHARGER_IDLE_SLEEP, CHARGER_IDLE_SHUTDOWN,
                BATTERY_IDLE_SLEEP, BATTERY_IDLE_SHUTDOWN,
            )

            if os.environ.get("PURPLE_SLEEP_DEMO"):
                check_interval = 1.0
                self.notify(
                    f"Demo: sleep@{BATTERY_IDLE_SLEEP}s/{CHARGER_IDLE_SLEEP}s, "
                    f"shutdown@{BATTERY_IDLE_SHUTDOWN}s/{CHARGER_IDLE_SHUTDOWN}s",
                    title="Sleep Demo",
                    timeout=5,
                )
            else:
                check_interval = 5.0

            self._idle_timer = self.set_interval(check_interval, self._check_idle_state)

        # Periodic toast cleanup: Textual's per-toast timer can drop callbacks
        # during screen transitions or heavy evdev input, and App.query only
        # walks the active screen — so toasts on backgrounded screens (e.g.
        # under a pushed modal) never get reaped by their own timer view.
        self.set_interval(1.0, self._reap_stale_toasts)

        # Keyboard diagnostic mode: if no evdev input for 60 seconds, exit to
        # debug shell. Activated by purple.inputtest=1 kernel parameter.
        # This lets developers diagnose keyboard issues when the app can't
        # receive input (can't open parent menu, can't switch to tty2).
        self._debug_no_input_received = False
        try:
            cmdline = Path("/proc/cmdline").read_text()
            if "purple.inputtest=1" in cmdline:
                self.set_timer(60.0, self._debug_exit_on_no_input)
        except Exception:
            pass

        # Auto-start demo if requested (for recording)
        if os.environ.get("PURPLE_DEMO_AUTOSTART"):
            # Wait 2 seconds for FFmpeg to stabilize (trimmed from final video)
            self.set_timer(2.0, self.start_demo)

        # Show live boot splash on first launch from USB
        if not os.environ.get("PURPLE_DEV_MODE") == "1":
            if is_live_boot():
                from .rooms.sleep_screen import LiveBootSplash
                self.push_screen(LiveBootSplash())

        # In dev mode, check for screenshot and command trigger files (for AI tools)
        if os.environ.get("PURPLE_DEV_MODE") == "1":
            self._dev_log("[Mount] Starting dev mode timers...")
            self._screenshot_timer = self.set_interval(0.2, self._check_screenshot_trigger)
            self._command_timer = self.set_interval(0.1, self._check_command_trigger)
            self._dev_log("[Mount] Dev mode timers started")

        boot_log.heartbeat("PurpleApp.on_mount complete")
        boot_log.mark_first_render()

        # Apply saved display brightness/contrast after first render so the
        # xrandr probe (~0.2-1s) doesn't delay time-to-first-frame. The
        # settings apply on the next event loop tick, imperceptible to users.
        self.call_later(apply_saved_display_settings)

        # Background warmup: subprocess-probe + init the pygame mixer so
        # MusicRoom entry is instant (and we know early if audio is broken).
        # Retries on failure: PulseAudio/ALSA may still be initializing at
        # boot, so the first probe can fail even on working hardware.
        self.audio_ok = None  # None = probing, True/False = probed result
        if os.environ.get("PURPLE_NO_AUDIO") == "1":
            self.audio_ok = False
            boot_log.heartbeat("mixer disabled (PURPLE_NO_AUDIO=1)")
        else:
            self._start_mixer_warmup()

    def _start_mixer_warmup(self) -> None:
        import threading
        import time as _time
        def _warm():
            from .rooms.music_room import warm_mixer, _reset_mixer_state
            if warm_mixer():
                self.audio_ok = True
                boot_log.heartbeat("mixer ok (attempt 1)")
            else:
                for delay in [0.5, 1, 2]:
                    if not _reset_mixer_state():
                        boot_log.heartbeat("mixer probe timed out (hw broken)")
                        break
                    boot_log.heartbeat(f"mixer probe failed, retrying in {delay}s")
                    _time.sleep(delay)
                    if warm_mixer():
                        self.audio_ok = True
                        boot_log.heartbeat("mixer ok (retry)")
                        break
                else:
                    self.audio_ok = False
                    boot_log.heartbeat("mixer warmup failed")
            # After the initial probe lands either way, start the hotplug listener
            # so USB speaker plug-in works without a restart. Started here (not at
            # app startup) so we don't race the warmup probe.
            self._start_audio_hotplug()
            self._start_audio_retry_poll()
        threading.Thread(target=_warm, daemon=True, name="mixer-warmup").start()

    def _start_audio_hotplug(self) -> None:
        from . import audio_hotplug

        def _on_event(action: str) -> None:
            boot_log.heartbeat(f"audio hotplug: {action}")
            from .rooms.music_room import reinit_mixer_after_hotplug
            ok = reinit_mixer_after_hotplug()
            # Flip audio_ok on the main thread so the parent menu indicator
            # updates without a Purple restart.
            self.call_from_thread(setattr, self, "audio_ok", ok)
            boot_log.heartbeat(f"audio hotplug reinit -> ok={ok}")

        audio_hotplug.start(_on_event)

    def _start_audio_retry_poll(self) -> None:
        # Kernel sound-subsystem hotplug doesn't fire when Pulse itself
        # transitions from dead to alive (the card was there the whole time),
        # so a first-boot Pulse crash-loop that later recovers would leave
        # audio_ok=False forever. Poll cheaply every few seconds while
        # audio_ok is False; flip to True the moment a probe succeeds.
        import threading
        import time as _time

        def _poll() -> None:
            from .rooms.music_room import reinit_mixer_after_hotplug
            while True:
                _time.sleep(5)
                if self.audio_ok:
                    return
                if reinit_mixer_after_hotplug():
                    self.call_from_thread(setattr, self, "audio_ok", True)
                    boot_log.heartbeat("audio retry poll: mixer came up")
                    return

        threading.Thread(target=_poll, daemon=True, name="audio-retry-poll").start()

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

        # Clean up lid switch reader
        if self._lid_switch_reader:
            await self._lid_switch_reader.stop()
            self._lid_switch_reader = None

        # Shut down pygame mixer to prevent SDL audio thread hang on exit.
        # Bounded timeout: on healthy systems quit() returns well under 1s and
        # the join completes immediately. On systems where SDL wedges against
        # the audio device (UTM/QEMU virt audio, flaky USB/Bluetooth audio on
        # real hardware), we don't block shutdown -- the process is exiting
        # anyway and the OS reaps the daemon thread.
        try:
            import pygame.mixer
            import threading
            if pygame.mixer.get_init():
                t = threading.Thread(target=pygame.mixer.quit, daemon=True)
                t.start()
                t.join(timeout=1.0)
        except Exception:
            pass

    def on_paint_mode_changed(self, event: PaintModeChanged) -> None:
        """Show/hide paint legend and update active row when paint mode changes."""
        try:
            legend = self.query_one("#paint-legend", ColorLegend)
            legend.set_visible(event.is_painting)
            legend.set_active_color(event.last_color)
        except NoMatches:
            pass
        # Refresh shift banner hint (paint vs text mode shows different hints)
        self._update_shift_indicator()

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

        # Mark that we've received evdev input (used by debug exit timer)
        self._debug_no_input_received = True

        # Record user activity for idle detection
        self._record_user_activity()

        # Flush stale TTS audio after long gaps (e.g., VM suspend/resume)
        now = time.monotonic()
        if now - getattr(self, '_last_evdev_time', now) > 5.0:
            from . import tts
            tts.stop()
            self._input_flood_guard.reset()
        self._last_evdev_time = now

        # Process through state machine
        actions = self._keyboard_state_machine.process(event)

        for action in actions:
            if self._input_flood_guard.should_drop(action):
                continue
            if os.environ.get("PURPLE_DEV_MODE") == "1":
                self._dev_log(f"[Evdev] action={action} (current_room={self.active_room.name})")
            await self._dispatch_keyboard_action(action)

        # Backslash hold: start a 3s timer when backslash is first pressed
        if self._keyboard_state_machine.backslash_held:
            if not hasattr(self, '_backslash_hold_timer') or self._backslash_hold_timer is None:
                self._backslash_hold_timer = self.set_timer(
                    self._keyboard_state_machine.BACKSLASH_HOLD_THRESHOLD,
                    self._check_backslash_hold,
                )
        else:
            if hasattr(self, '_backslash_hold_timer') and self._backslash_hold_timer is not None:
                self._backslash_hold_timer.stop()
                self._backslash_hold_timer = None

    async def _dispatch_keyboard_action(self, action) -> None:
        """Dispatch a keyboard action to the appropriate handler."""
        if isinstance(action, RoomAction):
            if action.room == 'parent':
                self.action_parent_menu()
            else:
                # Room switching (used by playback/demo system)
                self.action_switch_room(action.room)
            return

        # Handle escape key for long-hold detection and tap-to-pick
        # Only start timer on fresh press, not on repeat events (which would restart the timer)
        if isinstance(action, ControlAction) and action.action == 'escape':
            if action.is_down and not action.is_repeat:
                self._escape_triggered_long_hold = False  # Reset on fresh press
                self._escape_consumed_by_mode = False
                # Stop demo/code playback if running (in any room)
                if self.demo_running:
                    self.cancel_demo()
                    self._escape_consumed_by_mode = True
                # Stop code space execution if running
                if self._stop_code_execution():
                    self._escape_consumed_by_mode = True
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
                    if len(self.screen_stack) == 1 and not self._littles_mode:
                        self._show_room_picker()
                        return
            # Don't return - let escape events propagate to modes for other uses

        # Handle global volume/brightness controls (blocked in Littles Mode)
        if isinstance(action, ControlAction) and action.is_down and not self._littles_mode:
            if action.action == 'volume_mute':
                self.action_volume_mute()
                return
            if action.action == 'volume_down':
                self.action_volume_down()
                return
            if action.action == 'volume_up':
                self.action_volume_up()
                return
            if action.action == 'brightness_hint':
                self._show_brightness_hint()
                return

        # Kid-friendly math-symbol remaps: = -> +, / -> ÷, * -> ×.
        # Shifted forms (?, *) still flow through unchanged because CharacterAction
        # carries the produced char, not the physical key.
        _KID_MATH_REMAP = {'=': '+', '/': '÷', '*': '×'}
        if isinstance(action, CharacterAction) and action.char in _KID_MATH_REMAP:
            action = CharacterAction(
                char=_KID_MATH_REMAP[action.char],
                shifted=action.shifted, shift_held=action.shift_held,
                is_repeat=action.is_repeat, arrow_held=action.arrow_held,
            )

        # Check if a modal screen is active (e.g., ParentMenu)
        # screen_stack[0] is the base screen, anything above is a modal
        if len(self.screen_stack) > 1:
            active_screen = self.screen
            if hasattr(active_screen, 'handle_keyboard_action'):
                await active_screen.handle_keyboard_action(action)
            return

        # Block tab in Littles Mode (prevents sub-mode switching in music/art)
        if self._littles_mode and isinstance(action, ControlAction) and action.action == 'tab':
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
        """Called by timer after 1s. Trigger parent mode if escape still held.

        If the room picker is currently open, dismiss it first so parent menu
        replaces it cleanly instead of stacking on top.
        """
        if self._keyboard_state_machine.check_escape_hold():
            self._escape_triggered_long_hold = True  # Prevent picker open/close on release
            self._cancel_escape_hold_timer()
            if len(self.screen_stack) > 1 and isinstance(self.screen, RoomPickerScreen):
                self.screen.dismiss(None)
            self.action_parent_menu()

    def _check_backslash_hold(self) -> None:
        """Called by timer after 3s. Trigger parent menu if backslash still held."""
        if self._keyboard_state_machine.check_backslash_hold():
            self._backslash_hold_timer = None
            self.action_parent_menu()

    def _show_room_picker(self) -> None:
        """Show the mode picker modal."""
        self.clear_notifications()
        current_room = self.active_room.name.lower()
        picker = RoomPickerScreen(
            current_room=current_room,
            code_panel_open=self._code_panel_active,
            code_panel_enabled=self._code_panel_enabled,
        )
        self.push_screen(picker, self._on_room_picked)

    def on_room_picker_screen_room_selected(self, event: RoomPickerScreen.RoomSelected) -> None:
        """Handle room selection from picker: switch room, then dismiss picker.

        By switching the room content before dismissing, we avoid a flicker
        frame where the old room is visible behind the picker.
        """
        room_name = event.result.get("room")
        if room_name == "play":
            self.action_switch_room(ROOM_PLAY[0])
        elif room_name == "music":
            self.action_switch_room(ROOM_MUSIC[0])
        elif room_name == "art":
            self.action_switch_room(ROOM_ART[0])
        # Now dismiss the picker (new room is already showing underneath)
        if len(self.screen_stack) > 1:
            self.screen.dismiss(None)

    def _on_room_picked(self, result: dict | None) -> None:
        """Handle mode picker dismiss for non-room actions."""
        if result is None:
            return

        # Toggle code panel
        if result.get("close_code"):
            self._close_repl_panel()
            return
        if result.get("open_code"):
            self._code_panel_active = True
            self._open_code_panel_in_room(self.active_room)
            return

        # Start fresh: clear all rooms
        if result.get("start_fresh"):
            self._start_fresh()
            return

    _code_run_task: asyncio.Task | None = None

    def _stop_code_execution(self) -> bool:
        """Cancel any running code task. Returns True if something was stopped."""
        if self._code_run_task and not self._code_run_task.done():
            self._code_run_task.cancel()
            self._code_run_task = None
            return True
        return False

    def on_repl_command_submitted(self, message: ReplCommandSubmitted) -> None:
        """Handle command from REPL panel in music/art rooms."""
        self._stop_code_execution()
        self._code_run_task = asyncio.ensure_future(
            self._run_repl_command(message.room, message.lines)
        )

    async def _run_repl_command(self, room: str, lines: list[str]) -> None:
        """Execute REPL command for music/art rooms."""
        if room == "music":
            from .code_runner import MusicCodeRunner
            try:
                content_area = self.query_one("#content-area")
                music = content_area.query_one("#room-music")
                mode = "letters" if music._letters_mode else "music"

                def play_key(key, m):
                    music._play_key(key, m)

                def set_inst(name):
                    from .music_constants import INSTRUMENTS, INSTRUMENT_ALIASES
                    name_lower = INSTRUMENT_ALIASES.get(name.lower(), name.lower())
                    for i, (inst_id, inst_name) in enumerate(INSTRUMENTS):
                        if inst_name.lower() == name_lower or inst_id.lower() == name_lower:
                            music._instrument_index = i
                            if music.grid:
                                music.grid.set_instrument(i)
                            if music._header:
                                music._header.update_instrument(inst_name)
                            return
                    for i, (inst_id, inst_name) in enumerate(INSTRUMENTS):
                        if inst_name.lower().startswith(name_lower) or inst_id.lower().startswith(name_lower):
                            music._instrument_index = i
                            if music.grid:
                                music.grid.set_instrument(i)
                            if music._header:
                                music._header.update_instrument(inst_name)
                            return

                def set_letters(on):
                    music._letters_mode = on
                    if music._header:
                        music._header.update_mode(on)

                runner = MusicCodeRunner(
                    play_key_fn=play_key,
                    set_instrument_fn=set_inst,
                    color_fn=lambda k: music.grid.next_color(k, refresh=True),
                    flash_fn=lambda k: music.grid.flash_note(k),
                    set_letters_fn=set_letters,
                )
                await runner.run(lines, mode)
                # Show correction feedback
                if runner.corrections:
                    orig, corrected = runner.corrections[-1]
                    try:
                        from .code_input import RecallHint
                        panel = music.query_one(ReplPanel)
                        recall = panel.query_one("#repl-recall-hint", RecallHint)
                        recall.set_correction(orig, corrected)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log.error(f"REPL music command failed: {exc}")

        elif room == "art":
            from .code_runner import ArtCodeRunner
            try:
                content_area = self.query_one("#content-area")
                art = content_area.query_one("#room-art")
                canvas = art.query_one("#art-canvas")
                runner = ArtCodeRunner(canvas)
                # Canvas paint_mode determines default: paint vs write
                await runner.run(lines, paint=canvas._paint_mode)
                # Sync header with canvas state after code finishes
                canvas._post_paint_mode_changed()
                # Show correction feedback if the runner interpreted anything
                if runner.corrections:
                    orig, corrected = runner.corrections[-1]
                    try:
                        from .code_input import RecallHint
                        panel = art.query_one(ReplPanel)
                        recall = panel.query_one("#repl-recall-hint", RecallHint)
                        recall.set_correction(orig, corrected)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log.error(f"REPL art command failed: {exc}")

    def on_repl_panel_closed(self, message: ReplPanelClosed) -> None:
        """Handle REPL panel close request (from Escape on empty)."""
        # Panel already closed itself; restore viewport
        self._close_repl_panel()

    def on_loop_panel_toggle_requested(self, message: LoopPanelToggleRequested) -> None:
        """Mirror the REPL toggle: grow viewport on open, shrink on close."""
        self._apply_code_panel_ui(active=message.opened, kind='loop')

    def on_repl_panel_toggle_requested(self, message: ReplPanelToggleRequested) -> None:
        """Handle REPL toggle from room: resize viewport and hide/show indicator."""
        room_id = f"room-{message.room}"
        try:
            content_area = self.query_one("#content-area")
            room_widget = content_area.query_one(f"#{room_id}")
            panel = room_widget.query_one(ReplPanel)
            if panel.is_open:
                self._open_repl_panel()
            else:
                self._close_repl_panel()
        except NoMatches:
            pass

    def _open_repl_panel(self) -> None:
        """Grow viewport to accommodate REPL panel, switch to compact indicator."""
        self._stop_code_execution()
        self._code_panel_active = True
        self._apply_code_panel_ui(active=True)

    def _close_repl_panel(self) -> None:
        """Fully close code panel mode: restore viewport, indicator, and all room state."""
        self._stop_code_execution()
        self._code_panel_active = False
        self._apply_code_panel_ui(active=False)
        self._restore_room_code_state()
        # Close any open panel
        try:
            for panel in self.query(ReplPanel):
                if panel.is_open:
                    panel.close()
        except Exception:
            pass

    def _apply_code_panel_ui(self, active: bool, kind: str = 'code') -> None:
        """Toggle viewport size and indicator between expanded-panel and normal.

        kind: 'code' (REPL) or 'loop' (LoopPanel) — controls only the bottom
        border subtitle. Resize/indicator behavior is identical for both so
        the LoopPanel reuses this exact path.
        """
        try:
            viewport = self.query_one("#viewport")
            indicator = self.query_one("#room-indicator", RoomIndicator)
            compact = self.query_one("#compact-room-indicator", CompactRoomIndicator)
            with self.batch_update():
                if active:
                    indicator.display = False
                    compact.update_room(self.active_room)
                    compact.display = True
                    # Full indicator(4) → compact(1) frees 3 rows; the 4th
                    # row comes from VIEWPORT_HEIGHT being 1 below terminal
                    # budget. Panel(5) fits with pinned grid after hint
                    # bar(1) hidden.
                    viewport.styles.height = VIEWPORT_HEIGHT + 4
                    if kind == 'loop':
                        _set_viewport_hints(viewport, left=f"{ICON_MUSIC} Hold Enter: close looping {ICON_MUSIC}", right=None, active_theme=self.active_theme)
                    else:
                        _set_viewport_hints(viewport, left=None, right=f"{ICON_ROBOT} Hold Space: close code {ICON_ROBOT}", active_theme=self.active_theme)
                else:
                    viewport.styles.height = VIEWPORT_HEIGHT
                    compact.display = False
                    indicator.display = True
                    _apply_room_subtitle(viewport, self.active_room, self._code_panel_enabled, self.active_theme, self._music_looping_enabled)
        except NoMatches:
            pass

    def _restore_room_code_state(self) -> None:
        """Reset art canvas and music grid from code mode."""
        try:
            from .rooms.art_room import ArtCanvas, CanvasHeader
            content_area = self.query_one("#content-area")
            art = content_area.query_one("#room-art")
            canvas = art.query_one("#art-canvas", ArtCanvas)
            canvas.set_code_mode(False)
            canvas.styles.height = "1fr"
            header = art.query_one("#canvas-header", CanvasHeader)
            header.set_code_mode(False)
            from .rooms.art_room import ArtHintBar
            art.query_one("#art-hint-bar", ArtHintBar).display = True
        except Exception:
            pass
        try:
            from .rooms.music_room import MusicGrid, MusicRoomHeader
            from .music_constants import INSTRUMENTS
            content_area = self.query_one("#content-area")
            music = content_area.query_one("#room-music")
            grid = music.query_one(MusicGrid)
            # Sync instrument: code may have changed it via "choose"
            music._instrument_index = grid._instrument_index
            header = music.query_one(MusicRoomHeader)
            header.update_instrument(INSTRUMENTS[grid._instrument_index][1])
            grid._layout_ready = False
            grid.styles.height = "1fr"
            from .rooms.music_room import MusicExampleHint
            music.query_one("#example-hint", MusicExampleHint).display = True
        except Exception:
            pass

    def _close_repl_panels_only(self) -> None:
        """Close REPL panels and restore room widget state without changing UI chrome."""
        self._stop_code_execution()
        self._restore_room_code_state()
        try:
            for panel in self.query(ReplPanel):
                if panel.is_open:
                    panel.close()
        except Exception:
            pass

    def _open_code_panel_in_room(self, room: Room) -> None:
        """Open the REPL panel in the specified room and apply code panel UI.

        Pins canvas/grid height if the widget is already laid out (size > 0).
        If not laid out yet (room switch), height stays at 1fr and the
        viewport growth compensates for the REPL panel.
        """
        self._apply_code_panel_ui(active=True)
        room_id = f"room-{room.name.lower()}"
        try:
            content_area = self.query_one("#content-area")
            room_widget = content_area.query_one(f"#{room_id}")
            panel = room_widget.query_one(ReplPanel)
            if not panel.is_open:
                if room == Room.ART:
                    from .rooms.art_room import ArtCanvas, CanvasHeader, ArtHintBar
                    canvas = room_widget.query_one("#art-canvas", ArtCanvas)
                    canvas.set_code_mode(True)
                    if canvas.size.height > 0:
                        canvas.styles.height = canvas.size.height
                    header = room_widget.query_one("#canvas-header", CanvasHeader)
                    header.set_code_mode(True)
                    room_widget.query_one("#art-hint-bar", ArtHintBar).display = False
                elif room == Room.MUSIC:
                    from .rooms.music_room import MusicGrid, MusicExampleHint
                    room_widget.query_one("#example-hint", MusicExampleHint).display = False
                    grid = room_widget.query_one(MusicGrid)
                    if grid.size.height > 0:
                        grid.styles.height = grid.size.height
                        grid.set_instrument(room_widget._instrument_index)
                panel.open()
        except Exception:
            pass

    def _reset_viewport_border(self) -> None:
        """Reset viewport outline to default purple."""
        try:
            from textual.color import Color
            viewport = self.query_one("#viewport")
            primary_color = "#9b7bc4" if self.active_theme == "purple-dark" else "#7a4ca0"
            viewport.styles.border = ("heavy", Color.parse(primary_color))
        except Exception:
            pass

    def _apply_theme(self) -> None:
        """Apply the current color theme"""
        self.theme = self.active_theme
        # Update mode indicator to show current theme
        try:
            indicator = self.query_one("#room-indicator", RoomIndicator)
            indicator.refresh()
        except NoMatches:
            pass

    def _is_sleep_or_bye_active(self) -> bool:
        """Check if a sleep, shutdown confirm, or bye screen is currently showing."""
        from .rooms.sleep_screen import SleepScreen, ShutdownConfirmScreen, ByeScreen
        return any(
            isinstance(s, (SleepScreen, ShutdownConfirmScreen, ByeScreen))
            for s in self.screen_stack
        )

    def _debug_exit_on_no_input(self) -> None:
        """Exit to debug shell if no evdev input was received within 60 seconds.

        Only active on debug ISO. Lets developers diagnose keyboard issues
        when the app can't receive input.
        """
        if not self._debug_no_input_received:
            self.exit(return_code=0)

    def _reap_stale_toasts(self) -> None:
        """Wall-clock watchdog: kill any Toast that's been on screen longer
        than its own timeout, regardless of Textual's notification state.

        Stamps each Toast on first sight and removes it once age exceeds
        timeout + grace. We don't trust notification.has_expired — if that
        flag ever fails to flip (re-stamped raised_at, missed refresh, etc.)
        the toast would hang forever. Walks every screen in the stack so
        toasts under a pushed modal still get reaped.
        """
        from textual.widgets._toast import Toast, ToastHolder
        now = time.monotonic()
        for screen in self.screen_stack:
            for toast in screen.query(Toast):
                first_seen = getattr(toast, "_purple_first_seen", None)
                if first_seen is None:
                    toast._purple_first_seen = now
                    continue
                timeout = getattr(toast._notification, "timeout", 3.0) or 3.0
                if now - first_seen < timeout + 0.5:
                    continue
                holder = toast.parent if isinstance(toast.parent, ToastHolder) else toast
                try:
                    holder.remove()
                except Exception:
                    pass
                try:
                    self._unnotify(toast._notification, refresh=False)
                except Exception:
                    pass

    def inhibit_idle(self, reason: str) -> None:
        """Suppress idle sleep/shutdown while a long-running operation is active.

        Reason-based so multiple inhibitors compose without stomping on each other.
        Callers MUST pair every inhibit_idle() with an uninhibit_idle() with the
        same reason (typically in on_mount/on_unmount).
        """
        self._idle_inhibitors.add(reason)

    def uninhibit_idle(self, reason: str) -> None:
        """Release an idle inhibitor previously added by inhibit_idle()."""
        self._idle_inhibitors.discard(reason)

    def _check_idle_state(self) -> None:
        """Check if we should enter sleep mode due to inactivity.

        Lid detection is primarily handled by LidSwitchReader (evdev, instant).
        Falls back to polling /proc/acpi if evdev lid detection is unavailable.
        This timer also handles the lid-close shutdown countdown and idle timeouts.
        """
        try:
            from .power_manager import _power_log
            pm = get_power_manager()

            # Refresh charger state each tick (for smoothing)
            charger = pm.is_on_charger()

            # Fallback lid detection: if LidSwitchReader isn't available,
            # poll /proc/acpi (up to 5s latency, but works everywhere)
            if self._lid_switch_reader is None:
                lid_open = pm.get_lid_state()
                if lid_open is False and self._lid_close_time is None:
                    _power_log("LID CLOSED (polled /proc/acpi fallback)")
                    self._lid_close_time = time.time()
                    if not self._is_sleep_or_bye_active():
                        self._show_sleep_screen()
                elif lid_open is not False and self._lid_close_time is not None:
                    # Lid opened: reset shutdown countdown, record activity.
                    # Sleep screen stays visible (same as evdev path).
                    self._lid_was_closed_for = time.time() - self._lid_close_time
                    _power_log(f"LID OPENED (polled /proc/acpi fallback), was closed for {self._lid_was_closed_for:.1f}s")
                    self._lid_close_time = None
                    self._record_user_activity()

            # Lid-close shutdown countdown (lid events come from LidSwitchReader
            # or fallback polling above)
            if self._lid_close_time is not None:
                from .power_manager import LID_SHUTDOWN_DELAY
                elapsed = time.time() - self._lid_close_time
                if elapsed >= LID_SHUTDOWN_DELAY:
                    _power_log(f"LID SHUTDOWN: lid closed for {elapsed:.0f}s >= {LID_SHUTDOWN_DELAY}s, shutting down")
                    self._show_bye_screen()
                elif int(elapsed) % 30 == 0:
                    _power_log(f"TICK: lid closed {elapsed:.0f}s/{LID_SHUTDOWN_DELAY}s, charger={charger}")
                return  # Don't also check idle while lid is closed

            if self._is_sleep_or_bye_active():
                return

            # Idle sleep/shutdown can be suppressed while long-running modal
            # operations are in progress (e.g. install). Lid handling above
            # still runs so closing the lid still shuts down.
            if self._idle_inhibitors:
                return

            idle = pm.get_idle_seconds()
            # Idle threshold adapts to charger state
            sleep_threshold = pm.get_idle_sleep_threshold()
            if idle >= sleep_threshold:
                _power_log(f"IDLE SLEEP: idle {idle:.0f}s >= {sleep_threshold}s, charger={charger}")
                self._show_sleep_screen()
                return

            # Idle shutdown (10 min battery, 60 min charger)
            shutdown_threshold = pm.get_idle_shutdown_threshold()
            if idle >= shutdown_threshold:
                _power_log(f"IDLE SHUTDOWN: idle {idle:.0f}s >= {shutdown_threshold}s, charger={charger}")
                self._show_bye_screen()
        except Exception:
            pass

    def _show_sleep_screen(self) -> None:
        """Show the sleep screen overlay."""
        if self._is_sleep_or_bye_active():
            return

        try:
            from .rooms.sleep_screen import SleepScreen
            self.push_screen(SleepScreen())
        except Exception:
            pass

    def _show_shutdown_confirm(self) -> None:
        """Show the shutdown confirmation screen (power button tap)."""
        if self._is_sleep_or_bye_active():
            return

        try:
            from .rooms.sleep_screen import ShutdownConfirmScreen
            self.push_screen(ShutdownConfirmScreen())
        except Exception:
            pass

    def _record_user_activity(self) -> None:
        """Record that user is active. Resets idle timer."""
        try:
            pm = get_power_manager()
            pm.record_activity()
        except Exception:
            pass

    # ── Lid Switch ────────────────────────────────────────────────────

    async def _handle_lid_switch_event(self, event: LidSwitchEvent) -> None:
        """Handle lid open/close from LidSwitchReader (evdev, instant).

        Lid close: show sleep screen immediately, start shutdown countdown.
        Lid open: wake up, reset everything.
        """
        from .power_manager import _power_log

        if self._bye_screen_active:
            _power_log(f"LID EVENT ignored: bye screen active, is_open={event.is_open}")
            return

        if not event.is_open:
            # Lid closed: start shutdown countdown and show sleep screen
            _power_log("LID CLOSED (evdev)")
            self._lid_close_time = time.time()
            if not self._is_sleep_or_bye_active():
                self._show_sleep_screen()
        else:
            # Lid opened: reset shutdown countdown, record activity.
            # Sleep screen stays visible so parents can see power status.
            # Kid presses any key to wake (same as idle sleep).
            self._lid_was_closed_for = time.time() - self._lid_close_time if self._lid_close_time else 0
            _power_log(f"LID OPENED (evdev), was closed for {self._lid_was_closed_for:.1f}s")
            self._lid_close_time = None
            self._record_user_activity()

    # ── Power Button ──────────────────────────────────────────────────

    async def _handle_power_button_event(self, event: PowerButtonEvent) -> None:
        """Handle power button tap/hold from PowerButtonReader.

        Tap: show sleep screen (cute, not scary)
        Hold (3s): show bye screen and shut down
        """
        from .power_manager import _power_log
        _power_log(f"POWER BUTTON: action={event.action}, suspended={self._app_suspended}, "
                    f"bye_active={self._bye_screen_active}")

        if self._app_suspended or self._bye_screen_active:
            return

        if event.action == "tap":
            from .rooms.sleep_screen import ShutdownConfirmScreen
            confirm_showing = any(
                isinstance(s, ShutdownConfirmScreen) for s in self.screen_stack
            )
            if confirm_showing:
                # Second tap on confirm screen: shut down.
                # (Many laptops send tap-only for power, hold never fires.)
                self._show_bye_screen()
            else:
                self._show_shutdown_confirm()
        elif event.action == "hold":
            self._show_bye_screen()

    def _show_bye_screen(self) -> None:
        """Show the goodbye screen and shut down."""
        if self._bye_screen_active:
            return

        from .rooms.sleep_screen import ByeScreen, SleepScreen, ShutdownConfirmScreen

        # Dismiss sleep/confirm screen first if showing (avoid stacking)
        for screen in list(self.screen_stack):
            if isinstance(screen, (SleepScreen, ShutdownConfirmScreen)):
                screen.dismiss()
                break

        # Release evdev grabs before shutdown so they don't block
        # systemd's service stop sequence
        if self._evdev_reader:
            self._evdev_reader.release_grab()

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
        return None

    def _load_room_content(self) -> None:
        """Load the content widget for the current mode."""
        content_area = self.query_one("#content-area")
        room_id = f"room-{self.active_room.name.lower()}"

        # Show new room first, then hide others (avoids blank frame flicker)
        try:
            existing = content_area.query_one(f"#{room_id}")
            existing.display = True
            for child in content_area.children:
                if child is not existing:
                    child.display = False
            self._focus_room(existing)
            return
        except NoMatches:
            pass

        # Create and mount new widget (hides others after mount)
        widget = self._create_room_widget(self.active_room)
        if widget:
            widget.id = room_id
            # Hide others before mounting so the new widget appears immediately
            for child in content_area.children:
                child.display = False
            content_area.mount(widget)
            # Focus will happen in on_mount of the widget

    def _focus_room(self, widget) -> None:
        """Focus the appropriate element in a mode widget."""
        # If code panel is open, focus the REPL input
        if self._code_panel_active and self.active_room in (Room.MUSIC, Room.ART):
            try:
                panel = widget.query_one(ReplPanel)
                if panel.is_open:
                    panel.query_one("#repl-input").focus()
                    return
            except Exception:
                pass
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

            self._complete_room_switch(new_room)

    def _complete_room_switch(self, new_room: Room) -> None:
        """Complete the mode switch (updates UI, loads content)."""
        self.clear_notifications()
        self.active_room = new_room
        self._load_room_content()

        # Update title
        room_names = {Room.PLAY: ROOM_PLAY[0], Room.MUSIC: ROOM_MUSIC[0], Room.ART: ROOM_ART[0]}
        try:
            title = self.query_one("#title-bar", TitleBar)
            title.set_mode(room_names.get(new_room, ROOM_PLAY[0]))
        except NoMatches:
            pass

        # Update mode indicator
        try:
            indicator = self.query_one("#room-indicator", RoomIndicator)
            indicator.update_room(new_room)
            compact = self.query_one("#compact-room-indicator", CompactRoomIndicator)
            compact.update_room(new_room)
        except NoMatches:
            pass

        # Handle code panel state across room switches
        if self._code_panel_active:
            # Close old room's panel and widget state
            self._close_repl_panels_only()
            if new_room in (Room.MUSIC, Room.ART):
                # Open code panel in the new room
                self._open_code_panel_in_room(new_room)
            else:
                # Play room: no code panel, show normal indicator
                try:
                    viewport = self.query_one("#viewport")
                    indicator = self.query_one("#room-indicator", RoomIndicator)
                    compact = self.query_one("#compact-room-indicator", CompactRoomIndicator)
                    with self.batch_update():
                        compact.display = False
                        indicator.display = True
                        viewport.styles.height = VIEWPORT_HEIGHT
                        viewport.border_subtitle = ""
                except NoMatches:
                    pass
        else:
            # Not in code panel mode: clean close
            self._close_repl_panel()
            try:
                viewport = self.query_one("#viewport")
                _apply_room_subtitle(viewport, new_room, self._code_panel_enabled, self.active_theme, self._music_looping_enabled)
            except NoMatches:
                pass

        # Cycle play mode "Try" hint on room switch
        if new_room == Room.PLAY:
            try:
                from .rooms.play_room import ExampleHint
                self.query_one("#play-example-hint", ExampleHint).advance()
            except (NoMatches, Exception):
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

        # Refresh shift banner hint (different rooms show different hints)
        self._update_shift_indicator()

    def _start_fresh(self) -> None:
        """Clear all rooms: art canvas, music colors, play history, code buffers."""
        from .rooms.art_room import ArtMode
        from .rooms.music_room import MusicMode

        # Clear art canvas
        try:
            art = self.query_one(ArtMode)
            art.clear_canvas()
        except Exception:
            pass

        # Reset music colors and loop
        try:
            music = self.query_one(MusicMode)
            music.reset_state()
        except Exception:
            pass

        # Clear play history
        try:
            content_area = self.query_one("#content-area")
            play = content_area.query_one("#room-play")
            if hasattr(play, 'clear_history'):
                play.clear_history()
        except Exception:
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
        if self._silent_mode:
            return
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
        if self._silent_mode:
            return
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
        if self._silent_mode:
            return
        # Find current position in VOLUME_LEVELS and go up
        current_idx = len(VOLUME_LEVELS) - 1
        for i, level in enumerate(VOLUME_LEVELS):
            if self.volume_level <= level:
                current_idx = i
                break
        if current_idx < len(VOLUME_LEVELS) - 1:
            self.volume_level = VOLUME_LEVELS[current_idx + 1]
        self._apply_volume()  # Always show feedback, even at max

    def _show_brightness_hint(self) -> None:
        """Show a one-time hint about brightness being in the Parent Menu."""
        if self._brightness_hint_showing:
            return
        self._brightness_hint_showing = True
        self.notify("Go to the Parent Menu to change brightness", timeout=3)
        self.set_timer(3, lambda: setattr(self, '_brightness_hint_showing', False))

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

    def _effective_volume(self) -> int:
        """Volume actually applied to playback: 0 while the parent silence lock is on."""
        return 0 if self._silent_mode else self.volume_level

    def _apply_volume_system(self) -> None:
        """Set system volume via ALSA to match the effective volume (non-blocking).

        Maps app volume (0-100) onto 0-SYSTEM_VOLUME_MAX to avoid pushing
        the analog amplifier into its noisy range on real hardware.
        """
        try:
            import subprocess
            from .constants import SYSTEM_VOLUME_MAX
            system_vol = round(self._effective_volume() * SYSTEM_VOLUME_MAX / 100)
            subprocess.Popen(
                ["amixer", "sset", "Master", f"{system_vol}%"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _invalidate_sound_caches(self) -> None:
        """Clear cached Sound objects after a mixer reinit (they become invalid)."""
        try:
            from .rooms.music_room import MusicGrid
            for grid in self.query(MusicGrid):
                grid.cleanup_sounds()
        except Exception:
            pass

    def _apply_volume(self) -> None:
        """Apply volume level to TTS, system mixer, and update UI."""
        from . import tts
        if not self._silent_mode:
            from .settings import set_volume_level
            set_volume_level(self.volume_level)
        vol = self._effective_volume()
        tts.set_muted(vol == 0)
        self._apply_volume_system()

        # Update volume indicator badge
        try:
            indicator = self.query_one("#room-indicator", RoomIndicator)
            indicator.update_volume_indicator(vol)
        except NoMatches:
            pass

        # Build volume feedback message (6 levels: 0, 15, 35, 60, 85, 100)
        if vol == 0:
            icon = ICON_VOLUME_OFF
            label = "Sound Off"
            bars = "░░░░░░░░░░"
        elif vol <= 15:
            icon = ICON_VOLUME_LOW
            label = "Whisper"
            bars = "██░░░░░░░░"
        elif vol <= 35:
            icon = ICON_VOLUME_LOW
            label = "Quiet"
            bars = "████░░░░░░"
        elif vol <= 60:
            icon = ICON_VOLUME_MED
            label = "Medium"
            bars = "██████░░░░"
        elif vol <= 85:
            icon = ICON_VOLUME_HIGH
            label = "Loud"
            bars = "████████░░"
        else:
            icon = ICON_VOLUME_HIGH
            label = "Full"
            bars = "██████████"

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

    def _update_shift_indicator(self) -> None:
        """Update the shift icon in the title bar based on sticky shift state."""
        sm = self._keyboard_state_machine
        try:
            title_bar = self.query_one("#title-bar", TitleBar)
            if sm._sticky_shift_active:
                title_bar.set_shift(ICON_SHIFT, True)
            else:
                title_bar.set_shift("", False)
        except NoMatches:
            pass

    def _on_sticky_shift_change(self, active: bool) -> None:
        """Called when sticky shift state changes."""
        if self._sticky_shift_timer:
            self._sticky_shift_timer.stop()
            self._sticky_shift_timer = None

        self._update_shift_indicator()

        if active:
            self._sticky_shift_timer = self.set_timer(
                STICKY_SHIFT_GRACE, self._expire_sticky_shift_indicator
            )

    def _expire_sticky_shift_indicator(self) -> None:
        """Hide shift indicator after grace period."""
        self._sticky_shift_timer = None
        self._update_shift_indicator()

    def action_parent_menu(self) -> None:
        """Enter parent mode. Shows admin menu for parents."""
        # Cancel escape hold timer and reset state
        self._cancel_escape_hold_timer()
        self.keyboard.escape_hold.reset()
        self._keyboard_state_machine.reset()  # Clear all pressed keys state
        self.clear_notifications()
        # In littles mode, show the exit screen instead of the parent menu
        if self._littles_mode:
            from .rooms.parent_menu import LittlesExitScreen
            self.push_screen(LittlesExitScreen(), callback=self._on_littles_exit_dismissed)
            return
        from .rooms.parent_menu import ParentMenu
        self.push_screen(ParentMenu(), callback=self._on_parent_menu_dismissed)

    def _on_littles_exit_dismissed(self, result) -> None:
        """Handle littles exit screen dismiss."""
        from .rooms.parent_menu import (
            _LITTLES_EXIT, _LITTLES_PARENT, ParentMenu,
        )
        if result == _LITTLES_EXIT:
            from .settings import set_littles_mode
            set_littles_mode(None)
            self._apply_littles_mode(None)
        elif result == _LITTLES_PARENT:
            self.push_screen(ParentMenu(), callback=self._on_parent_menu_dismissed)

    def _on_parent_menu_dismissed(self, result) -> None:
        """Handle parent menu dismiss, applying any setting changes."""
        self.clear_notifications()

        if not result or not isinstance(result, dict):
            return

        # Littles Mode changed
        if "littles_mode" in result:
            self._apply_littles_mode(result["littles_mode"])

    def _apply_littles_mode(self, mode: str | None) -> None:
        """Apply a Littles Mode change. Switches room, hides/shows UI."""
        self._littles_mode = mode

        if mode:
            self._code_panel_enabled = False
            self._code_panel_active = False
            self._music_looping_enabled = False
            self._music_key_switching_enabled = False
        else:
            from .settings import get_code_panel, get_music_looping, get_music_key_switching
            self._code_panel_enabled = get_code_panel()
            self._music_looping_enabled = get_music_looping()
            self._music_key_switching_enabled = get_music_key_switching()

        if mode:
            # Switch to the locked room
            room_map = {"music": ROOM_MUSIC[0], "music_noscreen": ROOM_MUSIC[0], "art": ROOM_ART[0]}
            room_name = room_map.get(mode, ROOM_MUSIC[0])
            self.action_switch_room(room_name)

            # Close any open REPL panels
            from .repl_panel import ReplPanel
            for panel in self.query(ReplPanel):
                if panel.is_open:
                    panel.close()

            # Hide room indicators, clear subtitle, show littles hint
            try:
                self.query_one("#room-indicator", RoomIndicator).display = False
                self.query_one("#compact-room-indicator", CompactRoomIndicator).display = False
                self.query_one("#littles-hint", Static).display = True
                self.query_one("#viewport").border_subtitle = ""
            except NoMatches:
                pass
        else:
            # Show room indicator, hide littles hint
            try:
                self.query_one("#room-indicator", RoomIndicator).display = True
                self.query_one("#littles-hint", Static).display = False
            except NoMatches:
                pass

        # Apply no-screen music mode or restore normal music UI
        try:
            from .rooms.music_room import MusicMode
            for m in self.query(MusicMode):
                if mode == 'music_noscreen':
                    m._apply_noscreen()
                else:
                    m._restore_screen()
        except (NoMatches, Exception):
            pass

        # Refresh headers/hints so they pick up the new littles state
        try:
            from .rooms.music_room import MusicRoomHeader
            for h in self.query(MusicRoomHeader):
                h.refresh()
        except (NoMatches, Exception):
            pass
        try:
            from .rooms.art_room import CanvasHeader, ArtHintBar
            for h in self.query(CanvasHeader):
                h.refresh()
            for h in self.query(ArtHintBar):
                h.refresh()
        except (NoMatches, Exception):
            pass

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

    def _handle_exception(self, error: Exception) -> None:
        _write_crash(f"textual {type(error).__name__}", type(error), error, error.__traceback__)
        super()._handle_exception(error)

_CRASH_LOG_PATHS = ("/var/log/purple/crash.log", "/tmp/purple-crash.log")


def _write_crash(header: str, exc_type, exc_value, exc_tb):
    import traceback
    from datetime import datetime
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    stamp = datetime.now().isoformat(timespec="seconds")
    body = f"\n===== {stamp} {header} =====\n{text}"
    for path in _CRASH_LOG_PATHS:
        try:
            with open(path, "a") as f:
                f.write(body)
            return
        except OSError:
            continue


def _install_crash_logger():
    """Persist uncaught exceptions to disk.

    Textual renders to stderr, so an unhandled exception flashes for a frame
    before xinitrc re-execs the launcher and the traceback is gone. Append
    it to a file so we can read it after the fact.
    """
    import sys
    import threading

    prev_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        _write_crash("uncaught exception", exc_type, exc_value, exc_tb)
        prev_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    prev_thread_hook = threading.excepthook

    def _thread_excepthook(args):
        _write_crash(f"thread {args.thread.name if args.thread else '?'}", args.exc_type, args.exc_value, args.exc_traceback)
        prev_thread_hook(args)

    threading.excepthook = _thread_excepthook


def main():
    """Entry point for Purple Computer"""
    import sys
    import os
    import signal
    import atexit

    _install_crash_logger()

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

    # Show loading message that persists until Textual clears the screen on start
    print("\033[2J\033[H", end="")  # Clear screen, cursor to top-left
    print("\n\n    Loading...", end="", flush=True)

    try:
        app = PurpleApp()
    except RuntimeError as e:
        # Friendly error for configuration issues
        print(f"\n  Purple Computer cannot start:\n  {e}\n", file=sys.stderr)
        sys.exit(1)

    app.run(mouse=False)  # Purple Computer is keyboard-only


if __name__ == "__main__":
    main()
