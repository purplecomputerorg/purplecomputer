"""
Recording: capture keypresses in a single room for "Watch me!" in Code mode.

Kids press Enter on an empty Code mode canvas (or use Tab menu) to start
"Watch me!", pick a room, play in that room, then press F4 to return.
Captured events become editable blocks in the Code canvas.

Mode-aware conversion: Play events buffer into QUERY blocks, Art paint
arrows merge into STROKE blocks, and gaps > 300ms become explicit PAUSE blocks.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .keyboard import (
    CharacterAction,
    NavigationAction,
    ControlAction,
    KeyAction,
)
from .program import (
    ProgramBlock,
    ProgramBlockType,
    PAUSE_THRESHOLD_MS,
    PAUSE_PRESETS,
    TARGET_MUSIC_MUSIC,
    TARGET_MUSIC_LETTERS,
    TARGET_ART_TEXT,
    TARGET_ART_PAINT,
    TARGET_PLAY,
)


class RecordingState(Enum):
    IDLE = "idle"
    RECORDING = "recording"


def _room_to_target(room_name: str, mode: str = "") -> str:
    """Convert a mode name and optional mode to a target string."""
    if room_name == "music":
        if mode == "letters":
            return TARGET_MUSIC_LETTERS
        return TARGET_MUSIC_MUSIC
    elif room_name == "art":
        if mode == "text":
            return TARGET_ART_TEXT
        return TARGET_ART_PAINT
    elif room_name == "play":
        return TARGET_PLAY
    return TARGET_MUSIC_MUSIC


@dataclass
class RecordedEvent:
    """A single recorded event with context."""
    action: KeyAction
    room_name: str
    mode: str
    timestamp: float


class Recording:
    """A completed or in-progress recording of keyboard events."""

    def __init__(self):
        self.events: list[RecordedEvent] = []

    def add_event(self, action: KeyAction, room_name: str,
                  mode: str = "", timestamp: float = 0.0) -> None:
        self.events.append(RecordedEvent(
            action=action,
            room_name=room_name,
            mode=mode,
            timestamp=timestamp,
        ))

    def to_blocks(self, target: str, instrument: str = "") -> list[ProgramBlock]:
        """Convert recorded events to ProgramBlock list for a single room.

        Prepends a MODE_SWITCH block with the given target, then processes
        all events as that single mode.

        Mode-aware conversion:
        - Music/Art text: each action becomes a KEY block
        - Play: characters buffer into QUERY blocks, Enter finalizes.
          Backspace edits the buffer. Net result is captured, not editing journey.
        - Art paint: consecutive same-direction arrows merge into STROKE blocks.
          Character keys become KEY blocks (color selection).
        - Post-pass: inserts PAUSE blocks for gaps > 300ms
        """
        if not self.events:
            return []

        blocks: list[ProgramBlock] = []

        # Prepend MODE_SWITCH for the target room
        blocks.append(ProgramBlock(
            type=ProgramBlockType.MODE_SWITCH,
            target=target,
            instrument=instrument,
        ))

        query_buf = ""

        for i, event in enumerate(self.events):
            # Calculate gap_ms to next event
            gap_ms = 0
            if i < len(self.events) - 1:
                gap_ms = int((self.events[i + 1].timestamp - event.timestamp) * 1000)

            action = event.action

            # Play room: buffer characters into QUERY blocks
            if target == TARGET_PLAY:
                if isinstance(action, CharacterAction):
                    query_buf += action.char
                elif isinstance(action, ControlAction):
                    if action.action == "enter" and query_buf:
                        # Finalize query
                        blocks.append(ProgramBlock(
                            type=ProgramBlockType.QUERY,
                            query_text=query_buf,
                            recorded_gap_ms=gap_ms,
                        ))
                        query_buf = ""
                    elif action.action == "backspace" and query_buf:
                        query_buf = query_buf[:-1]
                    elif action.action in ("space",):
                        query_buf += " "
                continue

            # Art paint mode: arrows merge into STROKE, chars are KEY
            if target == TARGET_ART_PAINT:
                if isinstance(action, NavigationAction):
                    if (blocks and blocks[-1].type == ProgramBlockType.STROKE
                            and blocks[-1].direction == action.direction):
                        blocks[-1].distance += 1
                        blocks[-1].recorded_gap_ms = gap_ms
                    else:
                        blocks.append(ProgramBlock(
                            type=ProgramBlockType.STROKE,
                            direction=action.direction,
                            distance=1,
                            recorded_gap_ms=gap_ms,
                        ))
                    continue
                elif isinstance(action, CharacterAction):
                    blocks.append(ProgramBlock(
                        type=ProgramBlockType.KEY,
                        char=action.char,
                        recorded_gap_ms=gap_ms,
                    ))
                    continue
                elif isinstance(action, ControlAction):
                    if action.action in ("enter", "backspace", "space", "tab"):
                        blocks.append(ProgramBlock(
                            type=ProgramBlockType.KEY,
                            char=action.action,
                            is_control=True,
                            recorded_gap_ms=gap_ms,
                        ))
                    continue

            # Music music/letters, Art text: simple KEY blocks
            if isinstance(action, CharacterAction):
                blocks.append(ProgramBlock(
                    type=ProgramBlockType.KEY,
                    char=action.char,
                    recorded_gap_ms=gap_ms,
                ))
            elif isinstance(action, ControlAction):
                if action.action in ("enter", "backspace", "space", "tab"):
                    blocks.append(ProgramBlock(
                        type=ProgramBlockType.KEY,
                        char=action.action,
                        is_control=True,
                        recorded_gap_ms=gap_ms,
                    ))
            # NavigationAction in non-paint modes: not recorded

        # Flush remaining play buffer
        if query_buf:
            blocks.append(ProgramBlock(
                type=ProgramBlockType.QUERY,
                query_text=query_buf,
            ))

        # Post-pass: insert PAUSE blocks for large gaps
        blocks = self._insert_pauses(blocks)

        return blocks

    def _insert_pauses(self, blocks: list[ProgramBlock]) -> list[ProgramBlock]:
        """Post-pass: insert explicit PAUSE blocks for large gaps.

        For gaps >= PAUSE_THRESHOLD_MS, insert a PAUSE block and zero
        out the recorded_gap_ms on the preceding block.
        """
        result = []
        for block in blocks:
            result.append(block)
            if (block.recorded_gap_ms >= PAUSE_THRESHOLD_MS
                    and block.type != ProgramBlockType.MODE_SWITCH
                    and block.type != ProgramBlockType.PAUSE):
                gap_sec = block.recorded_gap_ms / 1000.0
                closest = min(PAUSE_PRESETS, key=lambda p: abs(p - gap_sec))
                result.append(ProgramBlock(
                    type=ProgramBlockType.PAUSE,
                    duration=closest,
                ))
                block.recorded_gap_ms = 0
        return result

    def is_empty(self) -> bool:
        return len(self.events) == 0


class RecordingManager:
    """Manages Watch me! recording.

    start_recording() begins capture, stop_recording() ends it and returns
    the Recording (or None if empty).
    """

    def __init__(self, time_fn: Callable[[], float] | None = None):
        self._is_recording = False
        self.current: Recording | None = None
        self._time_fn = time_fn or time.monotonic
        self._target_room: str = ""
        self._target_mode: str = ""

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def state(self) -> RecordingState:
        if self._is_recording:
            return RecordingState.RECORDING
        return RecordingState.IDLE

    def start_recording(self, room_name: str, mode: str = "") -> None:
        """Start recording for Watch me! in the given room."""
        self._is_recording = True
        self._target_room = room_name
        self._target_mode = mode
        self.current = Recording()

    def stop_recording(self) -> Recording | None:
        """Stop recording and return the Recording, or None if empty."""
        if not self._is_recording:
            return None
        self._is_recording = False
        recording = self.current
        self.current = None
        if recording is None or recording.is_empty():
            return None
        return recording

    def record_event(self, action: KeyAction, room_name: str,
                     mode: str = "") -> None:
        """Record a keyboard action if currently recording."""
        if not self._is_recording:
            return
        if self.current is None:
            return

        # Only record meaningful actions
        if not isinstance(action, (CharacterAction, NavigationAction, ControlAction)):
            return

        # Skip key-up events
        if isinstance(action, ControlAction) and not action.is_down:
            return

        # Skip key repeats
        if isinstance(action, CharacterAction) and action.is_repeat:
            return
        if isinstance(action, NavigationAction) and action.is_repeat:
            return
        if isinstance(action, ControlAction) and action.is_repeat:
            return

        # Skip non-recordable control actions
        if isinstance(action, ControlAction):
            if action.action not in ("enter", "backspace", "space", "tab"):
                return

        self.current.add_event(
            action=action,
            room_name=room_name,
            mode=mode,
            timestamp=self._time_fn(),
        )

    @property
    def target_room(self) -> str:
        return self._target_room

    @property
    def target_mode(self) -> str:
        return self._target_mode
