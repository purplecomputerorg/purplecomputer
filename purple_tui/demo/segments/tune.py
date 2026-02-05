"""Play Mode composition: Digital Smiley Face with glissando finale.

Based on: python tools/play_ai.py "make a smiley face pattern with all the colors" --save tune
"""

from ..script import PlayKeys, Comment, Pause, SwitchMode

SEGMENT = [
    SwitchMode("play"),
    Pause(0.3),

    Comment("=== Eyes (purple, 1 press each) - quick cheerful high notes ==="),
    PlayKeys(
        sequence=['4', None, None, '7'],
        seconds_between=0.2,
        pause_after=0.3,
    ),

    Comment("=== Nose (blue, 2 presses each) - middle harmony ==="),
    PlayKeys(
        sequence=['t', 't', None, 'y', 'y'],
        seconds_between=0.25,
        pause_after=0.3,
    ),

    Comment("=== Smile corners (red, 3 presses each) - rhythmic foundation ==="),
    PlayKeys(
        sequence=['d', 'd', 'd', None, None, 'k', 'k', 'k'],
        seconds_between=0.43,
        pause_after=0.4,
    ),

    Comment("=== Smile bottom (red, 3 presses each) - ascending melody ==="),
    PlayKeys(
        sequence=['v', 'v', 'v', 'b', 'b', 'b', 'n', 'n', 'n', 'm', 'm', 'm'],
        seconds_between=0.375,
        pause_after=0.3,
    ),

    Comment("=== Pause to admire the smiley ==="),
    Pause(1.0),

    Comment("=== Fast runs across all 4 keyboard rows ==="),
    PlayKeys(
        sequence=[
            '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
        ],
        seconds_between=0.05,
        pause_after=0.1,
    ),
    PlayKeys(
        sequence=[
            'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p',
        ],
        seconds_between=0.05,
        pause_after=0.1,
    ),
    PlayKeys(
        sequence=[
            'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';',
        ],
        seconds_between=0.05,
        pause_after=0.1,
    ),
    PlayKeys(
        sequence=[
            'z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/',
        ],
        seconds_between=0.05,
        pause_after=0.5,
    ),

    Pause(1.0),
]
