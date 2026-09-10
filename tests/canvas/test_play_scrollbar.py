"""The Play room's scrollbar: absent until history overflows, thumb at the
bottom while following new answers, climbing as the kid scrolls up."""

import pygame

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.play_room import scroll_thumb

TRACK = pygame.Rect(100, 0, 10, 400)


def test_thumb_fills_the_bottom_when_nothing_is_hidden():
    t = scroll_thumb(TRACK, viewport=100, total=400, hidden=0, min_h=10)
    assert (t.y, t.h, t.bottom) == (300, 100, 400)


def test_thumb_climbs_as_entries_hide_below():
    t = scroll_thumb(TRACK, viewport=100, total=400, hidden=200, min_h=10)
    assert (t.y, t.bottom) == (100, 200)


def test_thumb_never_shorter_than_min_or_past_the_top():
    t = scroll_thumb(TRACK, viewport=5, total=4000, hidden=3999, min_h=24)
    assert t.h == 24 and t.y == TRACK.y


def test_scrollbar_only_when_history_overflows():
    async def go():
        app = make_app()
        room = app.room
        g = app.g
        content = app.content_rect(app._viewport_rect())
        probe = lambda: g.surface.get_at((content.right - g.em(1.25), content.centery))[:3]
        await type_text(app, "cat", enter=True)
        app._draw()
        before = probe()
        for _ in range(14):
            await type_text(app, "cat", enter=True)
        app._draw()
        assert probe() != before
        await press(app, "up")
        app._draw()
        assert room.scroll == 1
    run(go())
