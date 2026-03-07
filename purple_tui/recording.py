"""
F5 Recording: intentional cross-mode recording and playback.

Kids press F5 to start recording, play in any mode (Play, Doodle, Explore),
press F5 again to stop. The recording can be played back via F5 or Space
in Code mode, and viewed/edited as blocks in Code mode (F4).

Mode-aware conversion: Explore events buffer into QUERY blocks, Doodle paint
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
    TARGET_PLAY_MUSIC,
    TARGET_PLAY_LETTERS,
    TARGET_DOODLE_TEXT,
    TARGET_DOODLE_PAINT,
    TARGET_EXPLORE,
)


class RecordingState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PLAYING = "playing"


def _room_to_target(room_name: str, mode: str = "") -> str:
    """Convert a mode name and optional mode to a target string."""
    if room_name == "play":
        if mode == "letters":
            return TARGET_PLAY_LETTERS
        return TARGET_PLAY_MUSIC
    elif room_name == "doodle":
        if mode == "paint":
            return TARGET_DOODLE_PAINT
        return TARGET_DOODLE_TEXT
    elif room_name == "explore":
        return TARGET_EXPLORE
    return TARGET_PLAY_MUSIC


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

    def to_blocks(self) -> list[ProgramBlock]:
        """Convert recorded events to ProgramBlock list.

        Mode-aware conversion:
        - Play/Doodle text: each action becomes a KEY block
        - Explore: characters buffer into QUERY blocks, Enter finalizes.
          Backspace edits the buffer. Net result is captured, not editing journey.
        - Doodle paint: consecutive same-direction arrows merge into STROKE blocks.
          Character keys become KEY blocks (color selection).
        - Post-pass: inserts PAUSE blocks for gaps > 300ms
        """
        if not self.events:
            return []

        blocks: list[ProgramBlock] = []
        prev_target = ""
        query_buf = ""

        for i, event in enumerate(self.events):
            current_target = _room_to_target(event.room_name, event.mode)

            # On target change, flush explore buffer and emit MODE_SWITCH
            if current_target != prev_target:
                if query_buf and prev_target == TARGET_EXPLORE:
                    blocks.append(ProgramBlock(
                        type=ProgramBlockType.QUERY,
                        query_text=query_buf,
                    ))
                    query_buf = ""

                blocks.append(ProgramBlock(
                    type=ProgramBlockType.MODE_SWITCH,
                    target=current_target,
                ))
                prev_target = current_target

            # Calculate gap_ms to next event
            gap_ms = 0
            if i < len(self.events) - 1:
                gap_ms = int((self.events[i + 1].timestamp - event.timestamp) * 1000)

            action = event.action

            # Explore mode: buffer characters into QUERY blocks
            if current_target == TARGET_EXPLORE:
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

            # Doodle paint mode: arrows merge into STROKE, chars are KEY
            if current_target == TARGET_DOODLE_PAINT:
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

            # Play music/letters, Doodle text: simple KEY blocks
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

        # Flush remaining explore buffer
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
    """Manages the F5 record/play/stop cycle.

    State machine:
        IDLE -> RECORDING -> IDLE (has recording)
        IDLE (has recording) -> PLAYING -> IDLE
    """

    def __init__(self, time_fn: Callable[[], float] | None = None):
        self.state = RecordingState.IDLE
        self.current: Recording | None = None
        self._time_fn = time_fn or time.monotonic
        self._stop_playback_fn: Callable | None = None

    def toggle(self) -> RecordingState:
        """Advance the state machine. Returns the new state."""
        if self.state == RecordingState.IDLE:
            if self.current is not None and not self.current.is_empty():
                self.state = RecordingState.PLAYING
            else:
                self.state = RecordingState.RECORDING
                self.current = Recording()
        elif self.state == RecordingState.RECORDING:
            self.state = RecordingState.IDLE
            if self.current and self.current.is_empty():
                self.current = None
        elif self.state == RecordingState.PLAYING:
            self.state = RecordingState.IDLE
            if self._stop_playback_fn:
                self._stop_playback_fn()

        return self.state

    def start_recording(self) -> None:
        """Explicitly start recording (used by Tab menu "Record in..." action)."""
        self.state = RecordingState.RECORDING
        self.current = Recording()

    def stop_recording(self) -> None:
        """Explicitly stop recording."""
        if self.state == RecordingState.RECORDING:
            self.state = RecordingState.IDLE
            if self.current and self.current.is_empty():
                self.current = None

    def record_event(self, action: KeyAction, room_name: str,
                     mode: str = "") -> None:
        """Record a keyboard action if currently recording."""
        if self.state != RecordingState.RECORDING:
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

    def to_blocks(self) -> list[ProgramBlock]:
        """Convert the current recording to blocks."""
        if self.current is None:
            return []
        return self.current.to_blocks()

    def has_recording(self) -> bool:
        """Check if there's a non-empty recording available."""
        return self.current is not None and not self.current.is_empty()

    def clear(self) -> None:
        """Clear the current recording."""
        self.current = None

    @property
    def indicator(self) -> str:
        """Title bar indicator string for current state."""
        if self.state == RecordingState.RECORDING:
            return "\u23fa"
        elif self.state == RecordingState.PLAYING:
            return "\u25b6"
        return ""

    def set_stop_playback_fn(self, fn: Callable) -> None:
        """Set the callback for stopping playback when toggle() is called during PLAYING."""
        self._stop_playback_fn = fn
