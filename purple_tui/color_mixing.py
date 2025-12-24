"""
Paint-like Color Mixing using RYB Color Model

This module implements subtractive color mixing similar to how paint mixes,
using the RYB (Red-Yellow-Blue) color model that kids learn in art class.

Key behaviors:
- red + blue = purple
- red + yellow = orange
- blue + yellow = green
- red + red + blue = reddish purple (weighted mixing)
- mixing complementary colors = brownish/muddy
"""

from typing import Tuple


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color string to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex color string"""
    return f"#{r:02X}{g:02X}{b:02X}"


# RYB to RGB conversion using trilinear interpolation
# Based on the Gosset and Chen paper approach
# These are the RGB values at the corners of the RYB cube

RYB_CUBE = {
    # (r, y, b) -> (R, G, B)
    (0, 0, 0): (255, 255, 255),  # white
    (1, 0, 0): (255, 0, 0),       # red
    (0, 1, 0): (255, 255, 0),     # yellow
    (0, 0, 1): (0, 0, 255),       # blue
    (1, 1, 0): (255, 128, 0),     # orange (red + yellow)
    (1, 0, 1): (128, 0, 128),     # purple (red + blue)
    (0, 1, 1): (0, 128, 0),       # green (yellow + blue)
    (1, 1, 1): (64, 32, 16),      # dark brown (all mixed)
}


def _cubic_interpolate(t: float, a: float, b: float) -> float:
    """Cubic interpolation for smoother color transitions"""
    return a + t * (b - a)


def ryb_to_rgb(r: float, y: float, b: float) -> Tuple[int, int, int]:
    """
    Convert RYB (0-1 range) to RGB (0-255 range) using trilinear interpolation.

    This maps the RYB color cube to RGB colors that look like paint mixing.
    """
    # Clamp inputs
    r = max(0, min(1, r))
    y = max(0, min(1, y))
    b = max(0, min(1, b))

    # Trilinear interpolation through the RYB cube
    # Interpolate along R axis first
    x00 = tuple(_cubic_interpolate(r, RYB_CUBE[(0,0,0)][i], RYB_CUBE[(1,0,0)][i]) for i in range(3))
    x01 = tuple(_cubic_interpolate(r, RYB_CUBE[(0,0,1)][i], RYB_CUBE[(1,0,1)][i]) for i in range(3))
    x10 = tuple(_cubic_interpolate(r, RYB_CUBE[(0,1,0)][i], RYB_CUBE[(1,1,0)][i]) for i in range(3))
    x11 = tuple(_cubic_interpolate(r, RYB_CUBE[(0,1,1)][i], RYB_CUBE[(1,1,1)][i]) for i in range(3))

    # Interpolate along Y axis
    y0 = tuple(_cubic_interpolate(y, x00[i], x10[i]) for i in range(3))
    y1 = tuple(_cubic_interpolate(y, x01[i], x11[i]) for i in range(3))

    # Interpolate along B axis
    final = tuple(int(_cubic_interpolate(b, y0[i], y1[i])) for i in range(3))

    return (
        max(0, min(255, final[0])),
        max(0, min(255, final[1])),
        max(0, min(255, final[2]))
    )


def rgb_to_ryb(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """
    Approximate conversion from RGB to RYB.

    This is an approximation since RGB->RYB is not perfectly invertible.
    We use the approach of removing whiteness and blackness first.
    """
    # Normalize to 0-1
    r, g, b = r / 255.0, g / 255.0, b / 255.0

    # Remove whiteness
    w = min(r, g, b)
    r -= w
    g -= w
    b -= w

    max_g = max(r, g, b)

    # Calculate yellow from red and green
    y = min(r, g)
    r -= y
    g -= y

    # If blue and green remain, convert to blue
    if b > 0 and g > 0:
        b += g
        g = 0

    # Redistribute
    if max_g > 0:
        n = max(r, y, b) / max_g
        if n > 0:
            r /= n
            y /= n
            b /= n

    # Add back whiteness
    r += w
    y += w
    b += w

    return (
        max(0, min(1, r)),
        max(0, min(1, y)),
        max(0, min(1, b))
    )


def mix_colors_paint(colors: list[str], weights: list[float] = None) -> str:
    """
    Mix multiple colors like paint using the RYB color model.

    Args:
        colors: List of hex color strings (e.g., ["#FF0000", "#0000FF"])
        weights: Optional list of weights for each color (defaults to equal)

    Returns:
        Hex color string of the mixed result

    Example:
        mix_colors_paint(["#FF0000", "#0000FF"]) -> purple
        mix_colors_paint(["#FF0000", "#FF0000", "#0000FF"]) -> reddish purple
    """
    if not colors:
        return "#808080"  # gray default

    if len(colors) == 1:
        return colors[0]

    # Default to equal weights
    if weights is None:
        weights = [1.0] * len(colors)

    # Normalize weights
    total_weight = sum(weights)
    if total_weight == 0:
        weights = [1.0 / len(colors)] * len(colors)
    else:
        weights = [w / total_weight for w in weights]

    # Convert all colors to RYB
    ryb_colors = []
    for hex_color in colors:
        rgb = hex_to_rgb(hex_color)
        ryb = rgb_to_ryb(*rgb)
        ryb_colors.append(ryb)

    # Weighted average in RYB space
    mixed_r = sum(ryb[0] * w for ryb, w in zip(ryb_colors, weights))
    mixed_y = sum(ryb[1] * w for ryb, w in zip(ryb_colors, weights))
    mixed_b = sum(ryb[2] * w for ryb, w in zip(ryb_colors, weights))

    # Convert back to RGB
    result_rgb = ryb_to_rgb(mixed_r, mixed_y, mixed_b)

    return rgb_to_hex(*result_rgb)


def get_color_name_approximation(hex_color: str) -> str:
    """
    Get an approximate name for a mixed color.

    This is used for speech output to describe the result.
    """
    r, g, b = hex_to_rgb(hex_color)

    # Convert to HSL-like values for easier categorization
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    l = (max_c + min_c) / 2 / 255  # lightness 0-1

    if max_c == min_c:
        # Grayscale
        if l < 0.2:
            return "black"
        elif l < 0.4:
            return "dark gray"
        elif l < 0.6:
            return "gray"
        elif l < 0.8:
            return "light gray"
        else:
            return "white"

    # Calculate hue
    d = max_c - min_c
    if max_c == r:
        h = ((g - b) / d) % 6
    elif max_c == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    h *= 60  # Convert to degrees

    # Saturation
    s = d / (255 - abs(2 * (max_c + min_c) / 2 - 255)) if max_c != min_c else 0

    # Name based on hue
    if s < 0.15:
        # Low saturation = grayish
        if l < 0.3:
            return "dark gray"
        elif l > 0.7:
            return "light gray"
        return "gray"

    # Map hue to color name
    if h < 15 or h >= 345:
        base = "red"
    elif h < 45:
        base = "orange"
    elif h < 70:
        base = "yellow"
    elif h < 150:
        base = "green"
    elif h < 200:
        base = "cyan"
    elif h < 260:
        base = "blue"
    elif h < 320:
        base = "purple"
    else:
        base = "pink"

    # Add modifiers
    if l < 0.25:
        return f"dark {base}"
    elif l > 0.75:
        return f"light {base}"
    elif s < 0.4:
        return f"muted {base}"

    return base
