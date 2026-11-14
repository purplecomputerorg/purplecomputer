"""Live boots on a laptop that already has Purple: one shared probe, and the splash and menu say so."""
from purple_tui.canvas import old_install
from purple_tui.canvas.rooms import parent_menu


def test_probe_runs_once_and_retries_when_it_could_not_run(monkeypatch):
    calls = []
    results = iter([None, ("found", "Sam")])
    monkeypatch.setattr(old_install, "_result", None)
    monkeypatch.setattr(old_install, "_run", lambda: calls.append(1) or next(results))
    assert old_install.probe() == old_install.NONE and old_install.known() == old_install.NONE
    assert old_install.probe() == ("found", "Sam") == old_install.probe()
    assert len(calls) == 2


def test_parent_menu_hint_names_the_installed_purple(monkeypatch):
    monkeypatch.setattr(parent_menu, "is_live_boot", lambda: True)
    monkeypatch.setattr(old_install, "_result", ("found", ""))
    assert "Purple is also on this laptop" in parent_menu._boot_mode_hint()
    monkeypatch.setattr(old_install, "_result", old_install.NONE)
    assert "also on this laptop" not in parent_menu._boot_mode_hint()
