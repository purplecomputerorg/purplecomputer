"""The code panel: the echo that writes code for what was done by hand, the
recipe cards under the line, and Blocks code."""

import asyncio

import pytest

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.panels import RECIPES, CodePanel, Echo, color_name
from purple_tui.keyboard import NavigationAction
from purple_tui.palette import get_key_color

KEYS = {get_key_color(k).lower(): k for k in "abcdefghijklmnopqrstuvwxyz"}


async def _room(name):
    app = make_app()
    app.action_switch_room(name)
    return app, app.rooms[name]


async def _run_code(app, room, code):
    await room.run_code([code])
    await asyncio.sleep(0)


def _rows(cells: dict) -> list:
    xs, ys = [x for x, _ in cells], [y for _, y in cells]
    return ["".join(cells.get((x, y), ".") for x in range(min(xs), max(xs) + 1)) for y in range(min(ys), max(ys) + 1)]


# ---------------------------------------------------------------- echo
def test_echo_groups_steps_letters_and_colors():
    e = Echo()
    e.color("#ED1C24")
    for _ in range(3):
        e.step("right")
    e.color("#ED1C24")
    e.step("down")
    e.letter("left", "h")
    e.letter("left", "i")
    assert e.line() == "red right 3 down 1 left hi"
    assert e.take() == "red right 3 down 1 left hi"
    assert e.take() == ""


def test_echo_leaves_out_separators_and_starts_over_after_a_pause(monkeypatch):
    e = Echo(pause=2.0)
    clock = iter([10.0, 10.5, 11.0, 20.0])
    monkeypatch.setattr("purple_tui.canvas.panels.time.monotonic", lambda: next(clock))
    for ch in "a,s":
        e.letter("", ch)
    e.letter("", "q")
    assert e.fresh == "as" and e.line() == "q"


def test_color_name_finds_the_nearest_plain_word():
    assert color_name("#ED1C24") == "red"
    assert color_name("#1F75FE") == "blue"
    assert color_name(get_key_color("e")).endswith("red")


def test_art_echo_writes_letters_then_opens_holding_them():
    async def go():
        app, art = await _room("art")
        await type_text(app, "hi")
        art.open_code_panel()
        assert art.code_panel.field.value == "right hi"
        assert app.code_lines("art") == []          # only what runs is kept
    run(go())


def test_art_echo_writes_a_pen_trail_with_its_color():
    async def go():
        app, art = await _room("art")
        art.set_brush_color("#1F75FE")
        art._set_pen(True)
        for _ in range(4):
            await press(app, "right")
        await press(app, "down")
        art.open_code_panel()
        assert art.code_panel.field.value == "blue right 4 down 1"
    run(go())


def test_typing_replaces_the_echo_but_editing_keeps_it():
    async def go():
        app, _ = await _room("art")
        panel = CodePanel(app, "art", "right hi")
        await panel.handle(NavigationAction(direction="left"))
        await type_text_into(panel, "x")
        assert panel.field.value == "right hxi"
        fresh = CodePanel(app, "art", "right hi")
        await type_text_into(fresh, "red")
        assert fresh.field.value == "red"
    run(go())


async def type_text_into(panel, text):
    from purple_tui.keyboard import CharacterAction
    for ch in text:
        await panel.handle(CharacterAction(char=ch))


def test_music_echo_writes_notes_and_instrument():
    async def go():
        app, music = await _room("music")
        await type_text(app, "qwer")
        music.open_code_panel()
        assert music.code_panel.field.value == "qwer"
    run(go())


def test_blocks_echo_writes_typing_and_space():
    async def go():
        app, blocks = await _room("blocks")
        await type_text(app, "ab")
        await press(app, "enter")       # turns typing upward, ending the stroke
        blocks.set_brush_color("#48D370")
        blocks._control("space")
        blocks._control("space")
        assert blocks.echo.fresh == "right ab"
        blocks.open_code_panel()
        assert blocks.code_panel.field.value == "green up 2"
    run(go())


# ---------------------------------------------------------------- cards
def test_down_steps_into_the_cards_and_enter_runs_one_and_keeps_it():
    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        panel = art.code_panel
        await press(app, "down")
        await press(app, "right")
        assert panel.card == 1 and panel.field.value == RECIPES["art"][1][0]
        await press(app, "enter")
        await asyncio.sleep(1)
        assert panel.card is None
        assert panel.field.value == RECIPES["art"][1][0]
        assert app.code_lines("art") == [RECIPES["art"][1][0]]
        assert art.has_content()
    run(go())


def test_up_leaves_the_cards_and_typing_edits_the_recipe():
    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        panel = art.code_panel
        await press(app, "down")
        await press(app, "up")
        assert panel.card is None and panel.field.value == RECIPES["art"][0][0]
        await press(app, "down")
        await press(app, "backspace")
        assert panel.card is None and panel.field.value == RECIPES["art"][0][0][:-1]
    run(go())


def test_tab_on_an_empty_code_line_does_not_crash():
    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        paint = art.paint_mode
        await press(app, "tab")
        assert art.paint_mode != paint      # falls through to the room
    run(go())


@pytest.mark.parametrize("code, color, rows", RECIPES["art"])
def test_art_recipe_pictures_match_what_they_paint(code, color, rows):
    async def go():
        app, art = await _room("art")
        art._cursor_x, art._cursor_y = 20, 10
        await _run_code(app, art, code)
        cells = {p: KEYS.get(c[2].lower(), "#") for p, c in art._grid.items() if art._painted(c)}
        assert _rows(cells) == rows
    run(go())


@pytest.mark.parametrize("code, color, rows", RECIPES["blocks"])
def test_blocks_recipe_pictures_match_what_they_build(code, color, rows):
    async def go():
        app, blocks = await _room("blocks")
        blocks._x, blocks._z = 5, 5
        await _run_code(app, blocks, code)
        cells = {(x, -y): KEYS.get(c.lower(), "#") for (x, z, y), c in blocks._blocks.items()}
        assert _rows(cells) == rows
    run(go())


# ---------------------------------------------------------------- blocks code
def test_blocks_code_builds_a_tower_then_a_row_from_its_top():
    async def go():
        app, blocks = await _room("blocks")
        x, z = blocks._x, blocks._z
        await _run_code(app, blocks, "red up 3 blue right 2")
        assert {p for p, c in blocks._blocks.items() if c == "#ED1C24"} == {(x, z, 0), (x, z, 1), (x, z, 2)}
        assert {p for p, c in blocks._blocks.items() if c == "#1F75FE"} == {(x, z, 3), (x + 1, z, 3)}
    run(go())


def test_blocks_code_back_and_front_go_in_depth():
    async def go():
        app, blocks = await _room("blocks")
        x, z = blocks._x, blocks._z
        await _run_code(app, blocks, "back 2")
        assert set(blocks._blocks) == {(x, z, 0), (x, z + 1, 0)}
    run(go())


def test_blocks_hold_space_opens_code_and_tab_still_turns():
    async def go():
        app, blocks = await _room("blocks")
        await press(app, "space", hold=1.0)
        assert blocks.code_panel is not None and app._panel is blocks.code_panel
        await press(app, "tab")
        assert blocks._back
    run(go())


def test_color_name_keeps_grays_gray():
    assert [color_name(c) for c in ("#F5F5F5", "#808080", "#1A1A1A")] == ["white", "gray", "black"]
