"""
Purple Computer - Shared Constants

Central location for constants used across the app.
"""
import os

# =============================================================================
# SUPPORT
# =============================================================================

SUPPORT_EMAIL = "support@purplecomputer.org"

# Debug mode: touch /opt/purple/debug to enable debug features on any install.
# Controls: "Exit to System" in parent menu, debug shell on exit, extra diagnostics.
DEBUG_FLAG_PATH = "/opt/purple/debug"

def is_debug() -> bool:
    """Check if this install has debug mode enabled."""
    from pathlib import Path
    return Path(DEBUG_FLAG_PATH).exists()

# =============================================================================
# ROOM NAMES
# =============================================================================
# Central location for room names to keep them DRY across the codebase.
# Format: (id, label) where id is lowercase for internal use, label is display text.

ROOM_PLAY = ("play", "Play")           # Math and emoji REPL
ROOM_MUSIC = ("music", "Music")        # Music and art grid
ROOM_ART = ("art", "Art")              # Drawing canvas
ROOM_CODE = ("code", "Code")           # Legacy (kept for compatibility, not a switchable room)

# =============================================================================
# TERMINAL LAYOUT CONSTANTS
# =============================================================================
# These define the terminal grid required for the full UI.
# Font size is calculated to fill the screen (see scripts/calc_font_size.py).
#
# Normal mode layout (from purple_tui.py CSS):
#   - Title row: 1h + margin-bottom 1h = 2 rows
#   - Viewport: VIEWPORT_HEIGHT + border(2) rows
#   - Room indicator: margin-top 1h + height 3h = 4 rows
#
# Code space layout (font shrinks so more rows fit):
#   - Title row: hidden (display: none)
#   - Viewport: VIEWPORT_HEIGHT + border-top(1) rows (no bottom border)
#   - Code panel: CODE_PANEL_MIN_HEIGHT rows (flexible via 1fr, no top border)
#   - Compact indicator: 1 row (no margin)

VIEWPORT_WIDTH = 134          # Viewport widget width (CSS)
VIEWPORT_HEIGHT = 29          # Viewport widget height (CSS)
REQUIRED_TERMINAL_COLS = VIEWPORT_WIDTH + 2 + 5 + 5  # Full UI width (+ border + spacer + legend)

# Normal mode: title(2) + viewport+border(32) + indicator margin(1) + indicator(3)
_TITLE_ROWS = 2               # Title row + margin-bottom
_VIEWPORT_ROWS = VIEWPORT_HEIGHT + 2  # Content + heavy border
_INDICATOR_ROWS = 4            # margin-top(1) + height(3)
REQUIRED_TERMINAL_ROWS = _TITLE_ROWS + _VIEWPORT_ROWS + _INDICATOR_ROWS
# Centering reference for #viewport-wrapper: rows below the title bar in normal mode.
WRAPPER_REFERENCE_ROWS = _VIEWPORT_ROWS + _INDICATOR_ROWS

# =============================================================================
# TIMING
# =============================================================================

# Timing
TOGGLE_DEBOUNCE = 0.3        # Delay before speaking toggle state (debounce rapid toggles)
STICKY_SHIFT_GRACE = 8.0     # How long sticky shift stays active (seconds)
ESCAPE_HOLD_THRESHOLD = 1.0  # How long to hold Escape for parent mode (seconds)
HOLD_OR_TAP_THRESHOLD = 0.8  # Space/Enter hold threshold for code panel / loop mode (seconds)

# Volume levels (0-100, perceptually spaced: more steps at low end)
VOLUME_LEVELS = [0, 15, 35, 60, 85, 100]
VOLUME_DEFAULT = 60
SYSTEM_VOLUME_MAX = 85  # Cap system mixer to avoid analog amp hiss on real hardware

