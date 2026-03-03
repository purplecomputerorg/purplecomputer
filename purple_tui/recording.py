"""
F5 Recording: intentional cross-mode recording and playback.

Kids press F5 to start recording, play in any mode (Play, Doodle, Explore),
press F5 again to stop. The recording can be played back via F5 or Space
in Code mode, and viewed/edited as blocks in Code mode (F4).

Replaces the always-on ActionRecorder with an intentional recording moment.
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
    action_to_block,
    quantize_pause,
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


def _mode_to_target(mode_name: str, sub_mode: str = "") -> str:
    """Convert a mode name and optional sub-mode to a target string."""
    if mode_name == "play":
        if sub_mode == "letters":
            return TARGET_PLAY_LETTERS
        return TARGET_PLAY_MUSIC
    elif mode_name == "doodle":
        if sub_mode == "paint":
            return TARGET_DOODLE_PAINT
        return TARGET_DOODLE_TEXT
    elif mode_name == "explore":
        return TARGET_EXPLORE
    return TARGET_PLAY_MUSIC


@dataclass
class RecordedEvent:
    """A single recorded event with context."""
    action: KeyAction
    mode_name: str
    sub_mode: str
    timestamp: float


class Recording:
    """A completed or in-progress recording of keyboard events."""

    def __init__(self):
        self.events: list[RecordedEvent] = []

    def add_event(self, action: KeyAction, mode_name: str,
                  sub_mode: str = "", timestamp: float = 0.0) -> None:
        self.events.append(RecordedEvent(
            action=action,
            mode_name=mode_name,
            sub_mode=sub_mode,
            timestamp=timestamp,
        ))

    def to_blocks(self) -> list[ProgramBlock]:
        """Convert recorded events to ProgramBlock list.

        Inserts MODE_SWITCH blocks when the mode/sub-mode changes between
        consecutive events. The first event's mode also gets a MODE_SWITCH
        block at the start.
        """
        if not self.events:
            return []

        blocks: list[ProgramBlock] = []
        prev_target = ""

        for i, event in enumerate(self.events):
            current_target = _mode_to_target(event.mode_name, event.sub_mode)

            # Insert MODE_SWITCH when target changes
            if current_target != prev_target:
                blocks.append(ProgramBlock(
                    type=ProgramBlockType.MODE_SWITCH,
                    target=current_target,
                    gap_level=0,
                ))
                prev_target = current_target

            # Convert action to block
            block = action_to_block(event.action, event.mode_name)
            if block is None:
                continue

            # Calculate gap from timing
            if i < len(self.events) - 1:
                next_ts = self.events[i + 1].timestamp
                pause = next_ts - event.timestamp
                block.gap_level = quantize_pause(pause)
            else:
                block.gap_level = 0  # last block has no trailing gap

            blocks.append(block)

        return blocks

    def is_empty(self) -> bool:
        return len(self.events) == 0


class RecordingManager:
    """Manages the F5 record/play/stop cycle.

    State machine:
        IDLE ──F5──> RECORDING ──F5──> IDLE (has recording)
        IDLE (has recording) ──F5──> PLAYING ──F5──> IDLE

    Usage:
        manager = RecordingManager()
        manager.toggle()           # IDLE → RECORDING
        manager.record_event(...)  # called from dispatch when RECORDING
        manager.toggle()           # RECORDING → IDLE
        manager.toggle()           # IDLE → PLAYING (if has recording)
        manager.toggle()           # PLAYING → IDLE
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
                # Has a recording, play it
                self.state = RecordingState.PLAYING
            else:
                # No recording, start recording
                self.state = RecordingState.RECORDING
                self.current = Recording()
        elif self.state == RecordingState.RECORDING:
            # Stop recording
            self.state = RecordingState.IDLE
            # If recording is empty, discard it
            if self.current and self.current.is_empty():
                self.current = None
        elif self.state == RecordingState.PLAYING:
            # Stop playback
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

    def record_event(self, action: KeyAction, mode_name: str,
                     sub_mode: str = "") -> None:
        """Record a keyboard action if currently recording.

        Only records meaningful actions (characters, arrows, controls).
        Skips key-up, repeats, and non-recordable control actions.
        """
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
            mode_name=mode_name,
            sub_mode=sub_mode,
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
            return "⏺"
        elif self.state == RecordingState.PLAYING:
            return "▶"
        return ""

    def set_stop_playback_fn(self, fn: Callable) -> None:
        """Set the callback for stopping playback when toggle() is called during PLAYING."""
        self._stop_playback_fn = fn
