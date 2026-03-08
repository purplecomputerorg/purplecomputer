#!/usr/bin/env python3
"""Calculate Alacritty font size for Purple Computer.

Simple approach:
1. Get screen resolution
2. Use known cell-to-point ratio for JetBrainsMono at 96 DPI
3. Calculate font to fill 75% of screen
4. Floor to nearest 0.5pt, clamp to 12-48pt
"""

import subprocess
import re
import math
import sys

# Terminal grid required for full UI (must stay in sync with purple_tui)
from purple_tui.constants import REQUIRED_TERMINAL_COLS, REQUIRED_TERMINAL_ROWS
REQUIRED_COLS = REQUIRED_TERMINAL_COLS
REQUIRED_ROWS = REQUIRED_TERMINAL_ROWS

# JetBrainsMono cell dimensions per point at 96 DPI (forced via WINIT_X11_SCALE_FACTOR=1.0)
# At 18pt: cell is 11x22 pixels, so ratio is 11/18 and 22/18
CELL_WIDTH_PER_PT = 11 / 18   # ~0.611 px per pt
CELL_HEIGHT_PER_PT = 22 / 18  # ~1.222 px per pt

# Target: fill 75% of screen (leaves visible border, never clips)
SCREEN_FILL = 0.75

# Font size limits (always reasonable)
MIN_FONT = 12
MAX_FONT = 48

# Fallbacks
FALLBACK_RESOLUTION = (1366, 768)


def get_resolution():
    """Get screen resolution. Returns (width, height)."""
    try:
        out = subprocess.check_output(
            ["xrandr"], text=True, timeout=5, stderr=subprocess.DEVNULL
        )
        # Match: "1920x1080+0+0" (current mode)
        m = re.search(r'(\d+)x(\d+)\+\d+\+\d+', out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return FALLBACK_RESOLUTION


def calculate_font(screen_w, screen_h):
    """Calculate font size to fill SCREEN_FILL of screen."""
    available_w = screen_w * SCREEN_FILL
    available_h = screen_h * SCREEN_FILL

    # Font size where grid fits available space
    font_from_w = available_w / (REQUIRED_COLS * CELL_WIDTH_PER_PT)
    font_from_h = available_h / (REQUIRED_ROWS * CELL_HEIGHT_PER_PT)

    # Use the more restrictive dimension
    font = min(font_from_w, font_from_h)

    # Floor to nearest 0.5pt for extra safety
    font = math.floor(font * 2) / 2

    return max(MIN_FONT, min(MAX_FONT, font))


def main():
    # Debug mode
    if len(sys.argv) > 1 and sys.argv[1] == '--info':
        screen = get_resolution()
        font = calculate_font(*screen)
        print(f"Screen: {screen[0]}x{screen[1]}")
        print(f"Grid: {REQUIRED_COLS}x{REQUIRED_ROWS}")
        print(f"Cell ratio: {CELL_WIDTH_PER_PT:.3f}w x {CELL_HEIGHT_PER_PT:.3f}h px/pt")
        print(f"Fill: {SCREEN_FILL*100:.0f}%")
        print(f"Font: {font:.1f}pt")
        return

    # Normal mode: output font size
    screen = get_resolution()
    font = calculate_font(*screen)
    print(f"{font:.1f}")


if __name__ == "__main__":
    main()
