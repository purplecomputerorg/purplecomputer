"""Write room: a page of text that wraps whole words, scrolls to the caret, travels in time,
saves, prints every page, copies to a USB drive as a .txt too, and starts off until a parent turns it on."""

import json
import random

import pytest

from purple_tui import settings
from purple_tui.canvas import paper, saves
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.room_picker import RoomPicker
from purple_tui.canvas.rooms.write_room import COLS, MAX_CHARS, keep_in_view, line_of, wrap

STORY = ("The dragon flew over the hills and the rivers, past the old mill and the orchard "
         "where the apples grew red and round. ")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("PURPLE_SAVES_DIR", str(tmp_path / "saves"))


async def _write(text=""):
    app = make_app()
    app.set_room_off("write", False)
    app.action_switch_room("write")
    await type_text(app, text)
    return app


def test_words_wrap_whole_and_enter_breaks_the_line():
    text = "a" * 10 + " " + "b" * 55 + "\nhi"
    assert [text[s:e] for s, e, _ in wrap(text)] == ["a" * 10 + " ", "b" * 55, "hi"]
    assert [soft for *_, soft in wrap(text)] == [True, False, False]
    assert all(e - s <= COLS + 1 for s, e, _ in wrap(STORY * 20))
    long = "x" * (COLS + 5)
    assert [long[s:e] for s, e, _ in wrap(long)] == ["x" * COLS, "x" * 5]


def test_typing_inserts_at_the_caret_and_backspace_takes_the_letter_before_it():
    async def go():
        app = await _write("cat")
        await press(app, "left")
        await press(app, "left")
        await type_text(app, "o")
        await press(app, "space")
        await press(app, "enter")
        assert app.room.plain_text() == "co \nat"
        await press(app, "backspace")
        await press(app, "backspace")
        assert app.room.plain_text() == "coat"
    run(go())


def test_holding_backspace_takes_letters_then_whole_words(monkeypatch):
    from purple_tui.canvas.rooms import write_room
    clock = [100.0]
    monkeypatch.setattr(write_room.time, "monotonic", lambda: clock[0])

    async def go():
        app = await _write("The cat\nsat on  the mat")
        await press(app, "backspace")
        await press(app, "backspace", is_repeat=True)
        assert app.room.plain_text() == "The cat\nsat on  the m"
        clock[0] += 1.0
        for left in ("The cat\nsat on  the ", "The cat\nsat on  ", "The cat\nsat ",
                     "The cat\n", "The cat", "The "):
            await press(app, "backspace", is_repeat=True)
            await press(app, "backspace", is_repeat=True)
            assert app.room.plain_text() == left
            clock[0] += 0.2
    run(go())


def test_shift_and_arrows_select_and_typing_or_backspace_replaces_it():
    async def go():
        app = await _write("big red dog")
        for _ in range(3):
            await press(app, "left", shift_held=True)
        assert app.room.selection() == (8, 11)
        await type_text(app, "cat")
        assert (app.room.plain_text(), app.room.selection()) == ("big red cat", None)
        await press(app, "home")
        await press(app, "right", shift_held=True)
        await press(app, "right", shift_held=True)
        await press(app, "right", shift_held=True)
        await press(app, "right", shift_held=True)
        await press(app, "backspace")
        assert app.room.plain_text() == "red cat"
        await press(app, "end")
        await press(app, "left", shift_held=True)
        await press(app, "left")
        assert app.room.field.cursor == 6 and app.room.selection() is None
    run(go())


def test_ctrl_or_cmd_cut_copy_paste_and_select_all():
    async def go():
        app = await _write("one two")
        app.room.field.cursor = 3
        await press(app, "left", shift_held=True, ctrl_held=True)
        await press(app, "c", ctrl_held=True)
        await press(app, "end")
        await press(app, "v", cmd_held=True)
        assert app.room.plain_text() == "one twoone"
        await press(app, "a", cmd_held=True)
        await press(app, "x", ctrl_held=True)
        assert app.room.plain_text() == ""
        await press(app, "v", ctrl_held=True)
        await press(app, "v", ctrl_held=True)
        assert app.room.plain_text() == "one twoone" * 2
        app.action_switch_room("play")
        await press(app, "v", ctrl_held=True)
        assert app.room.field.value == ""
    run(go())


