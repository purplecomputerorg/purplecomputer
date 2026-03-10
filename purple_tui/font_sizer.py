"""
Auto-size Alacritty font to fit the required terminal grid.

Instead of predicting font size from DPI/cell ratios (brittle),
this measures the actual terminal dimensions and adjusts empirically.

How it works:
1. Check os.get_terminal_size()
2. If rows/cols don't meet the minimum, compute correction
3. Set new font size via `alacritty msg config` (instant IPC)
4. Repeat until correct (usually 1-2 iterations)

The math: cell count is inversely proportional to font size, so
    new_font = current_font * (actual_rows / required_rows)
"""

import math
import os
import re
import subprocess
import time

from .constants import REQUIRED_TERMINAL_COLS, REQUIRED_TERMINAL_ROWS, CODE_FONT_RATIO

# Alacritty config path: set by xinitrc (writable copy), or fall back to /etc
ALACRITTY_CONFIG_ENV = "PURPLE_ALACRITTY_CONFIG"
ALACRITTY_CONFIG_DEFAULT = "/etc/purple/alacritty.toml"

# How many attempts before giving up
MAX_ATTEMPTS = 5

# Font size limits
MIN_FONT = 8.0
MAX_FONT = 48.0

# Brief pause after setting font size for terminal to resize
SETTLE_DELAY = 0.3


def _get_config_path() -> str | None:
    """Get the Alacritty config file path."""
    path = os.environ.get(ALACRITTY_CONFIG_ENV, ALACRITTY_CONFIG_DEFAULT)
    if os.path.isfile(path):
        return path
    return None


def _read_font_size(config_path: str) -> float | None:
    """Read the current font size from alacritty.toml."""
    try:
        with open(config_path) as f:
            content = f.read()
        # Match: size = 22.0 (under [font] section)
        m = re.search(r'^size\s*=\s*([\d.]+)', content, re.MULTILINE)
        if m:
            return float(m.group(1))
    except (OSError, ValueError):
        pass
    return None


def _set_font_size(new_size: float, config_path: str) -> bool:
    """Set font size via alacritty msg (IPC), with file fallback.

    Returns True on success.
    """
    # Try IPC first (instant, no file-watch delay)
    try:
        subprocess.run(
            ["alacritty", "msg", "config", f"font.size={new_size:.1f}"],
            timeout=2,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Fallback: write to config file (Alacritty live-reloads)
    try:
        with open(config_path) as f:
            content = f.read()
        new_content = re.sub(
            r'^(size\s*=\s*)[\d.]+',
            f'\\g<1>{new_size:.1f}',
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if new_content == content:
            return False
        with open(config_path, 'w') as f:
            f.write(new_content)
        return True
    except OSError:
        return False


def _floor_half(value: float) -> float:
    """Floor to nearest 0.5 for predictable rounding."""
    return math.floor(value * 2) / 2


def ensure_terminal_size() -> None:
    """Adjust Alacritty font size until the terminal has enough rows and columns.

    Call this before starting the Textual app. Prints "Loading..." while adjusting.
    Does nothing if the terminal is already the right size or config is unavailable.
    """
    cols, rows = os.get_terminal_size()
    if cols >= REQUIRED_TERMINAL_COLS and rows >= REQUIRED_TERMINAL_ROWS:
        return  # Already correct

    config_path = _get_config_path()
    if not config_path:
        return  # No config to modify, hope for the best

    current_font = _read_font_size(config_path)
    if not current_font:
        return

    # Show loading message (works at any font size)
    print("\033[2J\033[H", end="")  # Clear screen, cursor to top-left
    print("\n\n    Loading...", end="", flush=True)

    for attempt in range(MAX_ATTEMPTS):
        cols, rows = os.get_terminal_size()
        if cols >= REQUIRED_TERMINAL_COLS and rows >= REQUIRED_TERMINAL_ROWS:
            break

        # Calculate correction: font is inversely proportional to cell count
        # Use the more restrictive dimension
        font_for_cols = current_font * cols / REQUIRED_TERMINAL_COLS
        font_for_rows = current_font * rows / REQUIRED_TERMINAL_ROWS
        new_font = _floor_half(min(font_for_cols, font_for_rows))
        new_font = max(MIN_FONT, min(MAX_FONT, new_font))

        if new_font == current_font:
            break  # Can't adjust further

        if not _set_font_size(new_font, config_path):
            break  # Can't set font

        current_font = new_font

        # Wait for terminal to resize
        time.sleep(SETTLE_DELAY)

    # Clear loading message before Textual takes over
    print("\033[2J\033[H", end="", flush=True)


# =============================================================================
# CODE SPLIT: Font toggle for inline code panel
# =============================================================================

# Module-level state for font toggle (one Alacritty instance per app)
_original_font_size: float | None = None


def get_original_font_size() -> float | None:
    """Read and cache the current (normal mode) font size."""
    global _original_font_size
    if _original_font_size is not None:
        return _original_font_size
    config_path = _get_config_path()
    if config_path:
        _original_font_size = _read_font_size(config_path)
    return _original_font_size


def set_code_split_font() -> bool:
    """Shrink font to CODE_FONT_RATIO for split-screen code panel.

    Returns True if font was changed successfully.
    """
    original = get_original_font_size()
    if original is None:
        return False
    config_path = _get_config_path()
    if not config_path:
        return False
    new_size = _floor_half(original * CODE_FONT_RATIO)
    new_size = max(MIN_FONT, min(MAX_FONT, new_size))
    return _set_font_size(new_size, config_path)


def restore_normal_font() -> bool:
    """Restore font to the original (normal mode) size.

    Returns True if font was changed successfully.
    """
    original = get_original_font_size()
    if original is None:
        return False
    config_path = _get_config_path()
    if not config_path:
        return False
    return _set_font_size(original, config_path)
