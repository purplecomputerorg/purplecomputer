#!/usr/bin/env python3
"""Calculate Alacritty font size for 10x6 inch content area (100x28 cells).

The viewport must fit within the screen. We use empirically measured ratios
for JetBrainsMono Nerd Font to calculate the maximum font size that fits.

Key insight: cell dimensions scale linearly with font point size for a given font.
JetBrainsMono at 1pt has cell width ~0.6px and height ~1.2px (ratio varies by DPI).
"""

import subprocess
import re
import os

COLS, ROWS = 100, 28
MIN_FONT_PT = 6
MAX_FONT_PT = 72
FALLBACK_SW, FALLBACK_SH = 1366, 768

# JetBrainsMono Nerd Font: empirically measured cell size per point
# At 12pt on 96 DPI: cell is approximately 7.2 x 14.4 pixels
# This gives us pixels-per-point ratios
CELL_WIDTH_PER_PT = 0.6   # pixels of cell width per font point
CELL_HEIGHT_PER_PT = 1.2  # pixels of cell height per font point


def get_screen_size():
    """Get screen resolution via xrandr or python-xlib fallback."""
    # Try xrandr - look for current mode (marked with *)
    try:
        out = subprocess.check_output(["xrandr"], text=True, timeout=5)
        # Look for current mode on connected display: "1920x1080+0+0" or "1920x1080*"
        # Primary display with current mode
        m = re.search(r'(\d+)x(\d+)\+\d+\+\d+', out)
        if m:
            return int(m.group(1)), int(m.group(2))
        # Fallback: look for any resolution with * (current mode)
        m = re.search(r'(\d+)x(\d+)[^*]*\*', out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass

    # Fallback: python-xlib
    try:
        from Xlib import display
        d = display.Display()
        s = d.screen()
        return s.width_in_pixels, s.height_in_pixels
    except Exception:
        pass

    return FALLBACK_SW, FALLBACK_SH


def calc_font_size(screen_w, screen_h):
    """Calculate font size that fits 100x28 cell viewport in screen."""
    # Calculate max font size that fits width
    # viewport_width = COLS * CELL_WIDTH_PER_PT * font_pt
    # We want viewport_width <= screen_w
    # So: font_pt <= screen_w / (COLS * CELL_WIDTH_PER_PT)
    max_pt_for_width = screen_w / (COLS * CELL_WIDTH_PER_PT)

    # Calculate max font size that fits height
    max_pt_for_height = screen_h / (ROWS * CELL_HEIGHT_PER_PT)

    # Use the smaller to ensure both dimensions fit
    font_pt = min(max_pt_for_width, max_pt_for_height)

    # Apply a safety margin (95%) to account for window chrome, padding, etc.
    font_pt *= 0.95

    # Clamp to reasonable range
    font_pt = max(MIN_FONT_PT, min(MAX_FONT_PT, font_pt))

    return font_pt


def main():
    screen_w, screen_h = get_screen_size()
    font_pt = calc_font_size(screen_w, screen_h)
    print(f"{font_pt:.1f}")


if __name__ == "__main__":
    main()
