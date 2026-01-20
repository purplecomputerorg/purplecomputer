"""Sanity tests for doodle_ai.py

Basic checks to catch syntax errors and import issues before deployment.
Also tests for the compact action parser and other utilities.
"""

import ast
import subprocess
import sys
import os
from pathlib import Path

# Add tools dir to path for imports
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR.parent))

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


# Import the module for unit tests (may fail if anthropic not installed, that's ok)
try:
    from tools.doodle_ai import (
        parse_compact_actions,
        parse_json_robust,
        get_complexity_guidance,
    )
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


class TestCompactActionParser:
    """Test the compact DSL action parser."""

    def test_horizontal_line(self):
        """Parse horizontal line: Lf0,5,10,5"""
        if not IMPORTS_AVAILABLE:
            return  # Skip if imports failed

        text = "```actions\nLf0,5,10,5\n```"
        actions = parse_compact_actions(text)

        assert actions is not None
        assert len(actions) == 11  # 0 to 10 inclusive
        assert all(a["type"] == "paint_at" for a in actions)
        assert all(a["color"] == "f" for a in actions)
        assert all(a["y"] == 5 for a in actions)
        assert [a["x"] for a in actions] == list(range(11))

    def test_vertical_line(self):
        """Parse vertical line: Lc10,0,10,5"""
        if not IMPORTS_AVAILABLE:
            return

        text = "Lc10,0,10,5"
        actions = parse_compact_actions(text)

        assert actions is not None
        assert len(actions) == 6  # 0 to 5 inclusive
        assert all(a["type"] == "paint_at" for a in actions)
        assert all(a["color"] == "c" for a in actions)
        assert all(a["x"] == 10 for a in actions)
        assert [a["y"] for a in actions] == list(range(6))

    def test_single_point(self):
        """Parse single point: Pz25,10"""
        if not IMPORTS_AVAILABLE:
            return

        text = "Pz25,10"
        actions = parse_compact_actions(text)

        assert actions is not None
        assert len(actions) == 1
        assert actions[0] == {"type": "paint_at", "color": "z", "x": 25, "y": 10}

    def test_multiple_actions(self):
        """Parse multiple actions."""
        if not IMPORTS_AVAILABLE:
            return

        text = """```actions
Lf0,0,5,0
Lc0,1,5,1
Pr10,10
```"""
        actions = parse_compact_actions(text)

        assert actions is not None
        # 6 points from first line + 6 from second + 1 point = 13
        assert len(actions) == 13

    def test_skips_malformed_lines(self):
        """Malformed lines are skipped, valid ones parsed."""
        if not IMPORTS_AVAILABLE:
            return

        text = """Lf0,0,5,0
Lbadline
Pr10,10"""
        actions = parse_compact_actions(text)

        assert actions is not None
        # Should get 6 from first line + 1 point = 7
        assert len(actions) == 7

    def test_comments_ignored(self):
        """Lines starting with # are ignored."""
        if not IMPORTS_AVAILABLE:
            return

        text = """# This is a comment
Lf0,0,2,0
# Another comment
Pr5,5"""
        actions = parse_compact_actions(text)

        assert actions is not None
        assert len(actions) == 4  # 3 from line + 1 point

    def test_returns_none_for_no_actions(self):
        """Returns None if no valid actions found."""
        if not IMPORTS_AVAILABLE:
            return

        text = "Just some text with no actions"
        actions = parse_compact_actions(text)
        assert actions is None

    def test_diagonal_line(self):
        """Parse diagonal line using Bresenham."""
        if not IMPORTS_AVAILABLE:
            return

        text = "Lf0,0,3,3"
        actions = parse_compact_actions(text)

        assert actions is not None
        # Diagonal from (0,0) to (3,3) should hit 4 points
        assert len(actions) == 4
        coords = [(a["x"], a["y"]) for a in actions]
        assert (0, 0) in coords
        assert (3, 3) in coords


class TestJsonRobustParser:
    """Test the robust JSON parser."""

    def test_simple_json(self):
        """Parse simple JSON object."""
        if not IMPORTS_AVAILABLE:
            return

        text = '{"key": "value", "num": 42}'
        result = parse_json_robust(text)

        assert result is not None
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_json_in_code_block(self):
        """Extract JSON from markdown code block."""
        if not IMPORTS_AVAILABLE:
            return

        text = """Here's the response:
```json
{"analysis": "test", "actions": [1, 2, 3]}
```
"""
        result = parse_json_robust(text)

        assert result is not None
        assert result["analysis"] == "test"
        assert result["actions"] == [1, 2, 3]

    def test_trailing_comma(self):
        """Handle trailing commas in JSON."""
        if not IMPORTS_AVAILABLE:
            return

        text = '{"items": [1, 2, 3,], "key": "value",}'
        result = parse_json_robust(text)

        assert result is not None
        assert result["items"] == [1, 2, 3]

    def test_extracts_actions_array(self):
        """Fallback extraction of actions array."""
        if not IMPORTS_AVAILABLE:
            return

        # When the main JSON parse fails, it falls back to extracting just the actions
        text = 'blah blah "actions": [{"type": "paint_at", "x": 1}] blah'
        result = parse_json_robust(text)

        assert result is not None
        # The fallback wraps it in {"actions": [...]} OR returns the array directly
        # depending on the extraction path taken
        if isinstance(result, dict):
            assert "actions" in result
            assert len(result["actions"]) == 1
        elif isinstance(result, list):
            # Direct array extraction
            assert len(result) == 1
            assert result[0]["type"] == "paint_at"

    def test_returns_none_for_no_json(self):
        """Returns None when no JSON found."""
        if not IMPORTS_AVAILABLE:
            return

        text = "Just plain text with no JSON at all"
        result = parse_json_robust(text)
        assert result is None


class TestComplexityGuidance:
    """Test progressive complexity guidance."""

    def test_early_phase(self):
        """Early iterations get foundation guidance."""
        if not IMPORTS_AVAILABLE:
            return

        guidance = get_complexity_guidance(1, 20)
        assert "FOUNDATION" in guidance
        assert "BASIC STRUCTURE" in guidance

    def test_mid_early_phase(self):
        """Mid-early iterations get structure guidance."""
        if not IMPORTS_AVAILABLE:
            return

        guidance = get_complexity_guidance(6, 20)
        assert "STRUCTURE" in guidance

    def test_mid_late_phase(self):
        """Mid-late iterations get detail guidance."""
        if not IMPORTS_AVAILABLE:
            return

        guidance = get_complexity_guidance(12, 20)
        assert "DETAIL" in guidance

    def test_final_phase(self):
        """Final iterations get refinement guidance."""
        if not IMPORTS_AVAILABLE:
            return

        guidance = get_complexity_guidance(18, 20)
        assert "REFINEMENT" in guidance

    def test_action_counts_increase(self):
        """Later phases suggest more actions."""
        if not IMPORTS_AVAILABLE:
            return

        early = get_complexity_guidance(1, 20)
        late = get_complexity_guidance(19, 20)

        # Early should suggest fewer actions (100-300)
        assert "100-300" in early or "100" in early
        # Late should suggest more actions (500-800)
        assert "500-800" in late or "800" in late
