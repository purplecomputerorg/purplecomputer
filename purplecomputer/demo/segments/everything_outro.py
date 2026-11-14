"""Everything video, outro: back to Play, goodbye! speaks, hold the frame."""

from ..script import SwitchRoom, Pause, Comment, SetSpeed, type_and_enter

SEGMENT = [
    SetSpeed(1.0),

    SwitchRoom("play"),
    Pause(0.8),
    Comment("Speech plays; hold the final frame for the tail line"),
    *type_and_enter("goodbye!", 4.0),
    Pause(2.0),
]
