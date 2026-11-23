"""Kids: each gets their own computer on this one, with their own settings, Time Travel, and packs,
picked at every start once there's more than one."""

import pytest

from purplecomputer import content, settings
from purplecomputer import kids
from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.rooms import parent_menu
from purplecomputer.rooms.parent_menu import _get_menu_items
from purplecomputer.timeline import timeline_dir
from tests.test_pack_arrivals import drive, offered, zorb  # noqa: F401


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


@pytest.fixture
def live_key(monkeypatch, tmp_path):
    """A live Key that keeps work; set present[0] = False to pull it out."""
    from purplecomputer import key_save
    present = [True]
    monkeypatch.setattr(parent_menu, "is_live_boot", lambda: True)
    monkeypatch.setattr(key_save, "is_live_boot", lambda: True)
    monkeypatch.setattr(key_save, "MARKER", str(tmp_path / "key-save"))
    monkeypatch.setattr(key_save, "is_usb_present", lambda: present[0])
    monkeypatch.setattr(key_save, "is_usb_reinserted", lambda: False)
    (tmp_path / "key-save").write_text("p 0 1")
    return present


def test_a_live_key_that_keeps_work_has_kid_profiles(live_key):
    async def go():
        app = make_app()
        assert dict(_get_menu_items(app))["menu-kids"] == "Kid Profiles"
        assert not parent_menu.ParentMenu(app)._disabled("menu-kids")
    run(go())


def test_kids_cannot_be_added_or_removed_while_the_key_is_out(live_key):
    leo = settings.add_kid()
    kids.write_computer_name("Leo's Computer", leo)
    live_key[0] = False

    async def go():
        app = make_app()
        screen = kids.KidsScreen(app)
        assert ("add", "Add a kid", "Needs USB") in screen.options and "add" in screen.dim_values
        screen._on_confirm("add")
        screen._on_confirm(leo)
        assert [o[0] for o in app.top.options] == ["switch", None]
    run(go())


def test_the_first_computers_name_is_kept_with_its_settings(home):
    old = home / ".purple/computer_name.txt"
    old.parent.mkdir()
    old.write_text("Sam's Computer")
    assert kids.computer_name("") == "Sam's Computer"
    kids.write_computer_name("Ari's Computer", "")
    assert (home / ".config/purple/computer_name.txt").read_text() == "Ari's Computer" and not old.exists()
    assert kids.computer_name("") == "Ari's Computer"


def test_switching_kids_writes_the_key_first(live_key, monkeypatch):
    from purplecomputer import key_save
    writes = []
    monkeypatch.setattr(key_save.KeySave, "_write", lambda self, timeout=60: writes.append(timeout) or key_save.OK)
    leo = settings.add_kid()

    async def go():
        app = make_app()
        kids.switch(app, leo)
        assert writes == [key_save.FLUSH_TIMEOUT_S] and not app.running
    run(go())


def test_installing_from_the_key_offers_its_name_and_carries_the_one_typed(live_key, monkeypatch):
    kids.write_computer_name("Ari's Computer", "")
    installs = []
    monkeypatch.setattr(parent_menu, "InstallProgressScreen", lambda app, **k: installs.append(k) or parent_menu.Overlay(app))

    async def go():
        app = make_app()
        menu = parent_menu.ParentMenu(app)
        app.push(menu)
        menu._ask_install(None, "")
        assert app.top._name == "Ari's Computer"
        app.top.close("Sam's Computer")
        app.top.close(False)
        assert kids.computer_name("") == "Ari's Computer"
        menu._ask_install(None, "")
        app.top.close("Sam's Computer")
        app.top.close(True)
        assert kids.computer_name("") == "Sam's Computer" and installs[0]["computer_name"] == "Sam's Computer"
    run(go())
