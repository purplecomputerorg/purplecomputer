"""Demo autostart and idle bookkeeping through the real dispatcher.

Regression: with PURPLE_RECORD_GO_FILE set, the preroll is 0; a zero-delay
timer must still fire so recordings don't capture a frozen app.
"""

import asyncio

from purple_tui.harness import make_app, press, run


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
