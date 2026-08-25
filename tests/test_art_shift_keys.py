"""Two related behaviors:
1. Paint mode + shifted number row: Shift+9, Shift+0, Shift+-, Shift+= select
   the corresponding grayscale shade without stamping (like Shift+letter).
2. Write mode keeps the shifted glyph: Shift+/ types '?', Shift+3 types '#'.
"""

from purple_tui.harness import make_app, run
from purple_tui.keyboard import CharacterAction
from purple_tui.palette import GRAYSCALE


def _canvas(paint_mode: bool):
    app = make_app()
    app.action_switch_room("art")
    canvas = app.rooms["art"]
    canvas._set_paint_mode(paint_mode)
    canvas._cursor_x = canvas._cursor_y = 0
    canvas._painted_positions.clear()
    canvas._grid.clear()
    return canvas


def test_paint_mode_shift_number_row_selects_grayscale_without_stamping():
    async def _test():
        canvas = _canvas(paint_mode=True)
        start = (canvas._cursor_x, canvas._cursor_y)
        for shifted_char, bare_key in [('(', '9'), (')', '0'), ('_', '-'), ('+', '=')]:
            await canvas.handle(CharacterAction(char=shifted_char, shift_held=True))
            assert canvas._last_key_color == GRAYSCALE[bare_key], (
                f"Shift+{bare_key} (char={shifted_char!r}) should select {GRAYSCALE[bare_key]}, got {canvas._last_key_color}")
        assert (canvas._cursor_x, canvas._cursor_y) == start, "Shift+number must not advance the cursor"
        assert not canvas._painted_positions, "Shift+number must not paint any cells"
    run(_test())


def test_paint_mode_unshifted_number_stamps_and_advances():
    async def _test():
        canvas = _canvas(paint_mode=True)
        await canvas.handle(CharacterAction(char='9', shift_held=False))
        assert canvas._last_key_color == GRAYSCALE['9']
        assert (0, 0) in canvas._painted_positions, "Unshifted number key must stamp"
        assert canvas._cursor_x == 1, "Unshifted number key must advance cursor"
    run(_test())


def test_write_mode_keeps_shifted_glyph():
    async def _test():
        canvas = _canvas(paint_mode=False)
        for shifted_char in ('?', '#', '!', '@'):
            pos = (canvas._cursor_x, canvas._cursor_y)
            await canvas.handle(CharacterAction(char=shifted_char, shift_held=True))
            cell = canvas._grid.get(pos)
            assert cell is not None, f"No cell typed for {shifted_char!r}"
            assert cell[0] == shifted_char, f"Write mode must keep shifted glyph {shifted_char!r}, got {cell[0]!r}"
    run(_test())
