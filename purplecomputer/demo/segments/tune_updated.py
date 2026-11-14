"""Music room demo (updated): instrument switching, loop station, color finale.

Enter (tap) cycles instruments; Enter (hold) starts the loop station; Space
(tap) finishes recording and plays the loop back; Escape stops it.

Hold gestures depend on the 0.8s hold/tap threshold, so this segment runs at
SetSpeed(1.0): the real-time hold_duration must outlast the timer.
"""

from ..script import (
    SwitchRoom, PlayKeys, PressKey, Pause, Comment, SetSpeed,
)

# A tap is a short press under the 0.8s threshold; a hold outlasts it.
_TAP = dict(hold_duration=0.2)
_HOLD = dict(hold_duration=1.0)

SEGMENT = [
    SetSpeed(1.0),
    SwitchRoom("music"),
    Pause(0.4),

    Comment("=== Instrument showcase: tap Enter cycles the instrument ==="),
    Comment("Marimba (default)"),
    PlayKeys(sequence=['q', 'e', 't', 'y', 'u'], seconds_between=0.18, pause_after=0.5),

    Comment("-> Ukulele"),
    PressKey("enter", pause_after=0.8, **_TAP),
    PlayKeys(sequence=['a', 's', 'd', 'f', 'g'], seconds_between=0.18, pause_after=0.5),

    Comment("-> Accordion"),
    PressKey("enter", pause_after=0.8, **_TAP),
    PlayKeys(sequence=['z', 'x', 'c', 'v', 'b'], seconds_between=0.18, pause_after=0.6),

    Comment("=== Loop station: hold Enter to record ==="),
    PressKey("enter", pause_after=0.5, **_HOLD),
    Comment("Lay down a short riff"),
    PlayKeys(sequence=['t', 't', None, 'y', 'y'], seconds_between=0.25, pause_after=0.3),

    Comment("Tap Space: finish recording and start the loop playing back"),
    PressKey("space", pause_after=0.6, **_TAP),
    Comment("Play more notes on top while it loops"),
    PlayKeys(sequence=['q', None, 'e', None, 'r'], seconds_between=0.3, pause_after=0.3),

    Comment("Let the loop ride for a couple of cycles"),
    Pause(3.0),

    Comment("Escape stops the loop"),
    PressKey("escape", pause_after=0.6),

    Comment("=== Color finale: fast runs across all four rows ==="),
    PlayKeys(sequence=['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
             seconds_between=0.05, pause_after=0.1),
    PlayKeys(sequence=['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
             seconds_between=0.05, pause_after=0.1),
    PlayKeys(sequence=['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';'],
             seconds_between=0.05, pause_after=0.1),
    PlayKeys(sequence=['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/'],
             seconds_between=0.05, pause_after=0.5),

    Pause(1.0),
]
