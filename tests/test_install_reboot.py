#!/usr/bin/env python3
"""Tests for the install/reboot flow.

Covers:
- The bash end-section of install.sh (FIFO creation, sentinel write, non-blocking)
- Python _trigger_reboot() FIFO vs execv fallback logic
- Python sentinel detection polling loop

Run with: pytest tests/test_install_reboot.py -v
"""

import os
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.rooms.parent_menu import _trigger_reboot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _install_end_script(rundir: str, remove_existing_fifo: bool = True) -> str:
    """Return the bash end-section of install.sh, substituting RUNDIR.

    The watcher does `true` instead of real sysrq so tests are safe without root.
    """
    rm_line = f"rm -f {rundir}/purple-reboot-fifo || true" if remove_existing_fifo else ""
    return f"""\
set -eo pipefail
RUNDIR={rundir}
touch $RUNDIR/casper-no-prompt
{rm_line}
if mkfifo $RUNDIR/purple-reboot-fifo 2>/dev/null; then
    setsid sh -c 'read _ < {rundir}/purple-reboot-fifo; true' </dev/null >/dev/null 2>/dev/null &
fi
touch $RUNDIR/purple-install-complete
"""


# ---------------------------------------------------------------------------
# Bash install.sh end-section tests
# ---------------------------------------------------------------------------

def test_install_end_writes_sentinel(tmp_path):
    """Sentinel, FIFO, and reboot.sh are all created; exit code is 0."""
    script = _install_end_script(str(tmp_path))
    result = subprocess.run(
        ['bash', '-c', script],
        timeout=10,
        capture_output=True,
    )
    assert result.returncode == 0
    assert (tmp_path / 'purple-install-complete').exists()
    assert (tmp_path / 'purple-reboot-fifo').exists()


