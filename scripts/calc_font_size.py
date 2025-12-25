#!/usr/bin/env python3
"""Calculate Alacritty font size for Purple Computer kiosk display.

Strategy:
1. Wait for X11 resolution to stabilize (handles SPICE agent race)
2. Try to read cached probe results (instant on subsequent boots)
3. If cache miss, probe Alacritty at reference font to get real cell dimensions
4. Calculate largest font size such that REQUIRED terminal grid fits on screen
5. If physical screen size is known and sane, also try to hit ~10x6" viewport
6. Every step has fallbacks - nothing can error out

Terminal grid requirements are imported from purple_tui/constants.py to stay
in sync with the actual Textual layout (104 cols × 37 rows for full UI).
"""

import subprocess
import re
import os
import sys
import time

# Try to import layout constants from purple_tui
# Fall back to hardcoded values if import fails (e.g., during ISO build)
try:
    # When installed, purple_tui is in /opt/purple/purple_tui/
    sys.path.insert(0, '/opt/purple')
    from purple_tui.constants import (
        REQUIRED_TERMINAL_COLS,
        REQUIRED_TERMINAL_ROWS,
        TARGET_VIEWPORT_WIDTH_MM,
    )
except ImportError:
    # Fallback for development or if constants unavailable
    REQUIRED_TERMINAL_COLS = 104
    REQUIRED_TERMINAL_ROWS = 37
    TARGET_VIEWPORT_WIDTH_MM = 254  # 10 inches

# Probe settings
PROBE_FONT_PT = 18
CACHE_FILE = "/var/cache/purple/font_probe.cache"

# Safety limits
MIN_FONT_PT = 10
MAX_FONT_PT = 48
MAX_SCREEN_FILL = 0.85   # Never use more than 85% of screen
SAFETY_MARGIN = 0.95     # 5% reduction on calculated size
FALLBACK_FONT_PT = 14    # Conservative fallback (fits 1280x800)

# DPI validation - reject obviously wrong EDID data
MIN_SANE_DPI = 60    # Below this, EDID is probably wrong
MAX_SANE_DPI = 220   # Above this, EDID is probably wrong (or HiDPI which we don't support well)

# Resolution stabilization
MAX_STABILITY_WAIT = 5.0   # Max seconds to wait for resolution to stabilize
STABILITY_CHECK_INTERVAL = 0.3
STABILITY_REQUIRED_CHECKS = 2  # Must see same resolution this many times


def get_screen_info():
    """Get screen resolution (pixels) and physical size (mm) from xrandr.

    Returns: (width_px, height_px, width_mm, height_mm)
    width_mm/height_mm are None if not available or invalid DPI.
    """
    try:
        out = subprocess.check_output(
            ["xrandr"], text=True, timeout=5, stderr=subprocess.DEVNULL
        )

        # Find connected display with current mode
        # Example: "eDP-1 connected primary 2304x1536+0+0 (normal...) 267mm x 178mm"
        pattern = r'(\d+)x(\d+)\+\d+\+\d+[^0-9]*?(\d+)mm\s*x\s*(\d+)mm'
        m = re.search(pattern, out)
        if m:
            px_w, px_h = int(m.group(1)), int(m.group(2))
            mm_w, mm_h = int(m.group(3)), int(m.group(4))

            # Validate DPI is sane (not clearly wrong EDID)
            if mm_w > 0:
                dpi = px_w / (mm_w / 25.4)
                if MIN_SANE_DPI <= dpi <= MAX_SANE_DPI:
                    return px_w, px_h, mm_w, mm_h
            # DPI looks wrong, ignore physical size
            return px_w, px_h, None, None

        # Fallback: just get resolution without physical size
        m = re.search(r'(\d+)x(\d+)\+\d+\+\d+', out)
        if m:
            return int(m.group(1)), int(m.group(2)), None, None

    except Exception:
        pass

    # Ultimate fallback
    return 1366, 768, None, None


def wait_for_resolution_stability():
    """Wait until screen resolution stops changing (handles SPICE race).

    Returns the stable resolution (width_px, height_px, width_mm, height_mm).
    """
    start_time = time.time()
    last_res = None
    stable_count = 0

    while time.time() - start_time < MAX_STABILITY_WAIT:
        current = get_screen_info()
        current_res = (current[0], current[1])  # Just pixel dimensions

        if current_res == last_res:
            stable_count += 1
            if stable_count >= STABILITY_REQUIRED_CHECKS:
                return current
        else:
            stable_count = 0
            last_res = current_res

        time.sleep(STABILITY_CHECK_INTERVAL)

    # Timeout - return whatever we have
    return get_screen_info()


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

        # Validate cache matches current screen and probe font
        if int(cached_w) != screen_w or int(cached_h) != screen_h:
            return None
        if int(probe_pt) != PROBE_FONT_PT:
            return None

        cell_w, cell_h = int(cell_w), int(cell_h)

        # Sanity check cell dimensions (pixels per character)
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
        pass


