"""Tests for output_is_known_silent: outputs that let mixer.init() succeed
while nothing is audible.

Two ways this happens: a CS8409 (Apple T2 bridge) opens fine but drives no
speakers, and a machine with no sound card at all (e.g. missing SOF DSP
firmware) still gets a dummy sink from Pulse's module-always-sink. Both are
vetoed, unless a USB adapter is present (a real output Pulse can route to).
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
    _make_card(tmp_path, 0, "pci0000:00/0000:00:1f.3")
    _make_codec(tmp_path, 0, 0, "Cirrus Logic CS8409")
    _make_codec(tmp_path, 0, 2, "Intel Skylake HDMI")
    assert output_is_known_silent(str(tmp_path)) is True


def test_silent_codec_with_usb_adapter_is_allowed(tmp_path):
    _make_codec(tmp_path, 0, 0, "Cirrus Logic CS8409")
    _make_card(tmp_path, 0, "pci0000:00/0000:00:1f.3")
    _make_card(tmp_path, 1, "pci0000:00/usb1/1-2/1-2:1.0")
    assert output_is_known_silent(str(tmp_path)) is False


def test_ordinary_codec_is_allowed(tmp_path):
    _make_card(tmp_path, 0, "pci0000:00/0000:00:1f.3")
    _make_codec(tmp_path, 0, 0, "Realtek ALC256")
    assert output_is_known_silent(str(tmp_path)) is False


def test_no_sound_cards_is_vetoed(tmp_path):
    # Missing SOF firmware leaves zero cards; the dummy sink must not count.
    assert output_is_known_silent(str(tmp_path)) is True
    assert output_is_known_silent(str(tmp_path / "nonexistent")) is True


def test_usb_adapter_alone_is_allowed(tmp_path):
    _make_card(tmp_path, 0, "pci0000:00/usb1/1-2/1-2:1.0")
    assert output_is_known_silent(str(tmp_path)) is False


def test_card_without_hda_codec_is_allowed(tmp_path):
    # SOF and ACP cards can register without hwC*D* codec entries; a present
    # card with no denylisted codec must never be vetoed.
    _make_card(tmp_path, 0, "pci0000:00/0000:00:1f.3")
    assert output_is_known_silent(str(tmp_path)) is False


def test_reset_mixer_state_refuses_retry_when_silent(monkeypatch):
    monkeypatch.setattr(music_room, "_KNOWN_SILENT", True)
    monkeypatch.setattr(music_room, "_PROBE_TIMED_OUT", False)
    assert music_room._reset_mixer_state() is False


def _veto_then_reset(monkeypatch, reason):
    """Run warm_mixer under a forced veto, return whether retry is allowed."""
    monkeypatch.setattr(music_room, "_MIXER_READY", None)
    monkeypatch.setattr(music_room, "_KNOWN_SILENT", False)
    monkeypatch.setattr(music_room, "_PROBE_TIMED_OUT", False)
    monkeypatch.setattr(music_room, "_silence_reason", lambda *a, **k: reason)
    assert music_room.warm_mixer() is False
    return music_room._reset_mixer_state()


def test_no_card_veto_is_transient_and_retryable(monkeypatch):
    # A card that probes late (SOF firmware still loading) must keep the
    # boot warmup's fast retry ladder alive, not get the permanent-veto flag.
    assert _veto_then_reset(monkeypatch, "no-card") is True


def test_silent_codec_veto_is_permanent(monkeypatch):
    assert _veto_then_reset(monkeypatch, "silent-codec") is False
