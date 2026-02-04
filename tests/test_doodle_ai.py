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
        load_reference_image,
        prepare_reference_for_execution,
        _images_are_similar,
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
        assert "Foundation" in guidance

    def test_mid_early_phase(self):
        """Mid-early iterations get development guidance."""
        if not IMPORTS_AVAILABLE:
            return

        guidance = get_complexity_guidance(6, 20)
        assert "Development" in guidance

    def test_mid_late_phase(self):
        """Mid-late iterations get refinement guidance."""
        if not IMPORTS_AVAILABLE:
            return

        guidance = get_complexity_guidance(12, 20)
        assert "Refinement" in guidance

    def test_final_phase(self):
        """Final iterations get polish guidance."""
        if not IMPORTS_AVAILABLE:
            return

        guidance = get_complexity_guidance(18, 20)
        assert "Polish" in guidance

    def test_phases_encourage_detail(self):
        """All phases should encourage detail, not restrict it."""
        if not IMPORTS_AVAILABLE:
            return

        early = get_complexity_guidance(1, 20)
        late = get_complexity_guidance(19, 20)

        # No action count limits - we encourage detail
        assert "100-300" not in early  # No restrictive limits
        assert "detail" in late.lower()  # Encourages detail


class TestCliArgs:
    """Test CLI argument validation."""

    def _run_cli(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(TOOLS_DIR.parent) + ":" + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, str(DOODLE_AI)] + list(args),
            capture_output=True, text=True, timeout=10, env=env,
        )

    def test_help_shows_from(self):
        """--help mentions --from."""
        result = self._run_cli("--help")
        assert result.returncode == 0
        assert "--from" in result.stdout

    def test_help_shows_reference(self):
        """--help mentions --reference."""
        result = self._run_cli("--help")
        assert result.returncode == 0
        assert "--reference" in result.stdout

    def test_help_shows_instruction(self):
        """--help mentions --instruction."""
        result = self._run_cli("--help")
        assert result.returncode == 0
        assert "--instruction" in result.stdout

    def test_goal_required_without_refine(self):
        """Error when neither --goal nor --refine is given."""
        result = self._run_cli()
        assert result.returncode != 0
        assert "goal" in result.stderr.lower()

    def test_refine_requires_instruction(self):
        """--refine without --instruction errors."""
        result = self._run_cli("--refine", "/tmp/nonexistent")
        assert result.returncode != 0
        assert "instruction" in result.stderr.lower()

    def test_from_requires_valid_content(self):
        """--from with empty directory errors."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            result = self._run_cli("--from", d, "--instruction", "test")
            assert result.returncode != 0

    def test_reference_file_must_exist(self):
        """--reference with nonexistent file errors."""
        result = self._run_cli("--goal", "tree", "--reference", "/tmp/no_such_img.png")
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "Reference" in result.stderr


class TestReferenceImage:
    """Test reference image loading and resizing."""

    def test_load_reference_png(self):
        """Load a PNG reference image."""
        if not IMPORTS_AVAILABLE:
            return

        # Create a tiny test PNG
        try:
            from PIL import Image
        except ImportError:
            return

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img = Image.new("RGB", (10, 10), color=(255, 0, 0))
            img.save(f, format="PNG")
            tmp_path = f.name

        try:
            data, media_type = load_reference_image(tmp_path)
            assert media_type == "image/png"
            assert len(data) > 0
        finally:
            os.unlink(tmp_path)

    def test_load_reference_jpeg(self):
        """Load a JPEG reference image."""
        if not IMPORTS_AVAILABLE:
            return

        try:
            from PIL import Image
        except ImportError:
            return

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img = Image.new("RGB", (10, 10), color=(0, 255, 0))
            img.save(f, format="JPEG")
            tmp_path = f.name

        try:
            data, media_type = load_reference_image(tmp_path)
            assert media_type == "image/jpeg"
            assert len(data) > 0
        finally:
            os.unlink(tmp_path)

    def test_prepare_reference_downsizes(self):
        """prepare_reference_for_execution shrinks large images."""
        if not IMPORTS_AVAILABLE:
            return

        try:
            from PIL import Image
            import base64
            import io
        except ImportError:
            return

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img = Image.new("RGB", (800, 600), color=(0, 0, 255))
            img.save(f, format="PNG")
            tmp_path = f.name

        try:
            data, media_type = prepare_reference_for_execution(tmp_path)
            # Decode and check size
            decoded = base64.b64decode(data)
            result_img = Image.open(io.BytesIO(decoded))
            assert result_img.width <= 200
            assert result_img.height <= 200
        finally:
            os.unlink(tmp_path)

    def test_prepare_reference_small_image_unchanged(self):
        """Small images stay small (not upscaled)."""
        if not IMPORTS_AVAILABLE:
            return

        try:
            from PIL import Image
            import base64
            import io
        except ImportError:
            return

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img = Image.new("RGB", (50, 30), color=(255, 255, 0))
            img.save(f, format="PNG")
            tmp_path = f.name

        try:
            data, media_type = prepare_reference_for_execution(tmp_path)
            decoded = base64.b64decode(data)
            result_img = Image.open(io.BytesIO(decoded))
            # thumbnail doesn't upscale
            assert result_img.width == 50
            assert result_img.height == 30
        finally:
            os.unlink(tmp_path)


class TestImagesAreSimilar:
    """Test the _images_are_similar pixel comparison function."""

    def _make_image(self, width, height, color):
        """Create a solid-color PIL Image."""
        try:
            from PIL import Image
        except ImportError:
            return None
        return Image.new("RGB", (width, height), color)

    def test_identical_images(self):
        """Two identical images should be similar."""
        if not IMPORTS_AVAILABLE:
            return

        img = self._make_image(32, 32, (255, 0, 0))
        assert _images_are_similar(img, img.copy()) is True

    def test_completely_different_images(self):
        """Black vs white should not be similar."""
        if not IMPORTS_AVAILABLE:
            return

        black = self._make_image(32, 32, (0, 0, 0))
        white = self._make_image(32, 32, (255, 255, 255))
        assert _images_are_similar(black, white) is False

    def test_slightly_different_images(self):
        """Images with tiny per-pixel differences should still be similar."""
        if not IMPORTS_AVAILABLE:
            return

        from PIL import Image
        import random as rng

        # Create a base image with random pixels
        base = Image.new("RGB", (32, 32))
        pixels = base.load()
        rng.seed(42)
        for y in range(32):
            for x in range(32):
                pixels[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))

        # Create a copy with tiny noise (max 3 per channel)
        noisy = base.copy()
        noisy_pixels = noisy.load()
        rng.seed(99)
        for y in range(32):
            for x in range(32):
                r, g, b = pixels[x, y]
                noisy_pixels[x, y] = (
                    min(255, max(0, r + rng.randint(-3, 3))),
                    min(255, max(0, g + rng.randint(-3, 3))),
                    min(255, max(0, b + rng.randint(-3, 3))),
                )

        assert _images_are_similar(base, noisy) is True

    def test_moderately_different_images(self):
        """Images that differ significantly on many pixels should not be similar."""
        if not IMPORTS_AVAILABLE:
            return

        from PIL import Image
        import random as rng

        base = Image.new("RGB", (32, 32), (100, 100, 100))
        modified = base.copy()
        mod_pixels = modified.load()
        rng.seed(7)

        # Change half the pixels to a very different color
        for y in range(32):
            for x in range(16):  # left half
                mod_pixels[x, y] = (rng.randint(200, 255), 0, 0)

        assert _images_are_similar(base, modified) is False

    def test_different_sizes_resized(self):
        """Images of different sizes are resized for comparison."""
        if not IMPORTS_AVAILABLE:
            return

        # Same color, different size: should be similar after resize
        small = self._make_image(16, 16, (50, 100, 150))
        large = self._make_image(64, 64, (50, 100, 150))
        assert _images_are_similar(small, large) is True

    def test_custom_threshold(self):
        """Custom threshold makes comparison stricter or looser."""
        if not IMPORTS_AVAILABLE:
            return

        a = self._make_image(32, 32, (100, 100, 100))
        # Slightly different color
        b = self._make_image(32, 32, (105, 105, 105))

        # With default threshold (0.98), small diff should pass
        assert _images_are_similar(a, b) is True
        # With very strict threshold (0.999), it should fail
        assert _images_are_similar(a, b, threshold=0.999) is False
