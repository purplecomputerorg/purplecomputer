"""warm_mixer must always return, even when the probe child can't be reaped.

A wedged CS8409 leaves the probe in uninterruptible D-state; SIGKILL can't
reap it. The old subprocess.run path blocked forever in its post-timeout
wait(), so audio_ok stuck on None ("Audio: checking..."). warm_mixer now uses
Popen + wait(timeout) + abandon, so it returns at the deadline regardless.
"""

import subprocess
import time

from purple_tui.rooms import music_room


class _WedgedProc:
    """Times out on a bounded wait; a blocking wait (the daemon reaper) returns."""

    def __init__(self):
        self.killed = False

    def wait(self, timeout=None):
        if timeout is not None:
            raise subprocess.TimeoutExpired(cmd="probe", timeout=timeout)
        return -9  # reaper's blocking wait; pretend the kernel finally let go

    def kill(self):
        self.killed = True


def _reset(monkeypatch):
    monkeypatch.setattr(music_room, "_MIXER_READY", None)
    monkeypatch.setattr(music_room, "_PROBE_TIMED_OUT", False)
    monkeypatch.setattr(music_room, "_KNOWN_SILENT", False)
    monkeypatch.setattr(music_room, "output_is_known_silent", lambda *a, **k: False)


def test_warm_mixer_returns_when_probe_cannot_be_reaped(monkeypatch):
    _reset(monkeypatch)
    proc = _WedgedProc()
    monkeypatch.setattr(music_room.subprocess, "Popen", lambda *a, **k: proc)

    result = music_room.warm_mixer(timeout_seconds=0.2)

    assert result is False
    assert music_room._PROBE_TIMED_OUT is True
    assert proc.killed is True


def test_warm_mixer_does_not_retry_after_timeout(monkeypatch):
    _reset(monkeypatch)
    proc = _WedgedProc()
    monkeypatch.setattr(music_room.subprocess, "Popen", lambda *a, **k: proc)
    music_room.warm_mixer(timeout_seconds=0.2)

    # A timed-out probe is broken hardware: no retry.
    assert music_room._reset_mixer_state() is False


def test_warm_mixer_returns_promptly_against_a_real_hanging_probe(monkeypatch):
    """End-to-end (no mocks): a real probe child that sleeps past the timeout
    must not block warm_mixer. Exercises the real Popen + wait(timeout) + kill
    path. Note: it can't reproduce the actual D-state hang (you can't forge an
    unkillable process in userspace), so it would also pass under the old
    subprocess.run code; it guards the timeout path, not the regression itself.
    """
    _reset(monkeypatch)
    monkeypatch.setattr(music_room, "_PROBE_SCRIPT", "import time; time.sleep(30)")

    start = time.monotonic()
    result = music_room.warm_mixer(timeout_seconds=0.3)
    elapsed = time.monotonic() - start

    assert result is False
    assert music_room._PROBE_TIMED_OUT is True
    assert elapsed < 10  # bounded by the timeout, not the child's 30s sleep
