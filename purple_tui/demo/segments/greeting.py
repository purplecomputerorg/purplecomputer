"""Explore mode demo: introduction and feature showcase."""

from ..script import SwitchMode, TypeText, PressKey, Pause, Comment, ZoomIn, ZoomOut, ZoomTarget

# Typing speed (0.05s/char) with brief final_pause, longer pauses on results
_TYPING = dict(delay_per_char=0.05, final_pause=0.1)

SEGMENT = [
    SwitchMode("explore", pause_after=0.0),

    Comment("Start zoomed in on input area (skip blank purple screen)"),
    ZoomIn(region="input", zoom=3.0, duration=0.0),

    Comment("Greeting"),
    TypeText("Hi :)", **_TYPING),
    PressKey("enter", pause_after=0.3),

    Comment("Fly up to see rendered 'Hi :)' result"),
    ZoomTarget(y=0.28, duration=0.4),
    Pause(0.8),

    Comment("Fly back down to input area for next line"),
    ZoomTarget(y=0.75, x=0.3, duration=0.4),
    Pause(0.2),
    TypeText("Welcome to Purple Computer", **_TYPING),
    PressKey("enter", pause_after=0.3),

    Comment("Stay on left side, fly up to see rendered 'Welcome to Purple Computer'"),
    ZoomTarget(y=0.28, x=0.3, duration=0.4),
    Pause(1.0),

    Comment("Zoom out to full view"),
    ZoomOut(duration=0.4),
    Pause(0.3),

    Comment("Tagline"),
    TypeText("Turn any old laptop into a Purple Computer <3", **_TYPING),
    PressKey("enter", pause_after=1.0),

    Comment("Philosophy"),
    TypeText("Less is more. No videos. No internet. ", **_TYPING),
    Pause(1.5),
    TypeText("Explore, play, doodle.", **_TYPING),
    PressKey("enter", pause_after=2.0),

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
