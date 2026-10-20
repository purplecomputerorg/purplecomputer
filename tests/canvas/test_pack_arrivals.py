"""A USB drive with a Purple Pack plugged into a running Purple: it is offered, Add (after the
parent PIN when one is set) puts it in use without a restart, Not now drops it, and one added
before goes back in without asking."""

import pytest

from purple_tui import content, pack_arrivals, settings
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.room_picker import family_rooms
from purple_tui.canvas.rooms.parent_menu import PinEntry
from purple_tui.canvas.rooms.rooms_screen import RoomsScreen
from purple_tui.canvas.ui import Confirm
from purple_tui.usb_updater import sha256, update_from
from scripts.purplepack import build_pack
from tests.test_packs import make_pack

ID = "the-tests-pack"


@pytest.fixture
def drive(tmp_path, monkeypatch):
    """Plugs in a drive holding one Studio-shaped pack; returns that pack's sha256."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(pack_arrivals, "WAITING_DIR", tmp_path / "waiting")
    monkeypatch.setattr(content, "_content", None)
    (tmp_path / "stick").mkdir()
    pack = build_pack(make_pack(tmp_path / "src", ID), tmp_path / "stick" / f"{ID}.purplepack")

    def plug():
        update_from(pack.parent, pack_arrivals.WAITING_DIR)
        return sha256(pack)
    return plug


def zorb():
    return content.get_content().exact_emoji("zorb")


def offered(app, drive):
    sha = drive()
    app._check_pack_arrivals()
    assert isinstance(app.top, Confirm) and "The Tests' Purple" in app.top.DESCRIPTION
    return sha


def test_add_puts_the_pack_in_use_at_once(drive):
    async def go():
        app = make_app()
        assert zorb() is None
        sha = offered(app, drive)
        assert "pick which of its rooms" in app.top.DESCRIPTION
        await press(app, "enter")
        assert zorb() == "🐙"
        assert settings.get_packs_added() == {ID: sha}
        assert not any(pack_arrivals.WAITING_DIR.iterdir())
    run(go())


def test_after_add_the_parent_picks_which_rooms_to_turn_on(drive):
    async def go():
        app = make_app()
        offered(app, drive)
        await press(app, "enter")
        screen = app.top
        assert isinstance(screen, RoomsScreen) and "Parent Menu" in screen.description
        assert screen.labels[screen.row][1].startswith("New: ") and screen.rows[screen.row][0][1].pack == ID
        assert family_rooms() == []
        await press(app, "enter")
        assert [r.pack for r in family_rooms()] == [ID]
        await press(app, "escape")
        assert app.top is None
    run(go())


def test_not_now_drops_it(drive):
    async def go():
        app = make_app()
        offered(app, drive)
        await press(app, "down")
        await press(app, "enter")
        assert zorb() is None and app.top is None
        assert not any(pack_arrivals.WAITING_DIR.iterdir())
    run(go())


def test_with_a_parent_pin_add_asks_for_it(drive):
    settings.set_parent_pin("1234")

    async def go():
        app = make_app()
        offered(app, drive)
        await press(app, "enter")
        assert isinstance(app.top, PinEntry)
        await press(app, "escape")  # PinEntry lets go of an Esc that may still be held from the parent menu
        await press(app, "escape")
        assert app.top is None and zorb() is None and not any(pack_arrivals.WAITING_DIR.iterdir())

        offered(app, drive)
        await press(app, "enter")
        await type_text(app, "1234")
        assert zorb() == "🐙"
    run(go())


def test_a_pack_added_before_goes_back_in_without_asking(drive):
    settings.set_pack_added(ID, drive())  # a live boot: added last time, packs gone since

    async def go():
        app = make_app()
        assert zorb() == "🐙" and app.top is None
        drive()
        app._check_pack_arrivals()
        assert app.top is None and not any(pack_arrivals.WAITING_DIR.iterdir())
    run(go())


def test_a_drive_being_read_says_so_then_says_how_it_went(drive):
    reading = pack_arrivals.WAITING_DIR / ".reading"

    async def read(app, plug=None):
        pack_arrivals.WAITING_DIR.mkdir(exist_ok=True)
        reading.touch()
        app._check_pack_arrivals()
        assert app._toasts[-1].text == "Reading the Purple Pack..."
        if plug:
            plug()
        reading.unlink(missing_ok=True)
        app._check_pack_arrivals()

    async def go():
        app = make_app()
        await read(app)
        assert app._toasts[-1].text.startswith("Couldn't read that Purple Pack")

        await read(app, drive)
        assert isinstance(app.top, Confirm) and not app._toasts
        await press(app, "enter")
        app.top.close()

        await read(app, drive)
        assert app.top is None and app._toasts[-1].text.startswith("Already added")
    run(go())
