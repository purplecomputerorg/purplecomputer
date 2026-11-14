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


def _sleep_text(app):
    from purple_tui.canvas.rooms.sleep_screen import FullScreen
    screen = FullScreen(app)
    screen.message, screen.status = "Sleeping", "Battery. Shuts off in about 1 hr."
    return screen


def _install(phase, diag=()):
    def make(app):
        from purple_tui.canvas.rooms.parent_menu import InstallProgressScreen
        screen = InstallProgressScreen(app)
        screen._phase, screen._diag_lines = phase, list(diag)
        return screen
    return make


FULL_SCREENS = {"sleep": (_sleep_text, True), "installing": (_install("installing"), True),
                "install_error": (_install("error"), True), "install_diag": (_install("error", ["diag line"]), False)}


@pytest.mark.parametrize("size", SCREENS)
@pytest.mark.parametrize("name", FULL_SCREENS)
def test_full_screens_sit_on_the_stage(size, name):
    make, centered = FULL_SCREENS[name]

    async def go():
        app = make_app(size=size)
        make(app).draw(app.g)
        return app.g
    g = run(go())
    bg = g.surface.get_at((0, 0))
    ink = [(x, y) for x in range(0, g.w, 2) for y in range(0, g.h, 2) if g.surface.get_at((x, y)) != bg]
    xs, ys = [x for x, _ in ink], [y for _, y in ink]
    assert g.stage.inflate(4, 4).collidepoint(min(xs), min(ys)) and g.stage.inflate(4, 4).collidepoint(max(xs), max(ys))
    if centered:
        assert abs((min(xs) + max(xs)) / 2 - g.w / 2) <= g.vw(0.5)