# Nerd Font icons (https://www.nerdfonts.com/cheat-sheet)
# These require JetBrainsMono Nerd Font. Unicode emoji (🐱 🎉) use Noto Color Emoji.
# Volume icons (nf-md-volume variants)
ICON_VOLUME_OFF = "󰖁"       # nf-md-volume_off (muted)
ICON_VOLUME_LOW = "󰕿"       # nf-md-volume_low (15-35%)
ICON_VOLUME_MED = "󰖀"       # nf-md-volume_medium (60%)
ICON_VOLUME_HIGH = "󰕾"      # nf-md-volume_high (85-100%)
ICON_VOLUME_DOWN = "󰝞"      # nf-md-volume_minus
ICON_VOLUME_UP = "󰝝"        # nf-md-volume_plus
ICON_ERASER = "󰇾"           # nf-md-eraser
ICON_SAVE = "󰆓"             # nf-md-content_save
ICON_LOAD = "󰈔"             # nf-md-file_import
ICON_PALETTE = "󰏘"          # nf-md-palette
ICON_MUSIC = "\uf001"       # nf-fa-music
ICON_MUSIC_NOTE = "\U000f0387"  # nf-md-music_note_outline (single note for flash)
ICON_LOOP = ""        # nf-fa-repeat (looping indicator)
ICON_CHAT = "󰭹"             # nf-md-chat_question
ICON_DOCUMENT = "󰏫"         # nf-md-file_document
ICON_MOON = "󰖙"             # nf-md-weather_night
ICON_SUN = "󰖨"              # nf-md-weather_sunny
ICON_MENU = "󰀻"             # nf-md-apps (grid icon for room picker)
ICON_PENCIL = "󰏪"           # nf-md-pencil (write mode)
ICON_BRUSH = "󰏘"            # nf-md-brush (paint mode - same as palette)
ICON_SHIFT = "⇧"             # Unicode upward arrow (shift indicator)
ICON_SHIFT_ACTIVE = "⬆"       # Unicode upward arrow (shift active, filled)
ICON_CODE = "󰚩"               # nf-md-robot (code room)
ICON_KEYBOARD = "󰌌"          # nf-md-keyboard (key capture indicator)
ICON_TAB = "󰌒"                # nf-md-keyboard_tab
ICON_BROOM = "󰃢"              # nf-md-broom (start fresh / clear)
ICON_ROBOT = "󰚩"              # nf-md-robot (same as ICON_CODE, for code space toggle)

# Battery icons (nf-md-battery variants)
ICON_BATTERY_FULL = "󰁹"     # nf-md-battery (100%)
ICON_BATTERY_HIGH = "󰂀"     # nf-md-battery_70 (70-99%)
ICON_BATTERY_MED = "󰁾"      # nf-md-battery_50 (30-69%)
ICON_BATTERY_LOW = "󰁻"      # nf-md-battery_20 (10-29%)
ICON_BATTERY_EMPTY = "󰂃"    # nf-md-battery_alert (<10%)
ICON_BATTERY_CHARGING = "󰂄" # nf-md-battery_charging

APP_BACKGROUND = "#1e1033"

# USB / installed indicator
ICON_USB = "\uf287"           # nf-fa-usb
ICON_SIGN_OUT = "\uf08b"     # nf-fa-sign_out
ICON_HARDDISK = "󰋊"         # nf-md-harddisk (installed)


def display_len(text: str) -> int:
    """String length adjusted for double-wide Nerd Font icons in JetBrainsMono.

    Nerd Font glyphs in the Private Use Area render as 2 cells wide,
    but Python's len() counts them as 1. This adds 1 for each such character.
    """
    extra = 0
    for ch in text:
        cp = ord(ch)
        # Nerd Font PUA ranges: U+E000-U+F8FF (BMP PUA), U+F0000-U+FFFFF (Supp PUA-A)
        if 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFF:
            extra += 1
    return len(text) + extra


# Live boot squashfs caching
SQUASHFS_PATH = "/cdrom/casper/filesystem.squashfs"
USB_CACHE_MARKER = "/tmp/purple-usb-cached"

# Touched after the first frame paints. xinitrc waits for this before starting
# the compositor, so picom's GL init lands after the import/first-paint crunch
# instead of contending with it and slowing boot. See intel-display-tuning.md.
UI_READY_MARKER = "/tmp/purple-ui-ready"

