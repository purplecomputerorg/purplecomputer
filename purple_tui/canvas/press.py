"""Key presses expressed the way evdev would deliver them (down, optional hold, up), for code that
drives a running app: the headless harness, and Studio typing into the in-browser Purple."""

import asyncio

from ..keyboard import UNSHIFT_MAP, CharacterAction, ControlAction, NavigationAction

CONTROL_KEYS = {"enter", "tab", "space", "escape", "backspace", "home", "end", "page_up", "page_down"}
ARROWS = {"up", "down", "left", "right"}


async def press(app, key: str, hold: float = 0.0, **kw):
    """One key, down then up after an optional hold: arrows, control keys, or a character."""
    if key in CONTROL_KEYS:
        await app._dispatch_keyboard_action(ControlAction(action=key, is_down=True, **kw))
    elif key in ARROWS:
        await app._dispatch_keyboard_action(NavigationAction(direction=key, **kw))
    else:
        await app._dispatch_keyboard_action(CharacterAction(char=key, shifted=key.isupper(), **kw))
    if hold:
        await asyncio.sleep(hold)
    if key in CONTROL_KEYS:
        await app._dispatch_keyboard_action(ControlAction(action=key, is_down=False, **kw))
    else:
        app.release_key(UNSHIFT_MAP.get(key, key))


async def type_text(app, text: str, enter: bool = False):
    for ch in text:
        await press(app, ch)
    if enter:
        await press(app, "enter")
