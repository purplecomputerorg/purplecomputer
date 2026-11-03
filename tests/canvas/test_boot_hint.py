"""The boot hint: a card over the first room until the first key, which still does what it always does."""

from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.room_picker import RoomPicker
from purple_tui.canvas.rooms.sleep_screen import LiveBootSplash


def _booted():
    app = make_app(room="art")
    app.boot_hint = True
    return app


def test_the_first_key_clears_the_hint_and_still_paints():
    async def go():
        app = _booted()
        await press(app, "r")
        assert not app.boot_hint and app.rooms["art"]._cursor_x == 1
    run(go())


def test_the_key_that_closes_the_splash_leaves_the_hint_up():
    async def go():
        app = _booted()
        app.push(LiveBootSplash(app))
        await press(app, "enter")
        assert app.top is None and app.boot_hint
        await press(app, "a")
        assert not app.boot_hint
    run(go())


def test_esc_clears_the_hint_and_opens_the_room_picker():
    async def go():
        app = _booted()
        await press(app, "escape")
        assert not app.boot_hint and isinstance(app.top, RoomPicker)
    run(go())


def test_the_card_draws_with_and_without_the_esc_line():
    async def go():
        app = _booted()
        for littles in (None, "art"):   # Littles Mode has one room, so no Esc line
            app._littles_mode = littles
            app._draw()
    run(go())
