"""The Esc menu: rooms on top, Volume and the printer in the corners above them, the room's own tools below."""

from purplecomputer.harness import make_app, press, run
from purplecomputer.room_picker import HERE, ROWS, VOLUME, RoomPicker


def test_arrows_cross_between_rooms_tools_and_volume():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        app._show_room_picker()
        picker = app.top
        assert isinstance(picker, RoomPicker) and picker.tools[:2] == ["code", "colors"]
        await press(app, "down")
        assert picker.row == HERE and picker.tools[picker.col] in ("code", "colors")
        await press(app, "up")
        await press(app, "up")
        assert picker.row == VOLUME
        await press(app, "down")
        assert (picker.row, picker.options[picker.col].name) == (ROWS, "blocks")
    run(go())


def test_play_has_no_code_or_colors_tools():
    async def go():
        app = make_app()
        app.action_switch_room("play")
        app._show_room_picker()
        assert app.top.tools == ["time_travel", "save", "open", "clear"]
    run(go())


def test_the_code_card_says_when_code_is_on():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        await press(app, "escape")
        assert app.top._tool("code")[1] == "Code"
        await press(app, "space")
        assert app.room.code_panel is not None
        await press(app, "escape")
        assert app.top._tool("code")[1:] == ("Code is on", "Space", False, True)
        app._draw()
        await press(app, "space")
        assert app.room.code_panel is None
    run(go())


def test_left_and_right_wrap_around_the_rooms():
    async def go():
        app = make_app()
        app.action_switch_room(app.kid_rooms[0])
        app._show_room_picker()
        picker = app.top
        assert (picker.row, picker.col) == (ROWS, 0)
        await press(app, "left")
        assert picker.col == len(picker.options) - 1
        await press(app, "right")
        assert picker.col == 0
    run(go())
