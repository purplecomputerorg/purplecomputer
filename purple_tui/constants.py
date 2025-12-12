"""
Purple Computer - Shared Constants

Central location for constants used across the app.
"""

# Timing
TOGGLE_DEBOUNCE = 0.3        # Delay before speaking toggle state (debounce rapid toggles)
DOUBLE_TAP_TIME = 0.5        # Threshold for double-tap to get shifted characters
STICKY_SHIFT_GRACE = 1.0     # How long sticky shift stays active (seconds)
ESCAPE_HOLD_THRESHOLD = 1.0  # How long to hold Escape for parent mode (seconds)

# Nerd Font icons (https://www.nerdfonts.com/cheat-sheet)
ICON_VOLUME_ON = "󰕾"        # nf-md-volume_high
ICON_VOLUME_OFF = "󰖁"       # nf-md-volume_off
ICON_ERASER = "󰇾"           # nf-md-eraser
ICON_PALETTE = "󰏘"          # nf-md-palette
ICON_CHAT = "󰭹"             # nf-md-chat_question
ICON_HEADPHONES = "󰋋"       # nf-md-headphones
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
    "play": (ICON_PALETTE, "Play"),
    "listen": (ICON_HEADPHONES, "Listen"),
    "write": (ICON_DOCUMENT, "Write"),
}
