"""Run ruff as a test so undefined names / unused imports break the suite.

Pyflakes (ruff's `F` rules) statically catches the class of bug where a
helper is renamed or removed but a call site is missed — e.g. the `caps()`
NameError that crashed the Play room only at render time. Catching it here
is dramatically cheaper than booting the VM.
"""

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGETS = ["purple_tui", "tools", "scripts", "tests"]


def test_ruff_clean():
    ruff = REPO_ROOT / ".venv/bin/ruff"
    if not ruff.exists():
        ruff_path = shutil.which("ruff")
        assert ruff_path, "ruff not found; run `just setup`"
        ruff = Path(ruff_path)

    result = subprocess.run(
        [str(ruff), "check", *TARGETS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"ruff found issues:\n{result.stdout}\n{result.stderr}"
    )
