"""Everything video, Music Code Space: instrument, melody, tempo.

Runs right after the Music segment, already in the Music room, at 1.0x.
"""

from ..script import ToggleCode, Comment, SetSpeed, type_and_enter


SEGMENT = [
    SetSpeed(1.0),

    Comment("=== The code window opens ==="),
    ToggleCode(pause_after=1.2),
    *type_and_enter("choose ukulele", 1.6),
    *type_and_enter("fast abcdefg slow asdf", 4.5),
    ToggleCode(pause_after=1.0),
]
