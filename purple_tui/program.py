"""
Code Mode: program recording, editing, and playback.

Records keyboard actions from Play and Doodle modes as editable blocks.
Each block represents a single action (key press, arrow, control) with a
trailing gap that encodes the pause before the next action.

Pure logic with no UI dependencies. Used by build_mode.py (Code mode UI)
and purple_tui.py (recording tap).
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from .keyboard import (
    CharacterAction,
    NavigationAction,
    ControlAction,
    KeyAction,
    ModeAction,
)
from .demo.script import (
    DemoAction,
    TypeText,
    PressKey,
    SwitchMode,
    Pause,
)


# =============================================================================
# PAUSE LEVELS
# =============================================================================

# (max_seconds, gap_width_chars) - used for quantizing recorded timing
# and for up/down cycling in the editor
PAUSE_LEVELS = [
    (0.05, 0),    # simultaneous
    (0.2, 2),     # rapid rhythm ("tiny")
    (0.4, 4),     # natural typing ("short")
    (1.0, 8),     # deliberate pause ("medium")
    (2.0, 12),    # dramatic pause ("long")
]

NUM_PAUSE_LEVELS = len(PAUSE_LEVELS)


def quantize_pause(seconds: float) -> int:
    """Convert a pause duration to a gap level (0-4)."""
    for level, (threshold, _) in enumerate(PAUSE_LEVELS):
        if seconds < threshold:
            return level
    return NUM_PAUSE_LEVELS - 1


def gap_width(level: int) -> int:
    """Get the character width for a given gap level."""
    level = max(0, min(level, NUM_PAUSE_LEVELS - 1))
    return PAUSE_LEVELS[level][1]


def gap_duration(level: int) -> float:
    """Get the pause duration (midpoint of range) for a given gap level."""
    level = max(0, min(level, NUM_PAUSE_LEVELS - 1))
    if level == 0:
        return 0.0
    low = PAUSE_LEVELS[level - 1][0]
    high = PAUSE_LEVELS[level][0]
    return (low + high) / 2


# =============================================================================
# BLOCK TYPES AND DATA
# =============================================================================

class ProgramBlockType(Enum):
    KEY = "key"           # CharacterAction: a typed character
    ARROW = "arrow"       # NavigationAction: an arrow key
    CONTROL = "control"   # ControlAction: enter, backspace, space, tab
    EMOJI = "emoji"       # Emoji placed via Code mode (future)


# Row-based colors for KEY blocks (matching Doodle mode's keyboard rows)
QWERTY_ROW = set("qwertyuiop[]\\")
ASDF_ROW = set("asdfghjkl;'")
ZXCV_ROW = set("zxcvbnm,./")
NUMBER_ROW = set("1234567890-=")

KEY_COLOR_RED = "#BF4040"
KEY_COLOR_YELLOW = "#BFA040"
KEY_COLOR_BLUE = "#4060BF"
KEY_COLOR_GRAY = "#808080"

ARROW_COLOR = "#2d6a9e"
ENTER_COLOR = "#2d8a4e"
BACKSPACE_COLOR = "#c46b7b"
SPACE_COLOR = "#606060"
TAB_COLOR = "#606060"
EMOJI_COLOR = "#9b7bc4"

# Icons for control actions
CONTROL_ICONS = {
    "enter": "↵",
    "backspace": "⌫",
    "space": "␣",
    "tab": "⇥",
}

# Icons for arrow directions
ARROW_ICONS = {
    "up": "▲",
    "down": "▼",
    "left": "◀",
    "right": "▶",
}


def key_color(char: str) -> str:
    """Get the block color for a character key, based on keyboard row."""
    lower = char.lower()
    if lower in QWERTY_ROW:
        return KEY_COLOR_RED
    elif lower in ASDF_ROW:
        return KEY_COLOR_YELLOW
    elif lower in ZXCV_ROW:
        return KEY_COLOR_BLUE
    elif lower in NUMBER_ROW:
        return KEY_COLOR_GRAY
    return KEY_COLOR_GRAY


def control_color(action_name: str) -> str:
    """Get the block color for a control action."""
    if action_name == "enter":
        return ENTER_COLOR
    elif action_name == "backspace":
        return BACKSPACE_COLOR
    return SPACE_COLOR


@dataclass
class ProgramBlock:
    """A single block in a recorded program."""
    type: ProgramBlockType
    # Exactly one of these is set, depending on type:
    char: str = ""           # KEY: the character, EMOJI: the emoji
    direction: str = ""      # ARROW: up/down/left/right
    control: str = ""        # CONTROL: enter/backspace/space/tab
    gap_level: int = 1       # 0-4, index into PAUSE_LEVELS
    source_mode: str = ""    # "play" or "doodle"

    @property
    def icon(self) -> str:
        if self.type == ProgramBlockType.KEY:
            return self.char.upper() if len(self.char) == 1 else self.char
        elif self.type == ProgramBlockType.ARROW:
            return ARROW_ICONS.get(self.direction, "?")
        elif self.type == ProgramBlockType.CONTROL:
            return CONTROL_ICONS.get(self.control, "?")
        elif self.type == ProgramBlockType.EMOJI:
            return self.char
        return "?"

    @property
    def bg_color(self) -> str:
        if self.type == ProgramBlockType.KEY:
            return key_color(self.char)
        elif self.type == ProgramBlockType.ARROW:
            return ARROW_COLOR
        elif self.type == ProgramBlockType.CONTROL:
            return control_color(self.control)
        elif self.type == ProgramBlockType.EMOJI:
            return EMOJI_COLOR
        return KEY_COLOR_GRAY

    @property
    def total_width(self) -> int:
        """Total display width: icon section + gap section."""
        return 4 + gap_width(self.gap_level)

    def cycle_gap(self, direction: int) -> None:
        """Cycle gap level up (+1) or down (-1), clamping to valid range."""
        self.gap_level = max(0, min(NUM_PAUSE_LEVELS - 1,
                                     self.gap_level + direction))


# =============================================================================
# ACTION RECORDER
# =============================================================================

SESSION_TIMEOUT = 5.0    # seconds of inactivity before session resets
MAX_RECORDING_TIME = 30.0  # max recording duration in seconds

# Modes we record from (not Code mode itself)
RECORDABLE_MODES = {"play", "doodle"}


class ActionRecorder:
    """Records keyboard actions from Play and Doodle modes.

    Stores (action, mode, timestamp) tuples. Automatically resets
    after SESSION_TIMEOUT seconds of inactivity. Trims recordings
    older than MAX_RECORDING_TIME.

    Usage:
        recorder = ActionRecorder()
        recorder.record(action, "play")   # called from dispatch
        blocks = recorder.get_blocks()    # get editable blocks
        recorder.clear()                  # start fresh
    """

    def __init__(self, time_fn: Callable[[], float] | None = None):
        self._events: list[tuple[KeyAction, str, float]] = []
        self._time_fn = time_fn or time.monotonic

    def record(self, action: KeyAction, mode: str) -> None:
        """Record a keyboard action if it's from a recordable mode."""
        if mode not in RECORDABLE_MODES:
            return

        # Only record meaningful actions (not mode switches, shifts, etc.)
        if not isinstance(action, (CharacterAction, NavigationAction, ControlAction)):
            return

        # Skip key-up events for ControlAction (only record presses)
        if isinstance(action, ControlAction) and not action.is_down:
            return

        # Skip key repeats
        if isinstance(action, CharacterAction) and action.is_repeat:
            return
        if isinstance(action, NavigationAction) and action.is_repeat:
            return
        if isinstance(action, ControlAction) and action.is_repeat:
            return

        # Skip certain control actions that aren't useful to record
        if isinstance(action, ControlAction):
            if action.action not in ("enter", "backspace", "space", "tab"):
                return

        now = self._time_fn()

        # Session timeout: clear old events
        if self._events and (now - self._events[-1][2]) > SESSION_TIMEOUT:
            self._events.clear()

        self._events.append((action, mode, now))

        # Trim events older than MAX_RECORDING_TIME from the end
        if self._events:
            cutoff = now - MAX_RECORDING_TIME
            while self._events and self._events[0][2] < cutoff:
                self._events.pop(0)

    def get_blocks(self) -> list[ProgramBlock]:
        """Convert recorded events to ProgramBlock list."""
        if not self._events:
            return []

        blocks = []
        for i, (action, mode, ts) in enumerate(self._events):
            block = _action_to_block(action, mode)
            if block is None:
                continue

            # Calculate gap from previous event
            if i < len(self._events) - 1:
                next_ts = self._events[i + 1][2]
                pause = next_ts - ts
                block.gap_level = quantize_pause(pause)
            else:
                block.gap_level = 0  # last block has no trailing gap

            blocks.append(block)

        return blocks

    def has_events(self) -> bool:
        return bool(self._events)

    def clear(self) -> None:
        self._events.clear()

    @property
    def source_mode(self) -> str:
        """The mode most events were recorded in."""
        if not self._events:
            return "play"
        modes = [m for _, m, _ in self._events]
        # Return the most common mode
        play_count = modes.count("play")
        doodle_count = modes.count("doodle")
        return "doodle" if doodle_count > play_count else "play"


