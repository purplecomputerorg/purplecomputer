"""Printing: the Esc menu's Print card follows the printer, rooms print their work on white, and the queue is paced."""
import asyncio
import json

import pytest

from purple_tui import printing, settings
from purple_tui.canvas import paper
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.room_picker import RoomPicker

READY = {"ready": True, "model": "Brother HL-L2420DW", "via": "ipp-usb"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(printing, "STATE", str(tmp_path / "printer.json"))
    monkeypatch.setattr(printing, "_FAKE", False)
    monkeypatch.setattr(printing, "is_live_boot", lambda: False)
    monkeypatch.setattr(printing, "_last_at", -printing.COOLDOWN_S)
    monkeypatch.setattr(printing, "_count", 0)


@pytest.fixture
def plugged_in():
    with open(printing.STATE, "w") as f:
        json.dump(READY, f)


@pytest.fixture
def lp_calls(monkeypatch):
    calls = []

    async def fake_run(*argv):
        calls.append(argv)
        return ""
    monkeypatch.setattr(printing, "_run", fake_run)
    return calls


async def _menu(app):
    await press(app, "escape")
    return app.top


def _write(**state):
    with open(printing.STATE, "w") as f:
        json.dump(state, f)


def test_print_card_always_says_what_the_printer_is_doing():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        await type_text(app, "q")
        for state, label, enabled in [(None, "No Printer", False),
                                      ({"ready": False, "model": "a printer", "via": printing.SETTING_UP}, "Starting Up", False),
                                      ({"ready": False, "model": "Canon TS3520", "via": "no driver for this model"}, "Can't Print", False),
                                      (READY, "Print", True)]:
            if state:
                _write(**state)
            menu = await _menu(app)
            _, shown, key, disabled = menu._print_card()
            assert (shown, bool(key), not disabled) == (label, enabled, enabled)
            menu.close(None)
    run(go())


def test_a_print_card_that_cant_print_says_why_when_pressed():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        await type_text(app, "q")
        await _menu(app)
        await press(app, "p")
        assert app.has_overlay(RoomPicker)
        assert app._toasts[-1].text == "Plug in a printer with its USB cable"
        _write(ready=False, model="Canon TS3520", via="no driver for this model")
        assert printing.why_not() == "This printer doesn't work with Purple yet"
    run(go())


def test_plugging_in_a_printer_shows_a_toast_each_step():
    async def go():
        app = make_app()
        app._check_printer()
        _write(ready=False, model="a printer", via=printing.SETTING_UP)
        app._check_printer()
        assert app._toasts[-1].text == "Printer plugged in. Getting it ready"
        _write(**READY)
        app._check_printer()
        assert app._toasts[-1].text == "The printer is ready. Press Esc, then P"
        n = len(app._toasts)
        app._check_printer()
        assert len(app._toasts) == n
    run(go())


def test_a_stuck_setup_reads_as_broken(monkeypatch):
    _write(ready=False, model="a printer", via=printing.SETTING_UP)
    monkeypatch.setattr(printing.time, "time", lambda: printing._state_mtime() + printing.SETUP_TIMEOUT_S + 1)
    assert printing.status() == printing.BROKEN


def test_pulled_stick_cant_print_on_a_live_boot(plugged_in, monkeypatch):
    monkeypatch.setattr(printing, "is_live_boot", lambda: True)
    monkeypatch.setattr(printing, "is_usb_present", lambda: False)
    assert printing.printer() is None
    assert printing.why_not() == "Put the Purple USB back in to print"


def test_p_in_the_esc_menu_sends_the_art_page(plugged_in, lp_calls):
    async def go():
        app = make_app()
        app.action_switch_room("art")
        await type_text(app, "qwerty")
        await _menu(app)
        await press(app, "p")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not app.has_overlay(RoomPicker)
        (argv,) = lp_calls
        assert argv[:3] == ("lp", "-d", "purple") and "landscape" in argv
        assert app._toasts[-1].text == "Printing!"
    run(go())


def test_art_page_is_the_paint_on_white(plugged_in):
    async def go():
        app = make_app()
        app.action_switch_room("art")
        assert paper.page(app.room, app.g) is None
        await type_text(app, "q")
        surface, landscape = paper.page(app.room, app.g)
        assert landscape and surface.get_size() == paper.PAGE
        colors = {surface.get_at((x, y))[:3] for x in range(0, paper.PAGE[0], 25) for y in range(0, paper.PAGE[1], 25)}
        assert paper.WHITE in colors and len(colors) == 2
    run(go())


def test_every_room_with_work_makes_a_page():
    async def go():
        app = make_app()
        app.action_switch_room("play")
        await type_text(app, "cat", enter=True)
        assert paper.page(app.room, app.g)[1] is False
        app.action_switch_room("blocks")
        await type_text(app, "qa")
        assert paper.page(app.room, app.g)[0].get_size() == paper.PAGE
        app.action_switch_room("music")
        assert not paper.can_print(app.room)
    run(go())


def test_prints_are_paced(plugged_in, lp_calls):
    async def go():
        app = make_app()
        app.action_switch_room("art")
        await type_text(app, "q")
        app.action_print()
        await asyncio.sleep(0)
        app.action_print()
        assert len(lp_calls) == 1
        assert app._toasts[-1].text == "The printer is still busy"
    run(go())


def test_printer_problems_read_as_plain_words():
    assert printing.problem("printer-state-reasons: media-empty-error") == "The printer needs paper"
    assert printing.problem("Alerts: media-jam-error marker-supply-empty-warning") == "Paper is stuck in the printer"
    assert printing.problem("Alerts: none") is None


def test_support_info_names_the_printer(plugged_in):
    assert printing.status_line() == "Printer: Brother HL-L2420DW, ready"
    with open(printing.STATE, "w") as f:
        json.dump({"ready": False, "model": "Canon TS3520", "via": "no driver for this model"}, f)
    assert printing.status_line() == "Printer: Canon TS3520 can't print yet (Technical: no driver for this model)"


def test_maker_mark_uses_the_computer_name_and_keeps_the_brand():
    assert paper.maker_mark("My Purple Computer") == "Made on Purple Computer"
    assert paper.maker_mark("") == "Made on Purple Computer"
    assert paper.maker_mark("Ari's Purple Computer") == "Made on Ari's Purple Computer"
    assert paper.maker_mark("Ari's Laptop") == "Made on Ari's Laptop with Purple Computer"


def test_maker_mark_uses_the_computer_name_and_keeps_the_brand():
    assert paper.maker_mark("My Purple Computer") == "Made on Purple Computer"
    assert paper.maker_mark("") == "Made on Purple Computer"
    assert paper.maker_mark("Ari's Purple Computer") == "Made on Ari's Purple Computer"
    assert paper.maker_mark("Ari's Laptop") == "Made on Ari's Laptop with Purple Computer"
