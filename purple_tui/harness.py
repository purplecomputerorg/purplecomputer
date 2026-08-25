"""Headless driving of the app for previews and tests.

Builds a PurpleApp on SDL's dummy video driver, binds its timers to the
running asyncio loop, and offers key presses expressed the way evdev would
deliver them (down, optional hold, up), so tests exercise the same dispatch
path as a real keyboard.
"""

import asyncio
import os

for _k, _v in {"PURPLE_NO_EVDEV": "1", "PURPLE_DEV_MODE": "1", "SDL_VIDEODRIVER": "dummy",
               "SDL_AUDIODRIVER": "dummy", "PURPLE_NO_AUDIO": "1", "PYGAME_HIDE_SUPPORT_PROMPT": "1"}.items():
    os.environ.setdefault(_k, _v)

from .keyboard import CharacterAction, ControlAction, NavigationAction  # noqa: E402

CONTROL_KEYS = {"enter", "tab", "space", "escape", "backspace"}
ARROWS = {"up", "down", "left", "right"}
DEFAULT_SIZE = (1366, 768)


def make_app(size=None):
    from .app import PurpleApp, _env_size
    app = PurpleApp(headless=True, size=size or _env_size() or DEFAULT_SIZE)
    app.timers.bind(asyncio.get_running_loop())
    app.room.on_enter()
    return app


async def press(app, key: str, hold: float = 0.0, **kw):
    """One key: arrows, control keys (with an optional hold), or a character."""
    if key in ARROWS:
        await app._dispatch_keyboard_action(NavigationAction(direction=key, **kw))
        return
    if key in CONTROL_KEYS:
        await app._dispatch_keyboard_action(ControlAction(action=key, is_down=True, **kw))
        if hold:
            await asyncio.sleep(hold)
        await app._dispatch_keyboard_action(ControlAction(action=key, is_down=False, **kw))
        return
    await app._dispatch_keyboard_action(CharacterAction(char=key, shifted=key.isupper(), **kw))


async def type_text(app, text: str, enter: bool = False):
    for ch in text:
        await press(app, ch)
    if enter:
        await press(app, "enter")


def run(coro):
    return asyncio.run(coro)
