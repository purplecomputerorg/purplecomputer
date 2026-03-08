"""Centralized caps mode helpers.

When caps lock is on, ALL user-visible text should be uppercase.

For render() widgets: wrap the return value with caps_text().
For render_line() widgets: wrap the returned Strip with caps_strip().
"""

from textual.strip import Strip
from rich.segment import Segment


def caps_strip(strip: Strip, app) -> Strip:
    """Apply caps mode to all text in a Strip.

    Call this at the end of render_line() methods:
        return caps_strip(Strip(segments), self.app)
    """
    try:
        if app.caps_mode:
            return Strip([
                Segment(s.text.upper(), s.style, s.control)
                for s in strip._segments
            ])
    except Exception:
        pass
    return strip