def probe_alacritty():
    """Probe Alacritty at PROBE_FONT_PT to get actual cell dimensions.

    Returns: (cell_w, cell_h) or None if probe fails.
    """
    try:
        env = os.environ.copy()
        # Force scale factor to 1.0 for predictable sizing
        env['WINIT_X11_SCALE_FACTOR'] = '1.0'

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

    Primary constraint: terminal must fit REQUIRED_TERMINAL_COLS × REQUIRED_TERMINAL_ROWS
    Secondary goal: if physical size known, try to make viewport ~10" wide

    Always caps at 85% of screen and applies safety margin.
    """
    # Calculate viewport pixel size at probe font size
    probe_grid_w = cell_w * REQUIRED_TERMINAL_COLS
    probe_grid_h = cell_h * REQUIRED_TERMINAL_ROWS

    # Primary: ensure grid fits on screen (with margin)
    max_grid_w = screen_w * MAX_SCREEN_FILL
    max_grid_h = screen_h * MAX_SCREEN_FILL

    # Scale factor to fit
    scale_w = max_grid_w / probe_grid_w
    scale_h = max_grid_h / probe_grid_h
    fit_scale = min(scale_w, scale_h)

    # Secondary: if physical size known, calculate scale for ~10" viewport
    # (The viewport is ~96% of total width: 100 content / 104 total)
    physical_scale = None
    if screen_mm_w is not None and screen_mm_w > 0:
        # Calculate what fraction of screen width the viewport should be
        viewport_fraction = TARGET_VIEWPORT_WIDTH_MM / screen_mm_w
        # But cap it at MAX_SCREEN_FILL
        viewport_fraction = min(viewport_fraction, MAX_SCREEN_FILL)

        target_grid_w = screen_w * viewport_fraction
        physical_scale = target_grid_w / probe_grid_w

    # Use the smaller of fit_scale and physical_scale (if available)
    # This ensures we always fit, but also hit physical target if possible
    if physical_scale is not None:
        scale = min(fit_scale, physical_scale)
    else:
        scale = fit_scale

    # Calculate font size
    font_pt = PROBE_FONT_PT * scale

    # Apply safety margin
    font_pt *= SAFETY_MARGIN

    # Clamp to valid range
    font_pt = max(MIN_FONT_PT, min(MAX_FONT_PT, font_pt))

    return font_pt


def get_terminal_size():
    """Get current terminal size in columns and rows.

    Returns (cols, rows) or None if unavailable.
    """
    try:
        import struct
        import fcntl
        import termios

        # Try ioctl first (most reliable)
        with open('/dev/tty', 'r') as tty:
            result = fcntl.ioctl(tty.fileno(), termios.TIOCGWINSZ,
                                 b'\x00\x00\x00\x00\x00\x00\x00\x00')
            rows, cols = struct.unpack('HHHH', result)[:2]
            if cols > 0 and rows > 0:
                return cols, rows
    except Exception:
        pass

    try:
        # Fallback to stty
        result = subprocess.check_output(['stty', 'size'], text=True,
                                         stderr=subprocess.DEVNULL)
        rows, cols = map(int, result.strip().split())
        if cols > 0 and rows > 0:
            return cols, rows
    except Exception:
        pass

    try:
        # Fallback to environment
        cols = int(os.environ.get('COLUMNS', 0))
        rows = int(os.environ.get('LINES', 0))
        if cols > 0 and rows > 0:
            return cols, rows
    except Exception:
        pass

    return None


def validate_terminal_fits():
    """Check if current terminal is large enough.

    Returns True if terminal has enough cols/rows, False otherwise.
    """
    size = get_terminal_size()
    if size is None:
        return True  # Can't check, assume OK

    cols, rows = size
    return cols >= REQUIRED_TERMINAL_COLS and rows >= REQUIRED_TERMINAL_ROWS


def main():
    # Check for validation mode (called from inside terminal to verify fit)
    if len(sys.argv) > 1 and sys.argv[1] == '--validate':
        if validate_terminal_fits():
            print("OK")
            sys.exit(0)
        else:
            size = get_terminal_size()
            if size:
                print(f"FAIL:{size[0]}x{size[1]}")
            else:
                print("FAIL:unknown")
            sys.exit(1)

    # Check for info mode (debugging)
    if len(sys.argv) > 1 and sys.argv[1] == '--info':
        screen_w, screen_h, screen_mm_w, screen_mm_h = wait_for_resolution_stability()
        print(f"Screen: {screen_w}x{screen_h} px")
        if screen_mm_w:
            dpi = screen_w / (screen_mm_w / 25.4)
            print(f"Physical: {screen_mm_w}x{screen_mm_h} mm ({dpi:.0f} DPI)")
        else:
            print("Physical: unknown")
        print(f"Required grid: {REQUIRED_TERMINAL_COLS}x{REQUIRED_TERMINAL_ROWS}")

        cached = read_cache(screen_w, screen_h)
        if cached:
            print(f"Cached cell: {cached[0]}x{cached[1]} px (at {PROBE_FONT_PT}pt)")
        else:
            probed = probe_alacritty()
            if probed:
                print(f"Probed cell: {probed[0]}x{probed[1]} px (at {PROBE_FONT_PT}pt)")
            else:
                print("Probe: failed")
        return

    # Step 1: Wait for resolution to stabilize (handles SPICE race)
    screen_w, screen_h, screen_mm_w, screen_mm_h = wait_for_resolution_stability()

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
            # Step 4: Probe failed, use conservative fallback
            print(f"{FALLBACK_FONT_PT:.1f}")
            return

    # Step 5: Calculate font size
    font_pt = calculate_font_size(screen_w, screen_h, screen_mm_w, cell_w, cell_h)

    print(f"{font_pt:.1f}")


if __name__ == "__main__":
    main()
