"""Tests for calc_font_size.py"""

import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from calc_font_size import (
    REQUIRED_COLS, REQUIRED_ROWS, SCREEN_FILL, MIN_FONT, MAX_FONT,
    get_resolution, calculate_font
)


class TestConstants:
    def test_grid_size(self):
        """Grid must match purple_tui.constants (136x38 for current viewport)."""
        assert REQUIRED_COLS == 136
        assert REQUIRED_ROWS == 38

    def test_limits(self):
        assert MIN_FONT >= 10
        assert MAX_FONT <= 48  # Capped to prevent huge viewports
        assert MIN_FONT < MAX_FONT

    def test_fill(self):
        assert 0.7 <= SCREEN_FILL <= 0.9


class TestGetResolution:
    def test_returns_tuple(self):
        result = get_resolution()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_reasonable_values(self):
        w, h = get_resolution()
        assert 640 <= w <= 8000
        assert 480 <= h <= 5000


class TestCalculateFont:
    def test_1080p(self):
        """1920x1080 should give reasonable font."""
        font = calculate_font(1920, 1080)
        assert MIN_FONT <= font <= MAX_FONT

    def test_768p(self):
        """1366x768 should give smaller font."""
        font = calculate_font(1366, 768)
        assert MIN_FONT <= font <= MAX_FONT

    def test_4k(self):
        """4K should give a large font size."""
        font = calculate_font(3840, 2160)
        assert font > 30  # Should be significantly larger than 1080p
        assert font <= MAX_FONT

    def test_tiny_screen(self):
        """Tiny screen should hit min font."""
        font = calculate_font(800, 600)
        assert font == MIN_FONT

    def test_always_in_range(self):
        """Any reasonable input gives valid output."""
        for w in [800, 1280, 1920, 2560, 3840]:
            for h in [600, 720, 1080, 1440, 2160]:
                font = calculate_font(w, h)
                assert MIN_FONT <= font <= MAX_FONT

    def test_result_is_half_point(self):
        """Result should be floored to nearest 0.5pt."""
        font = calculate_font(1920, 1080)
        assert (font * 2) == int(font * 2)


class TestScript:
    @staticmethod
    def _get_env():
        """Get environment with PYTHONPATH set for purple_tui import."""
        project_root = os.path.join(os.path.dirname(__file__), '..')
        env = os.environ.copy()
        env['PYTHONPATH'] = project_root + ':' + env.get('PYTHONPATH', '')
        return env

    def test_runs(self):
        """Script runs without error."""
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py')
        result = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=10, env=self._get_env())
        assert result.returncode == 0

    def test_outputs_number(self):
        """Script outputs valid font size."""
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py')
        result = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=10, env=self._get_env())
        font = float(result.stdout.strip())
        assert MIN_FONT <= font <= MAX_FONT

    def test_info_mode(self):
        """--info outputs diagnostic info."""
        script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'calc_font_size.py')
        result = subprocess.run([sys.executable, script, '--info'], capture_output=True, text=True, timeout=10, env=self._get_env())
        assert 'Screen:' in result.stdout
        assert 'Font:' in result.stdout
