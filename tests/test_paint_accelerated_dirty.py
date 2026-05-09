"""Regression test: accelerated vertical paint must mark every passed row dirty.

Bug: when holding space (paint pen down) and holding an arrow long enough to
trigger 6x acceleration, _paint_at_cursor() writes 6 cells to the grid but
only the start and end rows were added to _dirty_lines. The 4 intermediate
rows kept their stale cached strips and rendered as gaps until a later cursor
pass happened to mark them dirty, at which point the painted cells suddenly
"filled in".
"""

import asyncio
import os

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


def test_accelerated_paint_marks_every_passed_row_dirty():
    async def _test():
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
            canvas._cursor_x = 5
            canvas._cursor_y = 2
            canvas._space_down = True
            canvas._last_key_color = "#FF0000"

            # Build the repeat counter up to the acceleration threshold
            # without yet crossing it. After this loop the next repeat will
            # jump 6 cells in one event.
            for _ in range(ARROW_HOLD_REPEAT_THRESHOLD):
                await canvas.handle_keyboard_action(
                    NavigationAction(direction='down', is_repeat=True, space_held=True)
                )

            assert canvas._arrow_repeat_count >= ARROW_HOLD_REPEAT_THRESHOLD

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
