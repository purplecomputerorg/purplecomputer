"""Play room demo (updated): welcome, color mixing, counting, and speech."""

from ..script import SwitchRoom, TypeText, PressKey, Pause, Comment, ZoomIn, ZoomOut

# Typing speed (0.05s/char) with brief final_pause, longer pauses on results
_TYPING = dict(delay_per_char=0.05, final_pause=0.1)

SEGMENT = [
    SwitchRoom("play", pause_after=0.0),

    Comment("Start zoomed in on input area (skip blank purple screen)"),
    ZoomIn(region="input", zoom=3.0, duration=0.0),

    Comment("Greeting: OpenCV auto-pan detects typing, then result rendering"),
    TypeText("Hi :)", **_TYPING),
    Pause(1.5),
    PressKey("enter", pause_after=2.0),

    Comment("Welcome: OpenCV pans down for typing, up for rendered result"),
    TypeText("Welcome to Purple Computer", **_TYPING),
    Pause(1.5),
    PressKey("enter", pause_after=2.0),

    Comment("Zoom out to full view"),
    ZoomOut(duration=0.4),
    Pause(0.3),

    Comment("Tagline"),
    TypeText("Turn any old laptop into a Purple Computer <3", **_TYPING),
    PressKey("enter", pause_after=2.0),

    Comment("Color mixing"),
    TypeText("blue + 2 pinks", **_TYPING),
    PressKey("enter", pause_after=1.5),

    Comment("Counting: number + color + noun draws that many colored emojis"),
    TypeText("2 red dogs", **_TYPING),
    PressKey("enter", pause_after=2.0),

    Comment("Counting + speech: trailing ! shows 25 ducks and reads it aloud"),
    TypeText("5 x 5 ducks!", **_TYPING),
    PressKey("enter", pause_after=4.0),

    Pause(0.3),
]
