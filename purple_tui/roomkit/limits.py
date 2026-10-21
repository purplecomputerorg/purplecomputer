"""What Purple holds a room to: canvas/rooms/family_room.py on the laptop, and check.py before a pack gets there."""

from pathlib import Path

RUN_ROOM = Path("/usr/local/bin/purple-room-run")   # the ISO's sealed launcher (scripts/purple-room-run.sh)

START_TIMEOUT_S = 8.0       # python3 startup on the slowest laptops, plus the room's top level
STEP_TIMEOUT_S = 3.0
MAX_REPLY_CHARS = 256 * 1024
MAX_SHAPES = 1000
MAX_SOUNDS = 8
KEEP_MAX_BYTES = 4096
MIN_WAKE_S, MAX_WAKE_S = 1 / 30, 3600


def sealed() -> list | None:
    """The command that starts a room sealed, as the ISO does; None off the ISO."""
    return ["sudo", "-n", str(RUN_ROOM)] if RUN_ROOM.exists() else None
