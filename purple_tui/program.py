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
from .playback.script import (
    PlaybackAction,
    TypeText,
    PressKey,
    SwitchMode,
    SwitchTarget,
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
    KEY = "key"               # CharacterAction: a typed character
    ARROW = "arrow"           # NavigationAction: an arrow key
    CONTROL = "control"       # ControlAction: enter, backspace, space, tab
    EMOJI = "emoji"           # Emoji placed via Code mode (future)
    REPEAT = "repeat"         # Repeat preceding section N times
    MODE_SWITCH = "mode_switch"  # Switch to a specific mode/sub-mode


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
REPEAT_COLOR = "#2d9e8a"  # teal

# MODE_SWITCH target constants
TARGET_PLAY_MUSIC = "play.music"
TARGET_PLAY_LETTERS = "play.letters"
TARGET_DOODLE_TEXT = "doodle.text"
TARGET_DOODLE_PAINT = "doodle.paint"
TARGET_EXPLORE = "explore"

ALL_TARGETS = [
    TARGET_PLAY_MUSIC,
    TARGET_PLAY_LETTERS,
    TARGET_DOODLE_TEXT,
    TARGET_DOODLE_PAINT,
    TARGET_EXPLORE,
]

TARGET_ICONS = {
    TARGET_PLAY_MUSIC: "♫",
    TARGET_PLAY_LETTERS: "Ab",
    TARGET_DOODLE_TEXT: "✎",
    TARGET_DOODLE_PAINT: "🖌",
    TARGET_EXPLORE: "?=",
}

TARGET_COLORS = {
    TARGET_PLAY_MUSIC: "#44DD44",
    TARGET_PLAY_LETTERS: "#44DDAA",
    TARGET_DOODLE_TEXT: "#DDAA44",
    TARGET_DOODLE_PAINT: "#DD44AA",
    TARGET_EXPLORE: "#44AADD",
}

TARGET_LABELS = {
    TARGET_PLAY_MUSIC: "Play (music)",
    TARGET_PLAY_LETTERS: "Play (letters)",
    TARGET_DOODLE_TEXT: "Doodle (text)",
    TARGET_DOODLE_PAINT: "Doodle (paint)",
    TARGET_EXPLORE: "Explore",
}

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
    repeat_count: int = 2    # REPEAT: how many times to play the section (2-99)
    gap_level: int = 1       # 0-4, index into PAUSE_LEVELS
    source_mode: str = ""    # "play" or "doodle"
    target: str = ""         # MODE_SWITCH: "play.music", "doodle.paint", etc.

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
        elif self.type == ProgramBlockType.REPEAT:
            return f"×{self.repeat_count}"
        elif self.type == ProgramBlockType.MODE_SWITCH:
            return TARGET_ICONS.get(self.target, "?")
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
        elif self.type == ProgramBlockType.REPEAT:
            return REPEAT_COLOR
        elif self.type == ProgramBlockType.MODE_SWITCH:
            return TARGET_COLORS.get(self.target, KEY_COLOR_GRAY)
        return KEY_COLOR_GRAY

    @property
    def total_width(self) -> int:
        """Total display width: icon section + gap section."""
        return 4 + gap_width(self.gap_level)

    def cycle_gap(self, direction: int) -> None:
        """Cycle gap level up (+1) or down (-1), clamping to valid range."""
        self.gap_level = max(0, min(NUM_PAUSE_LEVELS - 1,
                                     self.gap_level + direction))

    def cycle_repeat_count(self, direction: int) -> None:
        """Cycle repeat count up or down, clamping to 2-99."""
        self.repeat_count = max(2, min(99, self.repeat_count + direction))

    def cycle_target(self, direction: int) -> None:
        """Cycle MODE_SWITCH target through available targets."""
        if self.target not in ALL_TARGETS:
            self.target = ALL_TARGETS[0]
            return
        idx = ALL_TARGETS.index(self.target)
        idx = (idx + direction) % len(ALL_TARGETS)
        self.target = ALL_TARGETS[idx]


def action_to_block(action: KeyAction, mode: str) -> ProgramBlock | None:
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

def _block_to_playback_action(block: ProgramBlock) -> PlaybackAction | None:
    """Convert a single block to a PlaybackAction (without pause)."""
    if block.type == ProgramBlockType.KEY:
        return TypeText(text=block.char, delay_per_char=0.0, final_pause=0.0)
    elif block.type == ProgramBlockType.ARROW:
        return PressKey(key=block.direction, pause_after=0.0)
    elif block.type == ProgramBlockType.CONTROL:
        return PressKey(key=block.control, pause_after=0.0)
    elif block.type == ProgramBlockType.EMOJI:
        return TypeText(text=block.char, delay_per_char=0.0, final_pause=0.0)
    return None


def blocks_to_playback_actions(blocks: list[ProgramBlock]) -> list[PlaybackAction]:
    """Convert program blocks to PlaybackAction list for playback.

    MODE_SWITCH blocks emit SwitchTarget actions. If no MODE_SWITCH block
    is at position 0, a default SwitchTarget is emitted based on the
    first block's source_mode.

    Handles REPEAT blocks: a repeat block repeats all blocks since the
    previous repeat block (or from the start) N times total.

    Example: [A][B][×3] produces A B A B A B (3 iterations).
    """
    if not blocks:
        return []

    actions: list[PlaybackAction] = []

    # Determine initial target from first block
    first_target = _default_target_for_blocks(blocks)

    # If blocks don't start with MODE_SWITCH, emit initial SwitchTarget
    if blocks[0].type != ProgramBlockType.MODE_SWITCH:
        actions.append(SwitchTarget(target=first_target, pause_after=0.3))

    # Split blocks into sections delimited by REPEAT blocks
    # Then expand each section according to its repeat count
    section: list[ProgramBlock] = []

    for block in blocks:
        if block.type == ProgramBlockType.REPEAT:
            # Expand the current section repeat_count times
            count = block.repeat_count
            section_actions = _section_to_actions(section)
            for _ in range(count):
                actions.extend(section_actions)
            # Add the repeat block's own trailing gap
            pause = gap_duration(block.gap_level)
            if pause > 0:
                actions.append(Pause(duration=pause))
            section = []
        elif block.type == ProgramBlockType.MODE_SWITCH:
            # Flush current section, then emit SwitchTarget
            actions.extend(_section_to_actions(section))
            section = []
            actions.append(SwitchTarget(target=block.target, pause_after=0.3))
        else:
            section.append(block)

    # Remaining blocks after last repeat (or all blocks if no repeat)
    actions.extend(_section_to_actions(section))

    return actions


def _default_target_for_blocks(blocks: list[ProgramBlock]) -> str:
    """Determine the default target for a program based on its blocks."""
    for block in blocks:
        if block.type == ProgramBlockType.MODE_SWITCH:
            return block.target
        if block.source_mode == "doodle":
            return TARGET_DOODLE_TEXT
        if block.source_mode == "play":
            return TARGET_PLAY_MUSIC
        if block.source_mode == "explore":
            return TARGET_EXPLORE
    return TARGET_PLAY_MUSIC


def _section_to_actions(section: list[ProgramBlock]) -> list[PlaybackAction]:
    """Convert a section of blocks to playback actions (with pauses)."""
    actions = []
    for block in section:
        action = _block_to_playback_action(block)
        if action:
            actions.append(action)
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
    elif block.type == ProgramBlockType.REPEAT:
        d["count"] = block.repeat_count
    elif block.type == ProgramBlockType.MODE_SWITCH:
        d["target"] = block.target
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
        repeat_count=d.get("count", 2),
        gap_level=d.get("gap", 1),
        source_mode=d.get("mode", ""),
        target=d.get("target", ""),
    )
