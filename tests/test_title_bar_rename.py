"""Verify the title bar refreshes immediately when the parent renames the computer.

The bug we're chasing: after a rename, the title bar still shows the old name
until the app is restarted. We exercise two flows:

1. Direct: push ParentMenu, call _rename_computer, dismiss the name screen
   with a name, assert the TitleBar's rendered output contains the new name.
2. Persistence: write_computer_name + _push_to_title_bar updates both the
   widget state and the file on disk.
"""

import asyncio
import os


os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from purple_tui import purple_tui as pt_mod
from purple_tui.purple_tui import PurpleApp, TitleBar, BootModeIndicator
from purple_tui.constants import REQUIRED_TERMINAL_ROWS

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.3


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _settle(pilot):
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()


def _rendered_title(title_bar: TitleBar) -> str:
    """Concatenate the text of every segment in the title bar's rendered line."""
    strip = title_bar.render_line(0)
    return "".join(seg.text for seg in strip)


def test_rename_flow_updates_title_bar(tmp_path, monkeypatch):
    user_path = tmp_path / "computer_name.txt"
    monkeypatch.setattr(pt_mod, "_COMPUTER_NAME_USER_PATH", user_path)
    monkeypatch.setattr(pt_mod, "_COMPUTER_NAME_SYSTEM_PATH", tmp_path / "system_name.txt")
    monkeypatch.setattr(pt_mod, "_COMPUTER_NAME_CACHE", None, raising=False)
    monkeypatch.setattr(pt_mod, "_COMPUTER_NAME_LOADED", False, raising=False)

    async def run_test():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)

            title = app.screen.query_one("#title-bar", TitleBar)
            indicator = app.screen.query_one(BootModeIndicator)
            # Force "installed" mode so the title bar shows the name.
            indicator._is_live = False
            indicator._push_to_title_bar()
            await pilot.pause()
            baseline = _rendered_title(title)
            assert "My Purple Computer" in baseline, f"baseline: {baseline!r}"

            from purple_tui.rooms.parent_menu import ParentMenu, ComputerNameScreen

            app.push_screen(ParentMenu())
            await _settle(pilot)
            parent = app.screen
            assert isinstance(parent, ParentMenu)

            parent._rename_computer()
            await _settle(pilot)
            name_screen = app.screen
            assert isinstance(name_screen, ComputerNameScreen)

            name_screen.dismiss("Banana")
            await _settle(pilot)

            # While ParentMenu is still on top, the title bar widget on the
            # base screen should already reflect the new name.
            rendered = _rendered_title(title)
            assert "Banana" in rendered, (
                f"title bar render does not contain new name; "
                f"got {rendered!r}, _boot_text={title._boot_text!r}, "
                f"file={user_path.read_text() if user_path.exists() else '<missing>'!r}"
            )
            assert "My Purple Computer" not in rendered, (
                f"title bar still shows old name: {rendered!r}"
            )

            # Dismiss parent menu; render should still show new name.
            parent.dismiss()
            await _settle(pilot)
            rendered_after = _rendered_title(title)
            assert "Banana" in rendered_after, (
                f"after parent menu dismiss: {rendered_after!r}"
            )

            await app.action_quit()

    _run(run_test())
