"""Backslash opens the color wheel in Art and Blocks: arrows move the dot and
the brush follows it, Space keeps the color, Esc puts the old one back, any
other key keeps it and reaches the room, the wheel reopens on the last color
kept in that room, a wheel color paints like a letter color, the Esc menu
opens it too, and in ABC it colors the letters typed next. Also Art's eraser: holding Backspace makes arrows clear a trail."""

from purple_tui.canvas.color_wheel import ColorWheel, _cell, _spot, wheel_color
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.ui import AUTO
from purple_tui.keyboard import ControlAction
from purple_tui import palette as P
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


def test_the_wheel_reopens_on_the_last_kept_color_per_room():
    async def go():
        app, art = _room("art")
        await press(app, "\\")
        await press(app, "up")
        await press(app, "left")
        picked = art.brush_color
        await press(app, "g")
        assert art.brush_color == get_key_color("g")
        await press(app, "\\")
        assert art.brush_color == picked
        await press(app, "space")
        app.action_switch_room("blocks")
        blocks = app.rooms["blocks"]
        was = blocks.brush_color
        await press(app, "\\")
        assert blocks.brush_color == was
    run(go())


def test_escape_does_not_remember_the_color():
    async def go():
        app, room = _room("art")
        await press(app, "r")
        await press(app, "\\")
        await press(app, "down")
        await press(app, "escape")
        await press(app, "\\")
        assert room.brush_color == get_key_color("r")
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


def test_backslash_does_nothing_in_littles():
    async def go():
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


def test_the_esc_menu_opens_the_wheel():
    async def go():
        for name, keys, offered in (("art", [], True), ("blocks", [], True), ("art", ["tab"], True)):
            app, room = _room(name)
            for k in keys:
                await press(app, k)
            await press(app, "escape")
            assert ("colors" in app.top.tools) == offered
            await press(app, "\\")
            assert isinstance(app.top, ColorWheel) == offered
    run(go())


def test_in_abc_the_wheel_colors_the_letters():
    async def go():
        app, room = _room("art")
        await press(app, "tab")
        await press(app, "\\")
        await press(app, "down")
        await press(app, "down")
        ink = room.brush_color
        assert ink != P.TEXT
        await press(app, "space")
        await press(app, "h")
        await press(app, "|")
        cells = sorted((x, ch, fg) for (x, _), (ch, fg, _) in room._grid.items())
        assert [(ch, fg) for _, ch, fg in cells] == [("h", ink), ("|", ink)]
    run(go())


def test_in_abc_the_center_goes_back_to_auto_letters():
    async def go():
        app, room = _room("art")
        await press(app, "tab")
        assert room.brush_color == AUTO
        await press(app, "\\")
        await press(app, "down")
        await press(app, "down")
        await press(app, "space")
        assert room.brush_color != AUTO
        await press(app, "\\")
        await press(app, "up")
        await press(app, "up")
        await press(app, "space")
        assert room.brush_color == AUTO and room._ink is None
        await press(app, "h")
        assert [fg for ch, fg, _ in room._grid.values()] == [P.TEXT]
    run(go())


def test_in_paint_the_center_stays_white():
    async def go():
        app, room = _room("art")
        await press(app, "\\")
        app.top._x = app.top._y = 0.0
        app.top._move([])
        assert room.brush_color == "#FFFFFF"
    run(go())
