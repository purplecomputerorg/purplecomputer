"""Footer (RoomIndicator) layout regressions: the center room badges must stay
centered whether or not the mute badge shows, the Art arrow hint must align to
the right viewport border and only appear in Art, and a muted-at-startup volume
must surface the mute badge."""

import asyncio
import os

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

import purple_tui.settings as settings
from purple_tui.purple_tui import PurpleApp, RoomIndicator
from purple_tui.constants import REQUIRED_TERMINAL_ROWS
from textual.widgets import Static

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _setup(pilot):
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()


async def _switch_room(app, pilot, room_id):
    app.action_switch_room(room_id)
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    app._align_footer_to_viewport()
    await pilot.pause()


async def _set_mute(app, pilot, muted):
    ind = app.query_one("#room-indicator", RoomIndicator)
    ind.update_volume_indicator(0 if muted else 80)
    await pilot.pause()
    app._align_footer_to_viewport()
    await pilot.pause()


def _center_midpoint(app):
    c = app.query_one("#keys-center").region
    return c.x + c.width / 2


class TestCenterStaysCentered:
    def test_centered_in_art_unmuted(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")
                await _set_mute(app, pilot, muted=False)
                mid = _center_midpoint(app)
                assert abs(mid - app.size.width / 2) <= 1, (
                    f"center group not centered: mid={mid} screen_mid={app.size.width / 2}"
                )
        _run(_test())

    def test_centered_in_art_when_muted(self):
        """Regression: the mute badge used to sit outside the right spacer and
        shove the center group left when it appeared."""
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")
                await _set_mute(app, pilot, muted=False)
                mid_unmuted = _center_midpoint(app)
                await _set_mute(app, pilot, muted=True)
                mid_muted = _center_midpoint(app)
                assert abs(mid_muted - app.size.width / 2) <= 1, (
                    f"center group decentered when muted: mid={mid_muted}"
                )
                assert mid_muted == mid_unmuted, (
                    f"muting shifted the center group: {mid_unmuted} -> {mid_muted}"
                )
        _run(_test())


class TestArrowHintAlignment:
    def test_arrow_hint_at_right_border_unmuted(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")
                await _set_mute(app, pilot, muted=False)
                wrapper = app.query_one("#viewport-wrapper")
                hint = app.query_one("#art-arrow-hint", Static)
                # Mirrors the left hint's wrapper-relative inset against the right border.
                assert abs(hint.region.right - (wrapper.region.right - 6)) <= 1, (
                    f"arrow hint not at right border: right={hint.region.right} "
                    f"wrapper_right={wrapper.region.right}"
                )
        _run(_test())

    def test_mute_takes_border_and_arrow_slides_left(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                await _switch_room(app, pilot, "art")
                await _set_mute(app, pilot, muted=False)
                arrow_border = app.query_one("#art-arrow-hint", Static).region.right
                await _set_mute(app, pilot, muted=True)
                mute = app.query_one("#key-mute")
                hint = app.query_one("#art-arrow-hint", Static)
                assert mute.display
                assert mute.region.right == arrow_border, (
                    f"mute badge not at border: {mute.region.right} vs {arrow_border}"
                )
                assert hint.region.right < mute.region.x, (
                    "arrow cluster should sit left of the mute badge with a gap"
                )
        _run(_test())


class TestArrowHintArtOnly:
    def test_present_in_art_absent_elsewhere(self):
        async def _test():
            app = PurpleApp()
            async with app.run_test(size=APP_SIZE) as pilot:
                await _setup(pilot)
                hint = app.query_one("#art-arrow-hint", Static)

                await _switch_room(app, pilot, "art")
                assert "Arrows move" in str(hint.render())

                await _switch_room(app, pilot, "play")
                assert str(hint.render()) == ""

                await _switch_room(app, pilot, "music")
                assert str(hint.render()) == ""
        _run(_test())


class TestMuteBadgeAtStartup:
    def test_muted_volume_shows_badge_on_mount(self):
        """Regression: starting at volume 0 left the mute badge hidden because
        on_mount never refreshed the indicator."""
        async def _test():
            original = settings.get_volume_level
            settings.get_volume_level = lambda: 0
            try:
                app = PurpleApp()
                async with app.run_test(size=APP_SIZE) as pilot:
                    await _setup(pilot)
                    assert app._effective_volume() == 0
                    assert app.query_one("#key-mute").display, (
                        "mute badge should be visible when the app starts muted"
                    )
            finally:
                settings.get_volume_level = original
        _run(_test())
