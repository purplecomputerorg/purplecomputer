"""Space latches the pen: a tap puts it down and paints, a second tap lifts
it, and leaving paint mode or restoring history lifts it. Also covers the
Space routing (tap vs hold vs code panel disabled) and demo playback's pen
handling, including cancellation."""

import asyncio

from purple_tui.constants import HOLD_OR_TAP_THRESHOLD
from purple_tui.harness import make_app, run as _run
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


def test_blink_is_steady_while_pen_down():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        assert canvas._blink_on
        canvas._blink()
        assert canvas._blink_on  # pen down: no blink
        await _tap(canvas)
        canvas._blink()
        assert not canvas._blink_on  # pen up: blinks again
    _run(_test())


def test_timeline_restore_lifts_pen():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        assert canvas._pen_down
        canvas.restore_timeline_state(canvas.timeline_state())
        assert not canvas._pen_down
    _run(_test())


def test_hold_opens_code_panel_and_lifts_pen():
    async def _test():
        app, canvas = _art()
        await _tap(canvas)
        assert canvas._pen_down
        await canvas.handle(_space())
        await asyncio.sleep(HOLD_OR_TAP_THRESHOLD + 0.3)
        await canvas.handle(_space(is_down=False))
        assert canvas.code_panel is not None
        assert not canvas._pen_down
    _run(_test())


def test_code_panel_disabled_space_is_immediate():
    """With Code Space off there is no tap-or-hold ambiguity: Space reaches the
    canvas at once, so hold-space-then-arrows still paints."""
    async def _test():
        app, canvas = _art()
        app._code_panel_enabled = False
        canvas._cursor_x = canvas._cursor_y = 5
        await canvas.handle(_space())
        assert canvas._pen_down
        await canvas.handle(_space(is_repeat=True))
        assert canvas._pen_down
        await canvas.handle(NavigationAction(direction='right'))
        assert (6, 5) in canvas._painted_positions
        await asyncio.sleep(HOLD_OR_TAP_THRESHOLD + 0.3)
        assert canvas.code_panel is None
        await canvas.handle(_space(is_down=False))
        assert canvas._pen_down
        await canvas.handle(_space())
        assert not canvas._pen_down
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