def test_jump_keys_go_to_the_top_bottom_and_a_screen_at_a_time():
    async def go():
        app = await _write((STORY + "\n") * 30)
        app._draw()
        f, rows = app.room.field, app.room.rows
        await press(app, "up", ctrl_held=True)
        assert f.cursor == 0
        await press(app, "page_down")
        assert line_of(wrap(f.value), f.cursor) == rows
        await press(app, "page_up")
        assert f.cursor == 0
        await press(app, "down", ctrl_held=True)
        assert f.cursor == len(f.value)
    run(go())


def test_write_takes_math_keys_as_typed_while_play_still_turns_them_into_math():
    async def go():
        app = await _write("and/or 2=2 *")
        assert app.room.plain_text() == "and/or 2=2 *"
        app.action_switch_room("play")
        await type_text(app, "2=2")
        assert app.room.field.value == "2 + 2"
    run(go())


def test_only_a_canvas_keyboard_reports_cmd_and_the_jump_keys():
    from purple_tui.input import KeyCode, RawKeyEvent
    from purple_tui.keyboard import CharacterAction, ControlAction, KeyboardStateMachine

    def keys(edit_keys):
        m = KeyboardStateMachine(edit_keys=edit_keys)
        out = []
        for code, down in ((KeyCode.KEY_LEFTMETA, True), (KeyCode.KEY_C, True), (KeyCode.KEY_LEFTMETA, False),
                           (KeyCode.KEY_HOME, True)):
            out += m.process(RawKeyEvent(keycode=code, is_down=down, timestamp=100.0))
        return out
    char, home = keys(True)
    assert isinstance(char, CharacterAction) and char.cmd_held
    assert isinstance(home, ControlAction) and home.action == "home"
    [char] = keys(False)
    assert not char.cmd_held


def test_up_and_down_move_by_wrapped_line_and_keep_the_column():
    async def go():
        app = await _write(STORY * 2)
        f, lines = app.room.field, wrap(STORY * 2)
        f.cursor, col = lines[1][0] + 30, 30
        await press(app, "up")
        assert line_of(lines, f.cursor) == 0 and f.cursor - lines[0][0] == col
        await press(app, "down")
        await press(app, "down")
        assert line_of(lines, f.cursor) == 2
        f.cursor = lines[0][1]
        await press(app, "left")
        await press(app, "down")
        await press(app, "up")
        assert f.cursor == lines[0][1] - 1
        for _ in range(len(lines) + 1):
            await press(app, "down")
        assert f.cursor == len(f.value)
    run(go())


def test_the_page_scrolls_to_keep_the_caret_in_view():
    assert keep_in_view(0, 30, 10, 40) == 21
    assert keep_in_view(21, 5, 10, 40) == 5
    assert keep_in_view(30, 3, 10, 4) == 0

    async def go():
        app = await _write()
        app.room.field.set((STORY + "\n") * 40)
        app._draw()
        n = len(wrap(app.room.field.value))
        assert app.room.top > 0 and line_of(wrap(app.room.field.value), app.room.field.cursor) == n - 1
        for _ in range(n):
            await press(app, "up")
        app._draw()
        assert app.room.top == 0
    run(go())


def test_time_travel_and_clear_round_trip_the_text_and_caret():
    async def go():
        app = await _write("hello")
        await press(app, "left")
        state = app.room_state("write")
        assert state["text"] == "hello" and state["caret"] == 4
        app._start_fresh("write")
        assert app.room.plain_text() == ""
        app.apply_room_state("write", state)
        assert (app.room.field.value, app.room.field.cursor) == ("hello", 4)
    run(go())


