"""Loop station for the music room.

Pure logic with no UI or audio dependencies. Manages three states:

  IDLE: nothing happening
  RECORDING: capturing key presses with timing
  LOOPING: loop plays back, new key presses captured as overlay

Space transitions: IDLE → RECORDING → LOOPING → merge/stop.
Escape stops from any non-idle state.

Max loop duration prevents runaway recordings. When recording hits the
limit, the caller should auto-transition to looping.
"""

import time

MAX_LOOP_DURATION = 20.0  # seconds

# States
IDLE = 'idle'
RECORDING = 'recording'
LOOPING = 'looping'


class LoopStation:
    """Records, loops, and layers music key presses.

    Events are stored as (key, mode, offset) where offset is seconds
    from the start of the recording/loop cycle.

    Usage:
        loop = LoopStation()

        loop.start_recording()
        loop.record_event('A', 'music')
        loop.record_event('B', 'music')

        events, duration = loop.finish_recording()  # starts looping

        loop.record_event('C', 'music')  # overlay
        events, duration = loop.merge_overlay()

        loop.stop()
    """

    def __init__(self, time_fn=None, max_duration: float = MAX_LOOP_DURATION):
        self._time_fn = time_fn or time.monotonic
        self._max_duration = max_duration
        self._state = IDLE
        self._recording_start: float = 0.0
        self._recording_events: list[tuple[str, str, float]] = []
        self._loop_events: list[tuple[str, str, float]] = []
        self._loop_duration: float = 0.0
        self._overlay_events: list[tuple[str, str, float]] = []
        self._cycle_start: float = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def loop_duration(self) -> float:
        return self._loop_duration

    @property
    def loop_events(self) -> list[tuple[str, str, float]]:
        """Current loop events (read each cycle for up-to-date data after merge)."""
        return list(self._loop_events)

    @property
    def max_duration(self) -> float:
        return self._max_duration

    def start_recording(self, now: float | None = None) -> None:
        """Begin recording. Clears any existing loop."""
        now = now if now is not None else self._time_fn()
        self._state = RECORDING
        self._recording_start = now
        self._recording_events.clear()
        self._loop_events.clear()
        self._overlay_events.clear()
        self._loop_duration = 0.0

    def record_event(self, key: str, mode: str, now: float | None = None) -> None:
        """Record a key press.

        RECORDING: stores with offset from recording start (capped at max duration).
        LOOPING: stores as overlay with offset in current cycle.
        IDLE: ignored.
        """
        now = now if now is not None else self._time_fn()
        if self._state == RECORDING:
            offset = now - self._recording_start
            if offset <= self._max_duration:
                self._recording_events.append((key, mode, offset))
        elif self._state == LOOPING and self._loop_duration > 0:
            elapsed = now - self._cycle_start
            cycle_offset = elapsed % self._loop_duration
            self._overlay_events.append((key, mode, cycle_offset))

    def finish_recording(self, now: float | None = None) -> tuple[list[tuple[str, str, float]], float]:
        """Stop recording and begin looping.

        Duration spans from recording start to now (preserving trailing
        silence for rhythm). Returns (loop_events, loop_duration).
        Returns ([], 0.0) if not recording or no events.
        """
        if self._state != RECORDING or not self._recording_events:
            return [], 0.0
        now = now if now is not None else self._time_fn()
        duration = min(now - self._recording_start, self._max_duration)
        # Ensure duration covers at least the last event
        last_offset = self._recording_events[-1][2]
        if duration < last_offset:
            duration = last_offset
        self._loop_duration = duration
        self._loop_events = list(self._recording_events)
        self._recording_events.clear()
        self._overlay_events.clear()
        self._state = LOOPING
        self._cycle_start = now
        return list(self._loop_events), self._loop_duration

    def merge_overlay(self, now: float | None = None) -> tuple[list[tuple[str, str, float]], float]:
        """Merge overlay events into the loop.

        Returns (merged_events, duration). Overlay is cleared and a new
        cycle starts. Returns ([], 0.0) if not looping.
        """
        if self._state != LOOPING:
            return [], 0.0
        now = now if now is not None else self._time_fn()
        if self._overlay_events:
            self._loop_events.extend(self._overlay_events)
            self._loop_events.sort(key=lambda e: e[2])
            self._overlay_events.clear()
        self._cycle_start = now
        return list(self._loop_events), self._loop_duration

    def start_new_cycle(self, now: float | None = None) -> None:
        """Mark the start of a new playback cycle (for overlay timing)."""
        now = now if now is not None else self._time_fn()
        self._cycle_start = now

    def stop(self) -> None:
        """Stop everything and return to idle."""
        self._state = IDLE
        self._recording_events.clear()
        self._loop_events.clear()
        self._overlay_events.clear()
        self._loop_duration = 0.0

    def recording_remaining(self, now: float | None = None) -> float:
        """Seconds remaining before max duration. 0 if not recording."""
        if self._state != RECORDING:
            return 0.0
        now = now if now is not None else self._time_fn()
        return max(0.0, self._max_duration - (now - self._recording_start))

    def recording_progress(self, now: float | None = None) -> float:
        """Recording progress as 0.0 to 1.0. 0 if not recording."""
        if self._state != RECORDING:
            return 0.0
        now = now if now is not None else self._time_fn()
        elapsed = now - self._recording_start
        return min(1.0, elapsed / self._max_duration)

    def is_at_max_duration(self, now: float | None = None) -> bool:
        """Whether recording has reached the max duration."""
        if self._state != RECORDING:
            return False
        now = now if now is not None else self._time_fn()
        return (now - self._recording_start) >= self._max_duration

    def has_recording_events(self) -> bool:
        """Whether any events have been recorded in the current recording."""
        return bool(self._recording_events)

    def has_overlay_events(self) -> bool:
        """Whether any overlay events exist (played during looping)."""
        return bool(self._overlay_events)
