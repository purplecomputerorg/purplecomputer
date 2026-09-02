"""Toast reaper timer lifecycle.

The reaper exists because Textual's own toast expiry has failed three ways
historically (dropped timer callbacks under evdev load, toasts hidden on
backgrounded screens, has_expired never flipping). It now runs only while
toasts exist: _on_notify starts the interval and the reaper stops it after
two consecutive toast-free ticks, so an idle app has no 1 Hz wakeup but a
toast still mounting under load isn't orphaned.
"""

import asyncio
import os
import time
from types import SimpleNamespace

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from purple_tui.purple_tui import PurpleApp
from purple_tui.constants import REQUIRED_TERMINAL_ROWS


class _FakeTimer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _FakeScreen:
    def __init__(self, toasts):
        self._toasts = toasts

    def query(self, _cls):
        return self._toasts


def _app_with(toasts):
    return SimpleNamespace(
        screen_stack=[_FakeScreen(toasts)],
        _toast_empty_ticks=0,
        _toast_reaper_timer=_FakeTimer(),
    )


def _tick(app):
    PurpleApp._reap_stale_toasts(app)


def test_timer_survives_one_empty_tick_then_stops():
    app = _app_with([])
    _tick(app)
    assert app._toast_reaper_timer is not None and not app._toast_reaper_timer.stopped
    timer = app._toast_reaper_timer
    _tick(app)
    assert timer.stopped
    assert app._toast_reaper_timer is None


def test_visible_toast_resets_the_empty_count():
    toast = SimpleNamespace(_purple_first_seen=None)
    app = _app_with([toast])
    _tick(app)  # stamps the toast, counts as seen
    assert app._toast_empty_ticks == 0
    app.screen_stack = [_FakeScreen([])]
    _tick(app)
    assert app._toast_empty_ticks == 1
    assert not app._toast_reaper_timer.stopped


def test_arm_resets_ticks_even_when_timer_already_running():
    """A notify mid-countdown must restart the mounting grace, or the timer
    could stop before the new toast appears and orphan it."""
    created = []
    app = SimpleNamespace(
        _toast_empty_ticks=1,
        _toast_reaper_timer=_FakeTimer(),
        set_interval=lambda *a, **k: created.append(a),
    )
    PurpleApp._arm_toast_reaper(app)
    assert app._toast_empty_ticks == 0
    assert created == []  # existing timer kept, not duplicated


def test_toast_on_backgrounded_screen_keeps_timer_alive():
    """The May 2026 modal bug: toasts under a pushed screen must still count."""
    toast = SimpleNamespace(_purple_first_seen=None)
    app = _app_with([])
    app.screen_stack = [_FakeScreen([toast]), _FakeScreen([])]  # toast under a modal
    _tick(app)
    assert app._toast_empty_ticks == 0
    assert not app._toast_reaper_timer.stopped


async def _wait_until(cond, timeout=8.0):
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    assert cond()


def test_toast_lifecycle_end_to_end():
    """Real app: a toast appears, hides by its timeout, the reaper timer
    stops itself afterwards, and a later notify re-arms it."""
    from textual.widgets._toast import Toast

    def toast_count(app):
        return sum(len(screen.query(Toast)) for screen in app.screen_stack)

    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=(146, REQUIRED_TERMINAL_ROWS),
                                notifications=True) as pilot:
            await pilot.pause()
            assert app._toast_reaper_timer is None

            app.notify("hello", timeout=0.5)
            await _wait_until(lambda: toast_count(app) > 0)
            assert app._toast_reaper_timer is not None

            await _wait_until(lambda: toast_count(app) == 0)  # toast hides
            await _wait_until(lambda: app._toast_reaper_timer is None)  # timer stops

            app.notify("again", timeout=0.5)
            await pilot.pause()
            assert app._toast_reaper_timer is not None  # re-armed
            await _wait_until(lambda: app._toast_reaper_timer is None)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()