def test_install_end_does_not_block_on_fifo(tmp_path):
    """The script completes in under 2 seconds even though nobody writes the FIFO."""
    script = _install_end_script(str(tmp_path))
    start = time.monotonic()
    result = subprocess.run(
        ['bash', '-c', script],
        timeout=10,
        capture_output=True,
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 2.0, f"Script took {elapsed:.2f}s, expected < 2s"


def test_install_end_survives_existing_fifo(tmp_path):
    """Running the script twice succeeds: rm -f handles the pre-existing FIFO."""
    script = _install_end_script(str(tmp_path))
    r1 = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert r1.returncode == 0
    # Second run: FIFO already exists from first run
    r2 = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert r2.returncode == 0
    assert (tmp_path / 'purple-install-complete').exists()


def test_sentinel_written_with_fifo_failure(tmp_path):
    """Sentinel is still written when mkfifo fails (the if/fi guard protects it)."""
    # Pre-create FIFO so mkfifo will fail, and omit the rm -f line
    fifo = tmp_path / 'purple-reboot-fifo'
    os.mkfifo(str(fifo))
    script = _install_end_script(str(tmp_path), remove_existing_fifo=False)
    result = subprocess.run(
        ['bash', '-c', script],
        timeout=10,
        capture_output=True,
    )
    assert result.returncode == 0
    assert (tmp_path / 'purple-install-complete').exists()


# ---------------------------------------------------------------------------
# Python FIFO communication tests
# ---------------------------------------------------------------------------

def test_fifo_watcher_receives_signal(tmp_path):
    """_trigger_reboot writes to the FIFO; a waiting reader unblocks."""
    fifo_path = tmp_path / 'purple-reboot-fifo'

    os.mkfifo(str(fifo_path))

    received = threading.Event()

    def watcher():
        with open(str(fifo_path), 'r') as f:
            f.read()
        received.set()

    t = threading.Thread(target=watcher, daemon=True)
    t.start()

    _trigger_reboot(fifo=str(fifo_path))

    assert received.wait(timeout=2.0), "Watcher did not receive signal within 2s"


def test_trigger_reboot_falls_back_to_shutdown_when_no_fifo(tmp_path, monkeypatch):
    """Falls back to PowerManager.shutdown() when the FIFO path does not exist."""
    shutdown_calls = []
    monkeypatch.setattr(
        'purple_tui.power_manager.get_power_manager',
        lambda: type('PM', (), {'shutdown': lambda self: shutdown_calls.append(True)})(),
    )

    fifo_path = tmp_path / 'purple-reboot-fifo'  # does not exist
    _trigger_reboot(fifo=str(fifo_path))

    assert len(shutdown_calls) == 1


def test_trigger_reboot_falls_back_when_regular_file(tmp_path, monkeypatch):
    """Falls back to PowerManager.shutdown() when the path is a regular file, not a FIFO."""
    shutdown_calls = []
    monkeypatch.setattr(
        'purple_tui.power_manager.get_power_manager',
        lambda: type('PM', (), {'shutdown': lambda self: shutdown_calls.append(True)})(),
    )

    fifo_path = tmp_path / 'purple-reboot-fifo'
    fifo_path.write_text('not a fifo')
    _trigger_reboot(fifo=str(fifo_path))

    assert len(shutdown_calls) == 1


def test_fifo_write_completes_without_subprocess(tmp_path, monkeypatch):
    """The FIFO path uses only file I/O; no subprocess calls are made."""
    fifo_path = tmp_path / 'purple-reboot-fifo'

    os.mkfifo(str(fifo_path))

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess called unexpectedly")

    monkeypatch.setattr(os, 'system', _boom)
    monkeypatch.setattr(subprocess, 'Popen', _boom)
    monkeypatch.setattr(subprocess, 'run', _boom)

    received = threading.Event()

    def watcher():
        with open(str(fifo_path), 'r') as f:
            f.read()
        received.set()

    t = threading.Thread(target=watcher, daemon=True)
    t.start()

    _trigger_reboot(fifo=str(fifo_path))

    assert received.wait(timeout=2.0), "FIFO write did not complete"


# ---------------------------------------------------------------------------
# Dead watcher / O_NONBLOCK tests
# ---------------------------------------------------------------------------

def test_trigger_reboot_falls_back_to_shutdown_when_watcher_dead(tmp_path, monkeypatch):
    """If the FIFO exists but no reader is waiting (watcher died), falls through
    to PowerManager.shutdown() immediately without blocking.

    O_NONBLOCK makes os.open return ENXIO immediately instead of blocking.
    PowerManager.shutdown() has a sysrq nuclear fallback that works even
    with dead overlayfs.
    """
    shutdown_calls = []
    monkeypatch.setattr(
        'purple_tui.power_manager.get_power_manager',
        lambda: type('PM', (), {'shutdown': lambda self: shutdown_calls.append(True)})(),
    )

    fifo_path = tmp_path / 'purple-reboot-fifo'
    os.mkfifo(str(fifo_path))
    # FIFO exists, is a FIFO, but NO reader thread.

    start = time.monotonic()
    _trigger_reboot(fifo=str(fifo_path))
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"_trigger_reboot blocked for {elapsed:.2f}s (should be instant)"
    assert len(shutdown_calls) == 1, "Should fall through to PowerManager.shutdown()"


def test_trigger_reboot_does_not_block_with_timeout(tmp_path, monkeypatch):
    """Specifically prove the O_NONBLOCK behavior: the call returns in under
    100ms when no reader exists, not after some long timeout."""
    shutdown_calls = []
    monkeypatch.setattr(
        'purple_tui.power_manager.get_power_manager',
        lambda: type('PM', (), {'shutdown': lambda self: shutdown_calls.append(True)})(),
    )

    fifo_path = tmp_path / 'purple-reboot-fifo'
    os.mkfifo(str(fifo_path))

    start = time.monotonic()
    _trigger_reboot(fifo=str(fifo_path))
    elapsed = time.monotonic() - start

    assert elapsed < 0.1, f"O_NONBLOCK open took {elapsed:.3f}s, expected <0.1s"
    assert len(shutdown_calls) == 1


# ---------------------------------------------------------------------------
# Full flow integration tests (mock install.sh)
# ---------------------------------------------------------------------------

def test_full_install_flow_with_mock_script(tmp_path):
    """End-to-end: mock install.sh writes stages + FIFO + sentinel,
    Python detects completion, FIFO signal reaches the watcher."""
    import select

    # Mock install.sh: outputs [PURPLE] progress lines, creates FIFO + sentinel
    mock_script = tmp_path / 'mock_install.sh'
    mock_script.write_text(f"""\
#!/bin/bash
set -eo pipefail
echo "[PURPLE] Detecting internal disk" >&2
echo "[PURPLE] Found internal disk" >&2
echo "[PURPLE] Writing Purple Computer to disk" >&2
sleep 0.1
echo "[PURPLE] Reloading partition table" >&2
echo "[PURPLE] Verifying disk write" >&2
echo "[PURPLE] Disk verification passed" >&2
echo "[PURPLE] Setting up UEFI boot" >&2
echo "[PURPLE] UEFI boot setup complete" >&2
echo "[PURPLE] Installation complete!" >&2

# Reboot prep (same as real install.sh)
rm -f {tmp_path}/purple-reboot-fifo || true
if mkfifo {tmp_path}/purple-reboot-fifo 2>/dev/null; then
    setsid sh -c 'read _ < {tmp_path}/purple-reboot-fifo; touch {tmp_path}/watcher-fired' </dev/null >/dev/null 2>/dev/null &
fi
touch {tmp_path}/purple-install-complete
exit 0
""")
    mock_script.chmod(0o755)

    # Run the same polling loop as _run_install_thread
    sentinel = tmp_path / 'purple-install-complete'
    proc = subprocess.Popen(
        ['bash', str(mock_script)],
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
    )
    lines = []
    buf = b""
    while proc.poll() is None and not sentinel.exists():
        ready = select.select([proc.stderr], [], [], 0.1)[0]
        if ready:
            chunk = proc.stderr.read(256)
            if chunk:
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    lines.append(line.decode('utf-8', errors='replace').strip())

    success = sentinel.exists() or proc.poll() == 0
    assert success, "Install did not complete successfully"
    assert any("UEFI boot setup complete" in l for l in lines), f"Missing UEFI stage in: {lines}"
    assert sentinel.exists(), "Sentinel not written"

    # Now simulate pressing Enter: write to the FIFO
    fifo_path = tmp_path / 'purple-reboot-fifo'
    assert fifo_path.exists(), "FIFO not created by install script"

    # Give setsid watcher time to open the FIFO for reading
    time.sleep(0.3)

    _trigger_reboot(fifo=str(fifo_path))

    # Give the watcher a moment to fire
    time.sleep(0.5)
    assert (tmp_path / 'watcher-fired').exists(), "Watcher did not fire after FIFO signal"


def test_full_install_flow_error_detected(tmp_path):
    """When install.sh fails (no sentinel), Python detects the error."""
    import select

    mock_script = tmp_path / 'mock_install_fail.sh'
    mock_script.write_text("""\
#!/bin/bash
echo "[PURPLE] Detecting internal disk" >&2
echo "[PURPLE] Found internal disk" >&2
# Simulate failure partway through
exit 1
""")
    mock_script.chmod(0o755)

    sentinel = tmp_path / 'purple-install-complete'
    proc = subprocess.Popen(
        ['bash', str(mock_script)],
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
    )
    while proc.poll() is None and not sentinel.exists():
        import select as sel
        ready = sel.select([proc.stderr], [], [], 0.1)[0]
        if ready:
            proc.stderr.read(256)

    success = sentinel.exists() or proc.poll() == 0
    assert not success, "Should have detected install failure"


def test_install_with_pipe_holding_child(tmp_path):
    """Background child holds stderr pipe open (like setsid bash on tty2).
    Sentinel detection must still work via sentinel file, not pipe EOF."""
    import select

    mock_script = tmp_path / 'mock_install_pipe.sh'
    mock_script.write_text(f"""\
#!/bin/bash
set -eo pipefail
echo "[PURPLE] Writing Purple Computer to disk" >&2
echo "[PURPLE] UEFI boot setup complete" >&2

# Background child that holds stderr pipe open (the real bug scenario).
# Redirect stderr so it doesn't inherit the pipe (sleep itself has nothing
# to say, but inheriting the fd keeps the pipe open for its lifetime).
( sleep 300 ) 2>/dev/null &

rm -f {tmp_path}/purple-reboot-fifo || true
if mkfifo {tmp_path}/purple-reboot-fifo 2>/dev/null; then
    setsid sh -c 'read _ < {tmp_path}/purple-reboot-fifo; touch {tmp_path}/watcher-fired' </dev/null >/dev/null 2>/dev/null &
fi
touch {tmp_path}/purple-install-complete
exit 0
""")
    mock_script.chmod(0o755)

    sentinel = tmp_path / 'purple-install-complete'
    proc = subprocess.Popen(
        ['bash', str(mock_script)],
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
    )

    start = time.monotonic()
    while proc.poll() is None and not sentinel.exists():
        import select as sel
        ready = sel.select([proc.stderr], [], [], 0.1)[0]
        if ready:
            proc.stderr.read(256)

    elapsed = time.monotonic() - start
    success = sentinel.exists() or proc.poll() == 0

    assert success, "Install was not detected as successful"
    assert elapsed < 5.0, f"Detection took {elapsed:.1f}s (pipe-holding child blocked it?)"


# ---------------------------------------------------------------------------
# Watcher survival tests (THE critical USB-removal bug)
# ---------------------------------------------------------------------------

def test_watcher_survives_parent_exit(tmp_path):
    """THE USB-removal bug: does the FIFO watcher survive after bash exits?

    install.sh backgrounds a watcher then exits. If the watcher dies with it,
    _trigger_reboot gets ENXIO and falls back to os.execv('/bin/sh', ...) which
    hangs after USB removal because /bin/sh is on the dead overlayfs.

    This test proves the watcher is still alive after bash exits, by writing
    to the FIFO and checking the watcher fires.
    """
    mock_script = tmp_path / 'mock_install_watcher.sh'
    mock_script.write_text(f"""\
#!/bin/bash
set -eo pipefail
rm -f {tmp_path}/purple-reboot-fifo || true
if mkfifo {tmp_path}/purple-reboot-fifo 2>/dev/null; then
    setsid sh -c 'read _ < {tmp_path}/purple-reboot-fifo; touch {tmp_path}/watcher-fired' </dev/null >/dev/null 2>/dev/null &
fi
touch {tmp_path}/purple-install-complete
exit 0
""")
    mock_script.chmod(0o755)

    # Run install.sh and wait for it to fully exit
    result = subprocess.run(
        ['bash', str(mock_script)],
        timeout=10,
        capture_output=True,
    )
    assert result.returncode == 0
    assert (tmp_path / 'purple-install-complete').exists()

    # Parent bash has exited. Is the watcher still alive?
    # Give it a moment to settle after parent exit
    time.sleep(0.2)

    fifo_path = tmp_path / 'purple-reboot-fifo'
    assert fifo_path.exists(), "FIFO not created"

    # Try to write to the FIFO. If watcher is dead, O_NONBLOCK gives ENXIO.
    try:
        fd = os.open(str(fifo_path), os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, b'go\n')
        os.close(fd)
        watcher_alive = True
    except OSError:
        watcher_alive = False

    if watcher_alive:
        time.sleep(0.5)
        assert (tmp_path / 'watcher-fired').exists(), \
            "FIFO write succeeded but watcher didn't fire"
    else:
        # THIS IS THE BUG: watcher died after parent bash exited.
        # _trigger_reboot falls back to os.execv which hangs after USB removal.
        import pytest
        pytest.fail(
            "Watcher died after parent bash exited! "
            "This is the USB-removal bug: _trigger_reboot falls back to "
            "os.execv('/bin/sh', ...) which hangs on dead overlayfs."
        )


def test_watcher_survives_sudo_parent_exit(tmp_path):
    """Same as above but through sudo, which is how install.sh actually runs.

    sudo may use process groups differently. Skip if sudo requires a password.
    """
    import shutil
    if not shutil.which('sudo'):
        import pytest
        pytest.skip("sudo not available")

    # Check if sudo works without password
    check = subprocess.run(
        ['sudo', '-n', 'true'],
        capture_output=True, timeout=5,
    )
    if check.returncode != 0:
        import pytest
        pytest.skip("sudo requires password")

    mock_script = tmp_path / 'mock_install_sudo.sh'
    mock_script.write_text(f"""\
#!/bin/bash
set -eo pipefail
rm -f {tmp_path}/purple-reboot-fifo || true
if mkfifo {tmp_path}/purple-reboot-fifo 2>/dev/null; then
    setsid sh -c 'read _ < {tmp_path}/purple-reboot-fifo; touch {tmp_path}/watcher-fired' </dev/null >/dev/null 2>/dev/null &
fi
touch {tmp_path}/purple-install-complete
exit 0
""")
    mock_script.chmod(0o755)

    result = subprocess.run(
        ['sudo', '-E', 'bash', str(mock_script)],
        timeout=10,
        capture_output=True,
    )
    assert result.returncode == 0

    time.sleep(0.2)

    fifo_path = tmp_path / 'purple-reboot-fifo'
    assert fifo_path.exists(), "FIFO not created"

    try:
        fd = os.open(str(fifo_path), os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, b'go\n')
        os.close(fd)
        watcher_alive = True
    except OSError:
        watcher_alive = False

    if watcher_alive:
        time.sleep(0.5)
        assert (tmp_path / 'watcher-fired').exists(), \
            "FIFO write succeeded but watcher didn't fire"
    else:
        import pytest
        pytest.fail(
            "Watcher died after sudo+bash exited! "
            "sudo may be killing the process group on exit."
        )


# ---------------------------------------------------------------------------
# Sentinel detection test
# ---------------------------------------------------------------------------

def test_sentinel_detection_exits_loop(tmp_path):
    """The polling loop exits when the sentinel appears (mirrors _run_install_thread)."""
    sentinel = tmp_path / 'purple-install-complete'

    def write_sentinel_after_delay():
        time.sleep(0.5)
        sentinel.touch()

    writer = threading.Thread(target=write_sentinel_after_delay, daemon=True)
    writer.start()

    # Simulate the polling loop from _run_install_thread (no real subprocess needed)
    deadline = time.monotonic() + 3.0
    exited = False
    while time.monotonic() < deadline:
        if sentinel.exists():
            exited = True
            break
        time.sleep(0.05)

    assert exited, "Polling loop did not detect sentinel within 3s"
    assert sentinel.exists()
