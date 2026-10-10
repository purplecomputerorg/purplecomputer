"""Backslash opens the color wheel in Art and Blocks: arrows move the dot and
the brush follows it, Space keeps the color, Esc puts the old one back, any
other key keeps it and reaches the room, and a wheel color paints like a
letter color. Also Art's eraser: holding Backspace makes arrows clear a trail."""

from purple_tui.canvas.color_wheel import ColorWheel, _cell, _spot, wheel_color
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.keyboard import ControlAction
from purple_tui.palette import get_key_color


def _room(name):
    app = make_app()
    app.action_switch_room(name)
    return app, app.rooms[name]


def test_arrows_move_the_brush_and_space_keeps_it():
    async def go():
        for name in ("art", "blocks"):
            app, room = _room(name)
            await press(app, "\\")
            assert isinstance(app.top, ColorWheel)
            await press(app, "up")
            await press(app, "up")
            picked = room.brush_color
            await press(app, "space")
            assert app.top is None and room.brush_color == picked
    run(go())


def test_escape_puts_the_old_color_back():
    async def go():
        app, room = _room("art")
        await press(app, "r")
        await press(app, "\\")
        await press(app, "down")
        assert room.brush_color != get_key_color("r")
        await press(app, "escape")
        assert app.top is None and room.brush_color == get_key_color("r")
        assert app._overlays == []
    run(go())


def test_a_letter_closes_the_wheel_and_paints():
    async def go():
        app, room = _room("art")
        await press(app, "\\")
        await press(app, "g")
        assert app.top is None and room.brush_color == get_key_color("g")
        assert len(room._painted_positions) == 1
    run(go())


def test_a_wheel_color_builds_like_a_letter_color():
    async def go():
        app, room = _room("blocks")
        room._x, room._z = 5, 5
        await press(app, "\\")
        await press(app, "left")
        await press(app, "enter")
        await press(app, "space")
        assert room._blocks == {(5, 5, 0): room.brush_color}
    run(go())


def test_the_dot_starts_on_the_brush_color():
    for hue, ring in ((0, 0), (3, 2), (20, 6)):
        assert wheel_color(*_cell(*_spot(wheel_color(hue, ring)))) == wheel_color(hue, ring)


def test_backslash_writes_in_abc_and_does_nothing_in_littles():
    async def go():
        app, room = _room("art")
        await press(app, "tab")
        await press(app, "\\")
        assert app.top is None and room._grid[(0, 0)][0] == "\\"
        app, room = _room("blocks")
        app._littles_mode = True
        await press(app, "\\")
        assert app.top is None
    run(go())


def test_held_backspace_erases_along_the_arrows():
    async def go():
        app, room = _room("art")
        await press(app, "space")
        for _ in range(5):
            await press(app, "right")
        await press(app, "space")
        assert len(room._painted_positions) == 6
        await app._dispatch_keyboard_action(ControlAction(action="backspace"))
        assert room._erasing and room._cursor_x == 4
        await press(app, "left")
        await press(app, "left")
        await app._dispatch_keyboard_action(ControlAction(action="backspace", is_down=False))
        assert not room._erasing
        assert sorted(x for x, _ in room._painted_positions) == [0, 1, 5]
        await press(app, "left")
        assert sorted(x for x, _ in room._painted_positions) == [0, 1, 5]
    run(go())
