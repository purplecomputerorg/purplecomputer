"""Animations that redraw only their part of the screen (app.partial_redraws, off until measured): each
part drawn alone matches the same part of the whole screen."""

import time
import types

import pygame

from purplecomputer import ui
from purplecomputer.harness import make_app, run
from purplecomputer.rooms import art_room, music_room
from purplecomputer.rooms.admin_autorun import painting


def _freeze(monkeypatch, *modules) -> float:
    """The modules' clock stopped, so the whole screen and the part redrawn alone show the same moment."""
    now = time.monotonic()
    still = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")} | {"monotonic": lambda: now})
    for module in modules:
        monkeypatch.setattr(module, "time", still)
    return now


def _screen(app) -> bytes:
    return pygame.image.tobytes(app.g.surface, "RGB")


def _matches_whole(app, patch):
    """`patch()` over a blacked out copy of its rect paints back what the whole screen has there."""
    app._draw()
    whole = _screen(app)
    rect = patch()
    assert rect
    app.g.surface.fill((0, 0, 0), rect)
    assert patch() == rect and _screen(app) == whole


def test_partial_redraws_are_off_until_turned_on():
    async def go():
        app = make_app()
        app.g.dirty = False
        app.animate(app.room_patch)
        assert app.g.dirty and not app.g.patches
        app.g.dirty, app.partial_redraws = False, True
        app.animate(app.room_patch)
        assert not app.g.dirty and app.g.patches
    run(go())


def test_a_filling_hold_bar_redraws_alone(monkeypatch):
    async def go():
        app = make_app(room="blocks")
        now = _freeze(monkeypatch, ui)
        hold = app.room.enter_hold
        hold.down()
        hold._down_at = now - 0.6
        _matches_whole(app, app.hold_bar_patch)
        hold.up()
    run(go())


def test_a_music_key_change_redraws_only_the_room(monkeypatch):
    async def go():
        app = make_app(room="music")
        _freeze(monkeypatch, music_room)
        room = app.room
        room.set_key(room.root_index + 1)
        room._transition["start"] -= 0.1
        _matches_whole(app, app.room_patch)
    run(go())


def test_arts_pen_and_fade_redraw_only_the_room(monkeypatch):
    async def go():
        app = make_app(room="art")
        _freeze(monkeypatch, art_room)
        room = app.room
        room.restore_timeline_state(painting())
        room._set_pen(True)
        room._lift = 0.5
        _matches_whole(app, app.room_patch)
        room._fade_next_line()
        room._fade["since"] -= 0.2
        _matches_whole(app, app.room_patch)
        room.on_leave()
    run(go())
