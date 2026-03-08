"""
Code Mode: program recording, editing, and playback.

Records keyboard actions from Music, Art, and Play modes as editable blocks.
Six block types following a Scratch-inspired model: KEY, QUERY, STROKE, PAUSE,
REPEAT, MODE_SWITCH.

Every block renders as a uniform 5-char-wide, 3-row-tall cell. Timing is stored
as hidden metadata (recorded_gap_ms) with only explicit PAUSE blocks visible.

Pure logic with no UI dependencies. Used by code_room.py (Code mode UI)
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
    RoomAction,
)
from .playback.script import (
    PlaybackAction,
    TypeText,
    PressKey,
    SwitchRoom,
    SwitchTarget,
    Pause,
)


# =============================================================================
# CONSTANTS
# =============================================================================

BLOCK_WIDTH = 5   # every block is exactly 5 chars wide
BLOCK_ROWS = 3    # every block is exactly 3 rows tall

# Default tempo for blocks with no recorded timing (typed in code mode)
DEFAULT_TEMPO_MS = 150

# Threshold for inserting explicit PAUSE blocks during recording conversion
PAUSE_THRESHOLD_MS = 300

# Preset PAUSE durations (seconds), cycled with up/down
PAUSE_PRESETS = [0.25, 0.5, 1.0, 2.0]

# Row-based colors for KEY blocks (matching Art mode's keyboard rows)
QWERTY_ROW = set("qwertyuiop[]\\")
ASDF_ROW = set("asdfghjkl;'")
ZXCV_ROW = set("zxcvbnm,./")
NUMBER_ROW = set("1234567890-=")

KEY_COLOR_RED = "#BF4040"
KEY_COLOR_YELLOW = "#BFA040"
KEY_COLOR_BLUE = "#4060BF"
KEY_COLOR_GRAY = "#808080"

CONTROL_COLOR = "#2d6a9e"
QUERY_COLOR = "#44AADD"
STROKE_COLOR = "#2d6a9e"
PAUSE_COLOR = "#606060"
REPEAT_COLOR = "#2d9e8a"

# MODE_SWITCH target constants
TARGET_MUSIC_MUSIC = "music.music"
TARGET_MUSIC_LETTERS = "music.letters"
TARGET_ART_TEXT = "art.text"
TARGET_ART_PAINT = "art.paint"
TARGET_PLAY = "play"

ALL_TARGETS = [
    TARGET_MUSIC_MUSIC,
    TARGET_MUSIC_LETTERS,
    TARGET_ART_TEXT,
    TARGET_ART_PAINT,
    TARGET_PLAY,
]

# Room-level grouping: each room has a default target and list of all targets
ROOMS = {
    "music": {
        "default": TARGET_MUSIC_MUSIC,
        "targets": [TARGET_MUSIC_MUSIC, TARGET_MUSIC_LETTERS],
        "label": "Music",
    },
    "art": {
        "default": TARGET_ART_PAINT,
        "targets": [TARGET_ART_PAINT, TARGET_ART_TEXT],
        "label": "Art",
    },
    "play": {
        "default": TARGET_PLAY,
        "targets": [TARGET_PLAY],
        "label": "Play",
    },
}

ROOM_ORDER = ["play", "music", "art"]

def target_room(target: str) -> str:
    """Get the room name for a target (e.g., 'music.music' -> 'music')."""
    return target.split(".")[0]

def default_target_for_room(room: str) -> str:
    """Get the default target for a room."""
    return ROOMS.get(room, {}).get("default", TARGET_MUSIC_MUSIC)

# Room-level icons (matching the title bar Nerd Font icons)
from .constants import ICON_MUSIC, ICON_PALETTE, ICON_CHAT

ROOM_ICONS = {
    "music": ICON_MUSIC,
    "art": ICON_PALETTE,
    "play": ICON_CHAT,
}

# Per-target icons (shown inside MODE_SWITCH blocks)
TARGET_ICONS = {
    TARGET_MUSIC_MUSIC: ICON_MUSIC,
    TARGET_MUSIC_LETTERS: ICON_MUSIC,
    TARGET_ART_TEXT: ICON_PALETTE,
    TARGET_ART_PAINT: ICON_PALETTE,
    TARGET_PLAY: ICON_CHAT,
}

# Room-level colors (one color per room)
ROOM_COLORS = {
    "music": "#44DD44",
    "art": "#DD8844",
    "play": "#44AADD",
}

TARGET_COLORS = {
    TARGET_MUSIC_MUSIC: "#44DD44",
    TARGET_MUSIC_LETTERS: "#44DD44",
    TARGET_ART_TEXT: "#DD8844",
    TARGET_ART_PAINT: "#DD8844",
    TARGET_PLAY: "#44AADD",
}

# Sub-mode labels (shown when non-default mode is selected)
MODE_LABELS = {
    TARGET_MUSIC_MUSIC: "Music",
    TARGET_MUSIC_LETTERS: "Letters",
    TARGET_ART_TEXT: "Text",
    TARGET_ART_PAINT: "Paint",
    TARGET_PLAY: "",
}

TARGET_LABELS = {
    TARGET_MUSIC_MUSIC: "Music",
    TARGET_MUSIC_LETTERS: "Music (letters)",
    TARGET_ART_TEXT: "Art (text)",
    TARGET_ART_PAINT: "Art",
    TARGET_PLAY: "Play",
}

# Icons for control keys (KEY blocks with is_control=True)
CONTROL_ICONS = {
    "enter": "\U000f0311",
    "backspace": "\u232b",
    "space": "\u2423",
    "tab": "\u21e5",
}

# Icons for stroke directions
DIRECTION_ICONS = {
    "up": "\u25b2",
    "down": "\u25bc",
    "left": "\u25c0",
    "right": "\u25b6",
}


# =============================================================================
# BLOCK TYPES AND DATA
# =============================================================================

class ProgramBlockType(Enum):
    KEY = "key"               # Single key press (char or control key)
    QUERY = "query"           # Complete Play query
    STROKE = "stroke"         # Art paint direction + distance
    PAUSE = "pause"           # Explicit visible wait
    REPEAT = "repeat"         # Repeat preceding line N times
    MODE_SWITCH = "mode_switch"  # Switch target mode


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


@dataclass
class ProgramBlock:
    """A single block in a recorded program.

    Every block renders as a uniform 5-char-wide, 3-row-tall cell.
    """
    type: ProgramBlockType

    # KEY fields
    char: str = ""              # the character, or control key name ("enter", etc.)
    is_control: bool = False    # True for enter/backspace/space/tab

    # QUERY fields
    query_text: str = ""        # full query string

    # STROKE fields
    direction: str = ""         # up/down/left/right
    distance: int = 1           # number of steps

    # PAUSE fields
    duration: float = 0.5       # seconds (one of PAUSE_PRESETS)

    # REPEAT fields
    repeat_count: int = 2       # 2-99

    # MODE_SWITCH fields
    target: str = ""            # "music.music", "art.paint", etc.

    # Hidden timing metadata (not displayed, used for playback)
    recorded_gap_ms: int = 0    # exact milliseconds from F5 recording

    @property
    def display_width(self) -> int:
        """Width in chars for rendering this block."""
        if self.type == ProgramBlockType.QUERY:
            return max(BLOCK_WIDTH, len(self.query_text) + 2)
        return BLOCK_WIDTH

    @property
    def icon(self) -> str:
        """Icon text for the center of the block."""
        if self.type == ProgramBlockType.KEY:
            if self.is_control:
                return CONTROL_ICONS.get(self.char, "?")
            return self.char.upper() if len(self.char) == 1 else self.char
        elif self.type == ProgramBlockType.QUERY:
            return self.query_text
        elif self.type == ProgramBlockType.STROKE:
            arrow = DIRECTION_ICONS.get(self.direction, "?")
            return f"{arrow}{self.distance}"
        elif self.type == ProgramBlockType.PAUSE:
            return "\u23f8"
        elif self.type == ProgramBlockType.REPEAT:
            return f"x{self.repeat_count}"
        elif self.type == ProgramBlockType.MODE_SWITCH:
            room = target_room(self.target)
            room_info = ROOMS.get(room, {})
            icon = ROOM_ICONS.get(room, "?")
            # Show sub-mode hint for non-default modes
            if self.target != room_info.get("default"):
                label = MODE_LABELS.get(self.target, "")
                if label:
                    return f"{icon}{label[:2]}"
            return icon
        return "?"

    @property
    def bg_color(self) -> str:
        if self.type == ProgramBlockType.KEY:
            if self.is_control:
                return CONTROL_COLOR
            return key_color(self.char)
        elif self.type == ProgramBlockType.QUERY:
            return QUERY_COLOR
        elif self.type == ProgramBlockType.STROKE:
            return STROKE_COLOR
        elif self.type == ProgramBlockType.PAUSE:
            return PAUSE_COLOR
        elif self.type == ProgramBlockType.REPEAT:
            return REPEAT_COLOR
        elif self.type == ProgramBlockType.MODE_SWITCH:
            return TARGET_COLORS.get(self.target, KEY_COLOR_GRAY)
        return KEY_COLOR_GRAY

    def cycle_pause_duration(self, direction: int) -> None:
        """Cycle PAUSE duration through presets."""
        if self.type != ProgramBlockType.PAUSE:
            return
        try:
            idx = PAUSE_PRESETS.index(self.duration)
        except ValueError:
            idx = 1  # default to 0.5
        idx = max(0, min(len(PAUSE_PRESETS) - 1, idx + direction))
        self.duration = PAUSE_PRESETS[idx]

    def cycle_stroke_distance(self, direction: int) -> None:
        """Cycle STROKE distance up or down, clamping to 1-99."""
        if self.type != ProgramBlockType.STROKE:
            return
        self.distance = max(1, min(99, self.distance + direction))

    def cycle_repeat_count(self, direction: int) -> None:
        """Cycle repeat count up or down, clamping to 2-99."""
        self.repeat_count = max(2, min(99, self.repeat_count + direction))

    def cycle_target(self, direction: int) -> None:
        """Cycle MODE_SWITCH target through rooms (using default targets)."""
        room_defaults = [ROOMS[r]["default"] for r in ROOM_ORDER]
        current_room = target_room(self.target)
        if current_room in ROOM_ORDER:
            idx = ROOM_ORDER.index(current_room)
        else:
            idx = 0
        idx = (idx + direction) % len(ROOM_ORDER)
        self.target = room_defaults[idx]


def action_to_block(action: KeyAction, room: str) -> ProgramBlock | None:
    """Convert a single KeyAction to a ProgramBlock (simple, non-mode-aware)."""
    if isinstance(action, CharacterAction):
        return ProgramBlock(
            type=ProgramBlockType.KEY,
            char=action.char,
        )
    elif isinstance(action, NavigationAction):
        return ProgramBlock(
            type=ProgramBlockType.STROKE,
            direction=action.direction,
            distance=1,
        )
    elif isinstance(action, ControlAction):
        if action.action in ("enter", "backspace", "space", "tab"):
            return ProgramBlock(
                type=ProgramBlockType.KEY,
                char=action.action,
                is_control=True,
            )
    return None


# =============================================================================
# PLAYBACK: BLOCKS -> DEMO ACTIONS
# =============================================================================

def _block_to_playback_action(block: ProgramBlock) -> PlaybackAction | None:
    """Convert a single block to a PlaybackAction (without pause)."""
    if block.type == ProgramBlockType.KEY:
        if block.is_control:
            return PressKey(key=block.char, pause_after=0.0)
        return TypeText(text=block.char, delay_per_char=0.0, final_pause=0.0)
    elif block.type == ProgramBlockType.QUERY:
        return TypeText(text=block.query_text, delay_per_char=0.05, final_pause=0.0)
    elif block.type == ProgramBlockType.STROKE:
        # Expanded during section conversion
        return None
    elif block.type == ProgramBlockType.PAUSE:
        return Pause(duration=block.duration)
    return None


def _gap_pause(block: ProgramBlock) -> float:
    """Get the inter-block pause duration from recorded_gap_ms."""
    if block.recorded_gap_ms > 0:
        return block.recorded_gap_ms / 1000.0
    return DEFAULT_TEMPO_MS / 1000.0


def blocks_to_playback_actions(blocks: list[ProgramBlock]) -> list[PlaybackAction]:
    """Convert program blocks to PlaybackAction list for playback.

    MODE_SWITCH blocks emit SwitchTarget actions. REPEAT blocks repeat all
    blocks since the previous repeat block N times total.
    """
    if not blocks:
        return []

    actions: list[PlaybackAction] = []

    # Determine initial target from first block
    first_target = _default_target_for_blocks(blocks)

    # If blocks don't start with MODE_SWITCH, emit initial SwitchTarget
    if blocks[0].type != ProgramBlockType.MODE_SWITCH:
        actions.append(SwitchTarget(target=first_target, pause_after=0.3))

    section: list[ProgramBlock] = []

    for block in blocks:
        if block.type == ProgramBlockType.REPEAT:
            count = block.repeat_count
            section_actions = _section_to_actions(section)
            for _ in range(count):
                actions.extend(section_actions)
            gap = _gap_pause(block)
            if gap > 0:
                actions.append(Pause(duration=gap))
            section = []
        elif block.type == ProgramBlockType.MODE_SWITCH:
            actions.extend(_section_to_actions(section))
            section = []
            actions.append(SwitchTarget(target=block.target, pause_after=0.3))
        else:
            section.append(block)

    # Remaining blocks after last repeat
    actions.extend(_section_to_actions(section))

    return actions


def _default_target_for_blocks(blocks: list[ProgramBlock]) -> str:
    """Determine the default target for a program based on its blocks."""
    for block in blocks:
        if block.type == ProgramBlockType.MODE_SWITCH:
            return block.target
    return TARGET_MUSIC_MUSIC


def _section_to_actions(section: list[ProgramBlock]) -> list[PlaybackAction]:
    """Convert a section of blocks to playback actions (with pauses)."""
    actions = []
    for block in section:
        if block.type == ProgramBlockType.PAUSE:
            actions.append(Pause(duration=block.duration))
            continue

        if block.type == ProgramBlockType.STROKE:
            # Expand stroke into N arrow presses
            for _ in range(block.distance):
                actions.append(PressKey(key=block.direction, pause_after=0.05))
            gap = _gap_pause(block)
            if gap > 0:
                actions.append(Pause(duration=gap))
            continue

        if block.type == ProgramBlockType.QUERY:
            # Type the query text then press enter
            actions.append(TypeText(
                text=block.query_text,
                delay_per_char=0.05,
                final_pause=0.0,
            ))
            actions.append(PressKey(key="enter", pause_after=0.0))
            gap = _gap_pause(block)
            if gap > 0:
                actions.append(Pause(duration=gap))
            continue

        action = _block_to_playback_action(block)
        if action:
            actions.append(action)
            gap = _gap_pause(block)
            if gap > 0:
                actions.append(Pause(duration=gap))

    return actions


# =============================================================================
# SERIALIZATION
# =============================================================================

PROGRAMS_DIR = Path.home() / ".purple" / "programs"


def blocks_to_json(blocks: list[ProgramBlock], source_room: str = "music") -> str:
    """Serialize program blocks to JSON string (version 2 format)."""
    import datetime
    data = {
        "version": 2,
        "blocks": [_block_to_dict(b) for b in blocks],
        "source_room": source_room,
        "saved_at": datetime.datetime.now().isoformat(),
    }
    return json.dumps(data, indent=2)


def blocks_from_json(s: str) -> tuple[list[ProgramBlock], str]:
    """Deserialize program blocks from JSON string.

    Handles both v1 and v2 formats. Returns (blocks, source_room).
    """
    data = json.loads(s)
    version = data.get("version", 1)
    source_room = data.get("source_room", "music")

    if version == 1:
        blocks = _migrate_v1_blocks(data.get("blocks", []))
    else:
        blocks = [_dict_to_block(d) for d in data.get("blocks", [])]

    return blocks, source_room


def save_program(blocks: list[ProgramBlock], slot: int,
                 source_room: str = "music") -> bool:
    """Save a program to a numbered slot (1-9). Returns True on success."""
    if not 1 <= slot <= 9:
        return False
    try:
        PROGRAMS_DIR.mkdir(parents=True, exist_ok=True)
        path = PROGRAMS_DIR / f"slot-{slot}.json"
        path.write_text(blocks_to_json(blocks, source_room))
        return True
    except OSError:
        return False


def load_program(slot: int) -> tuple[list[ProgramBlock], str] | None:
    """Load a program from a numbered slot (1-9).

    Returns (blocks, source_room) or None if slot is empty.
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
    """Serialize a v2 ProgramBlock to dict."""
    d = {"type": block.type.value}
    if block.type == ProgramBlockType.KEY:
        d["char"] = block.char
        if block.is_control:
            d["is_control"] = True
    elif block.type == ProgramBlockType.QUERY:
        d["query_text"] = block.query_text
    elif block.type == ProgramBlockType.STROKE:
        d["direction"] = block.direction
        d["distance"] = block.distance
    elif block.type == ProgramBlockType.PAUSE:
        d["duration"] = block.duration
    elif block.type == ProgramBlockType.REPEAT:
        d["repeat_count"] = block.repeat_count
    elif block.type == ProgramBlockType.MODE_SWITCH:
        d["target"] = block.target
    if block.recorded_gap_ms > 0:
        d["gap_ms"] = block.recorded_gap_ms
    return d


