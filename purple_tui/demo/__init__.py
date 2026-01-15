"""Demo playback system for Purple Computer screencasts.

To run a specific demo, set PURPLE_DEMO_NAME environment variable:
    PURPLE_DEMO_NAME=magic_show PURPLE_DEMO_AUTOSTART=1 ./scripts/run_local.sh

Available demos:
    - default: The default demo (from default_script.py)
    - short: Quick version of default demo
    - magic_show: Color mixing showcase (~60s)
    - smiley_symphony: Play mode smiley drawing (~55s)
    - rainbow_explorer: Full color palette demo (~70s)
    - story_time: Narrative demo with speech (~65s)
    - quick_punchy: Fast highlights only (~35s)
"""

import os

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
from .demo_options import (
    DEMO_OPTION_1,
    DEMO_OPTION_2,
    DEMO_OPTION_3,
    DEMO_OPTION_4,
    DEMO_OPTION_5,
)

# All available demos by name
DEMO_SCRIPTS = {
    "default": DEMO_SCRIPT,
    "short": DEMO_SCRIPT_SHORT,
    "magic_show": DEMO_OPTION_1,
    "smiley_symphony": DEMO_OPTION_2,
    "rainbow_explorer": DEMO_OPTION_3,
    "story_time": DEMO_OPTION_4,
    "quick_punchy": DEMO_OPTION_5,
}


def get_demo_script() -> list:
    """Get the demo script to run based on PURPLE_DEMO_NAME env var."""
    name = os.environ.get("PURPLE_DEMO_NAME", "default")
    if name not in DEMO_SCRIPTS:
        print(f"Warning: Unknown demo '{name}', using 'default'")
        print(f"Available: {', '.join(DEMO_SCRIPTS.keys())}")
        name = "default"
    return DEMO_SCRIPTS[name]


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
    "DEMO_SCRIPTS",
    "get_demo_script",
]
