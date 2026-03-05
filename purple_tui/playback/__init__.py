"""Playback system for Code mode programs and demo scripts.

Core action types and player for executing scripted keyboard sequences.
Used by Code mode (build_mode.py) for program playback, and by the
advertising demo system (demo/) for screencast recordings.
"""

from .script import (
    PlaybackAction,
    TypeText,
    PressKey,
    SwitchRoom,
    SwitchTarget,
    Pause,
    Clear,
    ClearAll,
    ClearDoodle,
    PlayKeys,
    DrawPath,
    MoveSequence,
    SetSpeed,
    Comment,
    ZoomIn,
    ZoomOut,
    ZoomTarget,
    type_and_enter,
    section_pause,
    segment_duration,
)
from .player import PlaybackPlayer

__all__ = [
    "PlaybackAction",
    "TypeText",
    "PressKey",
    "SwitchRoom",
    "SwitchTarget",
    "Pause",
    "Clear",
    "ClearAll",
    "ClearDoodle",
    "PlayKeys",
    "DrawPath",
    "MoveSequence",
    "SetSpeed",
    "Comment",
    "ZoomIn",
    "ZoomOut",
    "ZoomTarget",
    "PlaybackPlayer",
    "type_and_enter",
    "section_pause",
    "segment_duration",
]
