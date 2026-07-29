"""Tests for purple_tui.audio_hotplug.

Covers:
- udev event line parsing (known-good and unrelated lines)
- debounce: a burst of adds within the window fires exactly one callback
- debounce: events separated by quiet periods fire separately
- debounce: end-of-stream flushes a pending event
- line iterator: blocks with no timeout when idle, ticks only during a burst
- the monitor subprocess is killed when the parent exits (no orphans)
- a pending event is not flushed into on_event during shutdown
"""

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from purple_tui import audio_hotplug
from purple_tui.audio_hotplug import debounce_events, parse_event_line


def test_parse_add_event():
    line = "UDEV  [1234.567] add      /devices/pci/sound/card1 (sound)"
    assert parse_event_line(line) == "add"


def test_parse_remove_event():
    line = "KERNEL[1234.567] remove   /devices/pci/sound/card1 (sound)"
    assert parse_event_line(line) == "remove"


def test_parse_non_sound_line_returns_none():
    assert parse_event_line("UDEV [1234.567] add /devices/pci/block/sda (block)") is None
    assert parse_event_line("random unrelated output") is None
    assert parse_event_line("") is None


def test_debounce_coalesces_burst():
    """Three adds within 0.5s debounce window fire one callback."""
    fires: list[str] = []
    # Fake clock: each call returns an incremented time in 0.1s steps.
    now = [0.0]
    def clock():
        now[0] += 0.1
        return now[0]

    lines = [
        "UDEV [1.0] add /devices/pci/sound/card1 (sound)",
        "UDEV [1.1] add /devices/pci/sound/card1/controlC1 (sound)",
        "UDEV [1.2] add /devices/pci/sound/card1/pcmC1D0p (sound)",
    ]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == ["add"]


def test_debounce_separates_distant_events():
    """Events with a quiet period between them fire separately."""
    fires: list[str] = []
    # Clock returns widely-separated times.
    times = iter([0.0, 10.0, 20.0, 30.0])
    def clock():
        return next(times)

    lines = [
        "UDEV [1] add /devices/pci/sound/card1 (sound)",
        "",  # silence flush
        "UDEV [2] remove /devices/pci/sound/card1 (sound)",
    ]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == ["add", "remove"]


def test_debounce_flushes_on_end_of_stream():
    """A trailing pending event fires even if stream ends without silence."""
    fires: list[str] = []
    def clock() -> float:
        return 0.0
    lines = ["UDEV [1] add /devices/pci/sound/card1 (sound)"]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == ["add"]


def test_debounce_ignores_non_matching_lines_alone():
    """Lines that don't match the sound pattern don't trigger callbacks."""
    fires: list[str] = []
    def clock() -> float:
        return 0.0
    lines = [
        "some random stderr",
        "UDEV [1] add /devices/pci/block/sda (block)",  # wrong subsystem
    ]
    debounce_events(lines, fires.append, debounce_seconds=0.5, _clock=clock)
    assert fires == []


def test_iterator_blocks_when_idle_and_ticks_during_burst(monkeypatch):
    """The idle listener must select with no timeout (zero wakeups); any
    line arms the debounce timeout until the silence flush disarms it."""
    timeouts: list[float | None] = []
    script = iter([
        ("ready", "monitor will print the received events for:\n"),
        ("ready", "KERNEL[12.3] add /devices/pci/sound/card1 (sound)\n"),
        ("silence", None),
        ("ready", ""),  # EOF
    ])
    pending: list[str] = []

    class Stdout:
        def readline(self):
            return pending.pop()

    stdout = Stdout()

    def fake_select(rlist, wlist, xlist, timeout=None):
        timeouts.append(timeout)
        kind, line = next(script)
        if kind == "ready":
            pending.append(line)
            return rlist, [], []
        return [], [], []

    monkeypatch.setattr(audio_hotplug.select, "select", fake_select)
    yielded = list(audio_hotplug._iter_lines_with_silence_flushes(stdout, 0.5))

    # Idle (None), armed after any line (0.5, 0.5), disarmed again after
    # the silence flush (None).
    assert timeouts == [None, 0.5, 0.5, None]
    assert yielded == [
        "monitor will print the received events for:\n",
        "KERNEL[12.3] add /devices/pci/sound/card1 (sound)\n",
        "",
    ]


# --- in-process tests: fake monitor, no subprocess ------------------------


class _FakePopen:
    """Stands in for the udevadm subprocess.

    `on_readline` runs before each line is returned, so a test can fire the
    atexit hook at a chosen point in the stream.
    """

    def __init__(self, lines, on_readline=None):
        self._lines = list(lines)
        self._on_readline = on_readline
        self.stdout = self
        self.terminated = False
        self.waited = False

    def readline(self):
        if self._on_readline:
            self._on_readline(self)
        return self._lines.pop(0) if self._lines else ""

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited = True
        return 0


def _install_fake_monitor(monkeypatch, lines, on_readline=None):
    """Patch Popen, select, and atexit. Returns (proc, fired, hooks)."""
    proc = _FakePopen(lines, on_readline)
    hooks = []
    fired = []
    monkeypatch.setattr(audio_hotplug.subprocess, "Popen", lambda *a, **kw: proc)
    monkeypatch.setattr(
        audio_hotplug.select, "select", lambda r, w, x, timeout=None: (r, [], [])
    )
    monkeypatch.setattr(audio_hotplug.atexit, "register", hooks.append)
    monkeypatch.setattr(
        audio_hotplug.atexit, "unregister", lambda f: hooks.remove(f) if f in hooks else None
    )
    return proc, fired, hooks


SOUND_EVENT = "UDEV  [12.3] remove /devices/pci/sound/card1 (sound)\n"


