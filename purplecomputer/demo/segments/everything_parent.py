"""Everything video, parent menu tour: scroll the whole menu slowly so the
voiceover can walk the items, then open the real terminal, which shows
itself for a few seconds and returns on its own (see _run_shell's demo
branch).

Injected escape holds can't trigger the state machine's 1s hold, so the
menu opens via the playback room action; the voiceover says "hold Escape".
SelectMenuItem finds Open Terminal by label, so menu changes don't break
the tour, and the visible scroll down to it doubles as the item tour.
Opening the shell dismisses the menu, so no exit keys are needed; the
event loop is blocked while the shell runs, so the pause after only needs
to cover the redraw.
"""

from ..script import SwitchRoom, SelectMenuItem, Pause, Comment, SetSpeed

SEGMENT = [
    SetSpeed(1.0),

    Comment("=== The grown-up menu (on hardware: hold Escape 1s) ==="),
    SwitchRoom("parent"),
    Pause(2.0),

    Comment("Scroll down to Open Terminal; the shell shows itself and returns"),
    SelectMenuItem("Open Terminal", delay_per_step=0.9, activate=True, pause_after=2.0),
    Pause(2.0),
]
