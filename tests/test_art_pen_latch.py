"""Space toggles a pen latch in Art's paint mode: down paints as arrows move,
a second tap lifts it, and leaving paint mode or restoring history lifts it.

Also covers the container-level space routing (tap vs hold vs code panel
disabled) and demo playback's pen handling, including cancellation.
"""

import asyncio
from contextlib import asynccontextmanager

from tests.test_paint_accelerated import _art_canvas, _run, APP_SIZE, SETTLE

from purple_tui.constants import HOLD_OR_TAP_THRESHOLD
from purple_tui.keyboard import NavigationAction, ControlAction
from purple_tui.playback.player import PlaybackPlayer
from purple_tui.playback.script import DrawPath


def _space(is_down=True, is_repeat=False):
    return ControlAction(action='space', is_down=is_down, is_repeat=is_repeat)


@asynccontextmanager
async def _art_mode():
    """Art room with its mode container, for container-level space routing."""
    from purple_tui.purple_tui import PurpleApp
    from purple_tui.rooms.art_room import ArtMode, ArtCanvas

    app = PurpleApp()
    async with app.run_test(size=APP_SIZE) as pilot:
        await pilot.pause()
        await asyncio.sleep(SETTLE)
        await pilot.pause()
        app.action_switch_room("art")
        await pilot.pause()
        await asyncio.sleep(SETTLE)
        await pilot.pause()
        mode = app.query_one(ArtMode)
        canvas = app.query_one("#art-canvas", ArtCanvas)
        assert canvas._paint_mode
        yield app, pilot, mode, canvas


# ---------------------------------------------------------------------------
# Canvas-level latch behavior
# ---------------------------------------------------------------------------

def test_pen_latch_toggles_and_paints():
    async def _test():
        async with _art_canvas() as canvas:
            canvas._cursor_x = 5
            canvas._cursor_y = 5
            canvas._last_key_color = "#FF0000"

            await canvas.handle_keyboard_action(_space())
            assert canvas._pen_down
            assert (5, 5) in canvas._painted_positions  # stamped on pen down

            await canvas.handle_keyboard_action(NavigationAction(direction='right'))
            assert (6, 5) in canvas._painted_positions

            # Release does not lift the latch; repeats do not flutter it
            await canvas.handle_keyboard_action(_space(is_down=False))
            await canvas.handle_keyboard_action(_space(is_repeat=True))
            assert canvas._pen_down

            await canvas.handle_keyboard_action(_space())
            assert not canvas._pen_down
            await canvas.handle_keyboard_action(NavigationAction(direction='right'))
            assert (7, 5) not in canvas._painted_positions
    _run(_test())


def test_pen_lifts_on_write_mode():
    async def _test():
        async with _art_canvas() as canvas:
            await canvas.handle_keyboard_action(_space())
            assert canvas._pen_down
            canvas._set_paint_mode(False)
            assert not canvas._pen_down
    _run(_test())


def test_pen_lifts_on_clear():
    async def _test():
        async with _art_canvas() as canvas:
            await canvas.handle_keyboard_action(_space())
            assert canvas._pen_down
            canvas._clear_canvas()
            assert not canvas._pen_down
    _run(_test())


def test_blink_is_steady_while_pen_down():
    async def _test():
        async with _art_canvas() as canvas:
            await canvas.handle_keyboard_action(_space())
            assert canvas._cursor_visible
            canvas._toggle_blink()
            assert canvas._cursor_visible  # pen down: no blink

            await canvas.handle_keyboard_action(_space())
            canvas._toggle_blink()
            assert not canvas._cursor_visible  # pen up: blinks again
    _run(_test())


# ---------------------------------------------------------------------------
# Container-level space routing (ArtMode's HoldOrTap layer)
# ---------------------------------------------------------------------------

def test_container_tap_toggles_pen():
    async def _test():
        async with _art_mode() as (app, pilot, mode, canvas):
            await mode.handle_keyboard_action(_space())
            await mode.handle_keyboard_action(_space(is_down=False))
            assert canvas._pen_down

            await mode.handle_keyboard_action(_space())
            await mode.handle_keyboard_action(_space(is_down=False))
            assert not canvas._pen_down
    _run(_test())


def test_timeline_restore_lifts_pen():
    async def _test():
        async with _art_mode() as (app, pilot, mode, canvas):
            await mode.handle_keyboard_action(_space())
            await mode.handle_keyboard_action(_space(is_down=False))
            assert canvas._pen_down
            mode.restore_timeline_state(mode.timeline_state())
            assert not canvas._pen_down
    _run(_test())


def test_container_hold_opens_repl_and_lifts_pen():
    async def _test():
        async with _art_mode() as (app, pilot, mode, canvas):
            # Latch the pen first so the hold must lift it
            await mode.handle_keyboard_action(_space())
            await mode.handle_keyboard_action(_space(is_down=False))
            assert canvas._pen_down

            await mode.handle_keyboard_action(_space())
            await asyncio.sleep(HOLD_OR_TAP_THRESHOLD + 0.3)
            await pilot.pause()
            await mode.handle_keyboard_action(_space(is_down=False))

            assert mode._repl_panel.is_open
            assert not canvas._pen_down
    _run(_test())


def test_code_panel_disabled_space_is_immediate():
    """Littles Mode regression: with the code panel off, space must reach the
    canvas directly so hold-space-then-arrows still paints."""
    async def _test():
        async with _art_mode() as (app, pilot, mode, canvas):
            app._code_panel_enabled = False
            canvas._cursor_x = 5
            canvas._cursor_y = 5

            # Press and hold: latch is immediate, repeats don't flutter it
            await mode.handle_keyboard_action(_space())
            assert canvas._pen_down
            await mode.handle_keyboard_action(_space(is_repeat=True))
            assert canvas._pen_down

            # Arrows while (or after) holding paint a trail
            await mode.handle_keyboard_action(NavigationAction(direction='right'))
            assert (6, 5) in canvas._painted_positions

            # A very long hold never opens the REPL
            await asyncio.sleep(HOLD_OR_TAP_THRESHOLD + 0.3)
            await pilot.pause()
            assert not mode._repl_panel.is_open

            # Release keeps the latch; the next press lifts it
            await mode.handle_keyboard_action(_space(is_down=False))
            assert canvas._pen_down
            await mode.handle_keyboard_action(_space())
            assert not canvas._pen_down
    _run(_test())


# ---------------------------------------------------------------------------
# Demo playback pen handling
# ---------------------------------------------------------------------------

def _pen_player(calls):
    async def dispatch(action):
        pass
    return PlaybackPlayer(
        dispatch_action=dispatch,
        set_art_pen=calls.append,
        is_art_paint_mode=lambda: True,
    )


def test_draw_path_sets_then_lifts_pen():
    async def _test():
        calls = []
        player = _pen_player(calls)
        await player._draw_path(DrawPath(
            directions=['right'], steps_per_direction=2,
            delay_per_step=0.0, pause_after=0.0))
        assert calls == [True, False]
    _run(_test())


def test_draw_path_lifts_pen_on_task_cancel():
    """cancel_demo() cancels the task mid-await; the pen must still lift."""
    async def _test():
        calls = []
        player = _pen_player(calls)
        task = asyncio.create_task(player._draw_path(DrawPath(
            directions=['right'], steps_per_direction=100,
            delay_per_step=0.05)))
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
        player = PlaybackPlayer(
            dispatch_action=dispatch, is_art_paint_mode=lambda: True)
        await player._draw_path(DrawPath(
            directions=['right'], delay_per_step=0.0, pause_after=0.0))
    _run(_test())
