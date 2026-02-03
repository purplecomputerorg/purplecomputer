"""Demo script format for defining playback sequences.

This module provides a simple, readable format for defining demo scripts.
Each action is a dataclass that describes what should happen.

Example script:
    DEMO_SCRIPT = [
        SwitchMode("explore"),
        TypeText("Hello World!"),
        PressKey("enter"),
        Pause(1.0),
        TypeText("2+3"),
        PressKey("enter"),
    ]
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class DemoAction:
    """Base class for all demo actions."""
    pass


@dataclass
class TypeText(DemoAction):
    """Type a string of text character by character.

    Args:
        text: The text to type
        delay_per_char: Seconds between each character (default: human-like 0.08s)
        final_pause: Pause after typing completes (default: 0.3s)
    """
    text: str
    delay_per_char: float = 0.08
    final_pause: float = 0.3


@dataclass
class PressKey(DemoAction):
    """Press a special key (enter, backspace, escape, space, arrows, etc).

    Args:
        key: Key name: 'enter', 'backspace', 'escape', 'space',
             'up', 'down', 'left', 'right', 'tab'
        hold_duration: How long to hold the key (for long-press features)
        pause_after: Pause after the key press
    """
    key: str
    hold_duration: float = 0.0
    pause_after: float = 0.2


@dataclass
class SwitchMode(DemoAction):
    """Switch to a different mode.

    Args:
        mode: 'explore' (F1), 'play' (F2), or 'doodle' (F3)
        pause_after: Pause after switching to let the mode render
    """
    mode: Literal["explore", "play", "doodle"]
    pause_after: float = 0.5


@dataclass
class Pause(DemoAction):
    """Pause for a duration (let viewer absorb what happened).

    Args:
        duration: Seconds to pause
    """
    duration: float


@dataclass
class Clear(DemoAction):
    """Clear the current mode's content.

    In Ask mode: clears history
    In Write mode: clears canvas
    """
    pause_after: float = 0.3


@dataclass
class ClearAll(DemoAction):
    """Clear all state across all modes. Use at start of demo.

    Clears:
    - Explore mode history and last result
    - Play mode colors (reset to defaults)
    - Doodle mode canvas
    """
    pause_after: float = 0.1


@dataclass
class PlayKeys(DemoAction):
    """Play a sequence of keys in Play mode (for making music).

    This types keys with musical timing. Each item can be:
    - A single key: 'q'
    - A chord (simultaneous): ['q', 'p']
    - A rest: None

    Args:
        sequence: List of keys, chords, or rests
        tempo_bpm: Beats per minute (each item = 1 beat)
        pause_after: Pause after the sequence
    """
    sequence: list
    tempo_bpm: float = 120.0
    pause_after: float = 0.5


@dataclass
class DrawPath(DemoAction):
    """Draw a path in Write mode (hold space + arrows).

    Args:
        directions: List of arrow directions: 'up', 'down', 'left', 'right'
        steps_per_direction: How many cells to move in each direction
        delay_per_step: Seconds between each step
        color_key: Optional key to press first to set the color (e.g., 'r' for red row)
    """
    directions: list[str]
    steps_per_direction: int = 1
    delay_per_step: float = 0.1
    color_key: str | None = None
    pause_after: float = 0.3


@dataclass
class MoveSequence(DemoAction):
    """Move cursor without painting (just arrow keys, no space held).

    Use this for repositioning the cursor between paint operations.
    For actual painting, use DrawPath instead.

    Args:
        directions: List of arrow directions: 'up', 'down', 'left', 'right'
        delay_per_step: Seconds between each step (fast by default)
        pause_after: Pause after the sequence
    """
    directions: list[str]
    delay_per_step: float = 0.01
    pause_after: float = 0.05


@dataclass
class Comment(DemoAction):
    """A comment in the script (does nothing, just for documentation).

    Useful for marking sections of the demo.
    """
    text: str


# Convenience functions for building scripts more readably

def type_and_enter(text: str, pause: float = 0.8) -> list[DemoAction]:
    """Type text and press enter, with a pause to show the result."""
    return [
        TypeText(text),
        PressKey("enter", pause_after=pause),
    ]


def section_pause(duration: float = 1.5) -> DemoAction:
    """A longer pause between demo sections."""
    return Pause(duration)