def _action_to_block(action: KeyAction, mode: str) -> ProgramBlock | None:
    """Convert a single KeyAction to a ProgramBlock."""
    if isinstance(action, CharacterAction):
        return ProgramBlock(
            type=ProgramBlockType.KEY,
            char=action.char,
            source_mode=mode,
        )
    elif isinstance(action, NavigationAction):
        return ProgramBlock(
            type=ProgramBlockType.ARROW,
            direction=action.direction,
            source_mode=mode,
        )
    elif isinstance(action, ControlAction):
        if action.action in ("enter", "backspace", "space", "tab"):
            return ProgramBlock(
                type=ProgramBlockType.CONTROL,
                control=action.action,
                source_mode=mode,
            )
    return None


# =============================================================================
# PLAYBACK: BLOCKS -> DEMO ACTIONS
# =============================================================================

def blocks_to_demo_actions(blocks: list[ProgramBlock],
                           target_mode: str = "play") -> list[DemoAction]:
    """Convert program blocks to DemoAction list for playback via DemoPlayer.

    Produces a sequence that:
    1. Switches to the target mode
    2. Dispatches each block's action with appropriate pauses
    """
    if not blocks:
        return []

    actions: list[DemoAction] = []

    # Switch to target mode first
    actions.append(SwitchMode(mode=target_mode, pause_after=0.3))

    for block in blocks:
        # Add the action
        if block.type == ProgramBlockType.KEY:
            actions.append(TypeText(
                text=block.char,
                delay_per_char=0.0,
                final_pause=0.0,
            ))
        elif block.type == ProgramBlockType.ARROW:
            actions.append(PressKey(
                key=block.direction,
                pause_after=0.0,
            ))
        elif block.type == ProgramBlockType.CONTROL:
            actions.append(PressKey(
                key=block.control,
                pause_after=0.0,
            ))
        elif block.type == ProgramBlockType.EMOJI:
            # Emoji dispatches as a character
            actions.append(TypeText(
                text=block.char,
                delay_per_char=0.0,
                final_pause=0.0,
            ))

        # Add pause for the trailing gap
        pause = gap_duration(block.gap_level)
        if pause > 0:
            actions.append(Pause(duration=pause))

    return actions


