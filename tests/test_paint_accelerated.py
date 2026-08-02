"""Regression tests for painting while an arrow is held past the accel threshold.

1. Accelerated vertical paint must mark every passed row dirty. Holding space
   (pen down) plus an arrow long enough to trigger 6x acceleration wrote 6
   cells to the grid but only marked the start and end rows dirty. The 4
   intermediate rows kept their stale cached strips and rendered as gaps until
   a later cursor pass happened to mark them dirty.

2. Holding a *letter* plus an arrow must paint every cell it passes. The
   letter-held path painted once per arrow repeat, so once acceleration kicked
   in it painted 1 cell and skipped the next 5, leaving a dotted trail where
   the space-held pen drew a solid streak.
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


async def _hold_to_accel_threshold(canvas: ArtCanvas, **nav_kwargs) -> None:
    """Repeat an arrow until the next event will take an accelerated jump."""
    for _ in range(ARROW_HOLD_REPEAT_THRESHOLD):
        await canvas.handle_keyboard_action(
            NavigationAction(is_repeat=True, **nav_kwargs)
        )
    assert canvas._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD


def test_accelerated_paint_marks_every_passed_row_dirty():
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x = 5
            canvas._cursor_y = 2
            canvas._space_down = True
            canvas._last_key_color = "#FF0000"

            await _hold_to_accel_threshold(
                canvas, direction='down', space_held=True
            )

            # Reset render bookkeeping so we observe only the accelerated step.
            canvas._dirty_lines.clear()
            canvas._all_dirty = False
            y_before = canvas._cursor_y

            await canvas.handle_keyboard_action(
                NavigationAction(direction='down', is_repeat=True, space_held=True)
            )

            y_after = canvas._cursor_y
            assert y_after - y_before == HOLD_ACCEL_MULTIPLIER, (
                f"Expected accelerated jump of {HOLD_ACCEL_MULTIPLIER} cells, "
                f"got {y_after - y_before}"
            )

            # Every cell in the accelerated path was painted.
            for row in range(y_before + 1, y_after + 1):
                assert (canvas._cursor_x, row) in canvas._painted_positions, (
                    f"Cell ({canvas._cursor_x}, {row}) was not painted"
                )

            # Every painted row must be in _dirty_lines so the cached strip
            # gets recomputed. Without the fix, only the rows around the
            # final cursor position (y_after-1, y_after, y_after+1) are dirty
            # and the rows in between render stale.
            for row in range(y_before + 1, y_after + 1):
                assert row in canvas._dirty_lines, (
                    f"Row {row} was painted but not marked dirty. "
                    f"Dirty rows: {sorted(canvas._dirty_lines)}. "
                    f"Without dirty marking the cached strip stays stale and "
                    f"the painted cell is invisible until a later cursor pass."
                )
    _run(_test())


def test_held_letter_paints_every_cell_through_acceleration():
    """Hold 'a' + hold the right arrow: the streak stays solid after accel."""
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x = 2
            canvas._cursor_y = 5
            canvas._space_down = False  # Letter held, not the space pen
            canvas._painted_positions.clear()

            start_x = canvas._cursor_x
            await _hold_to_accel_threshold(
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
                f"Painted: {sorted(painted)}. Once the arrow repeat crosses "
                f"the accel threshold the cursor jumps "
                f"{HOLD_ACCEL_MULTIPLIER} cells, so painting must happen at "
                f"every intermediate step, not once per repeat."
            )
    _run(_test())
