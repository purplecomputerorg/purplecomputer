"""Art edges: a held arrow stops at the edge and a fresh press comes out the
far side; typing wraps like lines of text, from the last row to the first,
in both write and paint mode, once the next letter comes."""

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.art_room import COLS, ROWS


def _art(paint=True):
    app = make_app()
    app.action_switch_room("art")
    canvas = app.rooms["art"]
    if canvas._paint_mode != paint:
        canvas._toggle_paint_mode()
    return app, canvas


def test_held_arrow_stops_at_the_edge_and_a_fresh_press_wraps():
    async def go():
        app, canvas = _art()
        canvas._cursor_x, canvas._cursor_y = 0, 3
        for i in range(COLS + 20):
            await press(app, "right", is_repeat=i > 0)
        assert canvas._cursor_x == COLS - 1
        await press(app, "right")
        assert (canvas._cursor_x, canvas._cursor_y) == (0, 3)
        await press(app, "left")
        assert canvas._cursor_x == COLS - 1
        canvas._cursor_y = 0
        await press(app, "up")
        assert canvas._cursor_y == ROWS - 1
    run(go())


def test_typing_off_the_last_row_wraps_to_the_top_in_both_modes():
    async def go():
        for paint in (True, False):
            app, canvas = _art(paint)
            canvas._cursor_x, canvas._cursor_y = COLS - 1, ROWS - 1
            await type_text(app, "a")
            assert (canvas._cursor_x, canvas._cursor_y) == (COLS - 1, ROWS - 1)
            await type_text(app, "b")
            assert (0, 0) in canvas._grid and (canvas._cursor_x, canvas._cursor_y) == (1, 0)
    run(go())


def test_backspace_at_the_edge_takes_the_last_stamp_and_stops_the_wrap():
    async def go():
        app, canvas = _art()
        canvas._cursor_x, canvas._cursor_y = COLS - 2, 3
        await type_text(app, "ab")
        await press(app, "backspace")
        assert (COLS - 1, 3) not in canvas._grid and (COLS - 2, 3) in canvas._grid
        await type_text(app, "c")
        assert (COLS - 1, 3) in canvas._grid and (0, 4) not in canvas._grid
    run(go())


def test_moving_away_from_the_edge_drops_the_wrap():
    async def go():
        app, canvas = _art()
        canvas._cursor_x, canvas._cursor_y = COLS - 1, 3
        await type_text(app, "a")
        await press(app, "left")
        await type_text(app, "b")
        assert (COLS - 2, 3) in canvas._grid and (0, 4) not in canvas._grid
    run(go())


def test_enter_in_write_mode_wraps_from_the_last_row():
    async def go():
        app, canvas = _art(paint=False)
        canvas._cursor_x, canvas._cursor_y = 4, ROWS - 1
        await press(app, "enter")
        assert (canvas._cursor_x, canvas._cursor_y) == (0, 0)
    run(go())
