"""The Esc menu: rooms on top, Volume in the corner above them, the room's own tools below."""

from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.room_picker import HERE, ROWS, VOLUME, RoomPicker


def test_arrows_cross_between_rooms_tools_and_volume():
    async def go():
        app = make_app()
        app.action_switch_room("art")
        app._show_room_picker()
        picker = app.top
        assert isinstance(picker, RoomPicker) and picker.tools[:2] == ["code", "colors"]
        await press(app, "down")
        assert picker.row == HERE and picker.tools[picker.col] in ("save", "open")
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
        assert app.top.tools == ["time_travel", "save", "open", "print", "clear"]
    run(go())
