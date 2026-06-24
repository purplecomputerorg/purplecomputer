"""Short ad screen footage: Play beats, then an Art paint + code beat.

Pure screen content for the short ad. No on-screen captions: text overlays
go on in the editor. Results stack rather than clearing (an Escape keypress,
Play's only "clear", cancels the running demo).
"""

from ..script import (
    SwitchRoom, TypeText, PressKey, Pause, ClearArt, MoveSequence,
    Comment, ZoomIn, ZoomOut,
)

_TYPING = dict(delay_per_char=0.07, final_pause=0.2)

_PLAY = [
    Comment("=== PLAY ==="),
    SwitchRoom("play", pause_after=0.3),
    ZoomIn(region="input", zoom=2.5, duration=0.2),

    TypeText("hello :)", **_TYPING),
    PressKey("enter", pause_after=1.8),

    TypeText("red + blue", **_TYPING),
    PressKey("enter", pause_after=1.8),

    Comment("'say' speaks the words aloud (needs a pre-generated clip)"),
    TypeText("say purple computer", **_TYPING),
    PressKey("enter", pause_after=2.6),

    Comment("Big number 9321 renders as the place-value abacus"),
    ZoomOut(duration=0.3),
    TypeText("33 dinos and 9321 butterflies", **_TYPING),
    PressKey("enter", pause_after=3.0),

    Comment("Trailing ... continues the counting sequence"),
    TypeText("3 dino 6 dino 9 dino...", **_TYPING),
    PressKey("enter", pause_after=2.6),
    Pause(0.4),
]

_ART = [
    Comment("=== ART: paint a row, then mix colors over it ==="),
    SwitchRoom("art", pause_after=0.4),
    ClearArt(),

    TypeText("asdfghjkl", **_TYPING),
    Comment("Back to the 'a' position, then paint over it so the colors mix"),
    MoveSequence(directions=['left'] * 9, delay_per_step=0.04),
    TypeText("qwertyuiop", **_TYPING),
    Pause(1.8),

    Comment("=== ART: draw with code ==="),
    PressKey("space", hold_duration=1.0, pause_after=0.7),

    TypeText("blue repeat 4 forward 10 turn", delay_per_char=0.06, final_pause=0.2),
    PressKey("enter", pause_after=2.0),
    TypeText("red right 100", delay_per_char=0.06, final_pause=0.2),
    PressKey("enter", pause_after=2.8),
    Pause(1.0),
]

SEGMENT = _PLAY + _ART

SPEED_MULTIPLIER = 1.0
