import asyncio
import time

from purple_tui.canvas.app import LETTER_HOLD
from purple_tui.canvas.color_recipe import example, partner
from purple_tui.canvas.harness import make_app, run
from purple_tui.color_mixing import mix_colors_paint
from purple_tui.input import KeyCode, RawKeyEvent
from purple_tui.palette import get_key_color


async def _key(app, code, down):
    await app._handle_raw_key_event(RawKeyEvent(keycode=code, is_down=down, timestamp=time.monotonic()))


async def _tap(app, code):
    await _key(app, code, True)
    await _key(app, code, False)


def test_example_mixes_the_brush_key_with_the_next_hue_row():
    assert [partner(k) for k in "rfc1"] == ["f", "v", "e", "r"]
    terms, result = example("r")
    assert terms == [("r", get_key_color("r")), ("f", get_key_color("f"))]
    assert result == mix_colors_paint([get_key_color("r"), get_key_color("f")])
    assert example("")[0][0][0] == "f"     # a wheel color has no key to hold


def test_held_letter_shows_only_after_the_hold_and_clears_on_release():
    async def go():
        app = make_app()
        await _key(app, KeyCode.KEY_R, True)
        assert app.held_letter is None
        await asyncio.sleep(LETTER_HOLD + 0.1)
        assert app.held_letter == "r"
        await _key(app, KeyCode.KEY_R, False)
        assert app.held_letter is None
    run(go())
