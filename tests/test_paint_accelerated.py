"""Acceleration is for travel only. While paint is going down (pen latch or a
held letter), every repeat moves exactly 1 cell: a 6-cell jump blows past
the corner of the shape a kid is drawing. Also guards two held-letter drag
behaviors: a drag paints every cell it passes (no dotted gaps), and a drag
over existing paint leaves a uniform trail (each cell gets exactly one coat,
since a second coat re-mixes to a different shade)."""

from contextlib import asynccontextmanager

from purple_tui.harness import make_app, run as _run
from purple_tui.keyboard import NavigationAction
from purple_tui.rooms.art_room import ARROW_HOLD_REPEAT_THRESHOLD, HOLD_ACCEL_MULTIPLIER


@asynccontextmanager
async def _art_canvas():
    app = make_app()
    app.action_switch_room("art")
    canvas = app.rooms["art"]
    assert canvas._paint_mode, "Art room should default to paint mode"
    yield canvas


async def _hold_past_accel_threshold(canvas, **nav_kwargs):
    for _ in range(ARROW_HOLD_REPEAT_THRESHOLD):
        await canvas.handle(NavigationAction(is_repeat=True, **nav_kwargs))
    assert canvas._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD


def test_travel_accelerates_past_threshold():
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x, canvas._cursor_y = 5, 2
            canvas._pen_down = False
            await _hold_past_accel_threshold(canvas, direction='down')
            y_before = canvas._cursor_y
            await canvas.handle(NavigationAction(direction='down', is_repeat=True))
            assert canvas._cursor_y - y_before == HOLD_ACCEL_MULTIPLIER
    _run(_test())


def test_pen_down_never_accelerates():
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x, canvas._cursor_y = 5, 2
            canvas._pen_down = True
            canvas._last_key_color = "#FF0000"
            await _hold_past_accel_threshold(canvas, direction='down')
            y_before = canvas._cursor_y
            await canvas.handle(NavigationAction(direction='down', is_repeat=True))
            assert canvas._cursor_y - y_before == 1, "Painting must not accelerate"
            assert (canvas._cursor_x, canvas._cursor_y) in canvas._painted_positions
    _run(_test())


def test_held_letter_never_accelerates():
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x, canvas._cursor_y = 2, 5
            canvas._pen_down = False
            await _hold_past_accel_threshold(canvas, direction='right', char_held='a')
            x_before = canvas._cursor_x
            await canvas.handle(NavigationAction(direction='right', is_repeat=True, char_held='a'))
            assert canvas._cursor_x - x_before == 1
    _run(_test())


def test_held_letter_drag_paints_every_cell():
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x, canvas._cursor_y = 2, 5
            canvas._pen_down = False
            canvas._painted_positions.clear()
            start_x = canvas._cursor_x
            await _hold_past_accel_threshold(canvas, direction='right', char_held='a')
            await canvas.handle(NavigationAction(direction='right', is_repeat=True, char_held='a'))
            row = canvas._cursor_y
            painted = {x for (x, y) in canvas._painted_positions if y == row}
            gaps = [x for x in range(start_x, canvas._cursor_x + 1) if x not in painted]
            assert not gaps, f"Held-letter paint skipped columns {gaps} on row {row}. Painted: {sorted(painted)}."
    _run(_test())


def test_held_letter_drag_over_existing_paint_is_uniform():
    async def _test():
        async with _art_canvas() as canvas:
            row = 5
            for x in range(0, 30):
                canvas._grid[(x, row)] = ("█", "#1F75FE", "#1F75FE")
                canvas._painted_positions.add((x, row))
            canvas._cursor_x, canvas._cursor_y = 2, row
            canvas._pen_down = False
            start_x = canvas._cursor_x
            await _hold_past_accel_threshold(canvas, direction='right', char_held='r')
            for _ in range(2):
                await canvas.handle(NavigationAction(direction='right', is_repeat=True, char_held='r'))
            colors = {canvas._grid[(x, row)][2] for x in range(start_x + 1, canvas._cursor_x)}
            assert len(colors) == 1, f"Drag over existing paint left {len(colors)} shades ({sorted(colors)})"
    _run(_test())
