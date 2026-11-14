"""
Paint-like Color Mixing using Spectral Reflectance

Based on spectral.js by Ronald van Wijnen (MIT License)
https://github.com/rvanwijnen/spectral.js

Uses Beer-Lambert spectral mixing with saturation correction for
realistic pigment mixing where:
- yellow + blue = green
- red + blue = purple
- red + yellow = orange
"""

import colorsys
import math

# The spectral mixer lives in the room library so family rooms can mix() with it too.
from .roomkit.purple import (BASE_SPECTRA, SIZE, _linear_rgb_to_spectrum, _linear_to_srgb, _spectrum_to_xyz,  # noqa: F401
                             _srgb_to_linear, _xyz_to_linear_rgb, hex_to_rgb, rgb_to_hex)
from .roomkit.purple import _mix as mix_colors_paint  # noqa: F401


def _ks(r: float) -> float:
    """Kubelka-Munk K/S coefficient from reflectance."""
    r = max(1e-10, r)
    return (1 - r) ** 2 / (2 * r)


def _km(ks: float) -> float:
    """Kubelka-Munk reflectance from K/S coefficient."""
    return 1 + ks - math.sqrt(ks * ks + 2 * ks)


COLOR_ADJECTIVES = {
    # adjective: (saturation_mult, lightness_func)
    # lightness_func takes current L and returns new L
    "bright":  (1.3, lambda l: min(1.0, l * 1.15)),
    "dark":    (1.0, lambda l: l * 0.55),
    "light":   (0.7, lambda l: l + (1 - l) * 0.45),
    "pale":    (0.4, lambda l: l + (1 - l) * 0.4),
    "deep":    (1.3, lambda l: l * 0.65),
    "vivid":   (1.6, lambda l: l),
    "dull":    (0.4, lambda l: l),
    "muted":   (0.4, lambda l: l + (1 - l) * 0.1),
    "neon":    (2.0, lambda l: l + (1 - l) * 0.25),
    "soft":    (0.5, lambda l: l + (1 - l) * 0.3),
    "rich":    (1.4, lambda l: l * 0.8),
    "warm":    (1.1, lambda l: min(1.0, l * 1.05)),  # slight shift handled below
    "cool":    (1.1, lambda l: min(1.0, l * 1.05)),  # slight shift handled below
}


def modify_color(hex_color: str, adjective: str) -> str:
    """Modify a color by an adjective (bright, dark, light, etc.) in HSL space."""
    adj = adjective.lower()
    if adj not in COLOR_ADJECTIVES:
        return hex_color

    s_mult, l_func = COLOR_ADJECTIVES[adj]
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)

    # Apply saturation and lightness modifications
    s = min(1.0, s * s_mult)
    l = l_func(l)

    # Warm/cool: nudge hue slightly
    if adj == "warm":
        # Nudge toward orange (reduce blue, boost red/yellow)
        if 0.33 < h < 0.83:  # greens/blues/purples
            h = h - 0.03
    elif adj == "cool":
        # Nudge toward blue
        if h < 0.33 or h > 0.83:  # reds/oranges/yellows
            h = h + 0.03

    h = h % 1.0
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex(
        max(0, min(255, round(r2 * 255))),
        max(0, min(255, round(g2 * 255))),
        max(0, min(255, round(b2 * 255))),
    )


def get_color_name_approximation(hex_color: str) -> str:
    """
    Get an approximate name for a color.
    Returns simple color names without modifiers.
    """
    r, g, b = hex_to_rgb(hex_color)

    max_c = max(r, g, b)
    min_c = min(r, g, b)
    l = (max_c + min_c) / 2 / 255

    if max_c == min_c:
        if l < 0.2:
            return "black"
        elif l > 0.8:
            return "white"
        return "gray"

    d = max_c - min_c
    if max_c == r:
        h = ((g - b) / d) % 6
    elif max_c == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    h *= 60

    s = d / (255 - abs(2 * (max_c + min_c) / 2 - 255)) if max_c != min_c else 0

    if s < 0.1:
        if l < 0.3:
            return "black"
        elif l > 0.7:
            return "white"
        return "gray"

    if h < 15 or h >= 345:
        return "red"
    elif h < 45:
        return "orange"
    elif h < 70:
        return "yellow"
    elif h < 150:
        return "green"
    elif h < 190:
        return "cyan"
    elif h < 250:
        return "blue"
    elif h < 320:
        return "purple"
    else:
        return "pink"
