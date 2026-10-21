"""Kids: each gets their own computer on this one, with their own settings, Time Travel, and packs,
picked at every start once there's more than one."""

import pytest

from purple_tui import content, settings
from purple_tui.canvas import kids
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms import parent_menu
from purple_tui.canvas.rooms.parent_menu import _get_menu_items
from purple_tui.timeline import timeline_dir
from tests.canvas.test_pack_arrivals import drive, offered, zorb  # noqa: F401


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / ".config/purple/settings.json")
    monkeypatch.setattr(kids, "PICKED", tmp_path / "picked")
    return tmp_path


def test_each_kid_keeps_their_own_settings_and_shares_the_parents(home, monkeypatch):
    monkeypatch.delenv("PURPLE_DEV_MODE", raising=False)
    settings.set_parent_pin("1234")
    settings.set_littles_mode("art")
    leo = settings.add_kid()
    settings.set_kid(leo)
    assert settings.get_littles_mode() is None and settings.get_parent_pin() == "1234"
    settings.set_littles_mode("music")
    settings.set_parent_pin("4321")
    assert timeline_dir() == home / ".config/purple/kids" / leo / "timeline"
    settings.set_kid("")
    assert settings.get_littles_mode() == "art" and settings.get_parent_pin() == "4321"
    assert timeline_dir() == home / ".config/purple/timeline"


def test_removing_a_kid_drops_their_things_and_packs_just_for_them(home):
    leo = settings.add_kid()
    kids.write_computer_name("Leo's Computer", leo)
    settings.set_pack_kid("dinos", leo)
    settings.remove_kid(leo)
    assert settings.get_kids() == [""] and settings.get_pack_kid("dinos") is None
    assert not (home / ".config/purple/kids" / leo).exists()


def test_a_new_pack_can_be_just_for_the_kid_playing_now(drive):  # noqa: F811
    leo = settings.add_kid()
    kids.write_computer_name("Leo's Computer", leo)

    async def go():
        app = make_app()
        offered(app, drive)
        await press(app, "enter")
        assert isinstance(app.top, kids.WhoGetsIt)
        assert [o[1] for o in app.top.options] == ["Everyone", "Just My Purple Computer"]
        await press(app, "down")
        await press(app, "enter")
        assert zorb() == "🐙"
        settings.set_kid(leo)
        content.reload_content()
        assert zorb() is None
    run(go())


def test_a_parent_adds_a_kid_and_switches_to_them(home):
    async def go():
        app = make_app()
        menu = dict(_get_menu_items(app))
        assert menu["menu-kids"] == "Kid Profiles"
        app.push(kids.KidsScreen(app))
        await press(app, "down")
        await press(app, "enter")
        assert "First, name" in app.top.title
        await type_text(app, "Ari's Computer")
        await press(app, "enter")
        assert "new computer" in app.top.title
        await type_text(app, "Ari's Computer")
        await press(app, "enter")
        assert "new computer" in app.top.title and settings.get_kids() == [""]
        for _ in "Ari's Computer":
            await press(app, "backspace")
        await type_text(app, "Noa's Computer")
        await press(app, "enter")
        assert app.top.title == "Switch to Noa's Computer now?"
        await press(app, "enter")
        assert not app.running and kids.PICKED.exists()
        assert kids.computer_name() == "Noa's Computer"
        assert kids.computer_name("") == "Ari's Computer"
    run(go())


def test_who_is_playing_shows_at_start_unless_a_kid_was_just_picked():
    leo = settings.add_kid()
    kids.write_computer_name("Leo's Computer", leo)

    async def go():
        app = make_app()
        kids.ask_at_boot(app)
        assert isinstance(app.top, kids.WhoIsPlaying)
        assert [o[1] for o in app.top.options] == ["My Purple Computer", "Leo's Computer"]
        await press(app, "escape")
        assert app.running and settings.get_kid() == ""
        kids.PICKED.touch()
        kids.ask_at_boot(app)
        assert not isinstance(app.top, kids.WhoIsPlaying) and not kids.PICKED.exists()
    run(go())


def test_kids_wait_for_purple_to_be_installed(monkeypatch):
    monkeypatch.setattr(parent_menu, "is_live_boot", lambda: True)

    async def go():
        app = make_app()
        assert dict(_get_menu_items(app))["menu-kids"] == "Kid Profiles (install Purple first)"
        assert parent_menu.ParentMenu(app)._disabled("menu-kids")
    run(go())