def test_a_save_opens_back_with_its_text_and_caret():
    async def go():
        app = await _write("Dear Grandma,")
        await press(app, "enter")
        await type_text(app, "Thank you!")
        await press(app, "left")
        app.save_room()
        [save] = saves.list_saves("write")
        app._start_fresh("write")
        app.open_save(save)
        assert (app.room.field.value, app.room.field.cursor) == ("Dear Grandma,\nThank you!", 23)
        assert app.save_artwork(save, on_screen=True) is not None
    run(go())


def test_a_long_story_prints_every_page_and_an_empty_one_prints_none():
    async def go():
        app = await _write()
        assert paper.pages(app.room, app.g) is None
        await type_text(app, "   ")
        assert paper.pages(app.room, app.g) is None
        app.room.field.set((STORY + "\n\n") * 30)
        made, landscape = paper.pages(app.room, app.g)
        assert not landscape and len(made) > 1 and {p.get_size() for p in made} == {paper.page_size(False)}
        app.room.field.set("One line.")
        assert len(paper.pages(app.room, app.g)[0]) == 1
    run(go())


def test_copying_to_usb_brings_a_txt_beside_the_picture(tmp_path):
    async def go():
        from purple_tui.canvas.rooms.save_export import FOLDER, export_saves
        app = await _write("A story about a cat.")
        app.save_room()
        app.action_switch_room("art")
        await type_text(app, "q")
        app.save_room()
        dest = tmp_path / "stick"

        def export(save):
            return app.save_artwork(save), app.save_text(save)
        assert export_saves(dest, export) == 2
        [txt] = (dest / FOLDER / "Write").glob("*.txt")
        assert txt.read_text(encoding="utf-8") == "A story about a cat."
        assert txt.with_suffix(".png").exists()
        assert not list((dest / FOLDER / "Art").glob("*.txt"))
    run(go())


def test_write_starts_off_on_new_and_upgraded_installs_until_a_parent_turns_it_on():
    async def go():
        app = make_app()
        assert "write" not in app.kid_rooms
        app.action_switch_room("write")
        assert app.active_room != "write"
        app.set_room_off("write", False)
        assert app.kid_rooms[-1] == "write" and [r.name for r in RoomPicker(app).options][-1] == "write"
        assert make_app().kid_rooms[-1] == "write"
        app.set_room_off("write", True)
        assert "write" not in make_app().kid_rooms
    run(go())
    settings.SETTINGS_FILE.write_text(json.dumps({"rooms_off": []}))
    assert run(_kid_rooms()) == ["art", "music", "play", "blocks"]


async def _kid_rooms():
    return make_app().kid_rooms


def test_mashing_keys_never_raises_or_overflows():
    rng = random.Random(156)
    keys = list("abcxyz.,!?' 0189") + ["enter", "space", "backspace", "tab", "up", "down", "left", "right", "home", "end", "page_up", "page_down"]

    async def go():
        app = await _write()
        for _ in range(800):
            await press(app, rng.choice(keys), is_repeat=rng.random() < 0.2)
        app._draw()
        app.room.field.set("x" * MAX_CHARS)
        await type_text(app, "more")
        assert len(app.room.plain_text()) == MAX_CHARS
        app._draw()
    run(go())


@pytest.mark.parametrize("room", ["art", "music", "play", "blocks"])
def test_other_rooms_ignore_editing_shortcuts_and_take_ctrl_arrows_as_arrows(room):
    async def go():
        app, plain = make_app(), make_app()
        for a in (app, plain):
            a.action_switch_room(room)
            await type_text(a, "ab")
        before = app.room_state(room)
        for key in ("a", "c", "x", "v"):
            await press(app, key, ctrl_held=True)
            await press(app, key, cmd_held=True)
        for key in ("home", "end", "page_up", "page_down"):
            await press(app, key)
        assert app.room_state(room) == before
        for a, kw in ((app, {"ctrl_held": True}), (plain, {})):
            await press(a, "right", **kw)
            await press(a, "down", **kw)
        assert app.room_state(room) == plain.room_state(room)
    run(go())
