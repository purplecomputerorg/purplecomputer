"""Demo autostart under the recording handshake.

Regression: with PURPLE_RECORD_GO_FILE set, the preroll is 0 and
set_timer(0) never fires in Textual (its Timer divides by the interval),
so the demo silently never started and recordings captured a frozen app.
"""

import asyncio
import os

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from purple_tui.purple_tui import PurpleApp
from purple_tui.constants import REQUIRED_TERMINAL_ROWS

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)


def test_autostart_fires_with_zero_preroll(tmp_path, monkeypatch):
    go_file = tmp_path / "go"
    go_file.write_text("go")
    monkeypatch.setenv("PURPLE_DEMO_AUTOSTART", "1")
    monkeypatch.setenv("PURPLE_RECORD_GO_FILE", str(go_file))
    monkeypatch.setenv("PURPLE_RECORD_READY_FILE", str(tmp_path / "ready"))
    monkeypatch.setenv("PURPLE_DEMO_COMPOSITION", "everything.json")

    async def go():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            deadline = 3.0
            while deadline > 0 and app._demo_task is None:
                await asyncio.sleep(0.1)
                deadline -= 0.1
            assert app._demo_task is not None, "demo never autostarted"
            await pilot.pause()
            assert not app._demo_task.done() or app._demo_task.exception() is None
            app.cancel_demo()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(go())
    finally:
        loop.close()


def test_dispatched_action_resets_idle():
    """Demo playback bypasses evdev, so dispatch itself must count as
    activity or long recordings hit the idle sleep face."""
    from purple_tui.keyboard import CharacterAction
    from purple_tui.power_manager import get_power_manager

    async def go():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.pause()
            pm = get_power_manager()
            pm._last_activity -= 100
            assert pm.get_idle_seconds() > 90
            await app._dispatch_keyboard_action(CharacterAction(char="a"))
            assert pm.get_idle_seconds() < 5

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(go())
    finally:
        loop.close()
