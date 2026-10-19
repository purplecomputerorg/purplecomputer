"""The last minute of playing in Music, kept so a save can play it back.

A note is [key, mode, instrument id, ms]. `start` is the key colors before the
oldest note kept: each note moves its key one color on, so playing the notes on
`start` lands on the colors that were saved. Pauses are cut to MAX_GAP_S as
notes come in, so a long think neither uses up the minute nor replays as silence.
"""

from ..music_constants import ALL_KEYS, COLORS

KEEP_S = 60.0
MAX_GAP_S = 1.5


class Recording:
    def __init__(self, start: dict, notes=()):
        self.start = {k: int(start.get(k, -1)) for k in ALL_KEYS}
        self.notes = [list(n) for n in notes]
        self._last = None

    @classmethod
    def load(cls, data, colors: dict) -> "Recording":
        """A save's recording, or an empty one starting from `colors`."""
        return cls(data.get("from", {}), data.get("notes", ())) if isinstance(data, dict) else cls(colors)

    def add(self, key: str, mode: str, instrument: str, now: float):
        gap = MAX_GAP_S if self._last is None else min(now - self._last, MAX_GAP_S)
        self._last = now
        ms = self.notes[-1][3] + round(gap * 1000) if self.notes else 0
        self.notes.append([key, mode, instrument, ms])
        while ms - self.notes[0][3] > KEEP_S * 1000:
            key = self.notes.pop(0)[0]
            self.start[key] = (self.start[key] + 1) % len(COLORS)

    @property
    def seconds(self) -> float:
        return (self.notes[-1][3] - self.notes[0][3]) / 1000 if self.notes else 0.0

    def data(self) -> dict:
        first = self.notes[0][3] if self.notes else 0
        return {"from": {k: v for k, v in self.start.items() if v != -1},
                "notes": [[k, m, i, ms - first] for k, m, i, ms in self.notes]}
