import pygame

from purplecomputer.harness import make_app, run, type_text
from purplecomputer.quake import FALL_S, SHAKE_S, TOTAL_S, Quake, is_quake


def test_word():
    assert is_quake("Earthquake!") and is_quake(" earthquake ")
    assert not is_quake("earthquakes") and not is_quake("big earthquake")


def test_play_earthquake_falls_and_comes_back():
    async def go():
        app = make_app(room="play")
        await type_text(app, "cat dog", enter=True)
        await type_text(app, "earthquake", enter=True)
        quake = app.top
        assert isinstance(quake, Quake)
        app._draw()
        before = pygame.image.tobytes(quake.ground, "RGB")
        assert quake.pieces and before
        for t in (0.5, SHAKE_S + 0.3, SHAKE_S + FALL_S, TOTAL_S - 0.4):
            quake.advance(t)
            app._draw()
        assert all(p.resting for p in quake.pieces)
        piled = [p for p in quake.pieces if p.inside]
        assert piled and max(p.y + p.home.h for p in piled) <= quake.inner.bottom
        quake.advance(TOTAL_S)
        assert all(quake._pose(p, k)[:2] == (p.home.x, p.home.y) for k, p in enumerate(quake.pieces))
        quake.close()
        assert not app.top and not quake._tick_handle.active
    run(go())
