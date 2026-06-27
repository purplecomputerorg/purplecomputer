"""Standalone ad beat: write "This is Purple Computer. Available now!" centered
in the Art room. Two lines, absolutely positioned (clamp to the top-left corner,
then offset) so they land centered no matter where the cursor started. A long
lead-in pause lets the recording warm up before any typing begins.
"""

from ..script import (
    SwitchRoom, Comment, PressKey, TypeText, MoveSequence, ClearArt,
    Pause, ZoomIn, ZoomOut,
)

_TYPING = dict(delay_per_char=0.06, final_pause=0.2)

# Canvas is ~132x25 inside the viewport (see constants.py). Center each line.
_LINE1 = "This is Purple Computer."
_LINE2 = "Available now!"
_ROW1 = 11
_LEFT1 = (132 - len(_LINE1)) // 2
_LEFT2 = (132 - len(_LINE2)) // 2

# Over-long left+up runs no-op at the edges, parking the cursor at (0,0).
_CLAMP_TO_CORNER = ['left'] * 150 + ['up'] * 40

SEGMENT = [
    Comment("=== AVAILABLE NOW (Art room) ==="),
    SwitchRoom("art"),  # starts in paint mode
    Pause(0.3),
    ClearArt(),

    Comment("Tab into write mode so keys are letters, not paint colors"),
    PressKey("tab", pause_after=0.1),

    Comment("Long lead-in so the room is fully painted and the recording is "
            "rolling before any text appears. Trim this in the editor."),
    Pause(3.0),

    Comment("Line 1, centered: clamp to corner, then offset right/down"),
    MoveSequence(directions=_CLAMP_TO_CORNER, delay_per_step=0.004),
    MoveSequence(directions=['right'] * _LEFT1 + ['down'] * _ROW1,
                 delay_per_step=0.004),
    ZoomIn(region="art-center", zoom=2.0, duration=0.3),
    TypeText(_LINE1, **_TYPING),

    Comment("Line 2, centered one row below"),
    MoveSequence(directions=_CLAMP_TO_CORNER, delay_per_step=0.004),
    MoveSequence(directions=['right'] * _LEFT2 + ['down'] * (_ROW1 + 1),
                 delay_per_step=0.004),
    TypeText(_LINE2, **_TYPING),

    Pause(2.5),
    ZoomOut(duration=0.4),
    PressKey("tab", pause_after=0.1),  # back to paint mode
]

SPEED_MULTIPLIER = 1.0
