"""Everything video, Code Space: real code in Art (square, stairs,
forgiving spelling, paint words), then Music code (instrument, tempo,
say letters).

Starts in Art (previous segment ends there). Cursor moves right first so
code drawings land clear of the hand-painted area.
"""

from ..script import (
    PressKey, Comment, SetSpeed, MoveSequence, PlayKeys, type_and_enter,
)

_TAP = dict(hold_duration=0.2)
_HOLD = dict(hold_duration=1.0)

SEGMENT = [
    SetSpeed(1.0),

    MoveSequence(directions=['right'] * 30 + ['up'] * 4, pause_after=0.3),
    Comment("=== Hold Space: the code window opens ==="),
    PressKey("space", pause_after=1.2, **_HOLD),
    *type_and_enter("repeat 4 forward 10 green turn", 2.8),
    *type_and_enter("orange repeat 4 right 4 down 4", 2.8),
    Comment("Forgiving spelling"),
    *type_and_enter("forwrd 10", 2.0),
    *type_and_enter("paint hello", 2.4),
    PressKey("space", pause_after=1.0, **_HOLD),

    Comment("=== Music code: melodies, tempo, instruments ==="),
    PressKey("escape", pause_after=1.4, **_TAP),
    PressKey("2", pause_after=1.0),
    PressKey("space", pause_after=1.2, **_HOLD),
    *type_and_enter("choose ukulele", 1.6),
    *type_and_enter("fast abcdefg slow asdf", 4.5),
    Comment("Say Letters mode, straight from code"),
    *type_and_enter("letters on", 1.2),
    PressKey("space", pause_after=0.8, **_HOLD),
    Comment("Now every key speaks its letter"),
    PlayKeys(sequence=['c', 'a', 't'], seconds_between=1.1, pause_after=1.2),
]
