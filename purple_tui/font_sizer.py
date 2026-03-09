"""
Auto-size Alacritty font to fit the required terminal grid.

Instead of predicting font size from DPI/cell ratios (brittle),
this measures the actual terminal dimensions and adjusts empirically.

How it works:
1. Check os.get_terminal_size()
2. If rows/cols don't meet the minimum, compute correction
3. Write new font size to the Alacritty config file
4. Alacritty auto-reloads, terminal resizes
5. Repeat until correct (usually 1 iteration)

The math: cell count is inversely proportional to font size, so
    new_font = current_font * (actual_rows / required_rows)
"""

import math
import os
import re
import sys
import time

from .constants import REQUIRED_TERMINAL_COLS, REQUIRED_TERMINAL_ROWS

# Alacritty config path: set by xinitrc (writable copy), or fall back to /etc
ALACRITTY_CONFIG_ENV = "PURPLE_ALACRITTY_CONFIG"
ALACRITTY_CONFIG_DEFAULT = "/etc/purple/alacritty.toml"

# How many attempts before giving up (each takes ~0.5s)
MAX_ATTEMPTS = 5

# Font size limits
MIN_FONT = 8.0
MAX_FONT = 48.0


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


def _write_font_size(config_path: str, new_size: float) -> bool:
    """Write a new font size to alacritty.toml. Returns True on success."""
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

        if not _write_font_size(config_path, new_font):
            break  # Can't write config

        current_font = new_font

        # Wait for Alacritty to detect the change and resize
        time.sleep(0.6)

    # Clear loading message before Textual takes over
    print("\033[2J\033[H", end="", flush=True)
