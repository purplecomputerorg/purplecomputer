"""Shared scrolling utilities for all modes."""

# Lines to scroll per up/down arrow press
SCROLL_LINES = 5


def scroll_widget(widget, direction: int) -> None:
    """Scroll a widget up (direction=-1) or down (direction=1) by SCROLL_LINES.

    Works with any widget that has scroll_relative (ScrollableContainer, TextArea, etc.)
    """
    widget.scroll_relative(y=direction * SCROLL_LINES, animate=False)
