"""Time Travel timeline: per-room append-only history that doubles as persistence.

Each room's state is a flat JSON dict (str keys). Steps are stored as NDJSON:
a full snapshot line {"s": {...}} or a delta line {"d": {changed}, "r": [removed]}
against the previous step. Replaying the file yields the room's latest state,
which is how rooms are restored after a restart; scrubbing to any step replays
from the nearest snapshot line.

A torn final line (power loss mid-append) is dropped on load, losing only that
step. On the live USB $HOME is tmpfs, so history is session-only there with no
special casing. In dev mode (PURPLE_DEV_MODE=1) the timeline is RAM-only unless
PURPLE_TIMELINE_DIR points somewhere, so previews and tests stay deterministic.
"""

import json
import os
from pathlib import Path

MAX_FILE_BYTES = 2_000_000
SNAPSHOT_EVERY = 20  # full snapshot line every N steps, bounding replay cost


def timeline_dir() -> Path | None:
    """Where logs live, or None for RAM-only (dev mode without an override)."""
    override = os.environ.get("PURPLE_TIMELINE_DIR")
    if override:
        return Path(override)
    if os.environ.get("PURPLE_DEV_MODE") == "1":
        return None
    return Path.home() / ".config" / "purple" / "timeline"


class RoomTimeline:
    """Append-only step history for one room."""

    def __init__(self, room: str):
        self._room = room
        self._steps: list[dict] = []  # parsed {"s": ...} or {"d": ..., "r": ...} lines
        self._tip: dict | None = None  # state after the last step
        self._loaded = False

    def _path(self) -> Path | None:
        base = timeline_dir()
        return base / f"{self._room}.jsonl" if base else None

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._path()
        if path is None or not path.exists():
            return
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return
        for line in lines:
            try:
                step = json.loads(line)
            except ValueError:
                break  # torn tail: keep everything before it
            if not self._steps and "s" not in step:
                continue  # history must start from a snapshot
            self._steps.append(step)
        self._tip = self.state_at(len(self._steps) - 1) if self._steps else None

    def __len__(self) -> int:
        self.load()
        return len(self._steps)

    def tip(self) -> dict | None:
        self.load()
        return dict(self._tip) if self._tip is not None else None

    def state_at(self, index: int) -> dict:
        """Replay to the state after step `index` (from the nearest snapshot)."""
        self.load()
        start = index
        while start > 0 and "s" not in self._steps[start]:
            start -= 1
        state = dict(self._steps[start].get("s", {}))
        for step in self._steps[start + 1:index + 1]:
            state.update(step.get("d", {}))
            for key in step.get("r", []):
                state.pop(key, None)
        return state

    def record(self, state: dict) -> bool:
        """Append `state` as a new step if it differs from the tip."""
        self.load()
        if self._tip is not None and state == self._tip:
            return False
        if self._tip is None or len(self._steps) % SNAPSHOT_EVERY == 0:
            step = {"s": state}
        else:
            changed = {k: v for k, v in state.items()
                       if k not in self._tip or self._tip[k] != v}
            removed = [k for k in self._tip if k not in state]
            step = {"d": changed, "r": removed}
        self._steps.append(step)
        self._tip = dict(state)
        self._append_to_disk(step)
        return True

    def _append_to_disk(self, step: dict) -> None:
        path = self._path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(step, separators=(",", ":")) + "\n")
            if path.stat().st_size > MAX_FILE_BYTES:
                self._compact()
        except OSError:
            pass

    def _compact(self) -> None:
        """Drop the oldest half of history and rewrite the file atomically."""
        cut = len(self._steps) // 2
        kept = [{"s": self.state_at(cut)}] + self._steps[cut + 1:]
        self._steps = kept
        path = self._path()
        if path is None:
            return
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w") as f:
                for step in kept:
                    f.write(json.dumps(step, separators=(",", ":")) + "\n")
            tmp.replace(path)
        except OSError:
            pass
