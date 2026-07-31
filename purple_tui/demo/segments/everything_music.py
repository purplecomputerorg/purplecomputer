"""Everything video, Music room: one tune three ways, then the loop station.

Opens on Mary Had a Little Lamb so the first thing anyone hears is a real
tune, then plays it again in a new key and again on a new instrument, with
that third version recorded into the loop and layered over. The feature
beats (drums, note names, letters) follow. Hold gestures depend on the 0.8s
threshold, so this runs at 1.0x.
"""

from ..script import PlayKeys, PressKey, Pause, Comment, SetSpeed

_TAP = dict(hold_duration=0.2)
_HOLD = dict(hold_duration=1.0)

# Mary Had a Little Lamb on the middle row: A is do, S re, D mi, G sol.
_MARY = ['d', 's', 'a', 's', 'd', 'd', 'd', None,
         's', 's', 's', None, 'd', 'g', 'g', None]
_MARY_ENDING = ['d', 's', 'a', 's', 'd', 'd', 'd', 'd', 's', 's', 'd', 's', 'a']

SEGMENT = [
    SetSpeed(1.0),

    Comment("Escape tap opens the room picker; 2 jumps to Music"),
    PressKey("escape", pause_after=1.4, **_TAP),
    PressKey("2", pause_after=0.8),

    Comment("=== Take 1: the whole tune, Marimba in C ==="),
    PlayKeys(sequence=_MARY + _MARY_ENDING, seconds_between=0.3, pause_after=1.1),

    Comment("=== Take 2: Right arrow moves the key to G, same keys, new mood ==="),
    PressKey("right", pause_after=1.1),
    PlayKeys(sequence=_MARY, seconds_between=0.3, pause_after=1.1),

    Comment("=== Take 3: Enter tap -> Ukulele, and this one goes in the loop ==="),
    PressKey("enter", pause_after=0.8, **_TAP),
    Comment("Hold Enter to start recording"),
    PressKey("enter", pause_after=0.5, **_HOLD),
    PlayKeys(sequence=_MARY, seconds_between=0.3, pause_after=0.2),
    Comment("Tap Space: recording ends, the loop starts playing back"),
    PressKey("space", pause_after=0.9, **_TAP),

    Comment("=== Play over the loop on other instruments ==="),
    Comment("-> Accordion counter-melody up top"),
    PressKey("enter", pause_after=0.5, **_TAP),
    PlayKeys(sequence=['u', None, 'i', None, 'o', 'i'],
             seconds_between=0.45, pause_after=0.4),
    Comment("-> Glockenspiel sparkle on top of that"),
    PressKey("enter", pause_after=0.5, **_TAP),
    PlayKeys(sequence=['p', 'o', None, 'i', 'p'],
             seconds_between=0.4, pause_after=0.3),
    Comment("Let it ride so all three layers are audible"),
    Pause(4.0),
    Comment("Escape stops the loop"),
    PressKey("escape", pause_after=1.0),

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
]
