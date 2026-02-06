"""Explore mode demo: introduction and feature showcase."""

from ..script import SwitchMode, TypeText, PressKey, Pause, Comment

# Fast typing (0.03s/char) with brief final_pause, longer pauses on results
_FAST = dict(delay_per_char=0.03, final_pause=0.1)

SEGMENT = [
    SwitchMode("explore", pause_after=0.3),

    Comment("Greeting"),
    TypeText("Hi :)", **_FAST),
    PressKey("enter", pause_after=0.6),

    Comment("Welcome"),
    TypeText("Welcome to Purple Computer", **_FAST),
    PressKey("enter", pause_after=0.8),

    Comment("Tagline"),
    TypeText("Turn any old laptop into a Purple Computer <3", **_FAST),
    PressKey("enter", pause_after=1.0),

    Comment("Philosophy"),
    TypeText("Less is more. No videos. No internet. Explore, play, doodle.", **_FAST),
    PressKey("enter", pause_after=1.3),

    Comment("Math with emojis"),
    TypeText("2 rabbits ate 3 + 7 carrots", **_FAST),
    PressKey("enter", pause_after=1.0),

    Comment("Color mixing"),
    TypeText("red + blue", **_FAST),
    PressKey("enter", pause_after=1.0),

    Comment("More colors"),
    TypeText("3 periwinkles + violet", **_FAST),
    PressKey("enter", pause_after=1.0),

    Comment("Math with speech (! triggers TTS)"),
    TypeText("10 x 10 dinosaurs!", **_FAST),
    PressKey("enter", pause_after=4.0),

    Pause(0.3),
]
