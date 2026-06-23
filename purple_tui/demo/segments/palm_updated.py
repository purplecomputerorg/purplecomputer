"""Art room demo (updated): intro + a centered palm tree + draw-with-code beat.

The palm is generated from a bitmap (see palm_art.py) and positioned absolutely,
so it lands centered on the canvas with no clipping. Cursor moves are made
absolute by first clamping to the top-left corner (over-long left+up runs that
no-op at the edge), then offsetting.
"""

from ..script import (
    SwitchRoom, SetSpeed, Comment, PressKey, TypeText, MoveSequence,
    ClearArt, Pause, ZoomIn, ZoomOut,
)
from .palm_art import build_palm, centered_margins

_TYPING = dict(delay_per_char=0.05, final_pause=0.1)

# Canvas is a fixed ~132x25 inside the 134x29 viewport (see constants.py).
_CANVAS_W = 132
_CANVAS_H = 25
_PALM_LEFT, _PALM_TOP = centered_margins(_CANVAS_W, _CANVAS_H)

_FAST_DRAW = 200.0
_CLAMP_TO_CORNER = ['left'] * 150 + ['up'] * 40

_INTRO = [
    Comment("=== ART ROOM INTRO ==="),
    SwitchRoom("art"),  # starts in paint mode
    Pause(0.3),
    SetSpeed(1.0),

    Comment("Tab into write mode for the intro text (default is paint mode)"),
    PressKey("tab", pause_after=0.1),
    MoveSequence(directions=['right'] * 55 + ['down'] * 9, delay_per_step=0.008),
    ZoomIn(region="art-text-right", zoom=3.0, duration=0.2),
    TypeText("This is the Art room.", **_TYPING),
    PressKey("enter", pause_after=0.1),
    MoveSequence(directions=['left'] * 21, delay_per_step=0.008),
    TypeText("Draw with colors or code!", **_TYPING),
    ZoomOut(duration=0.2),
    Pause(1.8),

    Comment("Back to paint mode, clear, then draw the palm tree on a fresh canvas"),
    PressKey("tab", pause_after=0.1),
    ClearArt(),
]

_DRAW_PALM = [
    Comment("=== PALM TREE (generated from palm_art bitmap, centered) ==="),
    SetSpeed(_FAST_DRAW),
    *build_palm(_PALM_LEFT, _PALM_TOP),
]

_CODE_BEAT = [
    Comment("=== DRAW WITH CODE (Art code panel) ==="),
    Pause(1.8),  # admire the finished palm tree
    SetSpeed(1.0),
    ClearArt(),

    Comment("Hold Space to open the code panel (REPL captures all keys while open)"),
    PressKey("space", hold_duration=1.0, pause_after=0.7),

    Comment("Pick a color, then draw a square (spin = a quarter turn)"),
    TypeText("blue", delay_per_char=0.08, final_pause=0.2),
    PressKey("enter", pause_after=0.6),
    TypeText("repeat 4 forward 8, spin", delay_per_char=0.06, final_pause=0.2),
    PressKey("enter", pause_after=2.4),

    Comment("Hold Space to close the code panel"),
    PressKey("space", hold_duration=1.0, pause_after=0.5),
    ClearArt(),  # also resets the canvas to paint mode
]

_BRIDGE = [
    Comment("=== HAND-OFF TO MUSIC ROOM ==="),
    SetSpeed(1.0),
    PressKey("tab", pause_after=0.1),  # paint -> write for the text
    Comment("Absolute-position each line (clamp to corner) so they don't collide"),
    MoveSequence(directions=_CLAMP_TO_CORNER, delay_per_step=0.004),
    MoveSequence(directions=['right'] * 4 + ['down'] * 20, delay_per_step=0.004),
    ZoomIn(region="art-text-left", zoom=3.0, duration=0.2),
    TypeText("Now let's go to the Music room", **_TYPING),
    MoveSequence(directions=_CLAMP_TO_CORNER, delay_per_step=0.004),
    MoveSequence(directions=['right'] * 4 + ['down'] * 21, delay_per_step=0.004),
    TypeText("Play with music and color", **_TYPING),
    Pause(2.5),

    Comment("Instant zoom out and clear so the next segment starts clean"),
    ZoomOut(duration=0.0),
    ClearArt(),
]

SEGMENT = _INTRO + _DRAW_PALM + _CODE_BEAT + _BRIDGE

SPEED_MULTIPLIER = _FAST_DRAW
