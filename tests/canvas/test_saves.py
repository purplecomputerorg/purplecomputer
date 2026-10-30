"""Saving from the Esc menu, the Open library (saves and pack pictures), removing saves, and code lines riding along."""

import asyncio

import pytest

from purple_tui.canvas import saves
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.library import DELETE_HOLD_S, Library, PictureTile
from purple_tui.canvas.rooms.art_room import COLS, ROWS, shift_from
from purple_tui.constants import OLD_ART_GRID


@pytest.fixture(autouse=True)
def saves_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_SAVES_DIR", str(tmp_path))
    return tmp_path


async def _art_with_drawing():
    app = make_app()
    app.action_switch_room("art")
    await type_text(app, "qwerty")
    return app


async def _save(app):
    await press(app, "escape")
    await press(app, "s")


async def _open_library(app):
    await press(app, "escape")
    await press(app, "o")
    assert isinstance(app.top, Library)
    app._draw()
    return app.top


def test_save_from_the_esc_menu_then_open_it_back():
    async def go():
        app = await _art_with_drawing()
        drawn = app.room_state("art")
        await _save(app)
        assert app.top is None
        [save] = saves.list_saves("art")
        assert save.state == drawn and app.save_artwork(save, on_screen=True) is not None
        assert [p.suffix for p in save.path.parent.iterdir()] == [".json"]
        app._start_fresh("art")
        assert app.room_state("art") != drawn
        library = await _open_library(app)
        await press(app, "enter")
        assert library.closed and app.room_state("art") == drawn
    run(go())


def test_pack_pictures_open_in_art_only_and_cannot_be_removed(monkeypatch):
    from purple_tui.content import Picture, get_content
    monkeypatch.setattr(get_content(), "pictures", [Picture("palm-tree", [(2, 3, "#ff0000")], letters=[(2, 3, "P", "#ffffff"), (5, 5, "Q", "#000000")])])

    async def go():
        app = await _art_with_drawing()
        drawn = app.room_state("art")
        library = await _open_library(app)
        [tile] = library.tiles
        assert isinstance(tile, PictureTile) and app.save_artwork(tile) is not None
        await press(app, "backspace", hold=DELETE_HOLD_S + 0.2)
        assert library.tiles == [tile]
        await press(app, "enter")
        dx, dy = shift_from(OLD_ART_GRID)
        assert app.room_state("art")[f"c:{2 + dx},{3 + dy}"][:3] == ["P", "#ffffff", "#ff0000"]
        assert app.rooms["art"].picture() == ([[2 + dx, 3 + dy, "#ff0000"]],
                                              [[2 + dx, 3 + dy, "P", "#ffffff"], [5 + dx, 5 + dy, "Q", "#000000"]])
        assert app._timelines["art"].tip() != drawn, "the picture is a new Time Travel step"
        library.close()
        app.action_switch_room("music")
        assert (await _open_library(app)).tiles == []
    run(go())


def test_saving_the_same_work_twice_adds_one_tile():
    async def go():
        app = await _art_with_drawing()
        assert app.save_room()
        assert app.save_room() is None
        assert len(saves.list_saves("art")) == 1
    run(go())


def test_nothing_to_save_saves_nothing():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        await _save(app)
        assert app.top is None and saves.list_saves("art") == []
    run(go())


def test_holding_backspace_removes_a_save_and_a_tap_does_not():
    async def go():
        app = await _art_with_drawing()
        app.save_room()
        await _open_library(app)
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


def test_library_scrolls_past_two_rows():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        for ch in "abcdefghij":
            await type_text(app, ch)
            app.save_room()
        library = await _open_library(app)
        for _ in range(3):
            await press(app, "down")
        assert library.top_row == 1
        app._draw()
    run(go())


