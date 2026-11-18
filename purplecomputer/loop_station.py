"""Loop station for the music room: plays a phrase over and over.

Pure logic with no UI or audio. IDLE until play() hands it a phrase (the
room's tape), then LOOPING; notes played while looping join the loop and
sound on the next cycle. With nothing to loop, record() counts down while the
room's tape fills (RECORDING), and the room then plays it. stop() goes back to IDLE.
"""

import time

IDLE = 'idle'
RECORDING = 'recording'
LOOPING = 'looping'


class LoopStation:
    """Events are (key, mode, offset): offset is seconds from the start of a
    cycle. They all play on the room's current instrument."""

    def __init__(self, time_fn=None):
        self._time_fn = time_fn or time.monotonic
        self._state = IDLE
        self._loop_events: list[tuple[str, str, float]] = []
        self._loop_duration: float = 0.0
        self._cycle_start: float = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def loop_duration(self) -> float:
        return self._loop_duration

    @property
    def loop_events(self) -> list[tuple[str, str, float]]:
        """Current loop events (may grow as new notes are added during looping)."""
        return list(self._loop_events)

    def play(self, events: list[tuple[str, str, float]], duration: float,
             now: float | None = None) -> None:
        """Loop these events right away."""
        self._loop_events = sorted(events, key=lambda e: e[2])
        self._loop_duration = duration
        self._state = LOOPING
        self._cycle_start = now if now is not None else self._time_fn()

    def record(self, seconds: float, now: float | None = None) -> None:
        """Count down `seconds` while the room's tape fills."""
        self._loop_events = []
        self._loop_duration = seconds
        self._state = RECORDING
        self._cycle_start = now if now is not None else self._time_fn()

    def recording_left(self, now: float | None = None) -> float:
        """Seconds left to record; 0 if not recording."""
        if self._state != RECORDING:
            return 0.0
        now = now if now is not None else self._time_fn()
        return max(0.0, self._loop_duration - (now - self._cycle_start))

    def record_event(self, key: str, mode: str, now: float | None = None) -> None:
        """While looping, a note joins the loop where it falls in the cycle and plays from the next one."""
        if self._state != LOOPING or self._loop_duration <= 0:
            return
        now = now if now is not None else self._time_fn()
        self._loop_events.append((key, mode, (now - self._cycle_start) % self._loop_duration))
        self._loop_events.sort(key=lambda e: e[2])

    def start_new_cycle(self, now: float | None = None) -> None:
        """Mark the start of a new playback cycle."""
        self._cycle_start = now if now is not None else self._time_fn()

    def loop_progress(self, now: float | None = None) -> float:
        """Current position in the loop as 0.0 to 1.0. 0 if not looping."""
        if self._state != LOOPING or self._loop_duration <= 0:
            return 0.0
        now = now if now is not None else self._time_fn()
        return ((now - self._cycle_start) % self._loop_duration) / self._loop_duration

    def stop(self) -> None:
        """Stop everything and return to idle."""
        self._state = IDLE
        self._loop_events.clear()
        self._loop_duration = 0.0
