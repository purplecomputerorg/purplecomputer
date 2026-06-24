"""Short ad screen footage: Play beats, then an Art paint + code beat.

Pure screen content for the short ad. No on-screen captions: text overlays
go on in the editor. Results stack rather than clearing (an Escape keypress,
Play's only "clear", cancels the running demo). Timings are kept snappy so
the whole thing stays short.
"""

from ..script import (
    SwitchRoom, TypeText, PressKey, Pause, ClearArt, MoveSequence,
    Comment, ZoomIn, ZoomOut,
)

_TYPING = dict(delay_per_char=0.045, final_pause=0.15)

_PLAY = [
    Comment("=== PLAY ==="),
    SwitchRoom("play", pause_after=0.3),
    ZoomIn(region="input", zoom=2.5, duration=0.2),

    TypeText("hello :)", **_TYPING),
    PressKey("enter", pause_after=0.9),

    TypeText("red + blue", **_TYPING),
    PressKey("enter", pause_after=0.9),

    Comment("'say' speaks the words aloud (needs a pre-generated clip)"),
    TypeText("say purple computer", **_TYPING),
    PressKey("enter", pause_after=1.6),

    TypeText("5 x 5 dinos", **_TYPING),
    PressKey("enter", pause_after=1.1),

    Comment("Big number 98321 renders as the place-value abacus"),
    ZoomOut(duration=0.3),
    TypeText("98321 butterflies", **_TYPING),
    PressKey("enter", pause_after=1.6),

    Comment("Trailing ... continues the counting sequence"),
    TypeText("3 sun 6 sun 9 sun...", **_TYPING),
    PressKey("enter", pause_after=1.6),
]

_ART = [
    Comment("=== ART: paint a row, then overwrite it to mix the colors ==="),
    SwitchRoom("art", pause_after=0.3),
    ClearArt(),
    MoveSequence(directions=['down'] * 4 + ['right'] * 20, delay_per_step=0.02),

    Comment("Both rows are 9 chars; paint zxc... over qwe... in place to blend"),
    TypeText("qwertyuio", **_TYPING),
    MoveSequence(directions=['left'] * 9, delay_per_step=0.02),
    TypeText("zxcvbnm,.", **_TYPING),
    Pause(0.9),

    Comment("=== ART: draw with code below the rows ==="),
    MoveSequence(directions=['down'] * 2, delay_per_step=0.04),
    PressKey("space", hold_duration=1.0, pause_after=0.5),

    TypeText("blue repeat 4 forward 10 turn", delay_per_char=0.04, final_pause=0.15),
    PressKey("enter", pause_after=1.2),
    TypeText("red right 100", delay_per_char=0.04, final_pause=0.15),
    PressKey("enter", pause_after=1.8),
    Pause(0.4),
]

SEGMENT = _PLAY + _ART

SPEED_MULTIPLIER = 1.0
