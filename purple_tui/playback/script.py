"""Playback script format for defining action sequences.

This module provides a simple, readable format for defining playback scripts.
Each action is a dataclass that describes what should happen.

Used by Code room for program playback, and by the demo system for
advertising screencasts.

Example script:
    SCRIPT = [
        SwitchRoom("play"),
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
class PlaybackAction:
    """Base class for all playback actions."""
    pass


@dataclass
class TypeText(PlaybackAction):
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
class PressKey(PlaybackAction):
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
class SwitchRoom(PlaybackAction):
    """Switch to a different room.

    Args:
        room: 'play' (F1), 'music' (F2), or 'art' (F3)
        pause_after: Pause after switching to let the room render
    """
    room: Literal["play", "music", "art"]
    pause_after: float = 0.5


@dataclass
class SwitchTarget(PlaybackAction):
    """Switch to a specific room and mode.

    Used by Code room playback to switch to the exact room/mode
    recorded during F5 recording.

    Args:
        target: Target string like "music.music", "art.paint", "play"
        pause_after: Pause after switching
    """
    target: str
    pause_after: float = 0.3


@dataclass
class Pause(PlaybackAction):
    """Pause for a duration (let viewer absorb what happened).

    Args:
        duration: Seconds to pause
    """
    duration: float


@dataclass
class Clear(PlaybackAction):
    """Clear the current room's content.

    In Play room: clears history
    In Art room: clears canvas
    """
    pause_after: float = 0.3


@dataclass
class ClearAll(PlaybackAction):
    """Clear all state across all modes. Use at start of demo.

    Clears:
    - Play room history and last result
    - Music room colors (reset to defaults)
    - Art room canvas
    """
    pause_after: float = 0.1


@dataclass
class ClearArt(PlaybackAction):
    """Clear the art canvas and reset cursor to (0,0).

    Use this to start fresh in art room without affecting other rooms.
    """
    pause_after: float = 0.2


@dataclass
class PlayKeys(PlaybackAction):
    """Play a sequence of keys in Music room (for making music).

    This types keys with musical timing. Each item can be:
    - A single key: 'q'
    - A chord (simultaneous): ['q', 'p']
    - A rest: None

    Args:
        sequence: List of keys, chords, or rests
        seconds_between: Seconds between each key press
        pause_after: Pause after the sequence
    """
    sequence: list
    seconds_between: float = 0.5
    pause_after: float = 0.5


@dataclass
class DrawPath(PlaybackAction):
    """Draw a path in Art room (hold space + arrows).

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
class MoveSequence(PlaybackAction):
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
class SetSpeed(PlaybackAction):
    """Change playback speed mid-demo. Inserted between segments."""
    multiplier: float = 1.0


@dataclass
class ZoomIn(PlaybackAction):
    """Zoom in to a named region for readability.

    Used during recording: markers are exported to a JSON sidecar file,
    then post-processing applies the zoom via FFmpeg crop/scale.

    Args:
        region: Named region ("input", "viewport", "art-center") or
                custom tuple (x, y, width, height) at recording resolution
        zoom: Zoom level (1.5 = 150%, 2.0 = 200%)
        duration: Transition time in seconds (ease-out for smooth arrival)
    """
    region: str = "input"
    zoom: float = 1.5
    duration: float = 0.4


@dataclass
class ZoomOut(PlaybackAction):
    """Zoom out to full viewport.

    Complements ZoomIn: returns to 1.0x zoom showing the full screen.

    Args:
        duration: Transition time in seconds (ease-in-out for smooth transition)
    """
    duration: float = 0.4


@dataclass
class ZoomTarget(PlaybackAction):
    """Pan the camera to a new position while zoomed in.

    Smoothly moves the crop region without changing the zoom level.
    Use this to follow text as it flows down the screen during typing.

    Args:
        y: Vertical center of the crop as a fraction of video height (0.0=top, 1.0=bottom).
            If None, keeps current y position.
        x: Horizontal center of the crop as a fraction of video width (0.0=left, 1.0=right).
            If None, keeps current x position.
        duration: Transition time in seconds
    """
    y: float | None = None
    x: float | None = None
    duration: float = 0.3


@dataclass
class Comment(PlaybackAction):
    """A comment in the script (does nothing, just for documentation).

    Useful for marking sections of the demo.
    """
    text: str


# Convenience functions for building scripts more readably

def type_and_enter(text: str, pause: float = 0.8) -> list[PlaybackAction]:
    """Type text and press enter, with a pause to show the result."""
    return [
        TypeText(text),
        PressKey("enter", pause_after=pause),
    ]


def section_pause(duration: float = 1.5) -> PlaybackAction:
    """A longer pause between demo sections."""
    return Pause(duration)


def segment_duration(actions: list[PlaybackAction]) -> float:
    """Compute the natural (speed=1.0) duration of a list of actions in seconds."""
    total = 0.0
    for action in actions:
        if isinstance(action, Pause):
            total += action.duration
        elif isinstance(action, SwitchRoom):
            total += action.pause_after
        elif isinstance(action, SwitchTarget):
            total += action.pause_after
        elif isinstance(action, TypeText):
            total += len(action.text) * action.delay_per_char + action.final_pause
        elif isinstance(action, PressKey):
            total += action.hold_duration + action.pause_after
        elif isinstance(action, PlayKeys):
            total += len(action.sequence) * action.seconds_between + action.pause_after
        elif isinstance(action, DrawPath):
            total_steps = len(action.directions) * action.steps_per_direction
            total += 0.1 + 0.1 + 0.05 + total_steps * action.delay_per_step + action.pause_after
        elif isinstance(action, MoveSequence):
            total += len(action.directions) * action.delay_per_step + action.pause_after
        elif isinstance(action, (Clear, ClearAll, ClearArt)):
            total += action.pause_after
        elif isinstance(action, (ZoomIn, ZoomOut, ZoomTarget)):
            total += action.duration
        # Comment, SetSpeed: 0 duration
    return total
