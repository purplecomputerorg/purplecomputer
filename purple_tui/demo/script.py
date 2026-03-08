"""Backward-compatible re-exports from purple_tui.playback.script.

All action types now live in purple_tui.playback.script. This module
re-exports them so existing demo code continues to work unchanged.
DemoAction is an alias for PlaybackAction.
"""

from ..playback.script import (
    PlaybackAction as DemoAction,
    TypeText,
    PressKey,
    SwitchRoom,
    SwitchTarget,
    Pause,
    Clear,
    ClearAll,
    ClearArt,
    PlayKeys,
    DrawPath,
    MoveSequence,
    SetSpeed,
    ZoomIn,
    ZoomOut,
    ZoomTarget,
    Comment,
    type_and_enter,
    section_pause,
    segment_duration,
)

__all__ = [
    "DemoAction",
    "TypeText",
    "PressKey",
    "SwitchRoom",
    "SwitchTarget",
    "Pause",
    "Clear",
    "ClearAll",
    "ClearArt",
    "PlayKeys",
    "DrawPath",
    "MoveSequence",
    "SetSpeed",
    "ZoomIn",
    "ZoomOut",
    "ZoomTarget",
    "Comment",
    "type_and_enter",
    "section_pause",
    "segment_duration",
]
