"""
Doodle Mode Configuration: shared source of truth for canvas layout and color system.

This module imports pure-data constants from doodle_mode.py and constants.py,
computes derived values (canvas dimensions), and provides functions that generate
English prompt text for the AI training from those constants.

Used by:
- tools/doodle_ai.py (AI training prompts and demo script generation)
"""

from purple_tui.constants import VIEWPORT_WIDTH, VIEWPORT_HEIGHT
from purple_tui.modes.doodle_mode import (
    GUTTER, GRAYSCALE,
    QWERTY_ROW, ASDF_ROW, ZXCV_ROW,
)


# =============================================================================
# CANVAS DIMENSIONS (computed from viewport and layout constants)
# =============================================================================

DOODLE_HEADER_ROWS = 1  # CanvasHeader (docked top, height: 1)

# Canvas = viewport content minus header minus gutter on all sides
# Note: ToolOverlay auto-hides (display:none) before AI training starts
CANVAS_WIDTH = VIEWPORT_WIDTH - 2 * GUTTER
CANVAS_HEIGHT = VIEWPORT_HEIGHT - DOODLE_HEADER_ROWS - 2 * GUTTER


# =============================================================================
# BEHAVIOR CONSTANTS
# =============================================================================

CURSOR_WRAPS = False              # Cursor stops at edges (no wrap-around)
PAINT_ADVANCE_DIRECTION = "right"  # Cursor moves right after stamping a color


# =============================================================================
# PROMPT TEXT GENERATORS
# =============================================================================

def describe_canvas() -> str:
    """Generate English description of canvas size and coordinate system."""
    max_x = CANVAS_WIDTH - 1
    max_y = CANVAS_HEIGHT - 1
    return (
        f"The canvas is **{CANVAS_WIDTH} cells wide × {CANVAS_HEIGHT} cells tall**.\n"
        f"- X coordinates: 0 (left) to {max_x} (right)\n"
        f"- Y coordinates: 0 (top) to {max_y} (bottom)\n"
        f"- Origin (0,0) is TOP-LEFT corner"
    )


def _format_key_list(keys: list[str]) -> str:
    """Format a list of keys as a spaced string for prompts."""
    return " ".join(keys)


def describe_colors() -> str:
    """Generate English description of the color system from key mappings."""
    grayscale_keys = _format_key_list(list(GRAYSCALE.keys()))
    qwerty_keys = _format_key_list(QWERTY_ROW)
    asdf_keys = _format_key_list(ASDF_ROW)
    zxcv_keys = _format_key_list(ZXCV_ROW)

    return (
        "Each keyboard row produces a COLOR FAMILY. "
        "Within each row, keys go from LIGHTER (left) to DARKER (right).\n"
        "**Use this for SHADING:** paint lighter keys (left side of row) for highlights, "
        "darker keys (right side) for shadows.\n"
        "\n"
        f"**GRAYSCALE (Number row: {grayscale_keys}):**\n"
        "- ` (backtick) = pure white (highlight)\n"
        "- 1-3 = light grays\n"
        "- 4-6 = medium grays\n"
        "- 7-9 = dark grays\n"
        "- 0, -, = = near/pure black (shadow)\n"
        "\n"
        f"**RED FAMILY (QWERTY row: {qwerty_keys}):**\n"
        f"- {', '.join(QWERTY_ROW[:2])} = lightest pink (highlight)\n"
        f"- {', '.join(QWERTY_ROW[2:6])} = medium red (primary)\n"
        f"- {', '.join(QWERTY_ROW[6:10])} = dark red\n"
        f"- {', '.join(QWERTY_ROW[10:])} = darkest burgundy (shadow)\n"
        "\n"
        f"**YELLOW FAMILY (ASDF row: {asdf_keys}):**\n"
        f"- {', '.join(ASDF_ROW[:2])} = lightest gold (highlight)\n"
        f"- {', '.join(ASDF_ROW[2:5])} = medium yellow (primary)\n"
        f"- {', '.join(ASDF_ROW[5:9])} = dark gold/brown\n"
        f"- {', '.join(ASDF_ROW[9:])} = darkest brown (shadow)\n"
        "\n"
        f"**BLUE FAMILY (ZXCV row: {zxcv_keys}):**\n"
        f"- {', '.join(ZXCV_ROW[:2])} = lightest periwinkle (highlight)\n"
        f"- {', '.join(ZXCV_ROW[2:5])} = medium blue (primary)\n"
        f"- {', '.join(ZXCV_ROW[5:7])} = dark blue\n"
        f"- {', '.join(ZXCV_ROW[7:])} = darkest navy (shadow)"
    )


def describe_colors_brief() -> str:
    """Generate a brief color system summary (for planning prompts)."""
    grayscale_keys = _format_key_list(list(GRAYSCALE.keys()))
    qwerty_keys = _format_key_list(QWERTY_ROW)
    asdf_keys = _format_key_list(ASDF_ROW)
    zxcv_keys = _format_key_list(ZXCV_ROW)

    return (
        "Each row provides a color family:\n"
        f"- **Number row ({grayscale_keys})**: GRAYSCALE (white to black)\n"
        f"- **QWERTY row ({qwerty_keys})**: RED family (pink to burgundy)\n"
        f"- **ASDF row ({asdf_keys})**: YELLOW family (gold to brown)\n"
        f"- **ZXCV row ({zxcv_keys})**: BLUE family (periwinkle to navy)"
    )


def describe_cursor() -> str:
    """Generate English description of cursor edge behavior and paint advance."""
    wrap_desc = "wraps around" if CURSOR_WRAPS else "stops at edges"
    return (
        f"The cursor {wrap_desc} when it reaches the canvas boundary. "
        f"After stamping a color, the cursor advances {PAINT_ADVANCE_DIRECTION}."
    )
