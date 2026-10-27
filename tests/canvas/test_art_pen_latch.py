"""Space latches the pen: a tap puts it down and paints, a second tap lifts
it, and leaving paint mode or restoring history lifts it. Holding Space while
moving paints until release. Also covers demo playback's pen handling,
including cancellation."""

import asyncio

from purple_tui.constants import HOLD_OR_TAP_THRESHOLD
from purple_tui.canvas.harness import make_app, run as _run
from purple_tui.keyboard import ControlAction, NavigationAction
from purple_tui.playback.player import PlaybackPlayer
from purple_tui.playback.script import DrawPath


def _space(is_down=True, is_repeat=False):
    return ControlAction(action='space', is_down=is_down, is_repeat=is_repeat)


def _art():
    app = make_app()
    app.action_switch_room("art")
    canvas = app.rooms["art"]
    assert canvas._paint_mode
    return app, canvas


async def _tap(canvas):
    await canvas.handle(_space())
    await canvas.handle(_space(is_down=False))


def test_pen_latch_toggles_and_paints():
    async def _test():
        app, canvas = _art()
        canvas._cursor_x = canvas._cursor_y = 5
        canvas._last_key_color = "#FF0000"
        await _tap(canvas)
        assert canvas._pen_down
        assert (5, 5) in canvas._painted_positions  # stamped on pen down
        await canvas.handle(NavigationAction(direction='right'))
        assert (6, 5) in canvas._painted_positions
        await canvas.handle(_space(is_repeat=True))
        assert canvas._pen_down
        await _tap(canvas)
        assert not canvas._pen_down
        await canvas.handle(NavigationAction(direction='right'))
        assert (7, 5) not in canvas._painted_positions
    _run(_test())


def test_pen_lifts_on_write_mode():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        assert canvas._pen_down
        canvas._set_paint_mode(False)
        assert not canvas._pen_down
    _run(_test())


def test_pen_lifts_on_clear():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        assert canvas._pen_down
        canvas.clear()
        assert not canvas._pen_down
    _run(_test())


def test_only_the_write_caret_blinks():
    """Blinking swaps the caret's own pixels (Gfx.blink): no room timer, no full repaints."""
    async def _test():
        app, canvas = _art()
        app._draw()
        assert app.g.caret is None  # brush tip: steady
        canvas._set_paint_mode(False)
        app._draw()
        assert app.g.caret is not None
        assert app.g.caret[0].h < app.g.vh(5)
        assert not [n for _, n in app.timers.intervals() if "ArtRoom" in n]
    _run(_test())


def test_timeline_restore_lifts_pen():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        assert canvas._pen_down
        canvas.restore_timeline_state(canvas.timeline_state())
        assert not canvas._pen_down
    _run(_test())


def test_opening_code_lifts_pen():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        assert canvas._pen_down
        canvas.open_code_panel()
        assert canvas.code_panel is not None
        assert not canvas._pen_down
    _run(_test())


def test_space_is_immediate():
    """Space reaches the canvas at once, so a tap latches and hold-space-then-arrows paints until release."""
    async def _test():
        app, canvas = _art()
        canvas._cursor_x = canvas._cursor_y = 5
        await canvas.handle(_space())
        assert canvas._pen_down
        await canvas.handle(_space(is_repeat=True))
        assert canvas._pen_down
        await canvas.handle(NavigationAction(direction='right', space_held=True))
        assert (6, 5) in canvas._painted_positions
        await asyncio.sleep(HOLD_OR_TAP_THRESHOLD + 0.3)
        assert canvas.code_panel is None
        await canvas.handle(_space(is_down=False))
        assert not canvas._pen_down
        await _tap(canvas)
        assert canvas._pen_down
    _run(_test())


def test_holding_space_while_moving_paints_until_release():
    async def _test():
        app, canvas = _art()
        canvas._cursor_x = canvas._cursor_y = 5
        await canvas.handle(_space())
        await canvas.handle(NavigationAction(direction='right', space_held=True))
        assert canvas._pen_down and {(5, 5), (6, 5)} <= canvas._painted_positions
        await asyncio.sleep(HOLD_OR_TAP_THRESHOLD + 0.3)
        assert canvas.code_panel is None
        await canvas.handle(_space(is_down=False))
        assert not canvas._pen_down
        await canvas.handle(NavigationAction(direction='right'))
        assert (7, 5) not in canvas._painted_positions
    _run(_test())


