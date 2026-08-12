"""Tests for power_manager's dual-path diagnostic logging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui import power_manager as pm


def _paths(tmp_path, monkeypatch):
    a, b = tmp_path / "tmp.log", tmp_path / "persist.log"
    monkeypatch.setattr(pm, "_LOG_PATHS", (str(a), str(b)))
    monkeypatch.setattr(pm, "_header_written", False)
    return a, b


class TestPowerDiag:

    def test_writes_both_paths(self, tmp_path, monkeypatch):
        a, b = _paths(tmp_path, monkeypatch)
        pm._power_diag("POWER SCAN: hello")
        assert "POWER SCAN: hello" in a.read_text()
        assert "POWER SCAN: hello" in b.read_text()

    def test_header_written_once(self, tmp_path, monkeypatch):
        a, _ = _paths(tmp_path, monkeypatch)
        pm._power_diag("one")
        pm._power_diag("two")
        assert a.read_text().count("Power log started") == 1

    def test_unwritable_path_never_raises(self, tmp_path, monkeypatch):
        b = tmp_path / "persist.log"
        monkeypatch.setattr(pm, "_LOG_PATHS",
                            ("/nonexistent-dir/x.log", str(b)))
        monkeypatch.setattr(pm, "_header_written", True)
        pm._power_diag("still ok")  # must not raise
        assert "still ok" in b.read_text()


class TestPowerLogGate:

    def test_verbose_log_respects_enable_flag(self, tmp_path, monkeypatch):
        a, _ = _paths(tmp_path, monkeypatch)
        monkeypatch.setattr(pm, "_log_enabled", False)
        pm._power_log("hidden")
        assert not a.exists()
        monkeypatch.setattr(pm, "_log_enabled", True)
        pm._power_log("visible")
        assert "visible" in a.read_text()
