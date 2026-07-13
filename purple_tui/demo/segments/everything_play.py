"""Everything video, Play room: words, speech, colors, math, patterns.

Mirrors the Play section of the everything page. The scripted
typo-and-fix shows backspace editing mid-line; the scripted misspelling
shows the quiet spelling correction.
"""

from ..script import TypeText, PressKey, Pause, Comment, SetSpeed, type_and_enter

SEGMENT = [
    SetSpeed(1.0),
    Pause(0.6),

    Comment("=== Words and emojis ==="),
    *type_and_enter("cat", 1.2),
    *type_and_enter("kitty", 1.2),
    *type_and_enter("3 cats", 1.4),
    *type_and_enter("4 birds + 2 owls", 1.8),
    *type_and_enter("I love cats", 1.6),
    *type_and_enter(":D", 1.2),
    Comment("Unknown words become colored letter blocks"),
    *type_and_enter("zibzab", 1.8),

    Comment("=== Reading out loud (wait for the speech) ==="),
    *type_and_enter("cat!", 2.4),
    Comment("Backspace edits mid-line: type a typo, back up, fix it"),
    TypeText("I have 5 dinso"),
    PressKey("backspace", pause_after=0.15),
    PressKey("backspace", pause_after=0.3),
    TypeText("os!"),
    PressKey("enter", pause_after=3.2),

    Comment("=== Colors ==="),
    *type_and_enter("red + blue", 1.6),
    *type_and_enter("yellow + blue", 1.6),
    *type_and_enter("bright pink unicorn", 2.0),

    Comment("=== Real math ==="),
    *type_and_enter("2 + 3", 1.8),
    *type_and_enter("2 + 3 x 4", 2.0),
    *type_and_enter("552 monkeys", 2.8),
    Comment("Messy typing figures itself out"),
    *type_and_enter("3 timess 2", 1.8),
    *type_and_enter("8 / 0", 1.8),

    Comment("=== Patterns ==="),
    *type_and_enter("2 4 6 8...", 2.2),
    *type_and_enter("5 cats ...", 2.2),

    Comment("=== Odds and ends ==="),
    *type_and_enter("repeat 3 cat", 1.8),
    Comment("Enter on an empty line repeats the last idea; let it land"),
    PressKey("enter", pause_after=3.5),
]
