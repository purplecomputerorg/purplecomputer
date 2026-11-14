"""Everything video, little touches: the = key means plus, mash-proof,
and the clear-room dialog defaulting to Go Back.

Sticky shift, double-letter capitals, and backtick-as-Escape live below the
injection layer (state machine / keyd), so they stay voiceover-only.
Go Back on the confirm screen returns to the still-open picker, so the
segment exits by picking Play.
"""

from ..script import TypeText, PressKey, Pause, Comment, SetSpeed, SwitchRoom, type_and_enter

_TAP = dict(hold_duration=0.2)

SEGMENT = [
    SetSpeed(1.0),

    Comment("Back to Play"),
    SwitchRoom("play"),
    Pause(0.8),

    Comment("=== The big = key just means plus ==="),
    *type_and_enter("5 = 3", 2.0),

    Comment("=== Mash the whole keyboard: nothing breaks ==="),
    TypeText("dfkjaweiruxcvnqpz", delay_per_char=0.04, final_pause=0.3),
    PressKey("enter", pause_after=2.0),

    Comment("=== Clearing asks first, Go Back is the default ==="),
    PressKey("escape", pause_after=1.4, **_TAP),
    Comment("C on the picker opens the clear confirmation"),
    PressKey("c", pause_after=2.2),
    Comment("Enter takes the Go Back default: nothing is lost"),
    PressKey("enter", pause_after=1.0),
    Comment("Picker is still open; pick Play to move on"),
    PressKey("1", pause_after=1.2),
]
