"""Closing text segment for demo."""

from purple_tui.demo.script import (
    SwitchMode, Pause, MoveSequence, Comment, TypeText,
)

SEGMENT = [
    Comment("=== CLOSING TEXT ==="),
    SwitchMode("doodle"),
    Pause(0.3),

    # Canvas already cleared at end of palm_tree segment
    # Position cursor to center for first line of text
    # First line "This is Purple Computer." is 24 chars
    # Center it at approximately x=45, y=12
    MoveSequence(directions=['right'] * 45 + ['down'] * 12, delay_per_step=0.008),

    # Type the first line
    TypeText("This is Purple Computer.", delay_per_char=0.12),

    # Move down two rows and position for second line
    # Second line "Coming soon to your old laptop!" is 31 chars, so start at x=41
    # After typing 24 chars, cursor is at x=69. Move left to x=41 (28 left) and down 2
    MoveSequence(directions=['down', 'down'] + ['left'] * 28, delay_per_step=0.01),

    Pause(2.0),

    # Type the second line
    TypeText("Coming soon to your old laptop!", delay_per_char=0.12),

    Pause(4.0),
    Comment("Closing complete!"),
]

SPEED_MULTIPLIER = 1.0
