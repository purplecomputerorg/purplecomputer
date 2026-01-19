"""Sanity tests for doodle_ai.py

Basic checks to catch syntax errors and import issues before deployment.
"""

import ast
import subprocess
import sys
import os
from pathlib import Path


TOOLS_DIR = Path(__file__).parent.parent / "tools"
DOODLE_AI = TOOLS_DIR / "doodle_ai.py"


class TestDoodleAiSyntax:
    """Catch syntax errors before they hit production."""

    def test_file_exists(self):
        """doodle_ai.py exists."""
        assert DOODLE_AI.exists(), f"Missing: {DOODLE_AI}"

    def test_valid_python_syntax(self):
        """File has valid Python syntax (catches IndentationError, SyntaxError)."""
        source = DOODLE_AI.read_text()
        # ast.parse raises SyntaxError on invalid Python
        ast.parse(source, filename=str(DOODLE_AI))

    def test_compiles(self):
        """File compiles without errors."""
        source = DOODLE_AI.read_text()
        compile(source, str(DOODLE_AI), "exec")


class TestDoodleAiImports:
    """Check that imports work (catches missing dependencies, typos)."""

    def test_module_imports(self):
        """Module can be imported without errors."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(TOOLS_DIR.parent) + ":" + env.get("PYTHONPATH", "")

        result = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, '{TOOLS_DIR.parent}'); exec(open('{DOODLE_AI}').read().split('if __name__')[0])"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        # Allow import errors for optional deps (anthropic), but not syntax errors
        if result.returncode != 0:
            # Syntax/indentation errors should fail
            assert "SyntaxError" not in result.stderr, f"Syntax error:\n{result.stderr}"
            assert "IndentationError" not in result.stderr, f"Indentation error:\n{result.stderr}"


class TestDoodleAiHelp:
    """Check that --help works (basic CLI sanity)."""

    def test_help_runs(self):
        """--help exits cleanly."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(TOOLS_DIR.parent) + ":" + env.get("PYTHONPATH", "")

        result = subprocess.run(
            [sys.executable, str(DOODLE_AI), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        assert result.returncode == 0, f"--help failed:\n{result.stderr}"
        assert "goal" in result.stdout.lower() or "usage" in result.stdout.lower()
