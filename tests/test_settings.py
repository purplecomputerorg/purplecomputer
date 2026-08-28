"""Tests for settings: round-trip + legacy migration."""

import json
import pytest
from purple_tui import settings


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    return settings


def test_volume_lock_round_trip(temp_settings):
    temp_settings.set_volume_lock(60)
    assert temp_settings.get_volume_lock() == 60
    temp_settings.set_volume_lock(0)
    assert temp_settings.get_volume_lock() == 0
    temp_settings.set_volume_lock(None)
    assert temp_settings.get_volume_lock() is None


def test_parent_pin_round_trip(temp_settings):
    temp_settings.set_parent_pin("1234")
    assert temp_settings.get_parent_pin() == "1234"
    temp_settings.set_parent_pin(None)
    assert temp_settings.get_parent_pin() is None


def test_legacy_silent_mode_migrates_to_lock_at_zero(temp_settings):
    """A pre-unification settings file with silent_mode=True comes back as volume_lock=0."""
    temp_settings.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_settings.SETTINGS_FILE.write_text(json.dumps({"silent_mode": True}))
    assert temp_settings.get_volume_lock() == 0


def test_legacy_silent_mode_does_not_override_existing_lock(temp_settings):
    """If both legacy silent_mode and a real lock are set, the lock wins."""
    temp_settings.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_settings.SETTINGS_FILE.write_text(json.dumps({"silent_mode": True, "volume_lock": 60}))
    assert temp_settings.get_volume_lock() == 60


def test_levels_saved_under_old_step_table_snap_on_load(temp_settings):
    temp_settings.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_settings.SETTINGS_FILE.write_text(json.dumps({"volume_level": 85, "volume_lock": 15}))
    assert temp_settings.get_volume_level() == 80
    assert temp_settings.get_volume_lock() == 20


def test_volume_is_unset_until_someone_chooses_one(temp_settings):
    assert temp_settings.get_volume_level() is None
    temp_settings.set_volume_level(60)
    assert temp_settings.get_volume_level() == 60
    temp_settings.set_all_caps(True)  # saving another setting must not invent a volume choice
    assert temp_settings.get_volume_level() == 60
