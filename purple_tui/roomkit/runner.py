"""A family room's process. On the laptop, canvas/rooms/family_room.py starts it
(sealed by /usr/local/bin/purple-room-run on the ISO) with python3 -I -S, so
nothing beside the room is importable by accident; Studio's room worker calls
serve() itself. The first line in is the start event, carrying the pack's
purple.py as `lib`, so the room runs on the library it was built with."""

import json
import sys
import types

LIMITS = {
    "RLIMIT_CPU": 1800,        # last resort for a room that outlives Purple anyway
    "RLIMIT_AS": 512 << 20,
    "RLIMIT_FSIZE": 1 << 20,   # /tmp is RAM on a live boot
    "RLIMIT_NOFILE": 32,
    "RLIMIT_NPROC": 16,
    "RLIMIT_CORE": 0,
}


def serve(recv_line, send_line):
    """recv_line() -> one JSON line from Purple; send_line(text) -> one JSON line back."""
    start = json.loads(recv_line())
    try:
        purple = types.ModuleType("purple")
        exec(compile(start["lib"], "purple.py", "exec"), purple.__dict__)
        sys.modules["purple"] = purple
    except Exception as exc:
        return send_line(json.dumps({"error": {"text": f"purple.py: {type(exc).__name__}: {exc}"[:300], "line": None}}))
    purple._send = lambda reply: send_line(json.dumps(reply, ensure_ascii=False))
    purple._recv = lambda: json.loads(recv_line())
    purple.run(start)


def _watch():
    """Ends the room when Purple lets go of it. Killing sudo or systemd-run doesn't reach a
    room in its own unit, so this parent stays behind, waits for Purple's end of stdin to
    close or the room to finish, and takes the room down with it. Returns in the room."""
    import os
    import select
    import signal
    room = os.fork()
    if room == 0:
        return
    poll = select.poll()
    poll.register(0, select.POLLHUP)
    while os.waitpid(room, os.WNOHANG) == (0, 0):
        if poll.poll(500):
            os.kill(room, signal.SIGKILL)
    os._exit(0)


def main():
    import os
    import resource
    _watch()
    for name, value in LIMITS.items():
        try:
            resource.setrlimit(getattr(resource, name), (value, value))
        except (ValueError, OSError):
            pass
    out = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    def send_line(text):
        out.write(text + "\n")
        out.flush()

    def recv_line():
        line = sys.stdin.readline()
        if not line:
            sys.exit(0)
        return line

    serve(recv_line, send_line)


if __name__ == "__main__":
    main()
