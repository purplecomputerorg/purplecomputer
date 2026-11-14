"""Closing text segment for demo (updated)."""

from purple_tui.demo.script import (
    SwitchRoom, Pause, MoveSequence, Comment, TypeText, ZoomIn, ZoomOut,
)

SEGMENT = [
    Comment("=== CLOSING TEXT ==="),
    SwitchRoom("art"),
    Pause(0.3),

    # Canvas already cleared at end of palm_updated segment.
    # First line "This is Purple Computer." is 24 chars; center near x=45, y=12.
    MoveSequence(directions=['right'] * 45 + ['down'] * 12, delay_per_step=0.008),

    Comment("Zoom in for the title"),
    ZoomIn(region="closing-title", zoom=2.5, duration=0.3),

    TypeText("This is Purple Computer.", delay_per_char=0.12),

    # Second line "Coming soon to your old laptop!" is 31 chars, start at x=41.
    # After 24 chars cursor is at x=69: move left 28, down 2.
    MoveSequence(directions=['down', 'down'] + ['left'] * 28, delay_per_step=0.01),

    Pause(1.5),

    Comment("Zoom out to show the full 'Coming soon' line"),
    ZoomOut(duration=0.5),
    Pause(0.3),

    TypeText("Coming soon to your old laptop!", delay_per_char=0.12),

    Pause(4.0),
    Comment("Closing complete!"),
]

SPEED_MULTIPLIER = 1.0
