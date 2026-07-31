"""fd-2 routing: C-level warnings go to the log, Textual keeps the terminal.

onnxruntime prints "Unknown CPU vendor" with a raw write to fd 2 when cpuinfo
can't identify the CPU (every VM, and the machines we record demos on), which
landed in the middle of the Ask line. Swapping sys.stderr never stopped it.

Both cases run in a subprocess: hide_native_stderr() rewires the fd for the
whole process, and doing that inside pytest would take the test runner's own
stderr with it.
"""

import os
import pty
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT = """
import ctypes, sys
from purple_tui.stderr_guard import hide_native_stderr

ok = hide_native_stderr(sys.argv[1])
ctypes.CDLL("libc.so.6").write(2, b"native-warning\\n", 15)
print("python-stderr", file=sys.stderr, flush=True)
sys.__stderr__.write("textual-paint")
sys.__stderr__.flush()
print(f"redirected={ok}")
"""


def _run(stderr, log_path):
    return subprocess.run(
        [sys.executable, "-c", _SCRIPT, log_path],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        timeout=30,
    )


def test_native_writes_land_in_the_log_not_on_the_terminal(tmp_path):
    log_path = str(tmp_path / "stderr.log")
    controller, terminal = pty.openpty()
    try:
        proc = _run(terminal, log_path)
        os.close(terminal)
        terminal = -1
        seen = os.read(controller, 4096).decode()
    finally:
        os.close(controller)
        if terminal != -1:
            os.close(terminal)

    assert "redirected=True" in proc.stdout
    # Textual's channel (sys.__stderr__) still reaches the real terminal...
    assert "textual-paint" in seen
    # ...while everything written to fd 2 is off-screen, in the log.
    assert "native-warning" not in seen
    assert "python-stderr" not in seen
    assert open(log_path).read() == "native-warning\npython-stderr\n"


def test_no_op_when_stderr_is_not_a_terminal(tmp_path):
    log_path = str(tmp_path / "stderr.log")
    proc = _run(subprocess.PIPE, log_path)

    assert "redirected=False" in proc.stdout
    assert "native-warning" in proc.stderr
    assert not os.path.exists(log_path)
