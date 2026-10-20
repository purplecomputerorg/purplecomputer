"""A parent turns built-in rooms off from the Parent Menu; the Esc menu and status strip skip them."""

import pytest

from purple_tui import settings
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.room_picker import RoomPicker
from purple_tui.canvas.rooms.parent_menu import ParentMenu
from purple_tui.canvas.rooms.rooms_screen import RoomsScreen


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")


def test_purple_opens_in_art_or_the_first_room_thats_on():
    async def go():
        return make_app().active_room
    assert run(go()) == "art"
    settings.set_room_off("art", True)
    assert run(go()) == "music"


def _states(screen) -> list:
    return [screen._state(item, settings.get_rooms_on()) for item in screen.rows[1]]


def test_turning_rooms_off_hides_them_and_leaves_the_room_youre_in():
    async def go():
        app = make_app()
        screen = RoomsScreen(app)
        app.push(screen)
        assert [x for _, x in screen.rows[1]] == list(app.rooms)
        assert _states(screen) == ["on", "on", "on", "on", "off"]
        app._draw()
        await press(app, "enter")
        assert app.active_room == "music" and settings.get_rooms_off() == ["art"]
        assert _states(screen)[0] == "off"
        assert [r.name for r in RoomPicker(app).options] == ["music", "play", "blocks"]
        await press(app, "enter")
        assert _states(screen)[0] == "on" and settings.get_rooms_off() == []
    run(go())


def test_the_last_room_stays_on():
    settings.set_room_off("play", True)
    settings.set_room_off("music", True)
    settings.set_room_off("art", True)

    async def go():
        app = make_app()
        assert app.active_room == "blocks" and app.kid_rooms == ["blocks"]
        screen = RoomsScreen(app)
        app.push(screen)
        screen.col = 3
        await press(app, "enter")
        assert app.kid_rooms == ["blocks"] and app._toasts
    run(go())


def test_arrows_move_between_littles_mode_and_the_rooms():
    async def go():
        app = make_app()
        screen = RoomsScreen(app)
        app.push(screen)
        await press(app, "right")
        await press(app, "right")
        await press(app, "up")
        assert screen.rows[screen.row] == [("littles", None)]
        await press(app, "down")
        await press(app, "down")
        assert screen.row == 1
        await press(app, "escape")
        assert app.top is None
    run(go())


def test_littles_mode_is_picked_in_rooms_and_the_parent_menu_follows():
    async def go():
        app = make_app()
        menu = ParentMenu(app)
        app.push(menu)
        assert [i for i, _ in menu.items].count("menu-rooms") == 1 and "menu-littles" not in [i for i, _ in menu.items]
        menu._open_rooms()
        await press(app, "up")
        await press(app, "enter")
        await press(app, "down")
        await press(app, "down")
        await press(app, "down")
        await press(app, "enter")  # Art
        assert app._littles_mode == "art" and app.active_room == "art"
        assert "Littles Mode is on" in app.top.description
        await press(app, "escape")
        assert app.top is menu
        assert dict(menu.items)["menu-rooms"] == "Rooms: Littles Mode, Art"
        assert "menu-code-panel" not in dict(menu.items)
    run(go())


def test_switching_to_a_room_thats_off_lands_on_one_thats_on():
    settings.set_room_off("art", True)

    async def go():
        app = make_app()
        app.action_switch_room("art")
        assert app.active_room == "music"
    run(go())


def test_littles_mode_keeps_its_room_even_if_it_is_off():
    settings.set_room_off("music", True)
    settings.set_littles_mode("music")

    async def go():
        app = make_app()
        assert app.active_room == "music"
        app._apply_littles_mode(None)
        assert app.active_room == "art"
    run(go())
