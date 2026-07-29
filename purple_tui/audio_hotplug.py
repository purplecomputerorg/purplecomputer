"""Background audio hotplug listener.

Watches for sound subsystem changes (USB speaker plug/unplug, Bluetooth
headset pair, internal card going idle/active) and triggers a full mixer
reinit so pygame's stream migrates to the new default sink without the
parent having to restart Purple.

Uses `udevadm monitor` as a subprocess instead of pyudev to avoid a new
Python dep. Parses line-oriented output, debounces bursts of events
(one plug-in emits several add events for card/pcm/control devices in
quick succession), and calls back once per quiet period.

Design: one daemon thread per app, started from _start_mixer_warmup after
the initial probe completes so we don't race the warmup's own probe.
The thread stops when the subprocess exits.

The subprocess is killed from an atexit hook, not just the loop's finally:
CPython kills daemon threads at interpreter exit without unwinding them, so
the finally never runs on the normal exit path, and `udevadm monitor` only
writes on a sound event, so it never sees EPIPE from our closed pipe. It
would outlive us indefinitely (xinitrc re-execs Purple in the same systemd
cgroup, so nothing else reaps it). Paths that never unwind Python at all,
os.execv and hard crashes, still leak one monitor until the next reboot.
"""

from __future__ import annotations

import atexit
import re
import select
import subprocess
import sys
import threading
import time
from typing import Callable, Iterable, Optional

# Matches the first line of a udev event block:
#   KERNEL[timestamp] add    /devices/.../sound/card1 (sound)
#   UDEV  [timestamp] remove /devices/.../sound/card1 (sound)
_EVENT_RE = re.compile(r"^(KERNEL|UDEV)\s*\[[\d.]+\]\s+(\w+)\s+\S+\s+\(sound\)")

_DEBOUNCE_SECONDS = 0.5


def parse_event_line(line: str) -> Optional[str]:
    """Return the action ('add', 'remove', etc.) for a udev event line, or None.

    Exposed for tests.
    """
    m = _EVENT_RE.match(line.strip())
    return m.group(2) if m else None


def debounce_events(
    lines: Iterable[str],
    on_event: Callable[[str], None],
    *,
    debounce_seconds: float = _DEBOUNCE_SECONDS,
    _clock: Callable[[], float] = time.monotonic,
) -> None:
    """Coalesce bursts of udev event lines into one callback per quiet period.

    Pure function over an iterable of lines, for deterministic testing.
    Fires `on_event(last_action)` after `debounce_seconds` of silence
    following one or more matching events.
    """
    pending_action: Optional[str] = None
    deadline: Optional[float] = None
    for line in lines:
        now = _clock()
        # If we have a pending event and its quiet period has elapsed, flush.
        if pending_action is not None and deadline is not None and now >= deadline:
            on_event(pending_action)
            pending_action = None
            deadline = None
        action = parse_event_line(line)
        if action is None:
            continue
        pending_action = action
        deadline = now + debounce_seconds
    # Flush any remaining pending event at end of stream.
    if pending_action is not None:
        on_event(pending_action)


def _iter_lines_with_silence_flushes(
    stdout,
    debounce_seconds: float,
) -> Iterable[str]:
    """Yield lines from stdout, plus a synthetic empty string after each burst.

    Empty strings let `debounce_events` notice quiet periods even when no
    more udev events are arriving (i.e. the last event of a burst). Between
    bursts the select blocks with no timeout, so an idle listener never wakes.

    Any line arms the one-shot silence flush (classifying lines is
    debounce_events' job, and arming on a superset of what it debounces can
    only add one harmless flush, never miss one).
    """
    armed = False  # a line arrived; one silence flush is owed
    while True:
        r, _, _ = select.select([stdout], [], [], debounce_seconds if armed else None)
        if r:
            line = stdout.readline()
            if not line:  # EOF
                return
            armed = True
            yield line
        else:
            # Silence window elapsed. Yield a non-matching marker so
            # debounce_events sees a "now" past the deadline.
            armed = False
            yield ""


def run_hotplug_loop(
    on_event: Callable[[str], None],
    *,
    debounce_seconds: float = _DEBOUNCE_SECONDS,
    _monitor_cmd: Optional[list[str]] = None,
) -> None:
    """Run the udev monitor loop until the subprocess exits."""
    cmd = _monitor_cmd or [
        "udevadm", "monitor",
        "--subsystem-match=sound",
        "--udev",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except (FileNotFoundError, OSError):
        return

    stopping = threading.Event()

    def _kill() -> None:
        stopping.set()
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            pass

    def _fire(action: str) -> None:
        # Our own terminate() EOFs the pipe, and EOF flushes any pending
        # event. Firing it here would run a full mixer re-probe against an
        # already-stopped app, mid-shutdown.
        if not stopping.is_set():
            on_event(action)

    atexit.register(_kill)
    # A hook registered after finalization began never runs, and we start on
    # the mixer-warmup thread, which can still be working when Purple exits.
    if sys.is_finalizing():
        _kill()
        return

    try:
        assert proc.stdout is not None
        debounce_events(
            _iter_lines_with_silence_flushes(proc.stdout, debounce_seconds),
            _fire,
            debounce_seconds=debounce_seconds,
        )
    finally:
        atexit.unregister(_kill)
        _kill()


def start(
    on_event: Callable[[str], None],
    *,
    debounce_seconds: float = _DEBOUNCE_SECONDS,
    _monitor_cmd: Optional[list[str]] = None,
) -> threading.Thread:
    """Start the hotplug listener in a daemon thread. Returns the thread."""
    t = threading.Thread(
        target=run_hotplug_loop,
        args=(on_event,),
        kwargs={"debounce_seconds": debounce_seconds, "_monitor_cmd": _monitor_cmd},
        daemon=True,
        name="audio-hotplug",
    )
    t.start()
    return t
