"""Demo playback system for Purple Computer screencasts."""

from .script import (
    DemoAction,
    TypeText,
    PressKey,
    SwitchMode,
    Pause,
    Clear,
    PlayKeys,
    DrawPath,
    Comment,
)
from .player import DemoPlayer
from .default_script import DEMO_SCRIPT, DEMO_SCRIPT_SHORT

__all__ = [
    "DemoAction",
    "TypeText",
    "PressKey",
    "SwitchMode",
    "Pause",
    "Clear",
    "PlayKeys",
    "DrawPath",
    "Comment",
    "DemoPlayer",
    "DEMO_SCRIPT",
    "DEMO_SCRIPT_SHORT",
]
