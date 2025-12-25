"""
Purple Computer - Shared Constants

Central location for constants used across the app.
"""

# =============================================================================
# TERMINAL LAYOUT CONSTANTS
# =============================================================================
# These define the terminal grid required for the full UI.
# Font size is calculated to fill 80% of screen (see scripts/calc_font_size.py).
#
# Layout (from purple_tui.py CSS):
#   - Title row: 100w × 2h (including margin)
#   - Viewport: 100w × 28h content + border(2) + padding(2) = 104w × 32h
#   - Footer: 3h
#
# Total: 104 cols × 37 rows

VIEWPORT_CONTENT_COLS = 100   # Inner content area width
VIEWPORT_CONTENT_ROWS = 28    # Inner content area height
REQUIRED_TERMINAL_COLS = 104  # Full UI width
REQUIRED_TERMINAL_ROWS = 37   # Full UI height

# =============================================================================
# TIMING
# =============================================================================

# Timing
TOGGLE_DEBOUNCE = 0.3        # Delay before speaking toggle state (debounce rapid toggles)
DOUBLE_TAP_TIME = 0.5        # Threshold for double-tap to get shifted characters
STICKY_SHIFT_GRACE = 1.0     # How long sticky shift stays active (seconds)
ESCAPE_HOLD_THRESHOLD = 1.0  # How long to hold Escape for parent mode (seconds)

# Nerd Font icons (https://www.nerdfonts.com/cheat-sheet)
ICON_VOLUME_ON = "󰕾"        # nf-md-volume_high
ICON_VOLUME_OFF = "󰖁"       # nf-md-volume_off
ICON_ERASER = "󰇾"           # nf-md-eraser
ICON_SAVE = "󰆓"             # nf-md-content_save
ICON_LOAD = "󰈔"             # nf-md-file_import
ICON_PALETTE = "󰏘"          # nf-md-palette
ICON_MUSIC = "\uf001"       # nf-fa-music
ICON_CHAT = "󰭹"             # nf-md-chat_question
ICON_DOCUMENT = "󰏫"         # nf-md-file_document
ICON_MOON = "󰖙"             # nf-md-weather_night
ICON_SUN = "󰖨"              # nf-md-weather_sunny

# Battery icons (nf-md-battery variants)
ICON_BATTERY_FULL = "󰁹"     # nf-md-battery (100%)
ICON_BATTERY_HIGH = "󰂀"     # nf-md-battery_70 (70-99%)
ICON_BATTERY_MED = "󰁾"      # nf-md-battery_50 (30-69%)
ICON_BATTERY_LOW = "󰁻"      # nf-md-battery_20 (10-29%)
ICON_BATTERY_EMPTY = "󰂃"    # nf-md-battery_alert (<10%)
ICON_BATTERY_CHARGING = "󰂄" # nf-md-battery_charging

# Mode titles with icons
MODE_TITLES = {
    "ask": (ICON_CHAT, "Ask"),
    "play": (ICON_MUSIC, "Play"),
    "write": (ICON_DOCUMENT, "Write"),
}