def test_holding_space_while_moving_keeps_a_latched_brush_down():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        await canvas.handle(_space())
        await canvas.handle(NavigationAction(direction='right', space_held=True))
        await canvas.handle(_space(is_down=False))
        assert canvas._pen_down
    _run(_test())


def _pen_player(calls):
    async def dispatch(action):
        pass
    return PlaybackPlayer(dispatch_action=dispatch, set_art_pen=calls.append, is_art_paint_mode=lambda: True)


def test_draw_path_sets_then_lifts_pen():
    async def _test():
        calls = []
        await _pen_player(calls)._draw_path(DrawPath(directions=['right'], steps_per_direction=2, delay_per_step=0.0, pause_after=0.0))
        assert calls == [True, False]
    _run(_test())


def test_draw_path_lifts_pen_on_task_cancel():
    async def _test():
        calls = []
        player = _pen_player(calls)
        task = asyncio.create_task(player._draw_path(DrawPath(directions=['right'], steps_per_direction=100, delay_per_step=0.05)))
        await asyncio.sleep(0.12)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert calls[0] is True
        assert calls[-1] is False
    _run(_test())


def test_draw_path_without_pen_callback_is_safe():
    async def _test():
        async def dispatch(action):
            pass
        player = PlaybackPlayer(dispatch_action=dispatch, is_art_paint_mode=lambda: True)
        await player._draw_path(DrawPath(directions=['right'], delay_per_step=0.0, pause_after=0.0))
    _run(_test())


def test_a_chord_paints_the_next_cell_in_the_mix():
    from purple_tui.canvas.harness import press
    from purple_tui.color_mixing import mix_colors_paint
    from purple_tui.palette import get_key_color

    async def _test():
        app, canvas = _art()
        canvas._cursor_x = canvas._cursor_y = 5
        await press(app, "b")
        await press(app, "g", char_held="b")
        await press(app, "r", char_held="g")    # the keyboard reports the newest held letter
        two = mix_colors_paint([get_key_color("b"), get_key_color("g")])
        mixed = mix_colors_paint([two, get_key_color("r")])
        assert [canvas._grid[(x, 5)][2] for x in (5, 6, 7)] == [get_key_color("b"), two, mixed]
        assert canvas.brush_color == mixed and (canvas._cursor_x, canvas._cursor_y) == (8, 5)
    _run(_test())


def test_holding_a_chord_keeps_painting_the_mix():
    from purple_tui.canvas.harness import press
    from purple_tui.color_mixing import mix_colors_paint
    from purple_tui.palette import get_key_color

    async def _test():
        app, canvas = _art()
        canvas._cursor_x = canvas._cursor_y = 5
        await press(app, "b")
        await press(app, "g", char_held="b")
        await press(app, "g", is_repeat=True)
        await press(app, "right", char_held="g")
        mixed = mix_colors_paint([get_key_color("b"), get_key_color("g")])
        assert all(canvas._grid[(x, 5)][2] == mixed for x in (6, 7, 8))
    _run(_test())

def test_brush_eases_down_and_up_then_rests():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        await asyncio.sleep(0.2)
        assert canvas._lift == 0.0 and canvas._lift_timer is None
        await _tap(canvas)
        await asyncio.sleep(0.2)
        assert canvas._lift == 1.0 and canvas._lift_timer is None
    _run(_test())


def _code_art():
    app, canvas = _art()
    canvas.open_code_panel()
    canvas._cursor_x = canvas._cursor_y = 5
    return app, canvas


def test_code_brush_holds_across_lines():
    async def _test():
        app, canvas = _code_art()
        await canvas.run_code(["brush up"])
        await canvas.run_code(["right 3"])
        assert not canvas._painted_positions
        await canvas.run_code(["brush down"])
        await canvas.run_code(["right 2"])
        assert canvas._painted_positions == {(8, 5), (9, 5)}
    _run(_test())


def test_a_color_keeps_the_code_brush_up():
    async def _test():
        app, canvas = _code_art()
        await canvas.run_code(["brush up red right 3"])
        assert not canvas._painted_positions
    _run(_test())


def test_code_cursor_shows_the_code_brush():
    async def _test():
        app, canvas = _code_art()
        await asyncio.sleep(0.2)
        assert canvas._lift == 0.0
        await canvas.run_code(["brush up"])
        await asyncio.sleep(0.2)
        assert canvas._lift == 1.0
        canvas.close_code_panel()
        canvas.open_code_panel()
        await asyncio.sleep(0.2)
        assert canvas._code_brush_down and canvas._lift == 0.0
    _run(_test())
