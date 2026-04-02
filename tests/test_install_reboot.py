#!/usr/bin/env python3
"""Tests for the install/reboot flow.

Covers:
- The bash end-section of install.sh (setuid binary copy, sentinel write)
- Python _trigger_reboot() setuid binary vs PowerManager fallback
- Sentinel detection polling loop

Run with: pytest tests/test_install_reboot.py -v
"""

import os
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

def _install_end_script(rundir: str, reboot_bin_src: str | None = None) -> str:
    """Return the bash end-section of install.sh, substituting paths.

    If reboot_bin_src is provided, it's used as the source binary.
    Otherwise creates a dummy binary to simulate the real flow.
    """
    if reboot_bin_src:
        cp_line = f"cp {reboot_bin_src} {rundir}/purple-reboot"
    else:
        # Create a dummy executable to simulate the static binary
        cp_line = f"echo '#!/bin/sh' > {rundir}/purple-reboot"
    return f"""\
set -eo pipefail
RUNDIR={rundir}
touch $RUNDIR/casper-no-prompt
{cp_line}
chmod 4755 $RUNDIR/purple-reboot 2>/dev/null || chmod 755 $RUNDIR/purple-reboot
touch $RUNDIR/purple-install-complete
"""


# ---------------------------------------------------------------------------
# Bash install.sh end-section tests
# ---------------------------------------------------------------------------

def test_install_end_writes_sentinel(tmp_path):
    """Sentinel and reboot binary are both created; exit code is 0."""
    script = _install_end_script(str(tmp_path))
    result = subprocess.run(
        ['bash', '-c', script],
        timeout=10,
        capture_output=True,
    )
    assert result.returncode == 0
    assert (tmp_path / 'purple-install-complete').exists()
    assert (tmp_path / 'purple-reboot').exists()


def test_install_end_does_not_block(tmp_path):
    """The script completes in under 2 seconds (no FIFO blocking)."""
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


def test_install_end_reboot_binary_is_executable(tmp_path):
    """The reboot binary has execute permission after install.sh runs."""
    script = _install_end_script(str(tmp_path))
    subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    reboot_bin = tmp_path / 'purple-reboot'
    assert reboot_bin.exists()
    assert os.access(str(reboot_bin), os.X_OK)


def test_install_end_idempotent(tmp_path):
    """Running the script twice succeeds (no leftover FIFOs blocking)."""
    script = _install_end_script(str(tmp_path))
    r1 = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert r1.returncode == 0
    r2 = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert r2.returncode == 0
    assert (tmp_path / 'purple-install-complete').exists()


# ---------------------------------------------------------------------------
# Python _trigger_reboot() tests
# ---------------------------------------------------------------------------

def test_trigger_reboot_calls_execv_when_binary_exists(tmp_path, monkeypatch):
    """_trigger_reboot() calls os.execv with the reboot binary path."""
    reboot_bin = tmp_path / 'purple-reboot'
    reboot_bin.write_text('#!/bin/sh\ntrue\n')
    reboot_bin.chmod(0o755)

    monkeypatch.setattr('purple_tui.rooms.parent_menu._REBOOT_BIN', str(reboot_bin))

    execv_calls = []
    monkeypatch.setattr(os, 'execv', lambda path, args: execv_calls.append((path, args)))

    _trigger_reboot()

    assert len(execv_calls) == 1
    assert execv_calls[0][0] == str(reboot_bin)


def test_trigger_reboot_falls_back_when_binary_missing(tmp_path, monkeypatch):
    """Falls back to PowerManager.shutdown() when the binary doesn't exist."""
    monkeypatch.setattr(
        'purple_tui.rooms.parent_menu._REBOOT_BIN',
        str(tmp_path / 'nonexistent'),
    )

    shutdown_calls = []
    monkeypatch.setattr(
        'purple_tui.power_manager.get_power_manager',
        lambda: type('PM', (), {'shutdown': lambda self: shutdown_calls.append(True)})(),
    )

    _trigger_reboot()

    assert len(shutdown_calls) == 1


def test_trigger_reboot_falls_back_when_not_executable(tmp_path, monkeypatch):
    """Falls back to PowerManager.shutdown() when binary exists but isn't executable."""
    reboot_bin = tmp_path / 'purple-reboot'
    reboot_bin.write_text('not executable')
    reboot_bin.chmod(0o644)

    monkeypatch.setattr('purple_tui.rooms.parent_menu._REBOOT_BIN', str(reboot_bin))

    shutdown_calls = []
    monkeypatch.setattr(
        'purple_tui.power_manager.get_power_manager',
        lambda: type('PM', (), {'shutdown': lambda self: shutdown_calls.append(True)})(),
    )

    _trigger_reboot()

    assert len(shutdown_calls) == 1


def test_trigger_reboot_no_subprocess_calls(tmp_path, monkeypatch):
    """The reboot binary path uses only os.execv; no subprocess calls."""
    reboot_bin = tmp_path / 'purple-reboot'
    reboot_bin.write_text('#!/bin/sh\ntrue\n')
    reboot_bin.chmod(0o755)

    monkeypatch.setattr('purple_tui.rooms.parent_menu._REBOOT_BIN', str(reboot_bin))
    monkeypatch.setattr(os, 'execv', lambda *a: None)

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess called unexpectedly")

    monkeypatch.setattr(subprocess, 'Popen', _boom)
    monkeypatch.setattr(subprocess, 'run', _boom)

    _trigger_reboot()  # Should not raise


# ---------------------------------------------------------------------------
# Full flow integration tests (mock install.sh)
# ---------------------------------------------------------------------------

def test_full_install_flow_with_mock_script(tmp_path):
    """End-to-end: mock install.sh writes stages + reboot binary + sentinel,
    Python detects completion."""
    import select

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
echo '#!/bin/sh' > {tmp_path}/purple-reboot
chmod 755 {tmp_path}/purple-reboot
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

    assert sentinel.exists(), "Sentinel not written"
    assert (tmp_path / 'purple-reboot').exists(), "Reboot binary not created"
    assert any("UEFI boot setup complete" in l for l in lines), f"Missing UEFI stage in: {lines}"


def test_full_install_flow_error_detected(tmp_path):
    """When install.sh fails (no sentinel), Python detects the error."""
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
    mock_script = tmp_path / 'mock_install_pipe.sh'
    mock_script.write_text(f"""\
#!/bin/bash
set -eo pipefail
echo "[PURPLE] Writing Purple Computer to disk" >&2
echo "[PURPLE] UEFI boot setup complete" >&2

# Background child that holds stderr pipe open (the real bug scenario).
( sleep 300 ) 2>/dev/null &

echo '#!/bin/sh' > {tmp_path}/purple-reboot
chmod 755 {tmp_path}/purple-reboot
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

    deadline = time.monotonic() + 3.0
    exited = False
    while time.monotonic() < deadline:
        if sentinel.exists():
            exited = True
            break
        time.sleep(0.05)

    assert exited, "Polling loop did not detect sentinel within 3s"
    assert sentinel.exists()