def test_pending_event_is_flushed_when_the_monitor_dies_on_its_own(monkeypatch):
    """EOF we did not cause still delivers the pending event."""
    proc, fired, _ = _install_fake_monitor(monkeypatch, [SOUND_EVENT])
    audio_hotplug.run_hotplug_loop(fired.append, debounce_seconds=30)
    assert fired == ["remove"]


def test_pending_event_is_not_flushed_after_our_own_shutdown_kill(monkeypatch):
    """The atexit kill EOFs the pipe; that must not re-enter the mixer.

    Firing on_event here would run reinit_mixer_after_hotplug and
    call_from_thread against an app that has already stopped.
    """
    def exit_before_eof(p):
        # First readline delivers the event; the next one is the interpreter
        # going down, which runs the hook and closes the pipe. `hooks` resolves
        # at call time, after the unpacking below has bound it.
        if not p._lines:
            for hook in list(hooks):
                hook()

    proc, fired, hooks = _install_fake_monitor(
        monkeypatch, [SOUND_EVENT], on_readline=exit_before_eof
    )

    audio_hotplug.run_hotplug_loop(fired.append, debounce_seconds=30)

    assert fired == [], "on_event fired during interpreter shutdown"
    assert proc.terminated


def test_monitor_is_terminated_and_reaped(monkeypatch):
    proc, fired, _ = _install_fake_monitor(monkeypatch, [])
    audio_hotplug.run_hotplug_loop(fired.append)
    assert proc.terminated and proc.waited


def test_atexit_hook_is_unregistered_on_the_normal_path(monkeypatch):
    proc, fired, hooks = _install_fake_monitor(monkeypatch, [])
    audio_hotplug.run_hotplug_loop(fired.append)
    assert hooks == []


def test_atexit_hook_kills_the_monitor(monkeypatch):
    """The hook is the only cleanup that runs when a daemon thread is killed."""
    proc, fired, hooks = _install_fake_monitor(monkeypatch, [])
    monkeypatch.setattr(audio_hotplug.atexit, "unregister", lambda f: None)

    audio_hotplug.run_hotplug_loop(fired.append)

    assert hooks, "no atexit hook registered"
    proc.terminated = False
    hooks[0]()
    assert proc.terminated


def test_monitor_is_killed_when_started_during_finalization(monkeypatch):
    """start() runs on the warmup thread, which may still be going at exit."""
    proc, fired, _ = _install_fake_monitor(monkeypatch, [SOUND_EVENT])
    monkeypatch.setattr(audio_hotplug.sys, "is_finalizing", lambda: True)

    audio_hotplug.run_hotplug_loop(fired.append)

    assert proc.terminated, "monitor leaked when registered too late to run"
    assert fired == []


def test_popen_failure_is_survivable(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("udevadm")

    monkeypatch.setattr(audio_hotplug.subprocess, "Popen", boom)
    audio_hotplug.run_hotplug_loop(lambda a: None)


def test_start_runs_the_loop_on_a_daemon_thread(monkeypatch):
    captured = {}

    def fake_loop(on_event, **kwargs):
        captured["on_event"] = on_event
        captured["kwargs"] = kwargs

    monkeypatch.setattr(audio_hotplug, "run_hotplug_loop", fake_loop)

    def cb(action):
        pass

    t = audio_hotplug.start(cb, _monitor_cmd=["true"])
    t.join(timeout=5)

    assert not t.is_alive()
    assert t.daemon
    assert captured["on_event"] is cb
    assert captured["kwargs"]["_monitor_cmd"] == ["true"]


# --- end-to-end: a real child process must not leak a real monitor --------

_MONITOR_STUB = """\
import os, sys, time
with open(sys.argv[1], "w") as f:
    f.write(str(os.getpid()))
if sys.argv[2]:
    sys.stdout.write(sys.argv[2])
    sys.stdout.flush()
time.sleep(600)
"""


def _run_child(tmp_path, *, emit="", debounce=0.5, linger=0.1):
    """Run the listener in a real child process that then exits.

    Returns the monitor's pid and whether on_event fired in the child.
    """
    pidfile = tmp_path / "monitor.pid"
    firedfile = tmp_path / "fired"
    program = textwrap.dedent(f"""
        import sys, time
        from purple_tui import audio_hotplug

        def on_event(action):
            with open({str(firedfile)!r}, "w") as f:
                f.write(action)

        cmd = [sys.executable, "-c", {_MONITOR_STUB!r}, {str(pidfile)!r}, {emit!r}]
        audio_hotplug.start(on_event, _monitor_cmd=cmd, debounce_seconds={debounce})

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if (pid := open({str(pidfile)!r}).read()):
                    break
            except OSError:
                pass
            time.sleep(0.02)
        time.sleep({linger})
    """)
    repo_root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    subprocess.run(
        [sys.executable, "-c", program],
        cwd=repo_root, env=env, check=True, timeout=60,
        capture_output=True, text=True,
    )
    assert pidfile.exists() and pidfile.read_text().strip(), (
        "the monitor never spawned, so this test proved nothing"
    )
    return int(pidfile.read_text()), firedfile.exists()


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _reap(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def test_monitor_child_dies_when_parent_exits(tmp_path):
    """The monitor must not outlive the app that spawned it."""
    pid, _ = _run_child(tmp_path)
    try:
        for _ in range(50):
            if not _alive(pid):
                break
            time.sleep(0.1)
        assert not _alive(pid), f"monitor {pid} survived the parent"
    finally:
        _reap(pid)


def test_no_event_callback_during_real_shutdown(tmp_path):
    """A pending event must not fire while the interpreter is going down."""
    pid, fired = _run_child(tmp_path, emit=SOUND_EVENT, debounce=30)
    try:
        assert not fired, "on_event ran during shutdown"
    finally:
        _reap(pid)
