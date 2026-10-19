"""Key presses expressed the way evdev would deliver them (down, optional hold, up), for code that
drives a running app: the headless harness, and Studio typing into the in-browser Purple."""

import asyncio

from ..keyboard import CharacterAction, ControlAction, NavigationAction

CONTROL_KEYS = {"enter", "tab", "space", "escape", "backspace", "home", "end", "page_up", "page_down"}
ARROWS = {"up", "down", "left", "right"}


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
