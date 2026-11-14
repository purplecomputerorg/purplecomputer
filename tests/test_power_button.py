"""Power button while the parent terminal's fullscreen xterm covers Purple."""

from purplecomputer.harness import make_app, run
from purplecomputer.rooms.parent_menu import TerminalScreen
from purplecomputer.rooms.sleep_screen import ShutdownConfirmScreen
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
