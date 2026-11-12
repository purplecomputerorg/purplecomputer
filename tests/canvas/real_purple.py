"""The keys scripts/e2e_vm.py presses on a Purple booted from a built ISO, where nothing can be looked
at but the screen and the drives. They're written in press() names so test_studio_to_purple.py can
replay the very same keys here and catch a script that no longer does what it says."""

import asyncio
import time

import pygame

from purple_tui.canvas.harness import press

# A key, or (key, seconds held). Room picker digits are the kid rooms in order: 1 Art, 2 Music, 3 Play.
ADD_PACK = ["enter", "enter", "escape"]          # Add, check the first new room, done
SAVE = ["escape", "s"]


def play_word(word: str) -> list:
    return ["escape", "3", *word, "enter"]


ART_FIRST_PICTURE = ["escape", "1", "escape", "o", "enter"]  # Art, Open, the first tile: a pack picture when nothing is saved
PICTURE_COLORS = ["#ff0000", "#00aaff"]  # the fixture pack's picture (studio/scripts/fixture-packs.ts)
PARENT_MENU = [("escape", 1.5)]


def to_menu_item(downs: int) -> list:
    return [*PARENT_MENU, *["down"] * downs, "enter"]


def menu_downs(app, item: str) -> int:
    """Down presses from the Parent Menu's first row to item, on a live boot as the ISO is."""
    from purple_tui.canvas.rooms import parent_menu
    real = parent_menu.is_live_boot
    parent_menu.is_live_boot = lambda: True
    try:
        rows = [i for i, _ in parent_menu._get_menu_items(app) if not i.startswith("sec-")]
    finally:
        parent_menu.is_live_boot = real
    return rows.index(item)


HELD = {"escape": 1}  # evdev keycodes: a held key goes through the keyboard state machine, where hold timing lives


async def replay(app, script: list) -> None:
    from purple_tui.input import RawKeyEvent
    for key in script:
        name, hold = key if isinstance(key, tuple) else (key, 0.0)
        if hold and name not in HELD:
            await press(app, name, hold=hold)
        elif hold:
            for down in (True, False):
                await app._handle_raw_key_event(RawKeyEvent(keycode=HELD[name], is_down=down, timestamp=time.monotonic()))
                await asyncio.sleep(hold if down else 0)
        else:
            await press(app, name)
        await asyncio.sleep(0.05)


QEMU = {"enter": "ret", "escape": "esc", " ": "spc", "-": "minus", "'": "apostrophe", ".": "dot", ",": "comma", "/": "slash"}


def qemu_keys(script: list) -> list[str]:
    """The script as QEMU monitor sendkey arguments ("esc 1500" holds Esc for 1.5s)."""
    return [f"{QEMU.get(k, k)} {round(h * 1000)}" if h else QEMU.get(k, k)
            for k, h in ((key if isinstance(key, tuple) else (key, 0.0)) for key in script)]


def page_has_colors(png, colors: list[str], tolerance: int = 24) -> list[str]:
    """Which of colors ("#rrggbb") a picture (a path or a Surface) has no pixel near."""
    surface = png if isinstance(png, pygame.Surface) else pygame.image.load(str(png))
    w, h = surface.get_size()
    seen = {tuple(surface.get_at((x, y)))[:3] for x in range(0, w, 2) for y in range(0, h, 2)}
    want = {c: tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colors}
    return [c for c, rgb in want.items() if not any(max(abs(a - b) for a, b in zip(rgb, s)) <= tolerance for s in seen)]
