"""Everything video, Play room: words, speech, colors, math, patterns.

Mirrors the Play section of the everything page. The scripted
typo-and-fix shows backspace editing mid-line; the scripted misspelling
shows the quiet spelling correction.
"""

from ..script import PressKey, Pause, Comment, SetSpeed, type_and_enter

SEGMENT = [
    SetSpeed(1.0),
    Pause(0.6),

    *type_and_enter("apple", 1.2),
    *type_and_enter("kitties", 1.2),
    *type_and_enter("2 times 3 dinos", 1.4),
    *type_and_enter("4 birds + 3 times 5 owls", 2),
    *type_and_enter("I love icecream", 1.6),
    *type_and_enter("say I love icecream", 2),
    *type_and_enter(":)", 1.2),
    *type_and_enter("zibzab", 1.8),

    *type_and_enter("I used 4 crayons at school!", 2),

    Comment("=== Colors ==="),
    *type_and_enter("red + blue", 1.6),
    *type_and_enter("yellow + 3 periwinkles", 1.6),
    *type_and_enter("say 2 blue + 2 reds", 1.6),
    *type_and_enter("bright pink unicorn and dark blue giraffe", 2.0),

    Comment("=== Real math ==="),
    *type_and_enter("2 + 3", 1.8),
    *type_and_enter("2 + 3 x 4 and 10 over 2.5", 2.0),
    *type_and_enter("552 monkeys", 2.8),
    *type_and_enter("3 timess 2", 1.8),
    PressKey("enter", pause_after=2),
    PressKey("enter", pause_after=2),
    *type_and_enter("8 / 0", 1.8),

    Comment("=== Patterns ==="),
    *type_and_enter("2 4 6 8...", 2.2),
    *type_and_enter("5 apples ...", 2.2),

    Comment("=== Odds and ends ==="),
    *type_and_enter("repeat 3: i love pizza!", 4),
]
