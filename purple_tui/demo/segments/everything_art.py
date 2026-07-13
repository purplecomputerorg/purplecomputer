"""Everything video, Art room: paint a small scene that doubles as the
feature tour. The keyboard-row gradients become a color chart in the
corner, then a tree whose canopy is yellow painted over with blue (mixing
makes it green), a sun with diagonal rays, a ground line painted by
holding a letter, a written word over the paint, and an erase.

Room changes use SwitchRoom (clean cuts): the room picker already had its
on-camera moment in the Music segment. Cursor positions are made absolute
by clamping to the top-left corner first (over-long left/up runs no-op at
the edge, same trick as the palm segment). Coordinates are approximate;
tune against a test render.
"""

from ..script import (
    TypeText, PressKey, Pause, Comment, SetSpeed, DrawPath, MoveSequence,
    ClearArt, SwitchRoom,
)

_CLAMP = ['left'] * 150 + ['up'] * 40

def _newline(cols_back: int) -> MoveSequence:
    return MoveSequence(directions=['down'] + ['left'] * cols_back, pause_after=0.3)

SEGMENT = [
    SetSpeed(1.0),

    SwitchRoom("art"),
    Pause(0.8),
    ClearArt(),

    Comment("=== Every key is a color: paint each keyboard row ==="),
    TypeText("1234567890", delay_per_char=0.12, final_pause=0.4),
    _newline(10),
    TypeText("qwertyuiop", delay_per_char=0.12, final_pause=0.4),
    _newline(10),
    TypeText("asdfghjkl", delay_per_char=0.12, final_pause=0.4),
    _newline(9),
    TypeText("zxcvbnm", delay_per_char=0.12, final_pause=0.6),

    Comment("=== A scene: tree canopy, yellow first ==="),
    MoveSequence(directions=_CLAMP, delay_per_step=0.003, pause_after=0.2),
    MoveSequence(directions=['right'] * 27 + ['down'] * 7, delay_per_step=0.02, pause_after=0.2),
    DrawPath(directions=['right'] * 6, color_key='d', delay_per_step=0.12, pause_after=0.3),
    MoveSequence(directions=['down'] + ['left'] * 6, delay_per_step=0.02, pause_after=0.1),
    DrawPath(directions=['right'] * 6, color_key='d', delay_per_step=0.12, pause_after=0.6),

    Comment("=== Blue over yellow: the canopy turns green ==="),
    MoveSequence(directions=['left'] * 6, delay_per_step=0.02, pause_after=0.1),
    DrawPath(directions=['right'] * 6, color_key='c', delay_per_step=0.12, pause_after=0.3),
    MoveSequence(directions=['up'] + ['left'] * 6, delay_per_step=0.02, pause_after=0.1),
    DrawPath(directions=['right'] * 6, color_key='c', delay_per_step=0.12, pause_after=0.9),

    Comment("=== Trunk ==="),
    MoveSequence(directions=['left'] * 3 + ['down'] * 2, delay_per_step=0.02, pause_after=0.1),
    DrawPath(directions=['down'] * 5, color_key='l', delay_per_step=0.12, pause_after=0.6),

    Comment("=== Ground: hold a letter and press arrows to paint ==="),
    MoveSequence(directions=['left'] * 6 + ['down'], delay_per_step=0.02, pause_after=0.2),
    MoveSequence(directions=['right'] * 14, char_held='8', delay_per_step=0.15, pause_after=0.8),

    Comment("=== Sun: hold Space to draw; two arrows makes diagonal rays ==="),
    MoveSequence(directions=['up'] * 13 + ['right'] * 10, delay_per_step=0.02, pause_after=0.2),
    DrawPath(directions=['right'] * 2, color_key='a', delay_per_step=0.15, pause_after=0.3),
    DrawPath(directions=['right+down'] * 3, color_key='s', delay_per_step=0.2, pause_after=0.3),
    MoveSequence(directions=['up'] * 3 + ['left'] * 8, delay_per_step=0.02, pause_after=0.1),
    DrawPath(directions=['left+down'] * 3, color_key='s', delay_per_step=0.2, pause_after=0.8),

    Comment("=== Tab switches to writing; text flips black or white ==="),
    PressKey("tab", pause_after=0.5),
    MoveSequence(directions=['down'] * 2 + ['left'] * 7, delay_per_step=0.02, pause_after=0.2),
    TypeText("hi!", delay_per_char=0.15, final_pause=0.8),
    PressKey("tab", pause_after=0.5),

    Comment("=== Backspace erases; repeats accelerate like holding it ==="),
    MoveSequence(directions=['down'] * 8, delay_per_step=0.02, pause_after=0.2),
    PressKey("backspace", pause_after=0.3),
    PressKey("backspace", pause_after=0.3),
    PressKey("backspace", pause_after=0.4),
    *[PressKey("backspace", pause_after=0.06, is_repeat=True) for _ in range(12)],
    Pause(0.8),

    Comment("=== Work stays put while you visit other rooms ==="),
    SwitchRoom("play"),
    Pause(1.4),
    SwitchRoom("art"),
    Pause(1.2),
]
