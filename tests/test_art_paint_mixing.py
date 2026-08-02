"""Regression tests: paint mixing must ignore what glyph sits on the cell.

Painting yellow, typing "H" on one of the cells, then painting blue over both
used to give a mixed green on the bare cell and pure blue on the letter cell,
because the mix branch only fired when the cell still held the brush glyph.
Mixing now keys off whether the cell was painted, so a letter (or a typed
space) on top of paint mixes exactly like the bare paint next to it.
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
from purple_tui.color_mixing import mix_colors_paint
from purple_tui.keyboard import CharacterAction
from purple_tui.rooms.art_room import ArtCanvas, BRUSH_CHAR, get_key_color

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4
YELLOW = "#FFFF00"
BLUE = "#0000FF"
YELLOW_ON_BLUE = mix_colors_paint([YELLOW, BLUE])


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
        canvas._grid.clear()
        canvas._painted_positions.clear()
        canvas._cursor_x = canvas._cursor_y = 0
        yield canvas


def _canvas_test(body):
    """Run `body(canvas)` inside a mounted app; used as a decorator."""
    def wrapper():
        async def _test():
            async with _art_canvas() as canvas:
                await body(canvas)
        asyncio.new_event_loop().run_until_complete(_test())
    wrapper.__name__ = body.__name__
    wrapper.__doc__ = body.__doc__
    return wrapper


def _paint(canvas, x, color):
    canvas._set_paint_mode(True)
    canvas._cursor_x, canvas._cursor_y = x, 0
    canvas._last_key_color = color
    canvas._paint_at_cursor()


def _type(canvas, x, char):
    canvas._set_paint_mode(False)
    canvas._cursor_x, canvas._cursor_y = x, 0
    canvas.type_char(char)


@_canvas_test
async def test_paint_over_typed_letter_mixes_like_bare_paint(canvas):
    _paint(canvas, 0, YELLOW)
    _paint(canvas, 1, YELLOW)
    _type(canvas, 1, "H")
    _paint(canvas, 0, BLUE)
    _paint(canvas, 1, BLUE)

    bare_char, _, bare_bg = canvas._grid[(0, 0)]
    letter_char, _, letter_bg = canvas._grid[(1, 0)]
    assert bare_bg == YELLOW_ON_BLUE
    assert letter_bg == YELLOW_ON_BLUE, (
        f"Letter cell should mix to {YELLOW_ON_BLUE}, got {letter_bg}"
    )
    assert letter_char == "H", "Painting must keep the typed letter"
    assert bare_char == BRUSH_CHAR


@_canvas_test
async def test_paint_over_letter_on_blank_canvas_stays_pure(canvas):
    """An unpainted cell must not blend the letter's canvas background in."""
    _type(canvas, 0, "H")
    _paint(canvas, 0, BLUE)

    char, _, bg = canvas._grid[(0, 0)]
    assert bg == BLUE, f"First stroke should be pure {BLUE}, got {bg}"
    assert char == "H"


@_canvas_test
async def test_letter_stays_readable_after_the_paint_under_it_mixes(canvas):
    """Yellow needs black letters, the yellow+blue mix needs white ones."""
    _paint(canvas, 0, YELLOW)
    _type(canvas, 0, "H")
    assert canvas._grid[(0, 0)][1] == "#000000"

    _paint(canvas, 0, BLUE)
    assert canvas._grid[(0, 0)][2] == YELLOW_ON_BLUE
    assert canvas._grid[(0, 0)][1] == "#FFFFFF", (
        "Letter color must follow the mixed background"
    )


@_canvas_test
async def test_repainting_the_same_color_over_a_letter_keeps_it(canvas):
    _paint(canvas, 0, YELLOW)
    _type(canvas, 0, "H")
    _paint(canvas, 0, YELLOW)

    assert canvas._grid[(0, 0)][2] == YELLOW


@_canvas_test
async def test_third_stroke_mixes_from_the_letter_cells_current_color(canvas):
    """Mixing compounds on a letter cell the same as on a bare one."""
    for x in (0, 1):
        _paint(canvas, x, YELLOW)
    _type(canvas, 1, "H")
    for color in (BLUE, YELLOW):
        _paint(canvas, 0, color)
        _paint(canvas, 1, color)

    assert canvas._grid[(0, 0)][2] == canvas._grid[(1, 0)][2]
    assert canvas._grid[(1, 0)][2] == mix_colors_paint([YELLOW_ON_BLUE, YELLOW])


@_canvas_test
async def test_paint_over_typed_space_mixes_and_restores_the_brush(canvas):
    _paint(canvas, 0, YELLOW)
    _type(canvas, 0, " ")
    _paint(canvas, 0, BLUE)

    char, _, bg = canvas._grid[(0, 0)]
    assert bg == YELLOW_ON_BLUE
    assert char == BRUSH_CHAR


@_canvas_test
async def test_backspacing_a_painted_cell_resets_it_to_a_first_stroke(canvas):
    _paint(canvas, 0, YELLOW)
    canvas._cursor_x, canvas._cursor_y = 1, 0
    canvas._backspace()
    assert (0, 0) not in canvas._grid

    _paint(canvas, 0, BLUE)
    assert canvas._grid[(0, 0)][2] == BLUE, "Erased cells must not remember paint"


@_canvas_test
async def test_code_runner_paint_mixes_over_a_letter(canvas):
    """The code panel's paint path shares the same mixing rule."""
    canvas._set_paint_mode(True)
    canvas._cursor_x, canvas._cursor_y = 0, 0
    canvas.paint_char("q")
    _type(canvas, 0, "H")
    canvas._set_paint_mode(True)
    canvas._cursor_x, canvas._cursor_y = 0, 0
    canvas.paint_char("p")

    expected = mix_colors_paint([get_key_color("q"), get_key_color("p")])
    char, _, bg = canvas._grid[(0, 0)]
    assert bg == expected
    assert char == "H"


@_canvas_test
async def test_real_key_presses_mix_over_a_letter(canvas):
    """End to end through the keyboard path: paint, write, paint again."""
    async def press(char, x):
        canvas._cursor_x, canvas._cursor_y = x, 0
        await canvas.handle_keyboard_action(CharacterAction(char=char, shift_held=False))

    canvas._set_paint_mode(True)
    await press("q", 0)
    await press("q", 1)
    canvas._set_paint_mode(False)
    await press("h", 1)
    canvas._set_paint_mode(True)
    await press("p", 0)
    await press("p", 1)

    expected = mix_colors_paint([get_key_color("q"), get_key_color("p")])
    assert canvas._grid[(0, 0)][2] == expected
    assert canvas._grid[(1, 0)][2] == expected
    assert canvas._grid[(1, 0)][0] == "h"
