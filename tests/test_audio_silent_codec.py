"""Tests for output_is_known_silent: codecs that init cleanly but are inaudible.

A CS8409 (Apple T2 bridge) opens fine and makes mixer.init() succeed, but
drives no speakers. We veto audio on codec identity, unless a USB adapter is
present (a real output Pulse can route to).
"""

import os

from purple_tui.rooms import music_room
from purple_tui.rooms.music_room import output_is_known_silent


def _make_codec(root, card, dev, chip_name):
    d = root / f"hwC{card}D{dev}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "chip_name").write_text(chip_name + "\n")


def _make_card(root, card, device_target):
    """Create cardN with a device symlink pointing at device_target."""
    target = root / "_devices" / device_target
    target.mkdir(parents=True, exist_ok=True)
    cdir = root / f"card{card}"
    cdir.mkdir(parents=True, exist_ok=True)
    os.symlink(target, cdir / "device")


def test_silent_codec_alone_is_vetoed(tmp_path):
    _make_codec(tmp_path, 0, 0, "Cirrus Logic CS8409")
    _make_codec(tmp_path, 0, 2, "Intel Skylake HDMI")
    assert output_is_known_silent(str(tmp_path)) is True


def test_silent_codec_with_usb_adapter_is_allowed(tmp_path):
    _make_codec(tmp_path, 0, 0, "Cirrus Logic CS8409")
    _make_card(tmp_path, 0, "pci0000:00/0000:00:1f.3")
    _make_card(tmp_path, 1, "pci0000:00/usb1/1-2/1-2:1.0")
    assert output_is_known_silent(str(tmp_path)) is False


def test_ordinary_codec_is_allowed(tmp_path):
    _make_codec(tmp_path, 0, 0, "Realtek ALC256")
    assert output_is_known_silent(str(tmp_path)) is False


def test_no_codecs_is_allowed(tmp_path):
    assert output_is_known_silent(str(tmp_path)) is False


def test_reset_mixer_state_refuses_retry_when_silent(monkeypatch):
    monkeypatch.setattr(music_room, "_KNOWN_SILENT", True)
    monkeypatch.setattr(music_room, "_PROBE_TIMED_OUT", False)
    assert music_room._reset_mixer_state() is False
