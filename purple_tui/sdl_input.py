"""Keyboard input from the SDL window, for dev machines without evdev.

On the real device the evdev reader owns the keyboard and this only pumps
window events. With PURPLE_NO_EVDEV=1 (or off Linux) SDL key events are
turned into the same RawKeyEvents evdev would produce, so every layer above
is identical in both worlds.
"""

import time

import pygame

from .input import KeyCode, RawKeyEvent

_NAMES = {
    pygame.K_ESCAPE: "ESC", pygame.K_BACKSPACE: "BACKSPACE", pygame.K_TAB: "TAB", pygame.K_RETURN: "ENTER",
    pygame.K_LCTRL: "LEFTCTRL", pygame.K_RCTRL: "RIGHTCTRL", pygame.K_LSHIFT: "LEFTSHIFT", pygame.K_RSHIFT: "RIGHTSHIFT",
    pygame.K_LALT: "LEFTALT", pygame.K_RALT: "RIGHTALT", pygame.K_SPACE: "SPACE", pygame.K_CAPSLOCK: "CAPSLOCK",
    pygame.K_UP: "UP", pygame.K_DOWN: "DOWN", pygame.K_LEFT: "LEFT", pygame.K_RIGHT: "RIGHT",
    pygame.K_MINUS: "MINUS", pygame.K_EQUALS: "EQUAL", pygame.K_LEFTBRACKET: "LEFTBRACE", pygame.K_RIGHTBRACKET: "RIGHTBRACE",
    pygame.K_SEMICOLON: "SEMICOLON", pygame.K_QUOTE: "APOSTROPHE", pygame.K_BACKQUOTE: "GRAVE", pygame.K_BACKSLASH: "BACKSLASH",
    pygame.K_COMMA: "COMMA", pygame.K_PERIOD: "DOT", pygame.K_SLASH: "SLASH", pygame.K_F1: "F1", pygame.K_F2: "F2",
    pygame.K_MENU: "COMPOSE",
}
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    _NAMES[getattr(pygame, f"K_{_c}")] = _c.upper()
for _n in ("MUTE", "VOLUMEDOWN", "VOLUMEUP", "POWER"):
    if hasattr(pygame, f"K_{_n}"):
        _NAMES[getattr(pygame, f"K_{_n}")] = _n
KEYMAP = {k: getattr(KeyCode, f"KEY_{n}") for k, n in _NAMES.items() if hasattr(KeyCode, f"KEY_{n}")}

_pressed: set = set()
_ready = False


def pump(g):
    """Yield RawKeyEvents (and None on window close) from the SDL queue."""
    global _ready
    if g.headless:
        return
    if not _ready:
        pygame.key.set_repeat(300, 33)
        _ready = True
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            yield None
        elif ev.type in (pygame.KEYDOWN, pygame.KEYUP):
            code = KEYMAP.get(ev.key)
            if code is None:
                continue
            down = ev.type == pygame.KEYDOWN
            repeat = down and ev.key in _pressed
            (_pressed.add if down else _pressed.discard)(ev.key)
            yield RawKeyEvent(keycode=code, is_down=down, timestamp=time.monotonic(), is_repeat=repeat)
