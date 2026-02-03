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
    """Get the demo script to run.

    Uses the AI-generated script if available, otherwise falls back
    to the default hand-crafted demo.
    """
    try:
        from .ai_generated_script import AI_DRAWING
        return AI_DRAWING
    except ImportError:
        return DEMO_SCRIPT


def get_speed_multiplier() -> float:
    """Get the speed multiplier for demo playback.

    AI-generated demos include a calculated speed multiplier to hit
    a target playback duration. Returns 1.0 if no AI script is installed.
    """
    try:
        from .ai_generated_script import SPEED_MULTIPLIER
        return SPEED_MULTIPLIER
    except ImportError:
        return 1.0


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
    "get_speed_multiplier",
]
