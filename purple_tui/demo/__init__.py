"""Demo playback system for Purple Computer screencasts.

To run the demo:
    PURPLE_DEMO_AUTOSTART=1 ./scripts/run_local.sh
"""

import importlib
import json
from pathlib import Path

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
    SetSpeed,
    Comment,
)
from .player import DemoPlayer
from .default_script import DEMO_SCRIPT, DEMO_SCRIPT_SHORT


def _load_composition(path: Path) -> list:
    """Load a composed demo from demo.json.

    Each entry names a segment module in purple_tui.demo.segments.
    A SetSpeed action is inserted before each segment.
    """
    entries = json.loads(path.read_text())
    script: list[DemoAction] = [ClearAll()]
    for entry in entries:
        name = entry["segment"]
        mod = importlib.import_module(f".segments.{name}", package="purple_tui.demo")
        speed = entry.get("speed")
        if speed is None:
            speed = getattr(mod, "SPEED_MULTIPLIER", 1.0)
        script.append(SetSpeed(multiplier=speed))
        script.extend(mod.SEGMENT)
    return script


def get_demo_script() -> list:
    """Get the demo script to run.

    Priority:
    1. demo.json composition (if it exists)
    2. AI-generated script (ai_generated_script.py)
    3. Default hand-crafted demo
    """
    demo_json = Path(__file__).parent / "demo.json"
    if demo_json.exists():
        return _load_composition(demo_json)
    try:
        from .ai_generated_script import AI_DRAWING
        return AI_DRAWING
    except ImportError:
        return DEMO_SCRIPT


def get_speed_multiplier() -> float:
    """Get the speed multiplier for demo playback.

    Returns 1.0 when composition mode is active (speed is handled
    per-segment via SetSpeed actions). Otherwise uses the AI-generated
    script's multiplier if available.
    """
    demo_json = Path(__file__).parent / "demo.json"
    if demo_json.exists():
        return 1.0
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
    "SetSpeed",
    "Comment",
    "DemoPlayer",
    "DEMO_SCRIPT",
    "DEMO_SCRIPT_SHORT",
    "get_demo_script",
    "get_speed_multiplier",
]
