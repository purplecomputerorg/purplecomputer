"""Short ad screen footage: Play beats, an Art paint + code beat, then Music.

Pure screen content for the short ad. No on-screen captions: text overlays
go on in the editor. Results stack rather than clearing (an Escape keypress,
Play's only "clear", cancels the running demo). Timings are kept snappy so
the whole thing stays short.
"""

from ..script import (
    SwitchRoom, TypeText, PressKey, Pause, ClearArt, MoveSequence,
    PlayKeys, Comment, ZoomIn, ZoomOut,
)

_TYPING = dict(delay_per_char=0.045, final_pause=0.15)

# Music gestures: a tap is under the 0.8s hold/tap threshold, a hold outlasts it.
_TAP = dict(hold_duration=0.2)
_HOLD = dict(hold_duration=1.0)

def _play_beat(text, read):
    """One Play beat: lean into the input to type, then pull back and pan up
    to reveal the result. Play content is left-aligned, so both regions are
    shifted left (see ad-input / ad-reveal). The input sits low; results stack
    from the top down, so going from "ad-input" to the wider "ad-reveal" both
    pans up and zooms out a bit, keeping the result framed whether it's one
    line or a tall abacus.
    """
    return [
        ZoomIn(region="ad-input", zoom=2.6, duration=0.35),
        TypeText(text, **_TYPING),
        PressKey("enter", pause_after=0.3),
        ZoomIn(region="ad-reveal", zoom=1.3, duration=0.5),
        Pause(read),
    ]


_PLAY = [
    Comment("=== PLAY ==="),
    SwitchRoom("play", pause_after=0.3),
    ZoomIn(region="ad-input", zoom=2.6, duration=0.2),

    Comment("Settle inside the recorded region so the first beat never lands "
            "on a not-yet-painted screen (the pre-roll timer alone wasn't "
            "enough on slow VMs). Trim this lead-in in the editor."),
    Pause(2.0),

    *_play_beat("hello :)", read=0.9),
    *_play_beat("red + blue", read=0.9),
    Comment("'say' speaks the words aloud (needs a pre-generated clip)"),
    *_play_beat("say purple computer", read=1.6),
    *_play_beat("5 x 5 dinos", read=1.1),
    Comment("Colored counting with addition and color adjectives"),
    *_play_beat("2 red cookies + 3 light green cookies", read=1.7),
    Comment("Big number 9876 renders as the place-value abacus"),
    *_play_beat("9876 butterflies", read=1.7),

    ZoomOut(duration=0.4),
]

_ART = [
    Comment("=== ART: paint a row, then overwrite it to mix the colors ==="),
    SwitchRoom("art", pause_after=0.3),
    ClearArt(),
    MoveSequence(directions=['down'] * 4 + ['right'] * 20, delay_per_step=0.02),

    Comment("Both rows are 9 chars. Start zxc... 5 cells left of qwe... so the "
            "left end stays pure blue and only the right end overlaps and mixes"),
    TypeText("qwertyuio", **_TYPING),
    MoveSequence(directions=['left'] * 14, delay_per_step=0.02),
    TypeText("zxcvbnm,.", **_TYPING),
    Pause(0.9),

    Comment("=== ART: draw with code below the rows ==="),
    MoveSequence(directions=['down'] * 2, delay_per_step=0.04),
    PressKey("space", hold_duration=1.0, pause_after=0.5),

    TypeText("blue repeat 4 forward 10 turn", delay_per_char=0.04, final_pause=0.15),
    PressKey("enter", pause_after=1.2),
    TypeText("red right 20", delay_per_char=0.04, final_pause=0.15),
    PressKey("enter", pause_after=1.8),

    Comment("Hold Space to close the code panel before leaving Art"),
    PressKey("space", hold_duration=1.0, pause_after=0.4),
]

_MUSIC = [
    Comment("=== MUSIC: a quick loop, an instrument change, then letters ==="),
    SwitchRoom("music", pause_after=0.4),

    Comment("Hold Enter to start recording the loop"),
    PressKey("enter", pause_after=0.4, **_HOLD),
    Comment("Syncopated riff with rests; short enough to keep the loop under ~2s"),
    PlayKeys(sequence=['t', None, 'y', 't', None, 'u'], seconds_between=0.2, pause_after=0.2),
    Comment("Tap Space to close the loop and start it playing back"),
    PressKey("space", pause_after=0.5, **_TAP),

    Comment("Layer a couple notes on top while it loops"),
    PlayKeys(sequence=['e', None, 'r'], seconds_between=0.3, pause_after=0.2),
    Pause(1.3),

    Comment("Tap Enter to change the instrument, then play in the new sound"),
    PressKey("enter", pause_after=0.4, **_TAP),
    PlayKeys(sequence=['t', 'y'], seconds_between=0.3, pause_after=0.2),
    Pause(1.2),

    Comment("Escape stops the loop"),
    PressKey("escape", pause_after=0.5),

    Comment("Tab into Say Letters mode, then type abc (no loop)"),
    PressKey("tab", pause_after=0.5),
    PlayKeys(sequence=['a', 'b', 'c'], seconds_between=0.6, pause_after=0.4),
    Pause(0.5),
]

SEGMENT = _PLAY + _ART + _MUSIC

SPEED_MULTIPLIER = 1.0
