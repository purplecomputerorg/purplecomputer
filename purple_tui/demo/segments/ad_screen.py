"""Ad screen footage: punchy magic beats, no on-screen narration.

This is the screen half of the 30-60s "hands + magic" ad. Unlike the
walkthrough segments, it carries no captions on the canvas: text overlays
are added in the editor over the hands footage. Each beat is one clean
moment (color, big count, speech, code, music), zoomed for phone screens.
"""

from ..script import (
    SwitchRoom, TypeText, PressKey, Pause, ClearArt,
    PlayKeys, Comment, ZoomIn, ZoomOut,
)

# Results stack rather than clearing between beats: an Escape keypress (the
# only "clear" Play has) cancels the running demo, so segments never clear.
_TYPING = dict(delay_per_char=0.06, final_pause=0.1)

_PLAY = [
    Comment("=== PLAY: color mixing ==="),
    SwitchRoom("play", pause_after=0.2),
    ZoomIn(region="input", zoom=2.5, duration=0.2),

    TypeText("red + blue", **_TYPING),
    PressKey("enter", pause_after=2.0),

    Comment("=== PLAY: big count floods the screen ==="),
    ZoomOut(duration=0.3),
    TypeText("100 sharks", **_TYPING),
    PressKey("enter", pause_after=2.2),

    Comment("=== PLAY: it talks (trailing ! speaks aloud) ==="),
    ZoomIn(region="input", zoom=2.5, duration=0.2),
    TypeText("cat!", **_TYPING),
    PressKey("enter", pause_after=2.8),
    ZoomOut(duration=0.2),
    Pause(0.3),
]

_CODE = [
    Comment("=== ART: draw with code (the 'grows with them' beat) ==="),
    SwitchRoom("art", pause_after=0.3),
    ClearArt(),

    Comment("Hold Space to open the code panel (same gesture as the kid uses)"),
    PressKey("space", hold_duration=1.0, pause_after=0.7),
    ZoomIn(region="art-center", zoom=1.6, duration=0.3),

    TypeText("green", delay_per_char=0.08, final_pause=0.2),
    PressKey("enter", pause_after=0.5),
    TypeText("repeat 4 forward 8, spin", delay_per_char=0.06, final_pause=0.2),
    PressKey("enter", pause_after=2.6),

    PressKey("space", hold_duration=1.0, pause_after=0.5),
    ZoomOut(duration=0.3),
    ClearArt(),
]

_MUSIC = [
    Comment("=== MUSIC: colorful runs, no wrong notes ==="),
    SwitchRoom("music", pause_after=0.4),
    ZoomIn(region="music-keys", zoom=1.5, duration=0.2),

    PlayKeys(sequence=['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
             seconds_between=0.07, pause_after=0.1),
    PlayKeys(sequence=['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
             seconds_between=0.07, pause_after=0.1),
    PlayKeys(sequence=['z', 'x', 'c', 'v', 'b', 'n', 'm'],
             seconds_between=0.07, pause_after=0.4),

    ZoomOut(duration=0.3),
    Pause(1.2),
]

SEGMENT = _PLAY + _CODE + _MUSIC

SPEED_MULTIPLIER = 1.0
