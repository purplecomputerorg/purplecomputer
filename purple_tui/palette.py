"""Colors: the theme and the keyboard-row palette that matches the key stickers.

The number row is grayscale, the letter rows are red, yellow and blue families
graded light to dark left to right, exactly the colors printed on the stickers
in the box. Play, Music and Art all read from here.
"""

import colorsys

from .color_mixing import hex_to_rgb

NAMED_COLORS = {
    "red": "#d94a4a", "green": "#5cb85c", "blue": "#4a7fd9", "yellow": "#e8d24a",
    "white": "#ffffff", "black": "#000000", "cyan": "#4ac8d9", "magenta": "#d94ac8",
}


def rgb(color) -> tuple:
    """'#rrggbb' or a tuple -> (r, g, b)."""
    if isinstance(color, str):
        c = NAMED_COLORS.get(color, color).lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return tuple(color[:3])


def luminance(color) -> float:
    def ch(v):
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(color)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_text(bg) -> str:
    """Black or white, whichever reads better on bg (WCAG)."""
    lum = luminance(bg)
    return "#FFFFFF" if 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05 else "#000000"

# Theme (single, dark on purpose: the screen is a calm object, not a document).
# Values are the design mock's CSS variables, ported verbatim.
BG = "#1d1234"          # app ground (--device)
SURFACE = "#251845"     # stage (--stage)
TILE = "#30244E"        # music keys, panels: white at 5% over SURFACE
TILE_LINE = "#332651"   # the keys' hairline border: white at 6% over SURFACE
FIELD = "#362A54"       # the Play input's fill: white at 8% over SURFACE
HAIR = "#2c2148"        # subtle borders: cards, the Esc pill (--hair)
LINE = "#7a5aa6"        # the stage border, the input border (--border)
PRIMARY = "#a074d6"     # the selection plate (--sel)
ON_PRIMARY = "#1a0f30"  # ink on the selection plate (--on-sel)
ACCENT = "#c39cf0"      # prompt label, titles, values (--accent)
TEXT = "#d8cbef"        # (--ink)
MUTED = "#9585b6"       # hints, status (--ink-dim)
DIM = "#6f5f92"         # quiet hints (--ink-faint)
CARET = "#d7e79c"
DANGER = "#c46b7b"
GOOD = "#7bc48a"

GRAYSCALE = {
    "1": "#FFFFFF", "2": "#E8E8E8", "3": "#D0D0D0", "4": "#B8B8B8", "5": "#A0A0A0",
    "6": "#888888", "7": "#707070", "8": "#585858", "9": "#404040", "0": "#282828",
    "-": "#101010", "=": "#000000", "+": "#000000",
}
QWERTY_ROW = list("qwertyuiop[]")
ASDF_ROW = list("asdfghjkl;'")
ZXCV_ROW = list("zxcvbnm,./")

# Legend swatches per keyboard row, light to dark, top to bottom like the keyboard
ROW_LEGEND_COLORS = [
    ["#C0C0C0", "#808080", "#404040"],
    ["#DF7070", "#BF4040", "#802020"],
    ["#DFC070", "#BFA040", "#806820"],
    ["#7090DF", "#4060BF", "#203080"],
]

DEFAULT_BRUSH_COLOR = PRIMARY
UNMAPPED = "#AAAAAA"


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def generate_row_gradient(hue: float, keys: list) -> dict:
    count = len(keys)
    return {k: hsl_to_hex(hue, 0.75, 0.80 - (i / max(count - 1, 1)) * 0.60) for i, k in enumerate(keys)}


KEY_COLORS: dict = {}
KEY_COLORS.update(GRAYSCALE)
KEY_COLORS.update(generate_row_gradient(0, QWERTY_ROW))
KEY_COLORS.update(generate_row_gradient(50, ASDF_ROW))
KEY_COLORS.update(generate_row_gradient(220, ZXCV_ROW))
# Kid-math remaps arrive as the displayed glyph
KEY_COLORS["÷"] = KEY_COLORS["/"]
KEY_COLORS["×"] = KEY_COLORS.get("*", KEY_COLORS["/"])


def get_key_color(char: str) -> str:
    """Sticker color for a key, or UNMAPPED (callers treat it as 'not a color')."""
    return KEY_COLORS.get(char.lower(), UNMAPPED)


def text_color_for(bg_hex: str) -> str:
    return contrast_text(bg_hex)


def get_legend_row_from_color(color: str) -> int:
    """0 gray, 1 red, 2 yellow, 3 blue, by hue and saturation."""
    r, g, b = hex_to_rgb(color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    hue = h * 360
    if s < 0.15:
        return 0
    if hue < 30 or hue > 330:
        return 1
    if 30 <= hue < 90:
        return 2
    if 180 <= hue < 270:
        return 3
    return 0
