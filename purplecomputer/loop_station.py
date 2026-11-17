"""Loop station for the music room: plays a phrase over and over.

Pure logic with no UI or audio. IDLE until play() hands it a phrase (the
room's tape), then LOOPING; notes played while looping join the loop and
sound on the next cycle. stop() goes back to IDLE.
"""

import time

MAX_LOOP_DURATION = 20.0  # seconds; a longer phrase loops its last stretch

IDLE = 'idle'
LOOPING = 'looping'


class LoopStation:
    """Events are (key, mode, offset, instrument): offset is seconds from the
    start of a cycle, instrument the index the note was played with, so a
    layered loop keeps each note's sound."""

    def __init__(self, time_fn=None, max_duration: float = MAX_LOOP_DURATION):
        self._time_fn = time_fn or time.monotonic
        self._max_duration = max_duration
        self._state = IDLE
        self._loop_events: list[tuple[str, str, float, int]] = []
        self._loop_duration: float = 0.0
        self._cycle_start: float = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def loop_duration(self) -> float:
        return self._loop_duration

    @property
    def loop_events(self) -> list[tuple[str, str, float, int]]:
        """Current loop events (may grow as new notes are added during looping)."""
        return list(self._loop_events)

    @property
    def max_duration(self) -> float:
        return self._max_duration

    def play(self, events: list[tuple[str, str, float, int]], duration: float,
             now: float | None = None) -> None:
        """Loop these events right away."""
        self._loop_events = sorted(events, key=lambda e: e[2])
        self._loop_duration = duration
        self._state = LOOPING
        self._cycle_start = now if now is not None else self._time_fn()

    def record_event(self, key: str, mode: str, now: float | None = None,
                     instrument: int = 0) -> None:
        """While looping, a note joins the loop where it falls in the cycle and plays from the next one."""
        if self._state != LOOPING or self._loop_duration <= 0:
            return
        now = now if now is not None else self._time_fn()
        self._loop_events.append((key, mode, (now - self._cycle_start) % self._loop_duration, instrument))
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
