"""Live boots on a laptop that already has Purple: one shared probe, and the splash and menu say so."""
from purplecomputer import old_install
from purplecomputer.rooms import parent_menu


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


def test_the_welcome_screen_offers_to_install_over_the_laptops_purple(monkeypatch):
    import asyncio
    from purplecomputer.harness import make_app, press, run
    from purplecomputer.rooms.sleep_screen import LiveBootSplash
    monkeypatch.setattr(old_install, "_result", ("found", "Sam's Computer"))
    installs = []
    monkeypatch.setattr(parent_menu, "InstallProgressScreen", lambda app, **k: installs.append(k) or parent_menu.Overlay(app))

    async def go():
        app = make_app()
        app.push(LiveBootSplash(app))
        await press(app, "space")
        assert isinstance(app.top, parent_menu.InstallOverScreen) and app.top.options[app.top.selected][1] == "Just play, don't install right now"
        await press(app, "enter")
        assert not isinstance(app.top, parent_menu.InstallOverScreen)
        app.push(LiveBootSplash(app))
        await press(app, "space")
        app.top.close("keep")
        for _ in range(200):
            if isinstance(app.top, parent_menu.ComputerNameScreen):
                break
            await asyncio.sleep(0.01)
        assert app.top._name == "Sam's Computer"
        app.top.close("Sam's Computer")
        assert installs == [{"computer_name": "Sam's Computer", "keep": True}]
    run(go())
