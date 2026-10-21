"""Art's Backspace: a tap takes back a cell's last stamp (the paint under a mix or a letter comes back),
a hold wipes cells clean at Time Travel's slow-then-faster pace, and backing off the start of a line
lands on the last thing on the line above."""

from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.rooms import art_room
from purple_tui.canvas.rooms.art_room import COLS
from purple_tui.keyboard import ControlAction


def _art():
    app = make_app()
    app.action_switch_room("art")
    return app, app.rooms["art"]


def test_a_tap_takes_back_one_layer():
    async def go():
        app, room = _art()
        await press(app, "r")
        red = room._grid[(0, 0)]
        room._cursor_x = 0
        await press(app, "f")
        assert room._grid[(0, 0)] != red, "painting over red mixes"
        await press(app, "backspace")
        assert room._grid[(0, 0)] == red and (0, 0) in room._painted_positions
        room._cursor_x = 1
        await press(app, "backspace")
        assert (0, 0) not in room._grid and not room._painted_positions
    run(go())


def test_backspacing_a_letter_leaves_the_paint_under_it():
    async def go():
        app, room = _art()
        await press(app, "r")
        painted = room._grid[(0, 0)]
        room._cursor_x = 0
        await press(app, "tab")
        await press(app, "h")
        await press(app, "backspace")
        assert room._grid[(0, 0)] == painted
    run(go())


def test_backing_off_a_line_lands_on_its_last_thing():
    async def go():
        app, room = _art()
        await press(app, "tab")
        for ch in "cat":
            await press(app, ch)
        await press(app, "enter")
        assert (room._cursor_x, room._cursor_y) == (0, 1)
        await press(app, "backspace")
        assert (room._cursor_x, room._cursor_y) == (2, 0)
        assert sorted(room._grid) == [(0, 0), (1, 0)]
    run(go())


def test_a_held_backspace_starts_slow_then_speeds_up_and_wipes_clean(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(art_room.time, "monotonic", lambda: clock[0])

    async def go():
        app, room = _art()
        for y in range(3):
            for x in range(COLS):
                room._cursor_x, room._cursor_y = x, y
                for color in ("#FF0000", "#0000FF"):    # two layers each, so a tap alone wouldn't clear a cell
                    room._last_key_color = color
                    room._paint_at_cursor()
        room._cursor_x, room._cursor_y = 0, 3
        held = lambda: app._dispatch_keyboard_action(ControlAction(action="backspace", is_repeat=True))
        await app._dispatch_keyboard_action(ControlAction(action="backspace"))
        await held()
        assert (COLS - 1, 2) not in room._grid, "a hold wipes the tapped cell's layers too"
        for _ in range(10):                 # a third of a second: only a couple of cells
            clock[0] += 0.033
            await held()
        assert len(room._grid) >= 3 * COLS - 5
        for _ in range(90):                 # three more seconds: all three lines
            clock[0] += 0.033
            await held()
        assert not room._grid
    run(go())
