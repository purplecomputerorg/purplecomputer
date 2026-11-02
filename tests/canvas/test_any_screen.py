"""Every screen shows the same picture: units measure the 16:9 stage, and Art's grid
fills the viewport in whole cells with its hint row lined up under it."""

import pytest

from purple_tui.canvas.harness import make_app, run
from purple_tui.constants import ART_BAND_UNITS, ART_COLS, ART_ROWS, ART_SIDE_UNITS

SCREENS = [(1024, 768), (1280, 800), (1366, 768), (1440, 900), (1920, 1080), (2256, 1504), (2560, 1080)]


@pytest.mark.parametrize("size", SCREENS)
def test_art_fills_the_frame_in_whole_cells(size):
    async def go():
        app = make_app(size=size, room="art")
        app._draw()
        return app
    app = run(go())
    art, u, vp = app.room, app.unit, app._viewport_rect()
    assert art._cell == u
    assert art._origin == (vp.x + ART_SIDE_UNITS * u, vp.y + ART_BAND_UNITS * u)
    assert (art.bar_foot.x, art.bar_foot.w) == (art._origin[0], ART_COLS * u)
    assert vp.size == ((ART_COLS + 2 * ART_SIDE_UNITS) * u, (ART_ROWS + 2 * ART_BAND_UNITS) * u)


@pytest.mark.parametrize("size", SCREENS)
def test_chrome_scales_with_the_frame(size):
    async def go():
        return make_app(size=size).g
    g = run(go())
    assert abs(g.stage.w / g.stage.h - 16 / 9) < 0.01
    assert all(abs(c - s / 2) <= 1 for c, s in zip(g.stage.center, size))
    assert g.em(10) == round(g.stage.w * 0.13)


@pytest.mark.parametrize("size", SCREENS)
def test_full_screen_text_is_centered(size):
    from purple_tui.canvas.rooms.sleep_screen import FullScreen

    async def go():
        app = make_app(size=size)
        screen = FullScreen(app)
        screen.message, screen.status = "Sleeping", "Battery. Shuts off in about 1 hr."
        screen.draw(app.g)
        return app.g
    g = run(go())
    bg = g.surface.get_at((0, 0))
    cols = [x for x in range(g.w) if any(g.surface.get_at((x, y)) != bg for y in range(0, g.h, 2))]
    assert abs((cols[0] + cols[-1]) / 2 - g.w / 2) <= g.vw(0.5)
