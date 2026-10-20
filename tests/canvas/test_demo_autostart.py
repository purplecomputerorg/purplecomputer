"""Demo autostart and idle bookkeeping through the real dispatcher.

Regression: with PURPLE_RECORD_GO_FILE set, the preroll is 0; a zero-delay
timer must still fire so recordings don't capture a frozen app.
"""

import asyncio

from purple_tui.canvas.harness import make_app, press, run


def test_autostart_fires_with_zero_preroll(tmp_path, monkeypatch):
    go_file = tmp_path / "go"
    go_file.write_text("go")
    monkeypatch.setenv("PURPLE_DEMO_AUTOSTART", "1")
    monkeypatch.setenv("PURPLE_RECORD_GO_FILE", str(go_file))
    monkeypatch.setenv("PURPLE_RECORD_READY_FILE", str(tmp_path / "ready"))
    monkeypatch.setenv("PURPLE_DEMO_COMPOSITION", "everything.json")

    async def go():
        app = make_app()
        app.timers.after(0.0, app.start_demo)
        deadline = 3.0
        while deadline > 0 and app._demo_task is None:
            await asyncio.sleep(0.1)
            deadline -= 0.1
        assert app._demo_task is not None, "demo never autostarted"
        await asyncio.sleep(0.2)
        assert not app._demo_task.done() or app._demo_task.exception() is None
        app.cancel_demo()
    run(go())


def test_dispatched_action_resets_idle():
    """Demo playback bypasses evdev, so dispatch itself must count as activity
    or long recordings hit the idle sleep face."""
    from purple_tui.power_manager import get_power_manager

    async def go():
        app = make_app()
        pm = get_power_manager()
        pm._last_activity -= 100
        assert pm.get_idle_seconds() > 90
        await press(app, "a")
        assert pm.get_idle_seconds() < 5
    run(go())


def test_lifting_an_idle_inhibitor_resets_idle():
    """Time under an inhibitor (terminal, install) was not idle, so the next
    idle tick must not show the sleep screen at once."""
    from purple_tui.power_manager import get_power_manager

    async def go():
        app = make_app()
        pm = get_power_manager()
        app.inhibit_idle("terminal")
        pm._last_activity -= 300
        app.uninhibit_idle("terminal")
        assert pm.get_idle_seconds() < 5
    run(go())


def test_away_skips_sleep_face_and_shuts_down_on_its_own_timer(monkeypatch):
    """With the terminal open or on another VT, a sleep face can't be seen or
    woken, so idle goes straight to shutdown on the longer away threshold."""
    from types import SimpleNamespace

    from purple_tui import power_manager
    from purple_tui.power_manager import get_power_manager
    monkeypatch.setattr(power_manager, "can_power_back_on", lambda: True)

    async def go():
        app = make_app()
        shown = []
        monkeypatch.setattr(app, "_show_sleep_screen", lambda: shown.append("sleep"))
        monkeypatch.setattr(app, "_show_bye_screen", lambda: shown.append("bye"))
        app._evdev_reader = SimpleNamespace(away=True)
        pm = get_power_manager()
        pm._last_activity -= pm.get_idle_shutdown_threshold(away=True) - 60
        app._check_idle_state()
        assert shown == []
        pm._last_activity -= 120
        app._check_idle_state()
        assert shown == ["bye"]
    run(go())
