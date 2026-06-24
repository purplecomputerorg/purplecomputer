"""Shared builder for the music loop-session comparison segments.

Each variant records a short riff, closes the loop, layers a couple notes,
then lets it ride a cycle before stopping. Only the notes differ, so the
choreography lives here and the variants are just data.
"""

from ..script import SwitchRoom, PressKey, PlayKeys, Pause, Comment

_HOLD = dict(hold_duration=1.0)
_TAP = dict(hold_duration=0.2)


def build_loop_session(riff, layer, riff_spacing=0.22, layer_spacing=0.3,
                       ride=2.5):
    return [
        Comment("=== MUSIC loop session ==="),
        SwitchRoom("music", pause_after=0.6),

        Comment("Hold Enter to start recording the loop"),
        PressKey("enter", pause_after=0.4, **_HOLD),
        PlayKeys(sequence=riff, seconds_between=riff_spacing, pause_after=0.2),

        Comment("Tap Space to close the loop and start it playing back"),
        PressKey("space", pause_after=0.5, **_TAP),
        PlayKeys(sequence=layer, seconds_between=layer_spacing, pause_after=0.2),

        Pause(ride),
        Comment("Escape stops the loop"),
        PressKey("escape", pause_after=0.5),
    ]
