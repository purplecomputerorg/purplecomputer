"""Smoke tests: visit each room and exercise its render path.

Catches the class of bug where a refactor leaves a stale identifier
(NameError, AttributeError, wrong-arity call) inside a `render()` method
that only fires when the widget is actually painted with content. Static
linting catches NameErrors; this catches the rest.
"""

import asyncio
import os

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from purple_tui.purple_tui import PurpleApp
from purple_tui.constants import REQUIRED_TERMINAL_ROWS

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4


def _make_app():
    app = PurpleApp()
    app._render_smoke_errors = []

    def _capture(error):
        app._render_smoke_errors.append(error)

    app._handle_exception = _capture
    return app


async def _settle(pilot):
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()


async def _switch(app, pilot, room):
    app.action_switch_room(room)
    await _settle(pilot)


async def _type(app, text):
    for ch in text:
        await app._execute_dev_command({"action": "key", "value": ch})
        await asyncio.sleep(0.03)


async def _press(app, key):
    await app._execute_dev_command({"action": "key", "value": key})


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _check(app):
    if app._render_smoke_errors:
        err = app._render_smoke_errors[0]
        raise AssertionError(f"render raised {type(err).__name__}: {err}") from err


def test_play_room_renders_math_answer():
    """Submitting a math expression in Play renders an answer line — the exact path that crashed on `caps`."""
    async def go():
        app = _make_app()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            await _switch(app, pilot, "play")
            await _type(app, "2+3")
            await _press(app, "enter")
            await _settle(pilot)
            _check(app)
    _run(go())


def test_play_room_renders_word_answer():
    """A word lookup hits the multi-line answer branch in PlayResultLine.render."""
    async def go():
        app = _make_app()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            await _switch(app, pilot, "play")
            await _type(app, "cat")
            await _press(app, "enter")
            await _settle(pilot)
            _check(app)
    _run(go())


def test_art_room_renders_after_typing():
    async def go():
        app = _make_app()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            await _switch(app, pilot, "art")
            await _type(app, "abc")
            await _settle(pilot)
            _check(app)
    _run(go())


def test_music_room_renders():
    async def go():
        app = _make_app()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            await _switch(app, pilot, "music")
            await _settle(pilot)
            _check(app)
    _run(go())