def test_export_writes_each_save_once(tmp_path):
    async def go():
        from purple_tui.canvas.rooms.save_export import FOLDER, export_saves
        app = await _art_with_drawing()
        app.save_room()
        dest = tmp_path / "stick"
        def page(save):
            return app.save_artwork(save), ""
        assert export_saves(dest, page) == 1
        assert len(list((dest / FOLDER / "Art").glob("*.png"))) == 1
        assert export_saves(dest, page) == 0
    run(go())


def test_export_finds_a_purple_keys_data_partition_not_its_efi(monkeypatch):
    import json
    import subprocess
    from purple_tui.canvas.rooms import save_export
    key = {"name": "/dev/sdb", "tran": "usb", "children": [
        {"name": "/dev/sdb1", "fstype": "iso9660", "parttype": "0x0"},
        {"name": "/dev/sdb2", "fstype": "vfat", "parttype": "0xef"},
        {"name": "/dev/sdb3", "fstype": "vfat", "parttype": "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"}]}
    out = json.dumps({"blockdevices": [key]})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert save_export.find_stick() == ("/dev/sdb3", None)


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
        await _save(app)
        assert saves.list_saves("art") == [] and saves.list_saves("play") == []
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
        await type_text(app, "z")
        await _save(app)
        assert len(saves.list_saves("art")) == 1, "a full USB takes no new saves"
    run(go())


def test_time_travel_stars_the_saved_moment_until_the_save_is_removed():
    async def go():
        app = await _art_with_drawing()
        drawn = app.room_state("art")
        await _save(app)
        await type_text(app, "asdf")
        app._start_time_travel()
        [star] = app.time_travel_position()[2]
        app._step_time_travel(-1)
        assert app.time_travel_position()[0] == star and app.room_state("art") == drawn
        app._draw()
        app._cancel_time_travel()
        app.delete_save(saves.list_saves("art")[0])
        app._start_time_travel()
        assert app.time_travel_position()[2] == []
    run(go())


def test_open_fills_in_its_pictures_a_frame_at_a_time_and_keeps_them(monkeypatch):
    import purple_tui.canvas.library as library
    monkeypatch.setattr(library, "FILL_BUDGET_S", 0)

    async def go():
        app = await _art_with_drawing()
        for keys in ("asdf", "zxcv"):
            await type_text(app, keys)
            app.save_room()
        lib = await _open_library(app)
        assert len(app.save_pictures) == 1
        await asyncio.sleep(0.05)
        app._draw()
        assert len(app.save_pictures) == 2
        lib.close()
        drawn = dict(app.save_pictures)
        await _open_library(app)
        assert all(app.save_pictures[k] is v for k, v in drawn.items())
    run(go())


def test_a_save_flashes_shows_its_picture_and_stars_the_title_until_the_work_changes():
    async def go():
        app = await _art_with_drawing()
        await _save(app)
        [toast] = app._toasts
        assert app._save_flash_at is not None and toast.picture is not None
        assert "art" in app._saved_digest
        app._draw()
        await _save(app)
        assert "Already" in app._toasts[-1].text
        await type_text(app, "z")
        assert "art" not in app._saved_digest
    run(go())


def test_art_from_the_old_grid_opens_centered_and_time_travels():
    """A save and Time Travel steps from before the grid grew name no grid; they come back centered."""
    old = {"c:0,0": ["", "#000000", "#ff0000", 1], "c:55,23": ["A", "#ffffff", "#00ff00", 1], "cursor": [55, 23]}
    dx, dy = shift_from(OLD_ART_GRID)

    async def go():
        app = make_app()
        app.action_switch_room("art")
        app.apply_room_state("art", old)
        art = app.rooms["art"]
        assert art.picture() == ([[dx, dy, "#ff0000"], [55 + dx, 23 + dy, "#00ff00"]], [[55 + dx, 23 + dy, "A", "#ffffff"]])
        assert (art._cursor_x, art._cursor_y) == (55 + dx, 23 + dy)
        now = app.room_state("art")
        assert now["grid"] == [COLS, ROWS]
        app.apply_room_state("art", now)
        assert app.room_state("art") == now, "today's states come back where they were"
    run(go())
