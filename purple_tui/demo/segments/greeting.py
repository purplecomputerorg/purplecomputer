"""Explore mode demo: introduction and feature showcase."""

from ..script import SwitchMode, TypeText, PressKey, Pause, Comment, ZoomIn, ZoomOut, ZoomTarget

# Typing speed (0.05s/char) with brief final_pause, longer pauses on results
_TYPING = dict(delay_per_char=0.05, final_pause=0.1)

SEGMENT = [
    SwitchMode("explore", pause_after=0.3),

    Comment("Greeting"),
    TypeText("Hi :)", **_TYPING),
    PressKey("enter", pause_after=0.6),

    Comment("Zoom in to input area so viewer sees typing and results"),
    ZoomIn(region="input", zoom=3.0, duration=0.2),
    Pause(0.2),
    TypeText("Welcome to Purple Computer", **_TYPING),
    PressKey("enter", pause_after=0.8),

    Comment("Tagline: pan up slightly to keep results in view"),
    Pause(0.2),
    ZoomTarget(y=0.70, duration=0.3),
    Pause(0.3),
    TypeText("Turn any old laptop into a Purple Computer <3", **_TYPING),
    PressKey("enter", pause_after=1.0),

    Comment("Philosophy: pan up a bit more as lines accumulate"),
    Pause(0.2),
    ZoomTarget(y=0.65, duration=0.3),
    Pause(0.3),
    TypeText("Less is more. No videos. No internet. ", **_TYPING),
    Pause(1.5),
    TypeText("Explore, play, doodle.", **_TYPING),
    PressKey("enter", pause_after=2.0),
    ZoomOut(duration=0.2),

    Comment("Math with emojis"),
    TypeText("This is Explore mode. ", **_TYPING),
    Pause(1.5),
    TypeText("2 rabbits ate 3 + 7 carrots", **_TYPING),
    PressKey("enter", pause_after=2.0),

    Comment("Color mixing"),
    TypeText("red + blue", **_TYPING),
    PressKey("enter", pause_after=1.0),

    Comment("More colors"),
    TypeText("3 periwinkles + violet", **_TYPING),
    PressKey("enter", pause_after=1.0),

    Comment("Math with speech (! triggers TTS)"),
    TypeText("10 x 10 dinosaurs!", **_TYPING),
    PressKey("enter", pause_after=4.0),

    Pause(0.3),
]
