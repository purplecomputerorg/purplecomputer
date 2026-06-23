"""Art room demo (updated): intro + faster palm tree + draw-with-code beat.

Reuses the palm tree keystrokes from palm_tree.py (no duplication): the segment
is sliced into intro / drawing / music-bridge by its marker actions, the drawing
is replayed at a faster speed, and a short "draw a shape with code" beat is
inserted on a fresh canvas before the hand-off to the Music room.
"""

from .palm_tree import SEGMENT as _PALM
from ..script import (
    SetSpeed, Comment, PressKey, TypeText, MoveSequence, ClearArt, Pause,
)

# Original palm_tree layout: intro... , SetSpeed(83.365), drawing... , bridge...
_draw_speed_idx = next(
    i for i, a in enumerate(_PALM)
    if isinstance(a, SetSpeed) and a.multiplier > 50
)
_bridge_idx = next(
    i for i, a in enumerate(_PALM)
    if isinstance(a, Comment) and "MUSIC ROOM INTRO TEXT" in a.text
)

_INTRO = _PALM[:_draw_speed_idx]
_DRAWING = _PALM[_draw_speed_idx + 1:_bridge_idx]
_BRIDGE = _PALM[_bridge_idx:]

# Faster than the original 83.365 so the palm tree takes noticeably less time.
_FAST_DRAW = 150.0

_CODE_BEAT = [
    Comment("=== DRAW WITH CODE (Art code panel) ==="),
    Pause(1.8),  # admire the finished palm tree
    SetSpeed(1.0),
    ClearArt(),

    Comment("Move into the canvas, then hold Space to open the code panel"),
    MoveSequence(directions=['right'] * 40 + ['down'] * 12, delay_per_step=0.01),
    PressKey("space", hold_duration=1.0, pause_after=0.7),

    Comment("Pick a color, then draw a square (spin = a quarter turn)"),
    TypeText("blue", delay_per_char=0.08, final_pause=0.2),
    PressKey("enter", pause_after=0.6),
    TypeText("repeat 4 forward 8, spin", delay_per_char=0.06, final_pause=0.2),
    PressKey("enter", pause_after=2.4),

    Comment("Hold Space to close the code panel"),
    PressKey("space", hold_duration=1.0, pause_after=0.5),
    ClearArt(),
]

SEGMENT = _INTRO + [SetSpeed(_FAST_DRAW)] + _DRAWING + _CODE_BEAT + _BRIDGE

SPEED_MULTIPLIER = _FAST_DRAW