def _dict_to_block(d: dict) -> ProgramBlock:
    """Deserialize a v2 dict to ProgramBlock."""
    block_type = ProgramBlockType(d["type"])
    return ProgramBlock(
        type=block_type,
        char=d.get("char", ""),
        is_control=d.get("is_control", False),
        query_text=d.get("query_text", ""),
        direction=d.get("direction", ""),
        distance=d.get("distance", 1),
        duration=d.get("duration", 0.5),
        repeat_count=d.get("repeat_count", 2),
        target=d.get("target", ""),
        recorded_gap_ms=d.get("gap_ms", 0),
    )


# =============================================================================
# V1 MIGRATION
# =============================================================================

# Old v1 pause levels: (max_seconds, gap_width_chars)
_V1_PAUSE_LEVELS = [
    (0.05, 0),    # simultaneous
    (0.2, 2),     # rapid
    (0.4, 4),     # natural
    (1.0, 8),     # deliberate
    (2.0, 12),    # dramatic
]


def _v1_gap_to_ms(gap_level: int) -> int:
    """Convert v1 gap_level to recorded_gap_ms using midpoint durations."""
    gap_level = max(0, min(len(_V1_PAUSE_LEVELS) - 1, gap_level))
    if gap_level == 0:
        return 0
    low = _V1_PAUSE_LEVELS[gap_level - 1][0]
    high = _V1_PAUSE_LEVELS[gap_level][0]
    return int(((low + high) / 2) * 1000)


