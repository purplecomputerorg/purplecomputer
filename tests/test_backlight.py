from purple_tui import backlight


def _device(root, name, value, top):
    d = root / name
    d.mkdir()
    (d / "brightness").write_text(str(value))
    (d / "max_brightness").write_text(str(top))
    return d / "brightness"


def test_sets_every_device_as_fraction_of_its_max(tmp_path, monkeypatch):
    monkeypatch.setattr(backlight, "BACKLIGHT_DIR", tmp_path)
    intel, acpi = _device(tmp_path, "intel_backlight", 19200, 96000), _device(tmp_path, "acpi_video0", 3, 15)
    assert backlight.set_level(0.5)
    assert (intel.read_text(), acpi.read_text()) == ("48000", "8")


def test_clamps_to_floor_and_full(tmp_path, monkeypatch):
    monkeypatch.setattr(backlight, "BACKLIGHT_DIR", tmp_path)
    b = _device(tmp_path, "intel_backlight", 100, 1000)
    backlight.set_level(0.0)
    assert int(b.read_text()) == round(1000 * backlight.FLOOR)
    backlight.set_level(2.0)
    assert b.read_text() == "1000"


def test_no_device_or_unreadable_max_reports_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(backlight, "BACKLIGHT_DIR", tmp_path)
    assert not backlight.set_level(0.5)
    (tmp_path / "broken").mkdir()
    assert not backlight.set_level(0.5)
