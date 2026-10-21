"""Art's Backspace: a tap erases the square under the brush, or right after typing or stamping, the
one before it. Backing off the start of a line lands on the last thing on the line above. Held, it
takes squares for a second, then whole lines, each fading out first; letting go mid-fade brings the line back."""

import pytest

from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.rooms import art_room
from purple_tui.canvas.rooms.art_room import COLS, LINE_FADE_S, LINES_AFTER
from purple_tui.keyboard import ControlAction


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(art_room.time, "monotonic", lambda: now[0])
    return now


def _art(rows=0):
    app = make_app()
    app.action_switch_room("art")
    room = app.rooms["art"]
    for y in range(rows):
        for x in range(COLS):
            room._cursor_x, room._cursor_y = x, y
            room._paint_at_cursor()
    room._cursor_x, room._cursor_y = 0, rows
    return app, room


async def _down(app, repeat=True):
    await app._dispatch_keyboard_action(ControlAction(action="backspace", is_repeat=repeat))


def test_a_tap_erases_the_whole_square():
    async def go():
        app, room = _art()
        await press(app, "r")
        room._cursor_x = 0
        await press(app, "f")
        await press(app, "backspace")
        assert (0, 0) not in room._grid and not room._painted_positions
    run(go())


def test_a_tap_on_a_painted_square_erases_it_in_place():
    async def go():
        app, room = _art(rows=1)
        room._cursor_x, room._cursor_y = COLS - 1, 0
        await press(app, "backspace")
        assert (COLS - 1, 0) not in room._grid and (COLS - 2, 0) in room._grid
        assert room._cursor_x == COLS - 1
    run(go())


def test_after_typing_on_paint_a_tap_takes_the_letter_not_the_paint_ahead():
    async def go():
        app, room = _art(rows=1)
        room._cursor_x, room._cursor_y = 3, 0
        await press(app, "tab")
        await press(app, "a")
        await press(app, "backspace")
        assert (3, 0) not in room._grid and (4, 0) in room._grid
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


def test_a_held_backspace_takes_squares_then_fades_out_whole_lines(clock):
    async def go():
        app, room = _art(rows=3)
        await _down(app, repeat=False)
        for _ in range(5):
            clock[0] += 0.1
            await _down(app)
        assert len(room._grid) == 3 * COLS - 6, "squares one at a time for the first second"
        clock[0] += LINES_AFTER
        await _down(app)
        assert room._fade["row"] == 2 and len(room._grid) == 3 * COLS - 6
        clock[0] += LINE_FADE_S
        room._step_fade()
        assert len(room._grid) == 2 * COLS and room._fade["row"] == 1
        assert (room._cursor_x, room._cursor_y) == (0, 2)
        clock[0] += LINE_FADE_S / 2
        room._step_fade()
        await app._dispatch_keyboard_action(ControlAction(action="backspace", is_down=False))
        assert room._fade is None and len(room._grid) == 2 * COLS, "letting go mid-fade keeps the line"
    run(go())


def test_held_lines_skip_empty_ones_and_stop_when_nothing_is_left(clock):
    async def go():
        app, room = _art(rows=1)
        room._cursor_x, room._cursor_y = 0, 5
        await _down(app, repeat=False)
        clock[0] += LINES_AFTER
        await _down(app)
        assert room._fade["row"] == 0
        clock[0] += LINE_FADE_S
        room._step_fade()
        assert not room._grid and room._fade is None and room._fade_timer is None
    run(go())