def _migrate_v1_blocks(v1_blocks: list[dict]) -> list[ProgramBlock]:
    """Migrate v1 block dicts to v2 ProgramBlock list.

    Conversions:
    - ARROW blocks in paint context become STROKE blocks
    - CONTROL blocks become KEY with is_control=True
    - EMOJI blocks become KEY blocks
    - LINE_BREAK blocks are dropped
    - gap_level becomes recorded_gap_ms
    - Auto-collapsed blocks (count > 1) are expanded into N blocks
    - Large gaps (> 300ms) insert explicit PAUSE blocks
    """
    result = []
    current_target = ""

    for d in v1_blocks:
        v1_type = d.get("type", "")
        gap_level = d.get("gap", 1)
        gap_ms = _v1_gap_to_ms(gap_level)
        count = d.get("count", 1)
        room = d.get("room", d.get("mode", ""))

        if v1_type == "mode_switch":
            target = d.get("target", "")
            current_target = target
            result.append(ProgramBlock(
                type=ProgramBlockType.MODE_SWITCH,
                target=target,
                recorded_gap_ms=gap_ms,
            ))
            continue

        if v1_type == "line_break":
            # Dropped in v2
            continue

        if v1_type == "key":
            char = d.get("char", "")
            block = ProgramBlock(
                type=ProgramBlockType.KEY,
                char=char,
                recorded_gap_ms=gap_ms,
            )
            # Expand auto-collapsed blocks
            for _ in range(count):
                result.append(ProgramBlock(
                    type=block.type, char=block.char,
                    recorded_gap_ms=block.recorded_gap_ms,
                ))
            _maybe_insert_pause(result, gap_ms)
            continue

        if v1_type == "arrow":
            direction = d.get("direction", "")
            if current_target == TARGET_ART_PAINT:
                # Merge consecutive same-direction arrows into STROKE
                # For migration, each arrow becomes distance 1; merging happens in recording
                block = ProgramBlock(
                    type=ProgramBlockType.STROKE,
                    direction=direction,
                    distance=count,
                    recorded_gap_ms=gap_ms,
                )
                result.append(block)
            else:
                # Non-paint arrows: not recorded in v2 (navigation only)
                # But preserve them as STROKEs for compatibility
                block = ProgramBlock(
                    type=ProgramBlockType.STROKE,
                    direction=direction,
                    distance=count,
                    recorded_gap_ms=gap_ms,
                )
                result.append(block)
            _maybe_insert_pause(result, gap_ms)
            continue

        if v1_type == "control":
            control_name = d.get("control", "")
            block = ProgramBlock(
                type=ProgramBlockType.KEY,
                char=control_name,
                is_control=True,
                recorded_gap_ms=gap_ms,
            )
            for _ in range(count):
                result.append(ProgramBlock(
                    type=block.type, char=block.char,
                    is_control=block.is_control,
                    recorded_gap_ms=block.recorded_gap_ms,
                ))
            _maybe_insert_pause(result, gap_ms)
            continue

        if v1_type == "emoji":
            char = d.get("char", "")
            block = ProgramBlock(
                type=ProgramBlockType.KEY,
                char=char,
                recorded_gap_ms=gap_ms,
            )
            result.append(block)
            _maybe_insert_pause(result, gap_ms)
            continue

        if v1_type == "repeat":
            repeat_count = d.get("repeat_count", d.get("count", 2))
            result.append(ProgramBlock(
                type=ProgramBlockType.REPEAT,
                repeat_count=repeat_count,
                recorded_gap_ms=gap_ms,
            ))
            continue

    return result


def _maybe_insert_pause(blocks: list[ProgramBlock], gap_ms: int) -> None:
    """Insert an explicit PAUSE block if the gap is large enough."""
    if gap_ms >= PAUSE_THRESHOLD_MS and blocks:
        # Find the closest preset
        gap_sec = gap_ms / 1000.0
        closest = min(PAUSE_PRESETS, key=lambda p: abs(p - gap_sec))
        blocks.append(ProgramBlock(
            type=ProgramBlockType.PAUSE,
            duration=closest,
        ))