# PURPLE_FAKE_USB env var simulates USB boot states for testing.
# Values: "caching" (USB blinking), "cached" (safe to remove), "removed" (USB pulled out)
_FAKE_USB = os.environ.get("PURPLE_FAKE_USB", "")


def is_live_boot() -> bool:
    """Check if running from a casper live boot (USB or otherwise).

    Reads /proc/cmdline once and caches the result (doesn't change at runtime).
    Set PURPLE_FAKE_USB=caching|cached|removed to simulate in dev/test.
    """
    if not hasattr(is_live_boot, "_cached"):
        if _FAKE_USB:
            is_live_boot._cached = True
        else:
            try:
                from pathlib import Path
                is_live_boot._cached = "boot=casper" in Path("/proc/cmdline").read_text()
            except Exception:
                is_live_boot._cached = False
    return is_live_boot._cached


def is_usb_cached() -> bool:
    """Check if the USB squashfs has been cached to RAM."""
    if _FAKE_USB:
        return _FAKE_USB in ("cached", "removed")
    return os.path.exists(USB_CACHE_MARKER)


def is_usb_present() -> bool:
    """Check if the USB drive is still physically connected."""
    if _FAKE_USB:
        return _FAKE_USB != "removed"
    return os.path.exists(SQUASHFS_PATH)

# Room titles with icons (uses room name constants)
ROOM_TITLES = {
    ROOM_PLAY[0]: (ICON_CHAT, ROOM_PLAY[1]),
    ROOM_MUSIC[0]: (ICON_MUSIC, ROOM_MUSIC[1]),
    ROOM_ART[0]: (ICON_PALETTE, ROOM_ART[1]),
}

# =============================================================================
# ZOOM REGIONS FOR DEMO RECORDING
# =============================================================================
# Named regions for dynamic zoom during demo videos.
# Coordinates are percentages of the viewport (0.0-1.0) for resolution independence.
# Format: (x_center, y_center, width_fraction, height_fraction)
# The post-processor calculates actual pixels based on recording resolution.
#
# Note: "input" focuses on the Play room input area (bottom portion of viewport).

# =============================================================================
# ZOOM REGIONS FOR DEMO RECORDING
# =============================================================================
ZOOM_REGIONS = {
    # Full viewport (no zoom, 100% of content visible)
    "viewport": (0.5, 0.5, 1.0, 1.0),

    # Play room input area (bottom 40% of viewport, horizontally centered)
    # Shows the input line and a few lines of results above it
    "input": (0.5, 0.75, 0.7, 0.4),

    # Play room results area (middle portion, for showing computation results)
    "results": (0.5, 0.5, 0.8, 0.5),

    # Ad: Play content is left-aligned ("Ask ->" starts at the far left), so
    # centered crops cut it off. These shift the center left (only x_center is
    # used by the crop math) so the left edge stays in frame.
    # "ad-input": tight on the input line for typing.
    # "ad-reveal": wider pull-back to show the stacked result.
    "ad-input": (0.18, 0.80, 0.4, 0.4),
    "ad-reveal": (0.33, 0.50, 0.75, 0.75),

    # Art room center (center of canvas for drawing demos)
    "art-center": (0.5, 0.5, 0.6, 0.6),

    # Music room keyboard area (lower portion where keys are displayed)
    "music-keys": (0.5, 0.7, 0.8, 0.5),

    # Play room welcome area (upper-left where text history appears)
    # With 3x zoom, center must be in range 0.17-0.83 to avoid clamping
    "play-welcome": (0.4, 0.28, 0.7, 0.5),

    # Art room lower-right (for "This is Art room" intro text)
    "art-text-right": (0.7, 0.7, 0.5, 0.4),

    # Art room lower-left (for "Now let's go to Music room" text)
    # Text is at very bottom-left, center at 0.83 vertical to show it
    "art-text-left": (0.25, 0.82, 0.4, 0.3),

    # Closing screen: "This is Purple Computer" centered text
    "closing-title": (0.5, 0.38, 0.6, 0.4),
}
