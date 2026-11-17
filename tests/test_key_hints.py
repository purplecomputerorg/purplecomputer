"""Keys Purple doesn't act on (Caps Lock, brightness) show a hint instead of doing nothing."""
from purplecomputer.harness import make_app, run
from purplecomputer.input import KeyCode, RawKeyEvent
from purplecomputer.keyboard import ControlAction, KeyboardStateMachine

CAPS_HINT = "Press Shift for a big letter"


def _texts(app):
    return [t.text for t in app._toasts]


def test_caps_lock_press_becomes_a_hint_action():
    actions = KeyboardStateMachine().process(RawKeyEvent(keycode=KeyCode.KEY_CAPSLOCK, is_down=True, timestamp=100.0))
    assert actions == [ControlAction(action='caps_hint', is_down=True)]


def test_caps_hint_shows_once_while_mashed():
    async def go():
        app = make_app()
        for _ in range(3):
            await app._dispatch_action(ControlAction(action='caps_hint', is_down=True))
        assert _texts(app).count(CAPS_HINT) == 1
    run(go())


def test_caps_hint_is_silent_when_all_caps_is_on():
    async def go():
        app = make_app()
        app.g.all_caps = True
        await app._dispatch_action(ControlAction(action='caps_hint', is_down=True))
        assert CAPS_HINT not in _texts(app)
    run(go())
