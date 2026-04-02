#!/usr/bin/env python3
"""Tests for the install/reboot flow.

Covers:
- The bash end-section of install.sh (reboot scripts, binary, sentinel)
- Sentinel detection polling loop
- Pipe-holding child doesn't block sentinel detection

Run with: pytest tests/test_install_reboot.py -v
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _install_end_script(rundir: str) -> str:
    """Return the bash end-section of install.sh, substituting paths."""
    return f"""\
set -eo pipefail
RUNDIR={rundir}
touch $RUNDIR/casper-no-prompt
echo '#!/bin/sh' > $RUNDIR/purple-reboot
chmod 755 $RUNDIR/purple-reboot
cat > $RUNDIR/purple-reboot.sh << 'EOF'
#!/bin/sh
clear
echo "All done!"
read _
EOF
chmod 755 $RUNDIR/purple-reboot.sh
touch $RUNDIR/purple-install-complete
"""


# ---------------------------------------------------------------------------
# Bash install.sh end-section tests
# ---------------------------------------------------------------------------

def test_install_end_writes_sentinel(tmp_path):
    """Sentinel, reboot script, and binary are all created."""
    script = _install_end_script(str(tmp_path))
    result = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert result.returncode == 0
    assert (tmp_path / 'purple-install-complete').exists()
    assert (tmp_path / 'purple-reboot.sh').exists()
    assert (tmp_path / 'purple-reboot').exists()


def test_install_end_does_not_block(tmp_path):
    """The script completes quickly."""
    script = _install_end_script(str(tmp_path))
    start = time.monotonic()
    result = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert result.returncode == 0
    assert time.monotonic() - start < 2.0


def test_install_end_reboot_script_is_executable(tmp_path):
    """The reboot script has execute permission."""
    script = _install_end_script(str(tmp_path))
    subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert os.access(str(tmp_path / 'purple-reboot.sh'), os.X_OK)


def test_install_end_idempotent(tmp_path):
    """Running the script twice succeeds."""
    script = _install_end_script(str(tmp_path))
    r1 = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    r2 = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True)
    assert r1.returncode == 0
    assert r2.returncode == 0


# ---------------------------------------------------------------------------
# Full flow integration tests
# ---------------------------------------------------------------------------

def test_full_install_flow_with_mock_script(tmp_path):
    """Mock install.sh writes stages + reboot script + sentinel."""
    import select

    mock_script = tmp_path / 'mock_install.sh'
    mock_script.write_text(f"""\
#!/bin/bash
set -eo pipefail
echo "[PURPLE] Detecting internal disk" >&2
echo "[PURPLE] Writing Purple Computer to disk" >&2
echo "[PURPLE] UEFI boot setup complete" >&2
echo '#!/bin/sh' > {tmp_path}/purple-reboot.sh
chmod 755 {tmp_path}/purple-reboot.sh
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

    assert sentinel.exists()
    assert (tmp_path / 'purple-reboot.sh').exists()
    assert any("UEFI boot setup complete" in l for l in lines)


def test_full_install_flow_error_detected(tmp_path):
    """When install.sh fails (no sentinel), Python detects the error."""
    mock_script = tmp_path / 'mock_install_fail.sh'
    mock_script.write_text("""\
#!/bin/bash
echo "[PURPLE] Detecting internal disk" >&2
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

    assert not (sentinel.exists() or proc.poll() == 0)


def test_install_with_pipe_holding_child(tmp_path):
    """Background child holds stderr pipe open. Sentinel detection still works."""
    mock_script = tmp_path / 'mock_install_pipe.sh'
    mock_script.write_text(f"""\
#!/bin/bash
set -eo pipefail
echo "[PURPLE] Writing Purple Computer to disk" >&2
( sleep 300 ) 2>/dev/null &
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

    assert sentinel.exists()
    assert time.monotonic() - start < 5.0


# ---------------------------------------------------------------------------
# Sentinel detection test
# ---------------------------------------------------------------------------

def test_sentinel_detection_exits_loop(tmp_path):
    """The polling loop exits when the sentinel appears."""
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

    assert exited
