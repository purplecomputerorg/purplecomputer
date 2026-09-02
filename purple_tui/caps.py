"""All-caps render-time chokepoint.

When `all_caps` is on, every Strip the app paints gets its segment
text uppercased. Stored buffers are unchanged — this is purely display.

Implemented as a one-time monkey-patch on Strip.__init__. The patch
runs unconditionally; the per-app flag decides whether to uppercase.
"""

from textual.strip import Strip
from rich.segment import Segment

_enabled = False
_patched = False


def set_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = bool(enabled)


def is_enabled() -> bool:
    return _enabled


def install() -> None:
    """Install the Strip.__init__ patch. Idempotent."""
    global _patched
    if _patched:
        return
    _patched = True

    original_init = Strip.__init__

    def patched_init(self, segments, cell_length=None):
        if _enabled:
            segments = [
                Segment(s.text.upper(), s.style, s.control) for s in segments
            ]
        original_init(self, segments, cell_length)

    Strip.__init__ = patched_init


install()
