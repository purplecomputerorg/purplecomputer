"""The render loop sleeps while nothing changes and wakes the moment something asks for a frame.

Each test runs the real loop on a headless app, counting its passes (one SDL poll each) and
its frames. Tests that prove a wake-up stretch the idle poll to seconds, so only the wake
itself can explain a prompt frame.
"""

import asyncio
import contextlib
import threading
import time
from types import SimpleNamespace

import pytest

from purple_tui.canvas import app as app_module
from purple_tui.canvas import sdl_input
from purple_tui.canvas.harness import make_app, press, run

PROMPT = 0.15   # a woken loop draws well inside this; the stretched poll would take seconds
SLOW_POLL = 5.0


@contextlib.asynccontextmanager
async def render_loop(monkeypatch, room="play", evdev=True, poll=None):
    if poll is not None:
        monkeypatch.setattr(app_module, "IDLE_POLL_S", poll)
    app = make_app(room=room)
    app._mark_ui_ready = lambda: None
    if evdev:   # the real machine: evdev owns the keyboard, SDL only reports window events
        app._evdev_reader = SimpleNamespace(away=False, release_grab=lambda: None)
    loop = SimpleNamespace(passes=0, frames=[], window_event=False, mid_frame=None)
    real_pump = sdl_input.pump

    def pump(g):
        loop.passes += 1
        if loop.window_event:   # what sdl_input.pump does for an expose (the parent terminal closing)
            loop.window_event = False
            g.dirty = True
        return real_pump(g)

    real_draw = app._draw

    def draw():
        loop.frames.append(time.monotonic())
        real_draw()
        if loop.mid_frame:
            loop.mid_frame, ask = None, loop.mid_frame
            ask()

    monkeypatch.setattr(sdl_input, "pump", pump)
    app._draw = draw
    loop.task = asyncio.create_task(app._render_loop())
    await asyncio.sleep(0.4)   # the first frame, then quiet
    try:
        yield app, loop
    finally:
        app.exit()
        await asyncio.wait_for(loop.task, 2)


def fresh(loop):
    loop.passes, loop.frames = 0, []
    return time.monotonic()


async def first_frame_after(loop, t0, limit=2.0):
    while time.monotonic() - t0 < limit:
        if loop.frames:
            return loop.frames[0] - t0
        await asyncio.sleep(0.005)
    return None


def on_another_thread(fn):
    t = threading.Thread(target=fn)
    t.start()
    t.join()


@pytest.mark.parametrize("room", ["play", "art", "music", "blocks", "write"])
def test_idle_screen_draws_nothing_and_polls_slowly(monkeypatch, room):
    async def go():
        async with render_loop(monkeypatch, room=room) as (app, loop):
            fresh(loop)
            await asyncio.sleep(1.0)
            assert loop.frames == [], f"{room} drew {len(loop.frames)} frames with nothing changing"
            assert 4 <= loop.passes <= 20, f"{room} polled {loop.passes} times in a second, expected about 10"
    run(go())


def test_without_evdev_the_window_is_polled_every_frame(monkeypatch):
    """Dev machines type through SDL, so the loop can't sleep between polls there."""
    async def go():
        async with render_loop(monkeypatch, evdev=False) as (app, loop):
            fresh(loop)
            await asyncio.sleep(0.5)
            assert loop.passes >= 20, f"polled {loop.passes} times in half a second, expected about 30"
            assert loop.frames == []
    run(go())


