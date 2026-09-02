"""Regression tests for shift-key behavior in the art room.

Two related bugs covered here:

1. Paint mode + shifted number row: Shift+9, Shift+0, Shift+-, Shift+= should
   select the corresponding grayscale shade without stamping (mirrors how
   Shift+letter just selects the letter's color). Before the fix Shift+9/0
   did nothing (their shifted glyphs aren't in GRAYSCALE) and Shift+= stamped
   black because '+' *is* in GRAYSCALE.

2. Write mode must keep the shifted glyph: Shift+/ types '?', Shift+3 types
   '#', etc. An earlier fix unshifted the char unconditionally and broke
   typing. This locks in that the unshift only applies in paint mode.
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
from purple_tui.keyboard import CharacterAction
from purple_tui.rooms.art_room import ArtCanvas, GRAYSCALE

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_canvas(pilot, app, paint_mode: bool) -> ArtCanvas:
    app.action_switch_room("art")
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()
    canvas = app.query_one("#art-canvas", ArtCanvas)
    canvas._set_paint_mode(paint_mode)
    canvas._cursor_x = 0
    canvas._cursor_y = 0
    canvas._painted_positions.clear()
    canvas._grid.clear()
    return canvas


def test_paint_mode_shift_number_row_selects_grayscale_without_stamping():
    """Shift+9/0/-/= folds to '9'/'0'/'-'/'=' for color lookup, no stamp."""
    async def _test():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.pause()
            await asyncio.sleep(SETTLE)
            await pilot.pause()
            canvas = await _make_canvas(pilot, app, paint_mode=True)

            # The shifted form of each number-row key, paired with the bare
            # key whose grayscale shade should end up selected. Note that
            # shift+= arrives as '+' here because SHIFT_MAP['='] = '+'; the
            # global kid-math remap also turns unshifted '=' into '+'. Both
            # routes resolve to the same #000000 entry.
            cases = [
                ('(', '9'),
                (')', '0'),
                ('_', '-'),
                ('+', '='),
            ]
            start_x, start_y = canvas._cursor_x, canvas._cursor_y
            for shifted_char, bare_key in cases:
                await canvas.handle_keyboard_action(
                    CharacterAction(char=shifted_char, shift_held=True)
                )
                assert canvas._last_key_color == GRAYSCALE[bare_key], (
                    f"Shift+{bare_key} (char={shifted_char!r}) should select "
                    f"{GRAYSCALE[bare_key]}, got {canvas._last_key_color}"
                )

            assert canvas._cursor_x == start_x and canvas._cursor_y == start_y, (
                "Shift+number must not advance the cursor"
            )
            assert not canvas._painted_positions, (
                "Shift+number must not paint any cells"
            )
    _run(_test())


def test_paint_mode_unshifted_number_stamps_and_advances():
    """Sanity check the inverse: pressing '9' (no shift) does stamp."""
    async def _test():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.pause()
            await asyncio.sleep(SETTLE)
            await pilot.pause()
            canvas = await _make_canvas(pilot, app, paint_mode=True)

            start_x, start_y = canvas._cursor_x, canvas._cursor_y
            await canvas.handle_keyboard_action(
                CharacterAction(char='9', shift_held=False)
            )
            assert canvas._last_key_color == GRAYSCALE['9']
            assert (start_x, start_y) in canvas._painted_positions, (
                "Unshifted number key must stamp"
            )
            assert canvas._cursor_x == start_x + 1, (
                "Unshifted number key must advance cursor"
            )
    _run(_test())


def test_write_mode_keeps_shifted_glyph():
    """Shift+/ types '?', Shift+3 types '#' — write mode must not unshift."""
    async def _test():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.pause()
            await asyncio.sleep(SETTLE)
            await pilot.pause()
            canvas = await _make_canvas(pilot, app, paint_mode=False)

            cases = [
                ('?', '/'),  # shift+/ should type '?', not '/'
                ('#', '3'),  # shift+3 should type '#', not '3'
                ('!', '1'),
                ('@', '2'),
            ]
            for shifted_char, bare_key in cases:
                pos = (canvas._cursor_x, canvas._cursor_y)
                await canvas.handle_keyboard_action(
                    CharacterAction(char=shifted_char, shift_held=True)
                )
                cell = canvas._grid.get(pos)
                assert cell is not None, f"No cell typed for {shifted_char!r}"
                typed_char = cell[0] if isinstance(cell, tuple) else cell.char
                assert typed_char == shifted_char, (
                    f"Write mode must keep shifted glyph {shifted_char!r} "
                    f"(would have been {bare_key!r} if incorrectly unshifted), "
                    f"got {typed_char!r}"
                )
    _run(_test())
