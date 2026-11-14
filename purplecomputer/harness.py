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

from .press import ARROWS, CONTROL_KEYS, press, type_text  # noqa: E402,F401

DEFAULT_SIZE = (1366, 768)


def make_app(size=None, room=None):
    from .app import PurpleApp, _env_size
    app = PurpleApp(headless=True, size=size or _env_size() or DEFAULT_SIZE)
    app.active_room = room or app.active_room
    app.timers.bind(asyncio.get_running_loop())
    app.room.on_enter()
    app.timeline_restore(app.active_room)
    return app


def run(coro):
    return asyncio.run(coro)
