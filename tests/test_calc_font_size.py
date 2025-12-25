"""Tests for calc_font_size.py"""

import subprocess
import sys
import os
import tempfile

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from calc_font_size import (
    REQUIRED_TERMINAL_COLS, REQUIRED_TERMINAL_ROWS,
    PROBE_FONT_PT, MIN_FONT_PT, MAX_FONT_PT,
    FALLBACK_FONT_PT, TARGET_VIEWPORT_WIDTH_MM, MAX_SCREEN_FILL, SAFETY_MARGIN,
    MIN_SANE_DPI, MAX_SANE_DPI,
    get_screen_info, read_cache, write_cache, calculate_font_size,
    wait_for_resolution_stability, validate_terminal_fits, get_terminal_size
)


class TestConstants:
    """Test that constants are reasonable."""

    def test_grid_dimensions(self):
        # Full UI requires 104x37 (viewport + borders + padding + chrome)
        assert REQUIRED_TERMINAL_COLS == 104, "Expected 104 columns for full UI"
        assert REQUIRED_TERMINAL_ROWS == 37, "Expected 37 rows for full UI"

    def test_probe_font(self):
        assert PROBE_FONT_PT == 18, "Probe font should be 18pt"

    def test_font_limits(self):
        assert MIN_FONT_PT >= 6, "Min font should be at least 6pt for readability"
        assert MAX_FONT_PT <= 72, "Max font should be reasonable"
        assert MIN_FONT_PT < FALLBACK_FONT_PT < MAX_FONT_PT

    def test_target_size(self):
        # 10 inches = 254mm
        assert TARGET_VIEWPORT_WIDTH_MM == 254

    def test_safety_margins(self):
        assert 0.8 <= MAX_SCREEN_FILL <= 0.9
        assert 0.9 <= SAFETY_MARGIN <= 1.0

    def test_dpi_validation_range(self):
        assert MIN_SANE_DPI >= 50, "Min DPI should catch very wrong EDID"
        assert MAX_SANE_DPI <= 250, "Max DPI should flag HiDPI as unsupported"
        assert MIN_SANE_DPI < MAX_SANE_DPI


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

    def test_mm_is_none_or_implies_sane_dpi(self):
        px_w, px_h, mm_w, mm_h = get_screen_info()
        if mm_w is not None and mm_w > 0:
            dpi = px_w / (mm_w / 25.4)
            assert MIN_SANE_DPI <= dpi <= MAX_SANE_DPI, \
                f"DPI {dpi:.0f} should be in sane range"


class TestWaitForResolutionStability:
    """Test resolution stability detection."""

    def test_returns_tuple(self):
        result = wait_for_resolution_stability()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_returns_valid_resolution(self):
        px_w, px_h, mm_w, mm_h = wait_for_resolution_stability()
        assert px_w > 0
        assert px_h > 0


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
        font = calculate_font_size(1280, 800, 254, 11, 22)
        assert MIN_FONT_PT <= font <= MAX_FONT_PT

        # 15" screen (381mm) - should target 10" (254mm) = 66% of screen
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

        # Calculate both width and height constraints
        probe_grid_w = cell_w * REQUIRED_TERMINAL_COLS
        probe_grid_h = cell_h * REQUIRED_TERMINAL_ROWS
        target_w = screen_w * MAX_SCREEN_FILL
        target_h = screen_h * MAX_SCREEN_FILL
        scale_w = target_w / probe_grid_w
        scale_h = target_h / probe_grid_h
        raw_scale = min(scale_w, scale_h)  # Use limiting factor
        raw_font = PROBE_FONT_PT * raw_scale

        # Actual calculation with safety margin
        actual_font = calculate_font_size(screen_w, screen_h, None, cell_w, cell_h)

        # Should be slightly smaller due to safety margin
        assert actual_font < raw_font
        assert actual_font >= raw_font * SAFETY_MARGIN * 0.99  # Allow tiny float error

    def test_height_constraint_applied(self):
        """Wide but short screens should be constrained by height."""
        # Very wide screen (21:9 ultrawide)
        screen_w, screen_h = 2560, 1080
        cell_w, cell_h = 11, 22

        font = calculate_font_size(screen_w, screen_h, None, cell_w, cell_h)

        # Calculate expected: height should be the limiting factor
        probe_grid_h = cell_h * REQUIRED_TERMINAL_ROWS
        max_grid_h = screen_h * MAX_SCREEN_FILL
        height_scale = max_grid_h / probe_grid_h
        expected_max = PROBE_FONT_PT * height_scale * SAFETY_MARGIN

        assert font <= expected_max * 1.01  # Allow tiny float error

    def test_uses_correct_grid_size(self):
        """Font calculation should use full UI grid (104x37), not just viewport."""
        screen_w, screen_h = 1920, 1080
        cell_w, cell_h = 11, 22

        # With REQUIRED_TERMINAL_COLS=104, REQUIRED_TERMINAL_ROWS=37
        probe_grid_w = cell_w * 104  # Full UI width
        probe_grid_h = cell_h * 37   # Full UI height

        # Screen fill at 85%
        max_w = screen_w * 0.85
        max_h = screen_h * 0.85

        # Scale to fit
        scale_w = max_w / probe_grid_w
        scale_h = max_h / probe_grid_h
        expected_scale = min(scale_w, scale_h)

        font = calculate_font_size(screen_w, screen_h, None, cell_w, cell_h)
        expected = PROBE_FONT_PT * expected_scale * SAFETY_MARGIN

        # Should match within rounding
        assert abs(font - expected) < 0.5, f"Expected ~{expected:.1f}, got {font:.1f}"


class TestValidation:
    """Test terminal validation functions."""

    def test_get_terminal_size_returns_tuple_or_none(self):
        result = get_terminal_size()
        assert result is None or (isinstance(result, tuple) and len(result) == 2)

    def test_validate_terminal_fits_returns_bool(self):
        result = validate_terminal_fits()
        assert isinstance(result, bool)


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
            timeout=15  # Longer timeout for stability wait
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
            timeout=15
        )
        output = result.stdout.strip()

        # Should be a valid float
        font_size = float(output)
        assert font_size >= MIN_FONT_PT, f"Font size {font_size} below minimum"
        assert font_size <= MAX_FONT_PT, f"Font size {font_size} above maximum"

    def test_script_info_mode(self):
        """Script --info mode should output diagnostic info."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py'
        )
        result = subprocess.run(
            [sys.executable, script_path, '--info'],
            capture_output=True,
            text=True,
            timeout=15
        )
        assert result.returncode == 0
        assert 'Screen:' in result.stdout
        assert 'Required grid:' in result.stdout

    def test_script_validate_mode(self):
        """Script --validate mode should check terminal size."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py'
        )
        result = subprocess.run(
            [sys.executable, script_path, '--validate'],
            capture_output=True,
            text=True,
            timeout=15
        )
        # May succeed or fail depending on terminal, but should not crash
        output = result.stdout.strip()
        assert output.startswith('OK') or output.startswith('FAIL')

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
