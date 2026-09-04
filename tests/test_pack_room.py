"""A family room on screen: the picker lists it, keys run its rules, Esc leaves."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("PURPLE_NO_EVDEV", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).parent.parent))

from textual.widgets import Static  # noqa: E402

from purple_tui import content as content_mod  # noqa: E402
from purple_tui.content import ContentManager  # noqa: E402
from purple_tui.keyboard import CharacterAction, ControlAction  # noqa: E402
from purple_tui.room_picker import ROW_PACK, RoomPickerScreen  # noqa: E402
from purple_tui.rooms.pack_room import PackRoomScreen  # noqa: E402

FARM = {"name": "farm", "title": "Farm", "background": "#1e1033", "rules": [
    {"when": {"event": "start"}, "do": [{"do": "show", "text": "🐄 🐖 🐑"}]},
    {"when": {"event": "key", "key": "c"}, "do": [{"do": "show", "text": "🐄"}, {"do": "say", "text": "cow"}, {"do": "play", "note": "C4", "instrument": "marimba"}]},
    {"when": {"event": "any_key"}, "do": [{"do": "add", "text": {"key": True}}, {"do": "drum", "name": "kick"}]},
    {"when": {"event": "every", "seconds": 0.5}, "do": [{"do": "add", "text": "·"}]},
]}


@pytest.fixture
def rooms_content(monkeypatch):
    cm = ContentManager(packs_dir=Path("/nonexistent"))
    cm.load_all()
    cm.rooms = [FARM, {"name": "sea", "title": "Sea", "rules": []}]
    monkeypatch.setattr(content_mod, "_content", cm)
    return cm


def shown(screen, selector: str) -> str:
    rendered = screen.query_one(selector, Static).render()
    return getattr(rendered, "plain", str(rendered))


def press(char: str) -> CharacterAction:
    return CharacterAction(char=char, shifted=False, shift_held=False, is_repeat=False, arrow_held=False)


def test_room_runs_its_rules_and_esc_leaves(rooms_content, monkeypatch):
    from purple_tui import tts
    from purple_tui.purple_tui import PurpleApp
    said: list[str] = []
    monkeypatch.setattr(tts, "speak", lambda text, **kw: said.append(text))

    async def go():
        app = PurpleApp()
        async with app.run_test(size=(146, 38)) as pilot:
            await pilot.pause()
            screen = PackRoomScreen(FARM)
            app.push_screen(screen)
            await pilot.pause()
            assert shown(screen, "#room-show") == "🐄 🐖 🐑"
            await screen.handle_keyboard_action(press("C"))
            await pilot.pause()
            assert shown(screen, "#room-show") == "🐄"
            assert shown(screen, "#room-line") == "c"
            assert said == ["cow"]
            await asyncio.sleep(0.7)
            await pilot.pause()
            assert "·" in shown(screen, "#room-line")
            await screen.handle_keyboard_action(ControlAction(action="escape", is_down=False))
            await pilot.pause()
            assert len(app.screen_stack) == 1
    asyncio.run(go())


def test_picker_lists_pack_rooms_and_number_keys_pick_them(rooms_content):
    from purple_tui.purple_tui import PurpleApp

    async def go():
        app = PurpleApp()
        async with app.run_test(size=(146, 38)) as pilot:
            await pilot.pause()
            picker = RoomPickerScreen(current_room="play")
            app.push_screen(picker, app._on_room_picked)
            await pilot.pause()
            assert [t for _, t in picker._pack_rooms] == ["Farm", "Sea"]
            assert picker.query_one("#opt-pack-1").render().strip().startswith("✦  Sea")
            await picker.handle_keyboard_action(press("5"))
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "PackRoomScreen"
            assert app.screen.program["name"] == "sea"
    asyncio.run(go())


def test_picker_walks_through_the_pack_row(rooms_content):
    from purple_tui.keyboard import NavigationAction
    from purple_tui.purple_tui import PurpleApp

    async def go():
        app = PurpleApp()
        async with app.run_test(size=(146, 38)) as pilot:
            await pilot.pause()
            picker = RoomPickerScreen(current_room="art")
            app.push_screen(picker)
            await pilot.pause()
            await picker.handle_keyboard_action(NavigationAction(direction="down"))
            assert (picker._active_row, picker._pack_index) == (ROW_PACK, 1)
            await picker.handle_keyboard_action(NavigationAction(direction="down"))
            assert picker._active_row != ROW_PACK and picker._extra_index == 1
            await picker.handle_keyboard_action(NavigationAction(direction="up"))
            assert (picker._active_row, picker._pack_index) == (ROW_PACK, 1)
            await picker.handle_keyboard_action(NavigationAction(direction="left"))
            assert picker._pack_index == 0
    asyncio.run(go())
