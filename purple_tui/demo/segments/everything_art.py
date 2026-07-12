"""Everything video, Art room: the paintbox rows, mixing, lines and
diagonals, held-letter painting, writing over paint, erasing, persistence.

Positions are approximate; tune against a test render. Typing in paint mode
stamps a color and auto-advances, so TypeText paints whole rows.
"""

from ..script import (
    TypeText, PressKey, Pause, Comment, SetSpeed, DrawPath, MoveSequence, ClearArt,
)

_TAP = dict(hold_duration=0.2)

def _newline(cols_back: int) -> MoveSequence:
    return MoveSequence(directions=['down'] + ['left'] * cols_back, pause_after=0.3)

SEGMENT = [
    SetSpeed(1.0),

    Comment("Escape tap opens the picker; 3 jumps to Art"),
    PressKey("escape", pause_after=1.4, **_TAP),
    PressKey("3", pause_after=1.0),
    ClearArt(),

    Comment("=== Every key is a color: paint each keyboard row ==="),
    TypeText("1234567890", delay_per_char=0.14, final_pause=0.5),
    _newline(10),
    TypeText("qwertyuiop", delay_per_char=0.14, final_pause=0.5),
    _newline(10),
    TypeText("asdfghjkl", delay_per_char=0.14, final_pause=0.5),
    _newline(9),
    TypeText("zxcvbnm", delay_per_char=0.14, final_pause=0.8),

    Comment("=== Mixing: blue over yellow makes green ==="),
    MoveSequence(directions=['down', 'down'] + ['left'] * 8, pause_after=0.3),
    DrawPath(directions=['right'] * 4, color_key='g', delay_per_step=0.18, pause_after=0.6),
    MoveSequence(directions=['left'] * 5, pause_after=0.3),
    DrawPath(directions=['right'] * 4, color_key='c', delay_per_step=0.18, pause_after=1.0),

    Comment("=== Hold Space and steer; two arrows makes diagonals ==="),
    MoveSequence(directions=['right'] * 3, pause_after=0.2),
    DrawPath(directions=['right'] * 4, color_key='e', delay_per_step=0.18, pause_after=0.4),
    DrawPath(directions=['right+down'] * 3, color_key='e', delay_per_step=0.25, pause_after=0.8),

    Comment("=== Hold a letter and press arrows to paint in a direction ==="),
    MoveSequence(directions=['right'] * 3, pause_after=0.2),
    MoveSequence(directions=['right'] * 5, char_held='w', delay_per_step=0.2, pause_after=0.8),

    Comment("=== Tab switches to writing; text flips black or white ==="),
    PressKey("tab", pause_after=0.5),
    MoveSequence(directions=['up', 'up'] + ['left'] * 10, pause_after=0.3),
    TypeText("hi!", delay_per_char=0.15, final_pause=0.8),
    PressKey("tab", pause_after=0.5),

    Comment("=== Backspace erases; repeats accelerate like holding it ==="),
    PressKey("backspace", pause_after=0.3),
    PressKey("backspace", pause_after=0.3),
    PressKey("backspace", pause_after=0.4),
    *[PressKey("backspace", pause_after=0.06, is_repeat=True) for _ in range(14)],
    Pause(0.8),

    Comment("=== Work stays put while you visit other rooms ==="),
    PressKey("escape", pause_after=1.2, **_TAP),
    PressKey("1", pause_after=1.4),
    PressKey("escape", pause_after=1.2, **_TAP),
    PressKey("3", pause_after=1.2),
]
