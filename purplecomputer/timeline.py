"""Time Travel timeline: per-room append-only history that doubles as persistence.

Each room's state is a flat JSON dict (str keys). Steps are stored as NDJSON:
a full snapshot line {"s": {...}} or a delta line {"d": {changed}, "r": [removed]}
against the previous step, each stamped with the wall-clock second it was taken ("t").
A {"k": tag} line tags the step before it (a save's digest, so Time Travel can
show which moments were saved). Replaying the file yields the room's latest state,
which is how rooms are restored after a restart; scrubbing to any step replays
from the nearest snapshot line. A snapshot is written once the deltas since the
last one outweigh it, which bounds replay cost without a big picture's copies
filling the file.

A timeline made with `fine_for_s` keeps every recorded step only that long: older
steps thin to one per pause (or one every COARSE_EVERY_S through steady play), so
the last few minutes step back like undo and the rest as before. That happens on
load, when Time Travel opens (`coarsen`), and before compaction.

Past MAX_FILE_BYTES the older half is thinned, not dropped: every other step
goes, but how each play session ended and tagged steps (and the step before
each) stay, so old days get coarser instead of vanishing. Only once there is
little left to thin does the oldest half go.

A torn final line (power loss mid-append) is dropped on load, losing only that
step. On the live USB $HOME is tmpfs, so history is session-only there with no
special casing. In dev mode (PURPLE_DEV_MODE=1) the timeline is RAM-only unless
PURPLE_TIMELINE_DIR points somewhere, so previews and tests stay deterministic.
"""

import json
import os
import time
from pathlib import Path

MAX_FILE_BYTES = 2_000_000
SESSION_GAP_S = 20 * 60  # a pause this long ends a play session
COARSE_PAUSE_S = 3       # a coarsened step is the last before a pause this long,
COARSE_EVERY_S = 15      # or the first this long after the last kept one
_GONE = object()


def state_dir(name: str, env: str) -> Path | None:
    """~/.config/purple/<name>, the `env` override, or None for RAM-only (dev mode without an override)."""
    override = os.environ.get(env)
    if override:
        return Path(override)
    if os.environ.get("PURPLE_DEV_MODE") == "1":
        return None
    from .settings import kid_path
    return kid_path(Path.home() / ".config" / "purple" / name)


def timeline_dir() -> Path | None:
    return state_dir("timeline", "PURPLE_TIMELINE_DIR")


class RoomTimeline:
    """Append-only step history for one room."""

    def __init__(self, room: str, fine_for_s: float | None = None):
        self._room = room
        self._fine_for_s = fine_for_s
        self._steps: list[dict] = []  # parsed {"s": ...} or {"d": ..., "r": ...} lines
        self._tip: dict | None = None  # state after the last step
        self._loaded = False
        self._snap_bytes = self._since_snap = 0  # size of the last snapshot line, and of the deltas after it

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
            if isinstance(step.get("k"), str):
                self._steps[-1].setdefault("k", []).append(step["k"])
                continue
            self._count(step, len(line))
            self._steps.append(step)
        self._tip = self.state_at(len(self._steps) - 1) if self._steps else None
        if self._fine_for_s is not None:
            self.coarsen(before=float("inf"))   # a past run's steps are all old now

    def __len__(self) -> int:
        self.load()
        return len(self._steps)

    def tip(self) -> dict | None:
        self.load()
        return dict(self._tip) if self._tip is not None else None

    def times(self) -> list:
        """When each step was taken (epoch seconds), None for steps from before stamping."""
        self.load()
        return [step.get("t") for step in self._steps]

    def tags(self) -> list:
        self.load()
        return [step.get("k", []) for step in self._steps]

    def mark(self, tag: str) -> None:
        """Tag the newest step."""
        self.load()
        if self._steps and tag not in self._steps[-1].get("k", []):
            self._steps[-1].setdefault("k", []).append(tag)
            self._append_to_disk(json.dumps({"k": tag}))

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
        tip = self._tip or {}
        changed = {k for k in state.keys() | tip.keys() if state.get(k, _GONE) != tip.get(k, _GONE)}
        step = self._encode(state, changed)
        step["t"] = round(time.time())
        self._tip = dict(state)
        self._append_to_disk(self._push(step))
        return True

    def _encode(self, state: dict, changed) -> dict:
        if not self._steps or self._since_snap >= self._snap_bytes:
            return {"s": dict(state)}
        return {"d": {k: state[k] for k in changed if k in state}, "r": [k for k in changed if k not in state]}

    def _count(self, step: dict, size: int) -> None:
        if "s" in step:
            self._snap_bytes, self._since_snap = size, 0
        else:
            self._since_snap += size

    def _push(self, step: dict) -> str:
        line = json.dumps(step, separators=(",", ":"))
        self._count(step, len(line))
        self._steps.append(step)
        return line

    def _append_to_disk(self, line: str) -> None:
        path = self._path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(line + "\n")
            if path.stat().st_size > MAX_FILE_BYTES:
                self._compact()
        except OSError:
            pass

    def coarsen(self, before: float | None = None) -> None:
        """Thin steps taken before `before` (default: fine_for_s ago) to one per pause, keeping tagged steps and the newest."""
        if self._fine_for_s is None or len(self) < 2:
            return
        cutoff = time.time() - self._fine_for_s if before is None else before
        steps, times = self._steps, self.times()
        keep, last = set(), None
        for i, t in enumerate(times):
            nxt = times[i + 1] if i + 1 < len(times) else None
            if (t is None or t >= cutoff or nxt is None or nxt - t >= COARSE_PAUSE_S or "k" in steps[i]
                    or "k" in steps[i + 1] or last is None or t - last >= COARSE_EVERY_S):
                keep.add(i)
                last = t
        if len(keep) < len(steps):
            self._rewrite(keep)

    def _compact(self) -> None:
        if self._fine_for_s is not None:
            self.coarsen()
            if self._path().stat().st_size <= MAX_FILE_BYTES:
                return
        steps, times = self._steps, self.times()
        half = len(steps) // 2

        def landmark(i):
            gap = times[i] is not None and times[i + 1] is not None and times[i + 1] - times[i] >= SESSION_GAP_S
            return gap or "k" in steps[i] or "k" in steps[i + 1]
        old = [i for i in range(half) if i % 2 or landmark(i)]
        self._rewrite(set(old if len(old) <= half * 3 // 4 else []) | set(range(half, len(steps))))

    def _rewrite(self, keep: set) -> None:
        """Re-encode just the steps in `keep`, then replace the file atomically."""
        old, self._steps = self._steps, []
        self._snap_bytes = self._since_snap = 0
        lines, state, changed = [], {}, set()
        for i, step in enumerate(old):
            if "s" in step:
                snap = step["s"]
                changed |= {k for k in state.keys() | snap.keys() if state.get(k, _GONE) != snap.get(k, _GONE)}
                state = dict(snap)
            else:
                state.update(step.get("d", {}))
                for key in step.get("r", []):
                    state.pop(key, None)
                changed |= step.get("d", {}).keys() | set(step.get("r", []))
            if i in keep:
                new = self._encode(state, changed)
                new.update({k: step[k] for k in ("t", "k") if k in step})
                lines.append(self._push(new))
                changed = set()
        path = self._path()
        if path is None:
            return
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text("".join(line + "\n" for line in lines))
            tmp.replace(path)
        except OSError:
            pass
