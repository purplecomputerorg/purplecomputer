"""
Purple Computer - Shared Constants

Central location for constants used across the app.
"""

# =============================================================================
# TERMINAL LAYOUT CONSTANTS
# =============================================================================
# These define the minimum terminal grid required to display the full UI.
# Used by calc_font_size.py to calculate appropriate font size.
#
# Layout breakdown (from purple_tui.py CSS):
#   - Title row: width 100, height 1 + margin-bottom 1 = 2 rows
#   - Viewport: width 100 + border(2) + padding(2) = 104 cols
#               height 28 + border(2) + padding(2) = 32 rows
#   - Mode indicator: height 3 (docked bottom)
#
# Total: 104 cols × 37 rows

VIEWPORT_CONTENT_COLS = 100   # Inner content area width
VIEWPORT_CONTENT_ROWS = 28    # Inner content area height

# Full terminal requirements (content + borders + padding + chrome)
REQUIRED_TERMINAL_COLS = 104  # viewport width + border(2) + padding(2)
REQUIRED_TERMINAL_ROWS = 37   # title(2) + viewport(32) + footer(3)

# Target physical size for viewport (mm) - hint only, not enforced
TARGET_VIEWPORT_WIDTH_MM = 254   # 10 inches
TARGET_VIEWPORT_HEIGHT_MM = 152  # 6 inches

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
ICON_SKETCH = "󰏬"           # nf-md-pencil
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
    "sketch": (ICON_SKETCH, "Sketch"),
}
