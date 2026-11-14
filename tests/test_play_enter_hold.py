"""Holding Enter in Play runs the line once instead of alternating run and recall."""

from purple_tui.canvas.harness import make_app, press, run, type_text


def test_held_enter_runs_once():
    async def go():
        app = make_app()
        app.action_switch_room("play")
        room = app.rooms["play"]
        await type_text(app, "2+3")
        await press(app, "enter")
        ran = len(room.history)
        for _ in range(6):
            await press(app, "enter", is_repeat=True)
        assert len(room.history) == ran
        assert room.field.value == ""
    run(go())
