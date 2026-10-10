"""A family room's process on the laptop. Started by canvas/rooms/program_room.py
as the purple-room user (python3 -I -S, so nothing beside the room is importable
by accident). Reads the room's source as the first line on stdin, then JSON
events; writes JSON messages on the original stdout. Room print() goes to stderr."""

import json
import os
import resource
import sys

LIMITS = {
    resource.RLIMIT_CPU: 1800,        # last resort for a room that outlives Purple anyway
    resource.RLIMIT_AS: 512 << 20,
    resource.RLIMIT_FSIZE: 1 << 20,   # /tmp is RAM on a live boot
    resource.RLIMIT_NOFILE: 32,
    resource.RLIMIT_NPROC: 16,
    resource.RLIMIT_CORE: 0,
}


def _die_with_parent():
    """Purple can't signal purple-room's processes, only sudo; this makes the
    kernel kill the room when sudo goes, so a stuck room never outlives its screen."""
    try:
        import ctypes
        import signal
        ctypes.CDLL(None).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass
    if os.getppid() == 1:
        sys.exit(0)


def main():
    _die_with_parent()
    for limit, value in LIMITS.items():
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            pass
    out = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import purple

    def send(msg):
        out.write(json.dumps(msg) + "\n")
        out.flush()

    def recv():
        line = sys.stdin.readline()
        if not line:
            sys.exit(0)
        return json.loads(line)

    purple._send, purple._recv = send, recv
    purple.run(recv()["source"])


if __name__ == "__main__":
    main()
