import asyncio
import time

import pytest

from purple_tui.canvas.app import LETTER_HOLD
from purple_tui.canvas.color_recipe import example, hint_row, partner
from purple_tui.canvas.harness import make_app, run
from purple_tui.color_mixing import mix_colors_paint
from purple_tui.input import KeyCode, RawKeyEvent
from purple_tui.palette import get_key_color


async def _key(app, code, down):
    await app._handle_raw_key_event(RawKeyEvent(keycode=code, is_down=down, timestamp=time.monotonic()))


async def _tap(app, code):
    await _key(app, code, True)
    await _key(app, code, False)


def test_example_mixes_the_brush_key_with_the_next_hue_row():
    assert [partner(k) for k in "rfc1"] == ["f", "v", "e", "r"]
    terms, result = example("r")
    assert terms == [("r", get_key_color("r")), ("f", get_key_color("f"))]
    assert result == mix_colors_paint([get_key_color("r"), get_key_color("f")])
    assert example("")[0][0][0] == "f"     # a wheel color has no key to hold


def test_held_letter_shows_only_after_the_hold_and_clears_on_release():
    async def go():
        app = make_app()
        await _key(app, KeyCode.KEY_R, True)
        assert app.held_letter is None
        await asyncio.sleep(LETTER_HOLD + 0.1)
        assert app.held_letter == "r"
        await _key(app, KeyCode.KEY_R, False)
        assert app.held_letter is None
    run(go())


def _hint(room):
    return hint_row(getattr(room, "_last_key_char", getattr(room, "_key", "")), room._mixed)


def _room(name):
    app = make_app()
    app.action_switch_room(name)
    return app, app.rooms[name]


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_hint_row_shows_the_keys_just_mixed_until_a_plain_key(name):
    from purple_tui.canvas.harness import press

    async def go():
        app, room = _room(name)
        assert _hint(room)["lead"] == "Hold"
        await press(app, "b")
        await press(app, "g", char_held="b")
        await press(app, "r", char_held="g")
        hint = _hint(room)
        assert hint["lead"] == "You mixed" and hint["result"] == room.brush_color
        assert [k for k, _ in hint["terms"]] == ["b", "g", "r"]
        await press(app, "y", char_held="r")
        assert [k for k, _ in _hint(room)["terms"]] == ["", "y"]   # the first three fold into one swatch
        await press(app, "q")
        assert _hint(room)["lead"] == "Hold"
    run(go())


def test_painting_over_paint_shows_what_was_there_first():
    from purple_tui.canvas.harness import press

    async def go():
        app, room = _room("art")
        await press(app, "b")
        room._cursor_x = 0
        await press(app, "r")
        blue, red = get_key_color("b"), get_key_color("r")
        mixed = mix_colors_paint([blue, red])
        assert _hint(room)["terms"] == [("", blue), ("r", red)] and _hint(room)["result"] == mixed == room._grid[(0, 0)][2]
    run(go())


def test_dropping_a_block_onto_one_shows_its_color_first():
    from purple_tui.canvas.harness import press
    from purple_tui.canvas.rooms.blocks_room import HEIGHT

    async def go():
        app, room = _room("blocks")
        room._blocks.update({(room._x, room._z, y): "#ff0000" for y in range(HEIGHT)})
        await press(app, "b")
        assert [k for k, _ in _hint(room)["terms"]] == ["", "b"] and _hint(room)["terms"][0][1] == "#ff0000"
    run(go())
