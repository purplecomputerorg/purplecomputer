#!/usr/bin/env python3
"""Calculate Alacritty font size for 10x6 inch content area (100x28 cells)."""

import subprocess
import re
import os

COLS, ROWS = 100, 28
PROBE_FONT_PT = 12
FALLBACK_CELL_W, FALLBACK_CELL_H = 8, 16
FALLBACK_SW, FALLBACK_SH = 1366, 768
MIN_FONT_PT = 6

def probe_cell_size():
    """Probe Alacritty at 12pt to measure actual cell dimensions."""
    try:
        env = os.environ.copy()
        env["WINIT_X11_SCALE_FACTOR"] = "1"
        proc = subprocess.run(
            ["alacritty", "-v", "-e", "true"],
            capture_output=True, text=True, timeout=5, env=env
        )
        output = proc.stderr + proc.stdout
        # Match "Cell size: WxH" or "CellDimensions W x H"
        m = re.search(r'Cell\s*(?:size:|Dimensions)\s*(\d+)\s*x\s*(\d+)', output, re.I)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return FALLBACK_CELL_W, FALLBACK_CELL_H

def get_screen_size():
    """Get screen resolution via xrandr or python-xlib fallback."""
    # Try xrandr
    try:
        out = subprocess.check_output(["xrandr"], text=True, timeout=5)
        # Look for primary monitor first
        m = re.search(r'primary\s+(\d+)x(\d+)', out)
        if m:
            return int(m.group(1)), int(m.group(2))
        # Otherwise find largest connected mode
        modes = re.findall(r'(\d+)x(\d+)', out)
        if modes:
            return max(modes, key=lambda x: int(x[0]) * int(x[1]))
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

def main():
    cell_w, cell_h = probe_cell_size()
    screen_w, screen_h = get_screen_size()

    target_w = cell_w * COLS
    target_h = cell_h * ROWS

    scale_w = int(screen_w) / target_w
    scale_h = int(screen_h) / target_h
    scale = min(scale_w, scale_h)

    if scale <= 0 or scale > 10:
        scale = 1

    font_pt = max(PROBE_FONT_PT * scale, MIN_FONT_PT)
    print(f"{font_pt:.1f}")

if __name__ == "__main__":
    main()