# =============================================================================
# SERIALIZATION
# =============================================================================

PROGRAMS_DIR = Path.home() / ".purple" / "programs"


def blocks_to_json(blocks: list[ProgramBlock], source_mode: str = "play") -> str:
    """Serialize program blocks to JSON string."""
    import datetime
    data = {
        "blocks": [_block_to_dict(b) for b in blocks],
        "source_mode": source_mode,
        "saved_at": datetime.datetime.now().isoformat(),
    }
    return json.dumps(data, indent=2)


def blocks_from_json(s: str) -> tuple[list[ProgramBlock], str]:
    """Deserialize program blocks from JSON string.

    Returns (blocks, source_mode).
    """
    data = json.loads(s)
    blocks = [_dict_to_block(d) for d in data.get("blocks", [])]
    source_mode = data.get("source_mode", "play")
    return blocks, source_mode


def save_program(blocks: list[ProgramBlock], slot: int,
                 source_mode: str = "play") -> bool:
    """Save a program to a numbered slot (1-9). Returns True on success."""
    if not 1 <= slot <= 9:
        return False
    try:
        PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
        path = PROGRAMS_DIR / f"slot-{slot}.json"
        path.write_text(blocks_to_json(blocks, source_mode))
        return True
    except OSError:
        return False


def load_program(slot: int) -> tuple[list[ProgramBlock], str] | None:
    """Load a program from a numbered slot (1-9).

    Returns (blocks, source_mode) or None if slot is empty.
    """
    if not 1 <= slot <= 9:
        return None
    path = PROGRAMS_DIR / f"slot-{slot}.json"
    if not path.exists():
        return None
    try:
        return blocks_from_json(path.read_text())
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def slot_occupied(slot: int) -> bool:
    """Check if a save slot has a program."""
    if not 1 <= slot <= 9:
        return False
    return (PROGRAMS_DIR / f"slot-{slot}.json").exists()


def _block_to_dict(block: ProgramBlock) -> dict:
    d = {"type": block.type.value, "gap": block.gap_level}
    if block.type == ProgramBlockType.KEY:
        d["char"] = block.char
    elif block.type == ProgramBlockType.ARROW:
        d["direction"] = block.direction
    elif block.type == ProgramBlockType.CONTROL:
        d["control"] = block.control
    elif block.type == ProgramBlockType.EMOJI:
        d["char"] = block.char
    if block.source_mode:
        d["mode"] = block.source_mode
    return d


def _dict_to_block(d: dict) -> ProgramBlock:
    block_type = ProgramBlockType(d["type"])
    return ProgramBlock(
        type=block_type,
        char=d.get("char", ""),
        direction=d.get("direction", ""),
        control=d.get("control", ""),
        gap_level=d.get("gap", 1),
        source_mode=d.get("mode", ""),
    )
