"""Short explore mode greeting to open the demo."""

from ..script import SwitchMode, TypeText, PressKey, Pause, Comment

SEGMENT = [
    SwitchMode("explore"),
    Comment("Say hello"),
    TypeText("hello!"),
    PressKey("enter", pause_after=1.0),

    Comment("Show color mixing"),
    TypeText("red + blue"),
    PressKey("enter", pause_after=1.5),

    Comment("Show emoji math"),
    TypeText("3 cats"),
    PressKey("enter", pause_after=1.5),

    Pause(0.5),
]
