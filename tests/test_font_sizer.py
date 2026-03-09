"""Tests for font_sizer module."""

import os
import tempfile
from unittest import mock

from purple_tui.font_sizer import (
    _read_font_size,
    _write_font_size,
    _floor_half,
    ensure_terminal_size,
)


class TestFloorHalf:
    def test_exact(self):
        assert _floor_half(22.0) == 22.0

    def test_rounds_down(self):
        assert _floor_half(22.3) == 22.0

    def test_half(self):
        assert _floor_half(22.7) == 22.5

    def test_just_under_half(self):
        assert _floor_half(22.49) == 22.0


class TestReadFontSize:
    def test_reads_size(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[font]\nsize = 22.0\n')
            f.flush()
            assert _read_font_size(f.name) == 22.0
            os.unlink(f.name)

    def test_reads_integer(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[font]\nsize = 16\n')
            f.flush()
            assert _read_font_size(f.name) == 16.0
            os.unlink(f.name)

    def test_missing_file(self):
        assert _read_font_size('/nonexistent/path.toml') is None


class TestWriteFontSize:
    def test_writes_size(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[font]\nsize = 22.0\n[colors]\n')
            path = f.name
        assert _write_font_size(path, 18.5) is True
        with open(path) as f:
            content = f.read()
        assert 'size = 18.5' in content
        assert '[colors]' in content  # Rest of config preserved
        os.unlink(path)

    def test_no_change(self):
        """Writing the same size returns False (no change detected)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[font]\nsize = 22.0\n')
            path = f.name
        assert _write_font_size(path, 22.0) is False
        os.unlink(path)


class TestEnsureTerminalSize:
    def test_already_correct_size(self):
        """No config modification when terminal is already the right size."""
        with mock.patch('purple_tui.font_sizer.os.get_terminal_size', return_value=os.terminal_size((114, 38))):
            # Should return immediately without touching any files
            ensure_terminal_size()

    def test_no_config_file(self):
        """Gracefully handles missing config."""
        with mock.patch('purple_tui.font_sizer.os.get_terminal_size', return_value=os.terminal_size((80, 24))):
            with mock.patch.dict(os.environ, {'PURPLE_ALACRITTY_CONFIG': '/nonexistent'}):
                ensure_terminal_size()  # Should not raise

    def test_adjusts_font_when_too_few_rows(self):
        """Writes smaller font when terminal has too few rows."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[font]\nsize = 24.0\n')
            path = f.name

        call_count = [0]
        def fake_terminal_size():
            call_count[0] += 1
            if call_count[0] <= 2:
                return os.terminal_size((118, 34))  # Too few rows (pre-loop + first loop check)
            return os.terminal_size((114, 38))  # Correct after adjustment

        with mock.patch('purple_tui.font_sizer.os.get_terminal_size', side_effect=fake_terminal_size):
            with mock.patch.dict(os.environ, {'PURPLE_ALACRITTY_CONFIG': path}):
                with mock.patch('purple_tui.font_sizer.time.sleep'):
                    with mock.patch('builtins.print'):
                        ensure_terminal_size()

        # Verify font was reduced
        with open(path) as f:
            content = f.read()
        # 24.0 * 34/38 = 21.47 -> floor to 21.0
        assert 'size = 21.0' in content
        os.unlink(path)
