"""Everything video, Art Code Space: square, stairs, forgiving spelling,
paint words.

Runs right after the Art segment, already in the Art room. The cursor is
clamped to the corner then moved to mid-canvas so the code drawings land
center screen, to the right of the painted scene.
"""

from ..script import PressKey, Comment, SetSpeed, MoveSequence, type_and_enter

_HOLD = dict(hold_duration=1.0)
_CLAMP = ['left'] * 150 + ['up'] * 40

SEGMENT = [
    SetSpeed(1.0),

    MoveSequence(directions=_CLAMP, delay_per_step=0.003, pause_after=0.1),
    MoveSequence(directions=['right'] * 58 + ['down'] * 6, delay_per_step=0.02, pause_after=0.3),
    Comment("=== Hold Space: code steers the paintbrush ==="),
    PressKey("space", pause_after=1.2, **_HOLD),
    *type_and_enter("repeat 4 forward 10 green turn", 2.8),
    *type_and_enter("orange repeat 4 right 4 down 4", 2.8),
    Comment("Forgiving spelling"),
    *type_and_enter("forwrd 10", 2.0),
    *type_and_enter("paint hello", 2.4),
    PressKey("space", pause_after=1.0, **_HOLD),
]
