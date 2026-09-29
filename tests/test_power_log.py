"""Tests for power_manager's always-on dual-path logging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui import power_manager as pm


def _paths(tmp_path, monkeypatch):
    a, b = tmp_path / "tmp.log", tmp_path / "persist.log"
    monkeypatch.setattr(pm, "_LOG_PATHS", (str(a), str(b)))
    monkeypatch.setattr(pm, "_header_written", False)
    return a, b


class TestPowerLog:

    def test_writes_both_paths(self, tmp_path, monkeypatch):
        a, b = _paths(tmp_path, monkeypatch)
        pm._power_log("POWER SCAN: hello")
        assert "POWER SCAN: hello" in a.read_text()
        assert "POWER SCAN: hello" in b.read_text()

    def test_header_written_once(self, tmp_path, monkeypatch):
        a, _ = _paths(tmp_path, monkeypatch)
        pm._power_log("one")
        pm._power_log("two")
        assert a.read_text().count("Power log started") == 1

    def test_unwritable_path_never_raises(self, tmp_path, monkeypatch):
        b = tmp_path / "persist.log"
        monkeypatch.setattr(pm, "_LOG_PATHS",
                            ("/nonexistent-dir/x.log", str(b)))
        monkeypatch.setattr(pm, "_header_written", True)
        pm._power_log("still ok")  # must not raise
        assert "still ok" in b.read_text()

    def test_lines_reach_the_journal_under_their_tag(self, tmp_path, monkeypatch):
        from purple_tui import diag_log
        sent = []
        class FakeSocket:
            def sendto(self, data, flags, addr):
                sent.append(data.decode())
        monkeypatch.setattr(diag_log, "_journal", FakeSocket())
        _paths(tmp_path, monkeypatch)
        pm._power_log("POWER KEY: pressed")
        assert any(m.startswith("<14>purple-power: ") and "POWER KEY: pressed" in m for m in sent)
        assert all(m.split(": ", 1)[1].strip() for m in sent)
