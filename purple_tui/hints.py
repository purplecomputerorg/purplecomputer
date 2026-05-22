"""Shared keyboard-hint rendering.

The laptop-style arrow-key cluster is used both in the bottom footer (Art room)
and in the Esc room picker, so it lives here as one source of truth."""

from rich.text import Text

TITLE_MUTED = "#6a5a80"  # soft purple: status text, computer name, hint brackets/labels
TITLE_PRIMARY = "#9b7bc4"  # brighter purple: centered room title and the live arrow glyphs

_ARROW_GLYPHS = "←↑↓→"

# Inverted-T laid out like a laptop's arrow keys: [↑] centered over [↓], with an
# "Arrows move" label to the left of the bottom row. Built so [↑] aligns over
# [↓] regardless of the label width.
_ARROW_KEYS_BOTTOM = "Arrows move  [←][↓][→]"
ARROW_KEYS_HINT = " " * _ARROW_KEYS_BOTTOM.index("[↓]") + "[↑]\n" + _ARROW_KEYS_BOTTOM


def arrow_keys_text() -> Text:
    """The arrow cluster as Rich Text with the four glyphs in bold title-purple
    while the brackets and label stay the widget's muted color."""
    text = Text(ARROW_KEYS_HINT)
    for i, ch in enumerate(ARROW_KEYS_HINT):
        if ch in _ARROW_GLYPHS:
            text.stylize(f"bold {TITLE_PRIMARY}", i, i + 1)
    return text
