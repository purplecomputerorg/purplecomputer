"""Standalone ad beat: write "This is Purple Computer. Available now!" centered
in the Art room. ClearArt parks the cursor at (0,0), so line 1 offsets straight
to its centered spot and line 2 makes a short relative hop from the end of line
1: no visible trip back to the corner. A long lead-in pause lets the recording
warm up before any typing begins.
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

# After line 1 the cursor sits at its end; hop down one row and left to line 2.
_HOP_LEFT = (_LEFT1 + len(_LINE1)) - _LEFT2

SEGMENT = [
    Comment("=== AVAILABLE NOW (Art room) ==="),
    SwitchRoom("art"),  # starts in paint mode
    Pause(0.3),
    ClearArt(),  # also parks the cursor at (0,0)

    Comment("Tab into write mode so keys are letters, not paint colors"),
    PressKey("tab", pause_after=0.1),

    Comment("Long lead-in so the room is fully painted and the recording is "
            "rolling before any text appears. Trim this in the editor."),
    Pause(3.0),

    Comment("Line 1, centered: offset right/down straight from (0,0)"),
    MoveSequence(directions=['right'] * _LEFT1 + ['down'] * _ROW1,
                 delay_per_step=0.004),
    ZoomIn(region="art-center", zoom=2.0, duration=0.3),
    TypeText(_LINE1, **_TYPING),

    Comment("Line 2, centered one row below: short relative hop from line 1's end"),
    MoveSequence(directions=['down'] + ['left'] * _HOP_LEFT,
                 delay_per_step=0.004),
    TypeText(_LINE2, **_TYPING),

    Pause(2.5),
    ZoomOut(duration=0.4),
    PressKey("tab", pause_after=0.1),  # back to paint mode
]

SPEED_MULTIPLIER = 1.0
