"""Everything video, Music Code Space: instrument, melody, tempo.

Runs right after the Music segment, already in the Music room. Hold
gestures depend on the 0.8s threshold, so this runs at 1.0x.
"""

from ..script import PressKey, Comment, SetSpeed, type_and_enter

_HOLD = dict(hold_duration=1.0)

SEGMENT = [
    SetSpeed(1.0),

    Comment("=== Hold Space: the code window opens ==="),
    PressKey("space", pause_after=1.2, **_HOLD),
    *type_and_enter("choose ukulele", 1.6),
    *type_and_enter("fast abcdefg slow asdf", 4.5),
    PressKey("space", pause_after=1.0, **_HOLD),
]
