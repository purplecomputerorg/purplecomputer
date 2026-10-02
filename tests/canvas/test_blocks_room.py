"""Blocks room: letters stack sticker-colored blocks on the cursor's column,
the pen lays a trail, Tab floats blocks at the last height (mixing like paint
when they land on a block), Backspace takes the top block off, and the Esc
picker reaches the room with 4."""

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.blocks_room import HEIGHT, WIDTH
from purple_tui.color_mixing import mix_colors_paint
from purple_tui.palette import get_key_color


def _blocks():
    app = make_app()
    app.action_switch_room("blocks")
    room = app.rooms["blocks"]
    room._x, room._z = 5, 5
    return app, room


def test_letters_stack_on_the_cursor_column():
    async def go():
        app, room = _blocks()
        await type_text(app, "rrg")
        assert room._blocks == {(5, 5, 0): get_key_color("r"), (5, 5, 1): get_key_color("r"),
                                (5, 5, 2): get_key_color("g")}
        await press(app, "backspace")
        assert (5, 5, 2) not in room._blocks and len(room._blocks) == 2
    run(go())


def test_column_stops_at_the_height_limit():
    async def go():
        app, room = _blocks()
        await type_text(app, "a" * (HEIGHT + 3))
        assert len(room._blocks) == HEIGHT
    run(go())


def test_pen_lays_a_trail_and_stops_at_the_edge():
    async def go():
        app, room = _blocks()
        await press(app, "z")
        await press(app, "space")
        for _ in range(WIDTH):
            await press(app, "right")
        assert room._x == WIDTH - 1
        assert all((x, 5, 0) in room._blocks for x in range(5, WIDTH))
        assert (5, 5, 1) in room._blocks  # pen down drops one on the first block
    run(go())


def test_float_keeps_the_last_height_and_mixes_paint():
    async def go():
        app, room = _blocks()
        await type_text(app, "aaa")
        await press(app, "tab")
        await press(app, "right")
        await press(app, "b")
        assert (6, 5, 2) in room._blocks and (6, 5, 0) not in room._blocks
        await press(app, "a")
        assert room._blocks[(6, 5, 2)] == mix_colors_paint([get_key_color("b"), get_key_color("a")])
    run(go())


def test_shift_picks_a_color_without_dropping():
    async def go():
        app, room = _blocks()
        await press(app, "Q", shift_held=True)
        assert not room._blocks and room._color == get_key_color("q")
    run(go())


def test_timeline_round_trip():
    async def go():
        app, room = _blocks()
        await type_text(app, "qwe")
        await press(app, "tab")
        state = room.timeline_state()
        room.clear()
        assert not room.has_content() and not room._floating
        room.restore_timeline_state(state)
        assert len(room._blocks) == 3 and room._floating and (room._x, room._z) == (5, 5)
    run(go())


def test_picker_number_four_opens_blocks():
    async def go():
        app = make_app()
        app._show_room_picker()
        await press(app, "4")
        assert app.active_room == "blocks"
    run(go())
