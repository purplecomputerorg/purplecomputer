"""A parent turns built-in rooms off from the Parent Menu; the Esc menu and status strip skip them."""

import pytest

from purple_tui import settings
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.room_picker import RoomPicker
from purple_tui.canvas.rooms.parent_menu import RoomsScreen


@pytest.fixture(autouse=True)
def settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")


def test_purple_opens_in_art_or_the_first_room_thats_on():
    async def go():
        return make_app().active_room
    assert run(go()) == "art"
    settings.set_room_off("art", True)
    assert run(go()) == "music"


def test_turning_rooms_off_hides_them_and_leaves_the_room_youre_in():
    async def go():
        app = make_app()
        screen = RoomsScreen(app)
        app.push(screen)
        assert [o[1:] for o in screen.options[:-1]] == [(app.rooms[r].label, "On") for r in app.kid_rooms] + \
            [("Write", "Off: a quiet page for stories and letters")]
        await press(app, "enter")
        assert app.active_room == "music" and settings.get_rooms_off() == ["art"]
        assert screen.options[0][2] == "Off"
        assert [r.name for r in RoomPicker(app).options] == ["music", "play", "blocks"]
        await press(app, "enter")
        assert screen.options[0][2] == "On" and settings.get_rooms_off() == []
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
        assert screen.options[3][2] == "On: the last room stays on"
        screen.selected = 3
        await press(app, "enter")
        assert app.kid_rooms == ["blocks"]
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
