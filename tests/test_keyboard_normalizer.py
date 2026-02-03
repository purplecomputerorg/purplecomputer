"""
Tests for keyboard_normalizer.py

This module is now only used for F-key calibration.
Runtime keyboard processing moved to purple_tui/input.py and purple_tui/keyboard.py.
See guides/keyboard-architecture.md for details.
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from keyboard_normalizer import KeyCodes, load_scancode_map, save_scancode_map


class TestKeyCodesConstants:
    """KeyCodes constants match Linux input-event-codes.h."""

    def test_f1_to_f10_sequential(self):
        """F1-F10 are sequential keycodes 59-68."""
        assert KeyCodes.KEY_F1 == 59
        assert KeyCodes.KEY_F2 == 60
        assert KeyCodes.KEY_F3 == 61
        assert KeyCodes.KEY_F4 == 62
        assert KeyCodes.KEY_F5 == 63
        assert KeyCodes.KEY_F6 == 64
        assert KeyCodes.KEY_F7 == 65
        assert KeyCodes.KEY_F8 == 66
        assert KeyCodes.KEY_F9 == 67
        assert KeyCodes.KEY_F10 == 68

    def test_f11_f12(self):
        """F11-F12 have different keycodes (not sequential with F1-F10)."""
        assert KeyCodes.KEY_F11 == 87
        assert KeyCodes.KEY_F12 == 88

    def test_letter_keys(self):
        """Letter key range for keyboard detection."""
        assert KeyCodes.KEY_A == 30
        assert KeyCodes.KEY_Z == 44


class TestScancodeMapIO:
    """Load/save scancode mapping to disk."""

    def test_load_returns_empty_dict_when_no_file(self, tmp_path, monkeypatch):
        """Returns empty dict when mapping file doesn't exist."""
        fake_file = tmp_path / "nonexistent" / "keyboard-map.json"
        monkeypatch.setattr("keyboard_normalizer.MAPPING_FILE", fake_file)
        assert load_scancode_map() == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        """Save and load preserves mapping."""
        fake_file = tmp_path / "keyboard-map.json"
        monkeypatch.setattr("keyboard_normalizer.MAPPING_FILE", fake_file)

        mapping = {0x3B: 59, 0x3C: 60}  # scancode -> keycode
        assert save_scancode_map(mapping) is True
        assert load_scancode_map() == mapping

    def test_load_handles_corrupt_json(self, tmp_path, monkeypatch):
        """Returns empty dict for corrupt JSON."""
        fake_file = tmp_path / "keyboard-map.json"
        fake_file.write_text("not valid json")
        monkeypatch.setattr("keyboard_normalizer.MAPPING_FILE", fake_file)
        assert load_scancode_map() == {}

    def test_load_handles_missing_scancodes_key(self, tmp_path, monkeypatch):
        """Returns empty dict if 'scancodes' key is missing."""
        fake_file = tmp_path / "keyboard-map.json"
        fake_file.write_text('{"other": "data"}')
        monkeypatch.setattr("keyboard_normalizer.MAPPING_FILE", fake_file)
        assert load_scancode_map() == {}
