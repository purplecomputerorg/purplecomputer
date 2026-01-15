#!/usr/bin/env python3
"""Calculate Alacritty font size for Purple Computer.

Simple approach:
1. Get screen resolution
2. Get cell dimensions (probe or estimate)
3. Calculate font to fill 80% of screen
4. Clamp to 12-32pt

No physical size detection (EDID is unreliable).
No validation loops (calculation should just work).
Always produces a reasonable result.
"""

import subprocess
import re
import os
import sys

# Terminal grid required for full UI (from purple_tui/constants.py)
REQUIRED_COLS = 104
REQUIRED_ROWS = 37

# Target: fill 80% of screen (leaves visible border, never clips)
SCREEN_FILL = 0.80

# Font size limits (always reasonable)
MIN_FONT = 12
MAX_FONT = 24  # Cap prevents huge viewport on large screens
PROBE_FONT = 18

# Fallbacks
FALLBACK_RESOLUTION = (1366, 768)
FALLBACK_CELL = (11, 22)  # Typical for JetBrainsMono at 18pt


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


def probe_cell_size():
    """Probe Alacritty for cell dimensions at PROBE_FONT. Returns (w, h)."""
    try:
        result = subprocess.run(
            ["alacritty", "-vvv", "-o", f"font.size={PROBE_FONT}", "-e", "true"],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, 'WINIT_X11_SCALE_FACTOR': '1.0'}
        )
        output = result.stderr + result.stdout
        # Match: "Cell size: 11 x 22" or similar
        m = re.search(r'[Cc]ell[^0-9]*(\d+)\s*x\s*(\d+)', output)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            if 5 <= w <= 30 and 10 <= h <= 60:  # Sanity check
                return w, h
    except Exception:
        pass
    return FALLBACK_CELL


def calculate_font(screen_w, screen_h, cell_w, cell_h):
    """Calculate font size to fill SCREEN_FILL of screen."""
    # How much space we have
    available_w = screen_w * SCREEN_FILL
    available_h = screen_h * SCREEN_FILL

    # How much space the grid needs at probe font size
    grid_w = cell_w * REQUIRED_COLS
    grid_h = cell_h * REQUIRED_ROWS

    # Scale factor (use the more restrictive dimension)
    scale = min(available_w / grid_w, available_h / grid_h)

    # Calculate and clamp
    font = PROBE_FONT * scale
    return max(MIN_FONT, min(MAX_FONT, font))


def main():
    # Debug mode
    if len(sys.argv) > 1 and sys.argv[1] == '--info':
        screen = get_resolution()
        cell = probe_cell_size()
        font = calculate_font(*screen, *cell)
        print(f"Screen: {screen[0]}x{screen[1]}")
        print(f"Cell: {cell[0]}x{cell[1]} (at {PROBE_FONT}pt)")
        print(f"Grid: {REQUIRED_COLS}x{REQUIRED_ROWS}")
        print(f"Fill: {SCREEN_FILL*100:.0f}%")
        print(f"Font: {font:.1f}pt")
        return

    # Normal mode: output font size
    screen = get_resolution()
    cell = probe_cell_size()
    font = calculate_font(*screen, *cell)
    print(f"{font:.1f}")


if __name__ == "__main__":
    main()
