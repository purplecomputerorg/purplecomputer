#!/usr/bin/env python3
"""Calculate Alacritty font size for 10x6 inch content area (100x28 cells).

Strategy:
1. Try to read cached probe results (instant)
2. If cache miss/invalid, probe Alacritty once at 18pt to get real cell dimensions
3. Calculate font size to achieve ~10x6 inch viewport (if physical size known)
   or fill ~85% of screen (if physical size unknown)
4. If anything fails, fall back to 16pt (guaranteed to fit 1280x800)

Every step has a fallback. Nothing can error out.
"""

import subprocess
import re
import os
import sys

# Target viewport: 100 columns x 28 rows
COLS, ROWS = 100, 28

# Target physical size in mm (10x6 inches)
TARGET_WIDTH_MM = 254   # 10 inches
TARGET_HEIGHT_MM = 152  # 6 inches

# Probe settings
PROBE_FONT_PT = 18
CACHE_FILE = "/var/cache/purple/font_probe.cache"

# Safety limits
MIN_FONT_PT = 10
MAX_FONT_PT = 48
MAX_SCREEN_FILL = 0.85  # Never use more than 85% of screen
SAFETY_MARGIN = 0.95    # 5% safety margin on calculated size

# Fallback if everything fails
FALLBACK_FONT_PT = 16

# Sane physical screen size range (mm) - reject obviously wrong EDID data
MIN_SCREEN_WIDTH_MM = 200   # ~8 inches
MAX_SCREEN_WIDTH_MM = 500   # ~20 inches


def get_screen_info():
    """Get screen resolution (pixels) and physical size (mm) from xrandr.

    Returns: (width_px, height_px, width_mm, height_mm)
    width_mm/height_mm are None if not available or invalid.
    """
    try:
        out = subprocess.check_output(["xrandr"], text=True, timeout=5, stderr=subprocess.DEVNULL)

        # Find connected display with current mode
        # Example: "eDP-1 connected primary 2304x1536+0+0 (normal...) 267mm x 178mm"
        # or: "HDMI-1 connected 1920x1080+0+0 (normal...) 527mm x 296mm"
        pattern = r'(\d+)x(\d+)\+\d+\+\d+[^0-9]*?(\d+)mm\s*x\s*(\d+)mm'
        m = re.search(pattern, out)
        if m:
            px_w, px_h = int(m.group(1)), int(m.group(2))
            mm_w, mm_h = int(m.group(3)), int(m.group(4))

            # Validate physical dimensions are sane
            if MIN_SCREEN_WIDTH_MM <= mm_w <= MAX_SCREEN_WIDTH_MM:
                return px_w, px_h, mm_w, mm_h
            else:
                # Physical size looks wrong, ignore it
                return px_w, px_h, None, None

        # Fallback: just get resolution without physical size
        m = re.search(r'(\d+)x(\d+)\+\d+\+\d+', out)
        if m:
            return int(m.group(1)), int(m.group(2)), None, None

    except Exception:
        pass

    # Ultimate fallback
    return 1366, 768, None, None


def read_cache(screen_w, screen_h):
    """Try to read cached probe results. Returns (cell_w, cell_h) or None."""
    try:
        if not os.path.exists(CACHE_FILE):
            return None

        with open(CACHE_FILE, 'r') as f:
            line = f.readline().strip()

        # Format: "WxH:probe_pt:cell_w:cell_h"
        parts = line.split(':')
        if len(parts) != 4:
            return None

        cached_res, probe_pt, cell_w, cell_h = parts
        cached_w, cached_h = cached_res.split('x')

        # Validate cache matches current screen
        if int(cached_w) != screen_w or int(cached_h) != screen_h:
            return None
        if int(probe_pt) != PROBE_FONT_PT:
            return None

        cell_w, cell_h = int(cell_w), int(cell_h)

        # Sanity check cell dimensions
        if not (5 <= cell_w <= 50 and 10 <= cell_h <= 100):
            return None

        return cell_w, cell_h

    except Exception:
        return None


