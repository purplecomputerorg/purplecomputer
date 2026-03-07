"""Play session recorder for replay functionality.

Pure logic with no UI or audio dependencies. Records key presses with timing
and mode info, and produces replay sequences.

A "session" is a sequence of key presses. If there's a gap of more than
SESSION_TIMEOUT seconds between presses, the old events are discarded
and a new session begins. Starting a replay ends the current session.
"""

import time

SESSION_TIMEOUT = 2.0  # seconds of inactivity before session resets
LONG_PAUSE_THRESHOLD = 1.0  # seconds: a "long pause" within a session

# Mode constants
MODE_MUSIC = 'music'
MODE_LETTERS = 'letters'


class PlaySession:
    """Records key presses with timing for replay in Play Mode.

    Each event records the key, which mode it was pressed in (music
    or letters), and the timestamp. Replay preserves mode so letter
    keys are spoken and music keys play sounds.

    Usage:
        session = PlaySession()

        # Record keys with their mode
        session.record('A', 'music')
        session.record('B', 'letters')

        # Get replay data (list of (key, submode, delay) triples)
        replay = session.get_replay()

        # Clear to start new session (called when replay begins)
        session.clear()
    """

    def __init__(self, time_fn=None):
        self._events: list[tuple[str, str, float]] = []  # (key, submode, timestamp)
        self._time_fn = time_fn or time.monotonic

    def record(self, key: str, submode: str = MODE_MUSIC, now: float | None = None) -> None:
        """Record a key press. Starts new session if timed out."""
        if now is None:
            now = self._time_fn()
        if self._events and (now - self._events[-1][2]) > SESSION_TIMEOUT:
            self._events.clear()
        self._events.append((key, submode, now))

    def get_replay(self) -> list[tuple[str, str, float]]:
        """Get the recorded session as (key, submode, delay_from_previous) triples.

        First event has delay 0.0. Subsequent events have the delay
        since the previous event.
        """
        if not self._events:
            return []
        result = []
        for i, (key, submode, ts) in enumerate(self._events):
            if i == 0:
                delay = 0.0
            else:
                delay = ts - self._events[i - 1][2]
            result.append((key, submode, delay))
        return result

    def get_recent_replay(self, max_seconds: float = 10.0) -> list[tuple[str, str, float]]:
        """Get the most recent events, capped by time or the last long pause.

        Returns events from whichever boundary is more recent:
        the last LONG_PAUSE_THRESHOLD gap, or max_seconds from the end.
        This gives the user the most natural-feeling "replay recent stuff".
        """
        if not self._events:
            return []

        end_time = self._events[-1][2]
        time_cutoff = end_time - max_seconds

        # Find the last long pause, scanning backward
        pause_idx = 0
        for i in range(len(self._events) - 1, 0, -1):
            gap = self._events[i][2] - self._events[i - 1][2]
            if gap >= LONG_PAUSE_THRESHOLD:
                pause_idx = i
                break

        # Find the time-based cutoff index
        time_idx = 0
        for i, (_, _, ts) in enumerate(self._events):
            if ts >= time_cutoff:
                time_idx = i
                break

        # Use whichever is more recent (fewer events)
        start_idx = max(pause_idx, time_idx)

        result = []
        for i in range(start_idx, len(self._events)):
            key, submode, ts = self._events[i]
            if i == start_idx:
                delay = 0.0
            else:
                delay = ts - self._events[i - 1][2]
            result.append((key, submode, delay))
        return result

    def has_events(self) -> bool:
        """Check if there are any recorded events."""
        return bool(self._events)

    def clear(self) -> None:
        """Clear the session."""
        self._events.clear()
