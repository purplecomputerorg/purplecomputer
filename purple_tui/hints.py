"""Shared keyboard-hint rendering.

The laptop-style arrow-key cluster appears in the bottom footer (one variant
per room) and in the Esc room picker, so it lives here as one source of
truth."""

from rich.text import Text

TITLE_MUTED = "#6a5a80"  # soft purple: status text, computer name, hint brackets/labels
TITLE_PRIMARY = "#9b7bc4"  # brighter purple: centered room title and the live arrow glyphs

_ARROW_GLYPHS = "←↑↓→"

# Art: inverted-T laid out like a laptop's arrow keys, label on the bottom row
# next to [↓] with [↑] floating directly above [↓].
_ART_BOTTOM = "Arrows move  [←][↓][→]"
ART_ARROW_HINT = " " * _ART_BOTTOM.index("[↓]") + "[↑]\n" + _ART_BOTTOM

# Play: just [↑] / [↓] stacked, label next to the bottom key.
_PLAY_BOTTOM = "Arrows scroll  [↓]"
PLAY_ARROW_HINT = " " * _PLAY_BOTTOM.index("[↓]") + "[↑]\n" + _PLAY_BOTTOM

# Music: single horizontal row. Padded with a blank top line so every room's
# footer hint occupies two lines and the footer height doesn't jump on switch.
MUSIC_ARROW_HINT = "\nArrows change key  [←][→]"


def _stylized(text: str) -> Text:
    out = Text(text)
    for i, ch in enumerate(text):
        if ch in _ARROW_GLYPHS:
            out.stylize(f"bold {TITLE_PRIMARY}", i, i + 1)
    return out


def arrow_keys_text() -> Text:
    """Art-style inverted-T cluster, also used in the Esc room picker."""
    return _stylized(ART_ARROW_HINT)


_ROOM_HINTS = {
    "ART": ART_ARROW_HINT,
    "PLAY": PLAY_ARROW_HINT,
    "MUSIC": MUSIC_ARROW_HINT,
}


def room_arrow_hint(room) -> Text | str:
    """The footer arrow hint for the given Room (matched by .name)."""
    hint = _ROOM_HINTS.get(getattr(room, "name", ""))
    return _stylized(hint) if hint else ""
