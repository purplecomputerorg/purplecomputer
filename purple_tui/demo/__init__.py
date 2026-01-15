"""Demo playback system for Purple Computer screencasts.

To run the demo:
    PURPLE_DEMO_AUTOSTART=1 ./scripts/run_local.sh
"""

from .script import (
    DemoAction,
    TypeText,
    PressKey,
    SwitchMode,
    Pause,
    Clear,
    ClearAll,
    PlayKeys,
    DrawPath,
    Comment,
)
from .player import DemoPlayer
from .default_script import DEMO_SCRIPT, DEMO_SCRIPT_SHORT


def get_demo_script() -> list:
    """Get the demo script to run."""
    return DEMO_SCRIPT


__all__ = [
    "DemoAction",
    "TypeText",
    "PressKey",
    "SwitchMode",
    "Pause",
    "Clear",
    "ClearAll",
    "PlayKeys",
    "DrawPath",
    "Comment",
    "DemoPlayer",
    "DEMO_SCRIPT",
    "DEMO_SCRIPT_SHORT",
    "get_demo_script",
]