def write_cache(screen_w, screen_h, cell_w, cell_h):
    """Write probe results to cache. Silent fail if it doesn't work."""
    try:
        cache_dir = os.path.dirname(CACHE_FILE)
        os.makedirs(cache_dir, exist_ok=True)

        with open(CACHE_FILE, 'w') as f:
            f.write(f"{screen_w}x{screen_h}:{PROBE_FONT_PT}:{cell_w}:{cell_h}\n")
    except Exception:
        pass  # Cache write failed, no big deal


def probe_alacritty():
    """Probe Alacritty at PROBE_FONT_PT to get actual cell dimensions.

    Returns: (cell_w, cell_h) or None if probe fails.
    """
    try:
        # Use same env settings as runtime for consistency
        env = os.environ.copy()

        # Run alacritty with verbose logging, execute 'true' and exit
        proc = subprocess.run(
            ["alacritty", "-vvv", "-o", f"font.size={PROBE_FONT_PT}", "-e", "true"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )

        output = proc.stderr + proc.stdout

        # Look for cell size in logs
        # Format varies by version: "Cell size: 11 x 22" or "cell_width=11, cell_height=22"
        m = re.search(r'[Cc]ell\s*(?:size)?[:\s]+(\d+)\s*x\s*(\d+)', output)
        if m:
            return int(m.group(1)), int(m.group(2))

        # Alternative format
        m = re.search(r'cell_width[=:\s]+(\d+).*cell_height[=:\s]+(\d+)', output, re.S)
        if m:
            return int(m.group(1)), int(m.group(2))

    except Exception:
        pass

    return None


def calculate_font_size(screen_w, screen_h, screen_mm_w, cell_w, cell_h):
    """Calculate optimal font size given screen and cell dimensions.

    If screen_mm_w is known, target 10" wide viewport.
    Otherwise, target 85% of screen width.
    Always cap at 85% of screen and apply safety margin.
    """
    # Calculate viewport pixel size at probe font size
    probe_viewport_w = cell_w * COLS
    probe_viewport_h = cell_h * ROWS

    if screen_mm_w is not None:
        # We know physical screen size - target 10" (254mm) viewport
        # But cap at 85% of screen
        target_fraction = min(TARGET_WIDTH_MM / screen_mm_w, MAX_SCREEN_FILL)
        target_viewport_w = screen_w * target_fraction

        # Also check height constraint (6" = 152mm)
        # Assuming similar mm accuracy for height
        target_viewport_h = screen_h * MAX_SCREEN_FILL  # Height is less critical
    else:
        # No physical size - just fill 85% of screen
        target_viewport_w = screen_w * MAX_SCREEN_FILL
        target_viewport_h = screen_h * MAX_SCREEN_FILL

    # Calculate scale factor from probe size
    scale_w = target_viewport_w / probe_viewport_w
    scale_h = target_viewport_h / probe_viewport_h
    scale = min(scale_w, scale_h)

    # Calculate font size
    font_pt = PROBE_FONT_PT * scale

    # Apply safety margin
    font_pt *= SAFETY_MARGIN

    # Clamp to valid range
    font_pt = max(MIN_FONT_PT, min(MAX_FONT_PT, font_pt))

    return font_pt


def main():
    # Step 1: Get screen info
    screen_w, screen_h, screen_mm_w, screen_mm_h = get_screen_info()

    # Step 2: Try cache
    cached = read_cache(screen_w, screen_h)
    if cached:
        cell_w, cell_h = cached
    else:
        # Step 3: Probe Alacritty
        probed = probe_alacritty()
        if probed:
            cell_w, cell_h = probed
            write_cache(screen_w, screen_h, cell_w, cell_h)
        else:
            # Step 4: Probe failed, use fallback
            print(f"{FALLBACK_FONT_PT:.1f}")
            return

    # Step 5: Calculate font size
    font_pt = calculate_font_size(screen_w, screen_h, screen_mm_w, cell_w, cell_h)

    print(f"{font_pt:.1f}")


if __name__ == "__main__":
    main()
