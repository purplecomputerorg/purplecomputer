"""Saving: the Save wall from the Esc menu, opening and removing saves, and code lines riding along."""

import asyncio

import pytest

from purple_tui.canvas import saves
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.save_wall import DELETE_HOLD_S, SaveWall


@pytest.fixture(autouse=True)
def saves_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_SAVES_DIR", str(tmp_path))
    return tmp_path


async def _art_with_drawing():
    app = make_app()
    app.action_switch_room("art")
    await type_text(app, "qwerty")
    return app


async def _open_wall(app):
    await press(app, "escape")
    await press(app, "s")
    assert isinstance(app.top, SaveWall)
    app._draw()
    return app.top


def test_save_from_wall_then_open_it_back():
    async def go():
        app = await _art_with_drawing()
        drawn = app.room_state("art")
        await _open_wall(app)
        await press(app, "enter")
        assert app.top is None
        [save] = saves.list_saves("art")
        assert save.state == drawn and save.thumbnail() is not None
        assert not any(p.suffix == ".png" and not p.name.endswith(".thumb.png") for p in save.path.parent.iterdir())
        app._start_fresh("art")
        assert app.room_state("art") != drawn
        wall = await _open_wall(app)
        await press(app, "right")
        await press(app, "enter")
        assert wall.closed and app.room_state("art") == drawn
    run(go())


def test_saving_the_same_work_twice_adds_one_tile():
    async def go():
        app = await _art_with_drawing()
        assert app.save_room()
        assert app.save_room() is None
        assert len(saves.list_saves("art")) == 1
    run(go())


def test_nothing_to_save_keeps_the_wall_open():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        await _open_wall(app)
        await press(app, "enter")
        assert isinstance(app.top, SaveWall) and saves.list_saves("art") == []
    run(go())


def test_holding_backspace_removes_a_save_and_a_tap_does_not():
    async def go():
        app = await _art_with_drawing()
        app.save_room()
        await _open_wall(app)
        await press(app, "right")
        await press(app, "backspace", hold=0.1)
        assert len(saves.list_saves("art")) == 1
        await press(app, "backspace", hold=DELETE_HOLD_S + 0.2)
        assert saves.list_saves("art") == []
        app._draw()
    run(go())


def test_code_lines_ride_along_and_mark_the_tile():
    async def go():
        app = await _art_with_drawing()
        app.room.open_code_panel()
        await type_text(app, "red", enter=True)
        await asyncio.sleep(0.05)
        save = app.save_room()
        assert save.has_code and app.code_lines("art") == ["red"]
        app._start_fresh("art")
        assert app.code_lines("art") == []
        app.open_save(save)
        assert app.code_lines("art") == ["red"]
        app.room.open_code_panel()
        await press(app, "up")
        assert app.room.code_panel.field.value == "red"
    run(go())


def test_wall_scrolls_past_two_rows():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        for ch in "abcdefghij":
            await type_text(app, ch)
            app.save_room()
        wall = await _open_wall(app)
        for _ in range(3):
            await press(app, "down")
        assert wall.top_row == 1
        app._draw()
    run(go())


def test_export_writes_each_save_once(tmp_path):
    async def go():
        from purple_tui.canvas.rooms.save_export import FOLDER, export_saves
        app = await _art_with_drawing()
        app.save_room()
        dest = tmp_path / "stick"
        page = app.save_artwork
        assert export_saves(dest, page) == 1
        assert len(list((dest / FOLDER / "Art").glob("*.png"))) == 1
        assert export_saves(dest, page) == 0
    run(go())


def test_reinstall_keeps_by_default_and_start_fresh_asks_again():
    async def go():
        from purple_tui.canvas.rooms.parent_menu import ReinstallConfirmScreen, StartFreshConfirmScreen
        app = make_app()
        results = []
        app.push(ReinstallConfirmScreen(app), on_close=results.append)
        app._draw()
        assert app.top.options[app.top.selected][0] == "keep"
        await press(app, "down")
        await press(app, "down")
        await press(app, "enter")
        assert isinstance(app.top, StartFreshConfirmScreen) and results == []
        app._draw()
        await press(app, "enter")          # Go back is preselected
        assert isinstance(app.top, ReinstallConfirmScreen) and results == []
        await press(app, "enter")
        await press(app, "up")
        await press(app, "enter")
        assert results == [True] and app.top is None
    run(go())


@pytest.mark.parametrize("room,keys", [("art", "qwerty"), ("music", "asdf"), ("play", "cat\n"), ("blocks", "qq")])
def test_every_room_redraws_a_save_offscreen_without_touching_the_screen(room, keys):
    async def go():
        app = make_app()
        app.action_switch_room(room)
        for ch in keys:
            await press(app, "enter" if ch == "\n" else ch)
        save = app.save_room()
        live = app.room_state(room)
        sentinel = object()
        app._panel = sentinel
        work = app.save_artwork(save)
        assert work is not None and work.get_width() > 100
        assert app._panel is sentinel and app.room_state(room) == live
        app._panel = None
    run(go())


def test_save_card_greys_out_on_a_key_that_cannot_keep_work(monkeypatch, tmp_path):
    from purple_tui.canvas import key_save
    monkeypatch.setattr(key_save, "is_live_boot", lambda: True)
    monkeypatch.setattr(key_save, "MARKER", str(tmp_path / "key-save"))
    present = [True]
    monkeypatch.setattr(key_save, "is_usb_present", lambda: present[0])
    assert key_save.unavailable() == "Needs Install"
    (tmp_path / "key-save").write_text("/dev/x 0 0\n")
    assert key_save.unavailable() is None and key_save.active()
    present[0] = False
    assert key_save.unavailable() == "Needs USB"

    async def go():
        app = make_app()
        await press(app, "escape")
        await press(app, "s")
        assert not isinstance(app.top, SaveWall)
        app._draw()
    run(go())


def test_key_writes_wait_for_a_quiet_moment_and_flush_before_power_off(monkeypatch, tmp_path):
    from purple_tui.canvas import key_save
    monkeypatch.setattr(key_save, "is_live_boot", lambda: True)
    monkeypatch.setattr(key_save, "is_usb_present", lambda: True)
    monkeypatch.setattr(key_save, "MARKER", str(tmp_path / "key-save"))
    monkeypatch.setattr(key_save, "DEBOUNCE_S", 0.05)
    (tmp_path / "key-save").write_text("/dev/x 0 0\n")
    writes = []
    monkeypatch.setattr(key_save.KeySave, "_write", lambda self, timeout=60: writes.append(timeout) or key_save.FULL)

    async def go():
        app = await _art_with_drawing()
        app.save_room()
        app.key_save.changed()
        await asyncio.sleep(0.3)
        assert len(writes) == 1 and app.key_save.full
        app.key_save.flush()
        assert len(writes) == 1, "nothing new since the last write"
        app.key_save.changed()
        app.flush_for_power_off()
        assert writes[-1] == key_save.FLUSH_TIMEOUT_S
        wall = await _open_wall(app)
        await press(app, "enter")
        assert isinstance(app.top, SaveWall) and len(saves.list_saves("art")) == 1, "a full USB takes no new saves"
        wall.close()
    run(go())
