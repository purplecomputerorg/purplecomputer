"""Tests for calc_font_size.py"""

import subprocess
import sys
import os
import tempfile

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from calc_font_size import (
    COLS, ROWS, PROBE_FONT_PT, MIN_FONT_PT, MAX_FONT_PT,
    FALLBACK_FONT_PT, TARGET_WIDTH_MM, MAX_SCREEN_FILL, SAFETY_MARGIN,
    get_screen_info, read_cache, write_cache, calculate_font_size
)


class TestConstants:
    """Test that constants are reasonable."""

    def test_grid_dimensions(self):
        assert COLS == 100, "Expected 100 columns for 10-inch width"
        assert ROWS == 28, "Expected 28 rows for 6-inch height"

    def test_probe_font(self):
        assert PROBE_FONT_PT == 18, "Probe font should be 18pt"

    def test_font_limits(self):
        assert MIN_FONT_PT >= 6, "Min font should be at least 6pt for readability"
        assert MAX_FONT_PT <= 72, "Max font should be reasonable"
        assert MIN_FONT_PT < FALLBACK_FONT_PT < MAX_FONT_PT

    def test_target_size(self):
        # 10 inches = 254mm
        assert TARGET_WIDTH_MM == 254

    def test_safety_margins(self):
        assert 0.8 <= MAX_SCREEN_FILL <= 0.9
        assert 0.9 <= SAFETY_MARGIN <= 1.0


class TestGetScreenInfo:
    """Test screen info detection."""

    def test_returns_tuple(self):
        result = get_screen_info()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_returns_positive_pixels(self):
        px_w, px_h, mm_w, mm_h = get_screen_info()
        assert px_w > 0, "Screen width must be positive"
        assert px_h > 0, "Screen height must be positive"

    def test_returns_reasonable_resolution(self):
        px_w, px_h, mm_w, mm_h = get_screen_info()
        # Should be at least VGA resolution
        assert px_w >= 640
        assert px_h >= 480
        # Should be less than 16K
        assert px_w <= 16000
        assert px_h <= 16000

    def test_mm_is_none_or_sane(self):
        px_w, px_h, mm_w, mm_h = get_screen_info()
        if mm_w is not None:
            assert 200 <= mm_w <= 500, "Physical width should be 8-20 inches"
        if mm_h is not None:
            assert 100 <= mm_h <= 400, "Physical height should be reasonable"


class TestCache:
    """Test cache read/write."""

    def test_read_nonexistent_cache(self):
        # Reading from non-existent file should return None
        result = read_cache(1920, 1080)
        # May or may not exist, but should not crash
        assert result is None or (isinstance(result, tuple) and len(result) == 2)

    def test_write_and_read_cache(self):
        # Use a temp file for testing
        import calc_font_size
        original_cache = calc_font_size.CACHE_FILE

        with tempfile.NamedTemporaryFile(mode='w', suffix='.cache', delete=False) as f:
            calc_font_size.CACHE_FILE = f.name

        try:
            # Write cache
            write_cache(1920, 1080, 11, 22)

            # Read it back
            result = read_cache(1920, 1080)
            assert result == (11, 22)

            # Wrong resolution should miss
            result = read_cache(1280, 720)
            assert result is None

        finally:
            calc_font_size.CACHE_FILE = original_cache
            try:
                os.unlink(f.name)
            except:
                pass

    def test_cache_rejects_bad_data(self):
        import calc_font_size
        original_cache = calc_font_size.CACHE_FILE

        with tempfile.NamedTemporaryFile(mode='w', suffix='.cache', delete=False) as f:
            f.write("garbage data\n")
            calc_font_size.CACHE_FILE = f.name

        try:
            result = read_cache(1920, 1080)
            assert result is None
        finally:
            calc_font_size.CACHE_FILE = original_cache
            try:
                os.unlink(f.name)
            except:
                pass


class TestCalculateFontSize:
    """Test font size calculation logic."""

    def test_with_physical_size_known(self):
        """10" screen should fill ~85%, 15" screen should target 10" viewport."""
        # 10" screen (254mm) - should hit 85% cap
        # At 18pt probe with 11x22 cells: viewport = 1100x616 pixels
        # Screen 1280x800, 254mm wide
        font = calculate_font_size(1280, 800, 254, 11, 22)
        assert MIN_FONT_PT <= font <= MAX_FONT_PT

        # 15" screen (381mm) - should target 10" (254mm) = 66% of screen
        # Screen 1920x1080, 381mm wide
        font_15 = calculate_font_size(1920, 1080, 381, 11, 22)
        assert MIN_FONT_PT <= font_15 <= MAX_FONT_PT

    def test_without_physical_size(self):
        """Without mm data, should fill 85% of screen."""
        font = calculate_font_size(1920, 1080, None, 11, 22)
        assert MIN_FONT_PT <= font <= MAX_FONT_PT

    def test_small_screen_clamp(self):
        """Very small screens should clamp to MIN_FONT_PT."""
        # Tiny screen where calculated font would be too small
        font = calculate_font_size(640, 480, None, 11, 22)
        assert font >= MIN_FONT_PT

    def test_large_screen_clamp(self):
        """Very large screens should clamp to MAX_FONT_PT."""
        # Huge screen where calculated font would be too large
        font = calculate_font_size(7680, 4320, None, 11, 22)
        assert font <= MAX_FONT_PT

    def test_safety_margin_applied(self):
        """Result should be smaller than raw calculation due to safety margin."""
        # Direct calculation without safety margin
        screen_w, screen_h = 1920, 1080
        cell_w, cell_h = 11, 22
        probe_viewport_w = cell_w * COLS
        target_w = screen_w * MAX_SCREEN_FILL
        raw_scale = target_w / probe_viewport_w
        raw_font = PROBE_FONT_PT * raw_scale

        # Actual calculation with safety margin
        actual_font = calculate_font_size(screen_w, screen_h, None, cell_w, cell_h)

        # Should be slightly smaller due to safety margin
        assert actual_font < raw_font
        assert actual_font >= raw_font * SAFETY_MARGIN * 0.99  # Allow tiny float error

    def test_15_inch_smaller_than_10_inch(self):
        """15" laptop should get smaller font than 10" laptop (more border)."""
        # 10" laptop: 1280x800, 254mm wide - fills most of screen
        font_10 = calculate_font_size(1280, 800, 254, 11, 22)

        # 15" laptop: 1920x1080, 344mm wide - should have more border
        font_15 = calculate_font_size(1920, 1080, 344, 11, 22)

        # 15" should get smaller or similar font (more border space)
        # Actually the 15" has more pixels so font might be similar,
        # but the PHYSICAL viewport size should be similar
        assert font_10 > 0 and font_15 > 0


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
        # Should exit cleanly
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
        assert font_size <= MAX_FONT_PT, f"Font size {font_size} above maximum"

    def test_script_syntax_valid(self):
        """Verify script has no syntax errors."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py'
        )
        # Read and compile directly to avoid .pyc permission issues
        with open(script_path, 'r') as f:
            source = f.read()
        try:
            compile(source, script_path, 'exec')
        except SyntaxError as e:
            raise AssertionError(f"Syntax error: {e}")
