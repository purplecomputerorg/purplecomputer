"""Tests for how hold-to-accelerate interacts with painting.

Acceleration is for travel only. While paint is going down (space or a
held letter), every repeat moves exactly 1 cell: a 6-cell jump blows past
the corner of the shape a kid is drawing. Also guards two held-letter drag
behaviors that predate this rule:

1. A drag must paint every cell it passes (no dotted gaps).
2. A drag over existing paint must leave a uniform trail: each cell gets
   exactly one coat, since a second coat re-mixes to a different shade.
"""

import asyncio
import os
from contextlib import asynccontextmanager

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from purple_tui.purple_tui import PurpleApp
from purple_tui.constants import REQUIRED_TERMINAL_ROWS
from purple_tui.keyboard import NavigationAction
from purple_tui.rooms.art_room import (
    ArtCanvas,
    ARROW_HOLD_REPEAT_THRESHOLD,
    HOLD_ACCEL_MULTIPLIER,
)

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@asynccontextmanager
async def _art_canvas():
    app = PurpleApp()
    async with app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await asyncio.sleep(SETTLE)
        await pilot.pause()
        app.action_switch_room("art")
        await pilot.pause()
        await asyncio.sleep(SETTLE)
        await pilot.pause()
        canvas = app.query_one("#art-canvas", ArtCanvas)
        assert canvas._paint_mode, "Art room should default to paint mode"
        yield canvas

async def _hold_past_accel_threshold(canvas: ArtCanvas, **nav_kwargs) -> None:
    """Repeat an arrow until the next event would take an accelerated jump."""
    for _ in range(ARROW_HOLD_REPEAT_THRESHOLD):
        await canvas.handle_keyboard_action(
            NavigationAction(is_repeat=True, **nav_kwargs)
        )
    assert canvas._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD

def test_travel_accelerates_past_threshold():
    """No paint going down: a sustained hold jumps HOLD_ACCEL_MULTIPLIER cells."""
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x = 5
            canvas._cursor_y = 2
            canvas._space_down = False

            await _hold_past_accel_threshold(canvas, direction='down')
            y_before = canvas._cursor_y
            await canvas.handle_keyboard_action(
                NavigationAction(direction='down', is_repeat=True)
            )
            assert canvas._cursor_y - y_before == HOLD_ACCEL_MULTIPLIER
    _run(_test())

def test_space_paint_never_accelerates():
    """Space held: repeats past the threshold still move 1 cell each."""
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x = 5
            canvas._cursor_y = 2
            canvas._space_down = True
            canvas._last_key_color = "#FF0000"

            await _hold_past_accel_threshold(canvas, direction='down')
            y_before = canvas._cursor_y
            await canvas.handle_keyboard_action(
                NavigationAction(direction='down', is_repeat=True)
            )
            assert canvas._cursor_y - y_before == 1, (
                "Painting must not accelerate: a multi-cell jump overshoots "
                "the corner of the shape being drawn"
            )
            assert (canvas._cursor_x, canvas._cursor_y) in canvas._painted_positions
    _run(_test())

def test_held_letter_never_accelerates():
    """Letter + arrow drag: repeats past the threshold still move 1 cell each."""
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x = 2
            canvas._cursor_y = 5
            canvas._space_down = False

            await _hold_past_accel_threshold(
                canvas, direction='right', char_held='a'
            )
            x_before = canvas._cursor_x
            await canvas.handle_keyboard_action(
                NavigationAction(direction='right', is_repeat=True, char_held='a')
            )
            assert canvas._cursor_x - x_before == 1
    _run(_test())

def test_held_letter_drag_paints_every_cell():
    """Hold 'a' + hold the right arrow: the streak is solid, no gaps."""
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x = 2
            canvas._cursor_y = 5
            canvas._space_down = False
            canvas._painted_positions.clear()

            start_x = canvas._cursor_x
            await _hold_past_accel_threshold(
                canvas, direction='right', char_held='a'
            )
            await canvas.handle_keyboard_action(
                NavigationAction(direction='right', is_repeat=True, char_held='a')
            )

            row = canvas._cursor_y
            painted = {x for (x, y) in canvas._painted_positions if y == row}
            gaps = [x for x in range(start_x, canvas._cursor_x + 1)
                    if x not in painted]
            assert not gaps, (
                f"Held-letter paint skipped columns {gaps} on row {row}. "
                f"Painted: {sorted(painted)}."
            )
    _run(_test())

def test_held_letter_drag_over_existing_paint_is_uniform():
    """Hold 'r' + right arrow across a blue stretch: one even blend, no stripes."""
    async def _test():
        async with _art_canvas() as canvas:
            row = 5
            for x in range(0, 30):
                canvas._grid[(x, row)] = ("█", "#1F75FE", "#1F75FE")
                canvas._painted_positions.add((x, row))

            canvas._cursor_x = 2
            canvas._cursor_y = row
            canvas._space_down = False

            start_x = canvas._cursor_x
            await _hold_past_accel_threshold(
                canvas, direction='right', char_held='r'
            )
            for _ in range(2):
                await canvas.handle_keyboard_action(
                    NavigationAction(direction='right', is_repeat=True, char_held='r')
                )

            colors = {canvas._grid[(x, row)][2]
                      for x in range(start_x + 1, canvas._cursor_x)}
            assert len(colors) == 1, (
                f"Drag over existing paint left {len(colors)} shades "
                f"({sorted(colors)}) between columns {start_x + 1} and "
                f"{canvas._cursor_x - 1}. Each cell must get exactly one coat: "
                f"a second coat re-mixes and stripes the trail."
            )
    _run(_test())
