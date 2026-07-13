"""Everything video, Music room: no wrong notes, instruments, drums,
note names, key changes, and the loop station.

Enters via the room picker (escape tap, then 2) so the picker itself is on
camera. Hold gestures depend on the 0.8s threshold, so this runs at 1.0x.
"""

from ..script import PlayKeys, PressKey, Pause, Comment, SetSpeed

_TAP = dict(hold_duration=0.2)
_HOLD = dict(hold_duration=1.0)

SEGMENT = [
    SetSpeed(1.0),

    Comment("Escape tap opens the room picker; 2 jumps to Music"),
    PressKey("escape", pause_after=1.4, **_TAP),
    PressKey("2", pause_after=1.0),

    Comment("=== No wrong notes: arpeggios up the octaves, then a tune ==="),
    PlayKeys(sequence=['z', 'c', 'b'], seconds_between=0.18, pause_after=0.25),
    PlayKeys(sequence=['a', 'd', 'g'], seconds_between=0.18, pause_after=0.25),
    PlayKeys(sequence=['q', 'e', 't', 'u'], seconds_between=0.18, pause_after=0.6),
    Comment("Mary Had a Little Lamb, first phrase"),
    PlayKeys(sequence=['d', 's', 'a', 's', 'd', 'd', 'd', None, 's', 's', 's', None, 'd', 'g', 'g'],
             seconds_between=0.32, pause_after=1.2),

    Comment("=== Tap Enter to change instruments ==="),
    Comment("-> Ukulele"),
    PressKey("enter", pause_after=0.6, **_TAP),
    PlayKeys(sequence=['a', 'd', 'g', 'j'], seconds_between=0.24, pause_after=0.7),
    Comment("-> Accordion"),
    PressKey("enter", pause_after=0.6, **_TAP),
    PlayKeys(sequence=['z', 'c', 'b', 'm'], seconds_between=0.24, pause_after=0.7),
    Comment("-> Glockenspiel"),
    PressKey("enter", pause_after=0.6, **_TAP),
    PlayKeys(sequence=['q', 'e', 't', 'u'], seconds_between=0.24, pause_after=0.7),
    Comment("-> back to Marimba for the rest"),
    PressKey("enter", pause_after=0.6, **_TAP),

    Comment("=== The number row is a drum kit ==="),
    PlayKeys(sequence=['1', '5', '2', '8', '1', '5', '2', '0'],
             seconds_between=0.22, pause_after=1.0),

    Comment("=== Space tap labels every key with its note ==="),
    PressKey("space", pause_after=0.8, **_TAP),
    PlayKeys(sequence=['q', 'w', 'e'], seconds_between=0.4, pause_after=1.0),
    PressKey("space", pause_after=0.5, **_TAP),

    Comment("=== Tab: Say Letters mode, keys speak their letter ==="),
    PressKey("tab", pause_after=0.8),
    PlayKeys(sequence=['c', 'a', 't'], seconds_between=1.1, pause_after=1.2),
    PressKey("tab", pause_after=0.8),

    Comment("=== Arrows change the musical key (watch the wave) ==="),
    PressKey("right", pause_after=1.3),
    PressKey("right", pause_after=1.3),
    PlayKeys(sequence=['q', 'w', 'e', 't'], seconds_between=0.28, pause_after=1.0),

    Comment("=== Loop station: hold Enter to record ==="),
    PressKey("enter", pause_after=0.5, **_HOLD),
    PlayKeys(sequence=['q', None, 'e', 'e', None, 't'], seconds_between=0.3, pause_after=0.3),
    Comment("Tap Space: finish recording, loop starts playing back"),
    PressKey("space", pause_after=0.7, **_TAP),
    Comment("Switch instrument and play on top of the loop"),
    PressKey("enter", pause_after=0.5, **_TAP),
    PlayKeys(sequence=['u', None, 'i', None, 'o'], seconds_between=0.45, pause_after=0.3),
    Comment("Let it ride so the layering is audible"),
    Pause(3.5),
    Comment("Escape stops the loop"),
    PressKey("escape", pause_after=1.0),
]
