"""Play room demo (updated): short hello, then color, counting, and math+speech.

Kept deliberately light on text: each typed line renders as colored letter
blocks, so the greeting is just "Hi!" and the name. The colorful payload is the
emoji / counting / math, not long sentences.
"""

from ..script import SwitchRoom, TypeText, PressKey, Pause, Comment, ZoomIn, ZoomOut

_TYPING = dict(delay_per_char=0.05, final_pause=0.1)

SEGMENT = [
    SwitchRoom("play", pause_after=0.0),

    Comment("Start zoomed in on the input area"),
    ZoomIn(region="input", zoom=3.0, duration=0.0),

    Comment("Short hello (only text lines in the whole greeting)"),
    TypeText("Hi!", **_TYPING),
    PressKey("enter", pause_after=1.5),
    TypeText("It's Purple Computer!", **_TYPING),
    PressKey("enter", pause_after=2.0),

    ZoomOut(duration=0.4),
    Pause(0.3),

    Comment("Color mixing"),
    TypeText("blue + 2 pinks", **_TYPING),
    PressKey("enter", pause_after=1.5),

    Comment("Counting: number + color + noun draws that many colored emojis"),
    TypeText("2 red dogs", **_TYPING),
    PressKey("enter", pause_after=2.0),

    Comment("Math + counting + speech: trailing ! shows 25 ducks and reads it aloud"),
    TypeText("5 x 5 ducks!", **_TYPING),
    PressKey("enter", pause_after=4.0),

    Pause(0.3),
]
