"""Tests for settings: mutual exclusion + round-trip for parent locks."""

import pytest
from purple_tui import settings


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    return settings


def test_volume_lock_round_trip(temp_settings):
    temp_settings.set_volume_lock(60)
    assert temp_settings.get_volume_lock() == 60
    temp_settings.set_volume_lock(None)
    assert temp_settings.get_volume_lock() is None


def test_parent_pin_round_trip(temp_settings):
    temp_settings.set_parent_pin("1234")
    assert temp_settings.get_parent_pin() == "1234"
    temp_settings.set_parent_pin(None)
    assert temp_settings.get_parent_pin() is None


def test_setting_volume_lock_clears_silent_mode(temp_settings):
    temp_settings.set_silent_mode(True)
    assert temp_settings.get_silent_mode() is True
    temp_settings.set_volume_lock(40)
    assert temp_settings.get_silent_mode() is False
    assert temp_settings.get_volume_lock() == 40


def test_setting_silent_mode_clears_volume_lock(temp_settings):
    temp_settings.set_volume_lock(40)
    assert temp_settings.get_volume_lock() == 40
    temp_settings.set_silent_mode(True)
    assert temp_settings.get_volume_lock() is None
    assert temp_settings.get_silent_mode() is True


def test_clearing_volume_lock_leaves_silent_mode_alone(temp_settings):
    temp_settings.set_silent_mode(True)
    temp_settings.set_volume_lock(None)
    assert temp_settings.get_silent_mode() is True


def test_clearing_silent_mode_leaves_volume_lock_alone(temp_settings):
    temp_settings.set_volume_lock(60)
    temp_settings.set_silent_mode(False)
    assert temp_settings.get_volume_lock() == 60
