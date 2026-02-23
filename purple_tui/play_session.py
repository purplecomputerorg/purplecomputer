"""Play session recorder for replay functionality.

Pure logic with no UI or audio dependencies. Records key presses with timing
and produces replay sequences.

A "session" is a sequence of key presses. If there's a gap of more than
SESSION_TIMEOUT seconds between presses, the old events are discarded
and a new session begins. Starting a replay ends the current session.
"""

import time

SESSION_TIMEOUT = 30.0  # seconds of inactivity before session resets


class PlaySession:
    """Records key presses with timing for replay in Play Mode.

    Usage:
        session = PlaySession()

        # Record keys as they're pressed
        session.record('A')
        session.record('B')

        # Get replay data (list of (key, delay) pairs)
        replay = session.get_replay()

        # Clear to start new session (called when replay begins)
        session.clear()
    """

    def __init__(self, time_fn=None):
        self._events: list[tuple[str, float]] = []  # (key, timestamp)
        self._time_fn = time_fn or time.monotonic

    def record(self, key: str, now: float | None = None) -> None:
        """Record a key press. Starts new session if timed out."""
        if now is None:
            now = self._time_fn()
        if self._events and (now - self._events[-1][1]) > SESSION_TIMEOUT:
            self._events.clear()
        self._events.append((key, now))

    def get_replay(self) -> list[tuple[str, float]]:
        """Get the recorded session as (key, delay_from_previous) pairs.

        First event has delay 0.0. Subsequent events have the delay
        since the previous event.
        """
        if not self._events:
            return []
        result = []
        for i, (key, ts) in enumerate(self._events):
            if i == 0:
                delay = 0.0
            else:
                delay = ts - self._events[i - 1][1]
            result.append((key, delay))
        return result

    def has_events(self) -> bool:
        """Check if there are any recorded events."""
        return bool(self._events)

    def clear(self) -> None:
        """Clear the session."""
        self._events.clear()
