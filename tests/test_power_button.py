"""Power button handling over the parent terminal and the sleep screen."""

from purplecomputer.harness import make_app, run
from purplecomputer.rooms.parent_menu import TerminalScreen
from purplecomputer.rooms.sleep_screen import ShutdownConfirmScreen, SleepScreen
from purplecomputer.input import PowerButtonEvent


class FakeProc:
    terminated = False

    def terminate(self):
        self.terminated = True


def test_power_tap_closes_terminal_and_confirms(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)

    async def go():
        app = make_app()
        term = TerminalScreen(app)
        app.push(term)
        term._proc, term._running = FakeProc(), True
        await app._handle_power_button_event(PowerButtonEvent("tap", 0.0))
        assert term._proc.terminated
        assert app.has_overlay(ShutdownConfirmScreen)
    run(go())


def test_power_tap_on_sleep_screen_confirms_then_wakes(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)

    async def go():
        app = make_app()
        app._show_sleep_screen()
        await app._handle_power_button_event(PowerButtonEvent("tap", 0.0))
        assert app.has_overlay(ShutdownConfirmScreen) and not app.has_overlay(SleepScreen)
        app.top._cancel()
        assert not app.has_overlay((ShutdownConfirmScreen, SleepScreen))
    run(go())


def test_cancelled_confirm_with_lid_closed_goes_back_to_sleep(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)

    async def go():
        app = make_app()
        app._lid_close_time = 1.0
        app._show_sleep_screen()
        await app._handle_power_button_event(PowerButtonEvent("tap", 0.0))
        app.top._cancel()
        assert app.has_overlay(SleepScreen) and not app.has_overlay(ShutdownConfirmScreen)
    run(go())
