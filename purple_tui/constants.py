"""
Purple Computer - Shared Constants

Central location for constants used across the app.
"""

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
# MODE NAMES
# =============================================================================
# Central location for mode names to keep them DRY across the codebase.
# Format: (id, label) where id is lowercase for internal use, label is display text.

MODE_EXPLORE = ("explore", "Explore")  # F1: Math and emoji REPL
MODE_PLAY = ("play", "Play")           # F2: Music and art grid
MODE_DOODLE = ("doodle", "Doodle")     # F3: Simple drawing canvas

# =============================================================================
# TERMINAL LAYOUT CONSTANTS
# =============================================================================
# These define the terminal grid required for the full UI.
# Font size is calculated to fill 80% of screen (see scripts/calc_font_size.py).
#
# Layout (from purple_tui.py CSS):
#   - Title row: VIEWPORT_WIDTH × 2h (including margin)
#   - Viewport: VIEWPORT_WIDTH × VIEWPORT_HEIGHT + border(2) = +2 each dimension
#   - Footer: 3h
#
# Total: (VIEWPORT_WIDTH + 2) cols × (VIEWPORT_HEIGHT + 2 + 3) rows

VIEWPORT_WIDTH = 112          # Viewport widget width (CSS)
VIEWPORT_HEIGHT = 32          # Viewport widget height (CSS)
REQUIRED_TERMINAL_COLS = VIEWPORT_WIDTH + 2   # Full UI width (+ border)
REQUIRED_TERMINAL_ROWS = VIEWPORT_HEIGHT + 7  # Full UI height (+ border + title + footer)

# =============================================================================
# TIMING
# =============================================================================

# Timing
TOGGLE_DEBOUNCE = 0.3        # Delay before speaking toggle state (debounce rapid toggles)
STICKY_SHIFT_GRACE = 1.0     # How long sticky shift stays active (seconds)
ESCAPE_HOLD_THRESHOLD = 1.0  # How long to hold Escape for parent mode (seconds)

# Volume levels (0-100, step by 25)
VOLUME_LEVELS = [0, 25, 50, 75, 100]
VOLUME_DEFAULT = 100

# Nerd Font icons (https://www.nerdfonts.com/cheat-sheet)
# These require JetBrainsMono Nerd Font. Unicode emoji (🐱 🎉) use Noto Color Emoji.
# Volume icons (nf-md-volume variants)
ICON_VOLUME_OFF = "󰖁"       # nf-md-volume_off (muted)
ICON_VOLUME_LOW = "󰕿"       # nf-md-volume_low (25%)
ICON_VOLUME_MED = "󰖀"       # nf-md-volume_medium (50%)
ICON_VOLUME_HIGH = "󰕾"      # nf-md-volume_high (75-100%)
ICON_VOLUME_DOWN = "󰝞"      # nf-md-volume_minus
ICON_VOLUME_UP = "󰝝"        # nf-md-volume_plus
ICON_ERASER = "󰇾"           # nf-md-eraser
ICON_SAVE = "󰆓"             # nf-md-content_save
ICON_LOAD = "󰈔"             # nf-md-file_import
ICON_PALETTE = "󰏘"          # nf-md-palette
ICON_MUSIC = "\uf001"       # nf-fa-music
ICON_CHAT = "󰭹"             # nf-md-chat_question
ICON_DOCUMENT = "󰏫"         # nf-md-file_document
ICON_MOON = "󰖙"             # nf-md-weather_night
ICON_SUN = "󰖨"              # nf-md-weather_sunny
ICON_CAPS_LOCK = "󰬈"        # nf-md-caps_lock
ICON_MENU = "󰀻"             # nf-md-apps (grid icon for mode picker)
ICON_PENCIL = "󰏪"           # nf-md-pencil (write mode)
ICON_BRUSH = "󰏘"            # nf-md-brush (paint mode - same as palette)
ICON_SHIFT = "⇧"             # Unicode upward arrow (shift indicator)

# Battery icons (nf-md-battery variants)
ICON_BATTERY_FULL = "󰁹"     # nf-md-battery (100%)
ICON_BATTERY_HIGH = "󰂀"     # nf-md-battery_70 (70-99%)
ICON_BATTERY_MED = "󰁾"      # nf-md-battery_50 (30-69%)
ICON_BATTERY_LOW = "󰁻"      # nf-md-battery_20 (10-29%)
ICON_BATTERY_EMPTY = "󰂃"    # nf-md-battery_alert (<10%)
ICON_BATTERY_CHARGING = "󰂄" # nf-md-battery_charging

# Mode titles with icons (uses mode name constants)
MODE_TITLES = {
    MODE_EXPLORE[0]: (ICON_CHAT, MODE_EXPLORE[1]),
    MODE_PLAY[0]: (ICON_MUSIC, MODE_PLAY[1]),
    MODE_DOODLE[0]: (ICON_PALETTE, MODE_DOODLE[1]),
}

# =============================================================================
# ZOOM REGIONS FOR DEMO RECORDING
# =============================================================================
# Named regions for dynamic zoom during demo videos.
# Coordinates are percentages of the viewport (0.0-1.0) for resolution independence.
# Format: (x_center, y_center, width_fraction, height_fraction)
# The post-processor calculates actual pixels based on recording resolution.
#
# Note: "input" focuses on the Explore mode input area (bottom portion of viewport).

ZOOM_REGIONS = {
    # Full viewport (no zoom, 100% of content visible)
    "viewport": (0.5, 0.5, 1.0, 1.0),

    # Explore mode input area (bottom 40% of viewport, horizontally centered)
    # Shows the input line and a few lines of results above it
    "input": (0.5, 0.75, 0.7, 0.4),

    # Explore mode results area (middle portion, for showing computation results)
    "results": (0.5, 0.5, 0.8, 0.5),

    # Doodle mode center (center of canvas for drawing demos)
    "doodle-center": (0.5, 0.5, 0.6, 0.6),

    # Play mode keyboard area (lower portion where keys are displayed)
    "play-keys": (0.5, 0.7, 0.8, 0.5),

    # Explore mode welcome area (upper-left where text history appears)
    # With 3x zoom, center must be in range 0.17-0.83 to avoid clamping
    "explore-welcome": (0.4, 0.28, 0.7, 0.5),

    # Doodle mode lower-right (for "This is Doodle mode" intro text)
    "doodle-text-right": (0.7, 0.7, 0.5, 0.4),

    # Doodle mode lower-left (for "Now let's go to Play mode" text)
    # Text is at very bottom-left, center at 0.83 vertical to show it
    "doodle-text-left": (0.25, 0.82, 0.4, 0.3),

    # Closing screen: "This is Purple Computer" centered text
    "closing-title": (0.5, 0.38, 0.6, 0.4),
}
