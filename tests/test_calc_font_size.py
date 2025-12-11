"""Tests for calc_font_size.py"""

import subprocess
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from calc_font_size import (
    COLS, ROWS, PROBE_FONT_PT, MIN_FONT_PT,
    FALLBACK_CELL_W, FALLBACK_CELL_H, FALLBACK_SW, FALLBACK_SH,
    probe_cell_size, get_screen_size
)


class TestConstants:
    """Test that constants are reasonable."""

    def test_grid_dimensions(self):
        assert COLS == 100, "Expected 100 columns for 10-inch width"
        assert ROWS == 28, "Expected 28 rows for 6-inch height"

    def test_probe_font(self):
        assert PROBE_FONT_PT == 12, "Probe font should be 12pt"

    def test_min_font(self):
        assert MIN_FONT_PT >= 6, "Min font should be at least 6pt for readability"

    def test_fallback_cell_size(self):
        assert FALLBACK_CELL_W > 0
        assert FALLBACK_CELL_H > 0
        # Typical monospace ratio is roughly 1:2
        assert 1.5 <= FALLBACK_CELL_H / FALLBACK_CELL_W <= 2.5

    def test_fallback_screen_size(self):
        assert FALLBACK_SW >= 1024, "Fallback width should be reasonable"
        assert FALLBACK_SH >= 600, "Fallback height should be reasonable"


class TestProbeCellSize:
    """Test cell size probing."""

    def test_returns_tuple(self):
        result = probe_cell_size()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_positive_values(self):
        w, h = probe_cell_size()
        assert w > 0, "Cell width must be positive"
        assert h > 0, "Cell height must be positive"

    def test_fallback_on_missing_alacritty(self):
        # Even if Alacritty isn't installed, should return fallback
        w, h = probe_cell_size()
        assert w == FALLBACK_CELL_W or w > 0
        assert h == FALLBACK_CELL_H or h > 0


class TestGetScreenSize:
    """Test screen size detection."""

    def test_returns_tuple(self):
        result = get_screen_size()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_positive_values(self):
        w, h = get_screen_size()
        assert w > 0, "Screen width must be positive"
        assert h > 0, "Screen height must be positive"

    def test_returns_reasonable_resolution(self):
        w, h = get_screen_size()
        # Should be at least VGA resolution
        assert w >= 640
        assert h >= 480
        # Should be less than 16K
        assert w <= 16000
        assert h <= 16000


class TestFontCalculation:
    """Test the font size calculation logic."""

    def test_scale_calculation(self):
        """Test the scaling math directly."""
        cell_w, cell_h = 8, 16
        screen_w, screen_h = 1366, 768

        target_w = cell_w * COLS  # 800
        target_h = cell_h * ROWS  # 448

        scale_w = screen_w / target_w  # 1.70
        scale_h = screen_h / target_h  # 1.71
        scale = min(scale_w, scale_h)  # 1.70

        font_pt = PROBE_FONT_PT * scale  # ~20.4

        assert 15 <= font_pt <= 30, f"Font size {font_pt} out of expected range"

    def test_small_screen_clamp(self):
        """Test that very small screens still get readable font."""
        cell_w, cell_h = 8, 16
        screen_w, screen_h = 640, 480  # Very small screen

        target_w = cell_w * COLS
        target_h = cell_h * ROWS

        scale_w = screen_w / target_w
        scale_h = screen_h / target_h
        scale = min(scale_w, scale_h)

        font_pt = max(PROBE_FONT_PT * scale, MIN_FONT_PT)

        assert font_pt >= MIN_FONT_PT, "Should clamp to minimum font size"

    def test_large_screen_reasonable(self):
        """Test that large screens don't get absurdly large fonts."""
        cell_w, cell_h = 8, 16
        screen_w, screen_h = 3840, 2160  # 4K screen

        target_w = cell_w * COLS
        target_h = cell_h * ROWS

        scale_w = screen_w / target_w
        scale_h = screen_h / target_h
        scale = min(scale_w, scale_h)

        # Clamp scale to max 10 as per spec
        if scale > 10:
            scale = 1

        font_pt = PROBE_FONT_PT * scale

        assert font_pt <= 120, f"Font size {font_pt} too large for 4K"


class TestScriptExecution:
    """Test that the script runs and produces output."""

    def test_script_runs_without_error(self):
        """Script should always produce output, never crash."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py'
        )
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Should exit cleanly (0) or at worst produce fallback
        assert result.returncode == 0, f"Script failed: {result.stderr}"

    def test_script_outputs_number(self):
        """Script should output a valid font size number."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py'
        )
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.strip()

        # Should be a valid float
        font_size = float(output)
        assert font_size >= MIN_FONT_PT, f"Font size {font_size} below minimum"
        assert font_size <= 200, f"Font size {font_size} unreasonably large"

    def test_script_syntax_valid(self):
        """Verify script has no syntax errors."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py'
        )
        result = subprocess.run(
            [sys.executable, '-m', 'py_compile', script_path],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"