def test_redraw_request_wakes_the_loop_at_once(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            t0 = fresh(loop)
            app.invalidate()
            assert (await first_frame_after(loop, t0)) < PROMPT
    run(go())


def test_redraw_request_from_another_thread_wakes_the_loop_at_once(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            t0 = fresh(loop)
            on_another_thread(app.invalidate)
            assert (await first_frame_after(loop, t0)) < PROMPT
    run(go())


def test_key_press_on_an_idle_screen_draws_at_once(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            t0 = fresh(loop)
            await press(app, "a")
            assert (await first_frame_after(loop, t0)) < PROMPT
            assert app.room.field.value.endswith("a")
    run(go())


def test_window_event_repaints_within_the_idle_poll(monkeypatch):
    """SDL can't wake the loop, so a repaint it asks for waits for the next poll, never longer."""
    async def go():
        async with render_loop(monkeypatch) as (app, loop):
            t0 = fresh(loop)
            loop.window_event = True
            took = await first_frame_after(loop, t0)
            assert took is not None and took < app_module.IDLE_POLL_S + 0.1
    run(go())


@pytest.mark.parametrize("from_thread", [False, True])
def test_request_made_during_a_frame_gets_its_own_frame(monkeypatch, from_thread):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            loop.mid_frame = (lambda: on_another_thread(app.invalidate)) if from_thread else app.invalidate
            t0 = fresh(loop)
            app.invalidate()
            await asyncio.sleep(0.3)
            assert len(loop.frames) == 2, f"expected the mid-frame request to draw again, got {len(loop.frames)} frames"
            assert loop.frames[1] - t0 < PROMPT * 2
    run(go())


def test_toast_leaves_on_time_while_idle(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            app.notify("Hello", timeout=0.3)
            await asyncio.sleep(0.1)
            t0 = fresh(loop)
            await asyncio.sleep(0.4)
            assert app._toasts == []
            assert len(loop.frames) == 1, "the toast's exit should be exactly one frame"
            assert loop.frames[0] - t0 < 0.2 + PROMPT
    run(go())


def test_a_headless_screenshot_leaves_out_a_toast_whose_time_is_up(tmp_path):
    """e2e runs screenshot a harness app with no render loop; an old "Added" toast stayed in every shot."""
    async def go():
        app = make_app()
        app.notify("Added purple-sunny-otter", timeout=3).expires = time.monotonic() - 1
        kept = app.notify("Still here", timeout=3)
        app.screenshot(str(tmp_path / "shot.png"))
        assert app._toasts == [kept]
    run(go())


def test_save_flash_animates_to_its_end_then_stops(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            fresh(loop)
            app._save_flash_at = time.monotonic()
            app.invalidate()
            await asyncio.sleep(app_module.SAVE_FLASH_S + 0.2)
            assert app._save_flash_at is None
            assert len(loop.frames) >= 10, f"the flash fade drew only {len(loop.frames)} frames"
            fresh(loop)
            await asyncio.sleep(0.3)
            assert loop.frames == []
    run(go())


def test_music_note_lights_then_goes_dark_on_time(monkeypatch):
    """A timer turns the note's label off a second later; that timer has to wake the loop."""
    async def go():
        async with render_loop(monkeypatch, room="music", poll=SLOW_POLL) as (app, loop):
            t0 = fresh(loop)
            await press(app, "a")
            await asyncio.sleep(1.3)
            assert len(loop.frames) >= 2
            assert 0.9 < loop.frames[-1] - t0 < 1.3, "the note label didn't clear when its timer fired"
            assert not app.room._note_labels
            await asyncio.sleep(2.0)   # the legend's fade and the Time Travel step land in here too
            fresh(loop)
            await asyncio.sleep(0.5)
            assert loop.frames == [], "Music kept redrawing after the note"
    run(go())


def test_held_enter_animates_the_music_hold_bar(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, room="music", poll=SLOW_POLL) as (app, loop):
            fresh(loop)
            await press(app, "enter", hold=0.8)
            assert len(loop.frames) >= 10, f"the hold bar drew only {len(loop.frames)} frames"
    run(go())


def test_typing_fast_draws_at_most_one_frame_per_tick(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            t0 = fresh(loop)
            for c in "abcdefghijklmnopqrst":
                await press(app, c)
            await asyncio.sleep(0.2)
            elapsed = time.monotonic() - t0
            assert loop.frames, "typing drew nothing"
            assert len(loop.frames) <= elapsed * 60 + 2
            assert app.room.field.value.endswith("abcdefghijklmnopqrst")
    run(go())


def test_exit_while_idle_stops_the_loop_at_once(monkeypatch):
    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            t0 = time.monotonic()
            app.exit()
            await asyncio.wait_for(loop.task, PROMPT)
            assert time.monotonic() - t0 < PROMPT
    run(go())


def test_redraw_request_before_the_loop_starts_is_not_lost():
    async def go():
        app = make_app(room="play")
        app._mark_ui_ready = lambda: None
        app.g.dirty = False
        app.invalidate()
        assert app.g.dirty
        drawn = []
        real = app._draw
        app._draw = lambda: (drawn.append(1), real())
        task = asyncio.create_task(app._render_loop())
        await asyncio.sleep(0.1)
        app.exit()
        await asyncio.wait_for(task, 1)
        assert drawn
    run(go())


def test_wake_from_a_worker_after_the_loop_closed_is_harmless():
    """A worker thread can outlive the app; its late redraw request must not raise."""
    async def go():
        app = make_app(room="play")
        app._mark_ui_ready = lambda: None
        task = asyncio.create_task(app._render_loop())
        await asyncio.sleep(0.05)
        app.exit()
        await asyncio.wait_for(task, 1)
        return app
    app = run(go())
    on_another_thread(app.invalidate)


def test_signal_exit_while_idle_stops_the_loop_at_once(monkeypatch):
    """SIGTERM runs app.exit() on the loop thread while it waits in epoll; that wait must end now, not at its timeout."""
    import os
    import signal

    async def go():
        async with render_loop(monkeypatch, poll=SLOW_POLL) as (app, loop):
            old = signal.signal(signal.SIGUSR2, lambda s, f: app.exit())
            try:
                sent = []
                threading.Timer(0.2, lambda: (sent.append(time.monotonic()), os.kill(os.getpid(), signal.SIGUSR2))).start()
                await asyncio.wait_for(asyncio.shield(loop.task), 2.0)
                assert time.monotonic() - sent[0] < PROMPT, "the loop slept out its poll after the signal"
            finally:
                signal.signal(signal.SIGUSR2, old)
    run(go())
