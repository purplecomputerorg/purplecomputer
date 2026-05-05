"""
Purple Computer - The Calm Computer for Kids

A Textual TUI application providing:
- Ask Mode: Math and emoji REPL
- Music Room: Music and art grid
- Write Mode: Simple text editor

Designed for 4–7 and fun for 2–8+. Safe, calm, distraction-free.
"""

# Suppress ONNX runtime warnings BEFORE any imports that might load it
# This must happen at package init, before piper or any ML libs are imported
import os as _os
_os.environ.setdefault('ORT_LOGGING_LEVEL', '3')  # ERROR level only
_os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')  # Suppress TensorFlow too

__version__ = "2.0.0"


# Tell Rich that Nerd Font PUA glyphs are 2 cells wide. Purple ships
# JetBrainsMono Nerd Font, in which every PUA glyph renders as a wide
# (2-cell) char. Rich's default tables list PUA as 1-cell, breaking any
# width-based layout (border subtitles, truncation). Patching the loaded
# CellTable propagates to cell_len, split_graphemes, and set_cell_size
# consistently. Wrapped in try/except so a future Rich layout change
# can never block app startup over a cosmetic fix.
def _patch_rich_pua_widths():
    try:
        import rich.cells as _rc

        nerd_pua = [
            (0xE000, 0xF8FF, 2),
            (0xF0000, 0xFFFFF, 2),
        ]

        _orig_load = _rc.load_cell_table
        _patched_cache: dict = {}

        def load_cell_table(unicode_version: str = "auto"):
            if unicode_version in _patched_cache:
                return _patched_cache[unicode_version]
            table = _orig_load(unicode_version)
            merged = [w for w in table.widths
                      if not any(start <= w[0] <= end for start, end, _ in nerd_pua)]
            merged.extend(nerd_pua)
            merged.sort()
            new_table = table._replace(widths=tuple(merged))
            _patched_cache[unicode_version] = new_table
            return new_table

        _rc.load_cell_table = load_cell_table
        if hasattr(_rc.get_character_cell_size, "cache_clear"):
            _rc.get_character_cell_size.cache_clear()
        if hasattr(_rc.cached_cell_len, "cache_clear"):
            _rc.cached_cell_len.cache_clear()
    except Exception:
        pass


_patch_rich_pua_widths()
del _patch_rich_pua_widths


