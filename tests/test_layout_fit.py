"""Nothing in the chrome covers anything else, on every screen shape a laptop
might have: the status strip's parts sit side by side, the header's pills and
arrow hint sit side by side, and the hold bar stays under the room's canvas."""

import pytest

from purplecomputer import ui
from purplecomputer.harness import make_app, run
from purplecomputer.rooms.art_room import ROWS

SIZES = [(1024, 768), (1280, 800), (1366, 768), (1440, 900), (1920, 1080), (2560, 1080), (3440, 1440), (2560, 1600)]
ROOMS = ["play", "music", "art", "blocks"]


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("legend", [False, True])
def test_status_strip_parts_never_overlap(size, legend):
    async def go():
        app = make_app(size)
        app._legend_visible = legend
        frame = app._frame_rect(app._viewport_rect())
        for room in ROOMS:
            app.action_switch_room(room)
            for left in ("Keyboard only, on purpose", ""):
                _, parts = app._status_layout(frame, left)
                row = [parts["left"], parts["esc"], *(r for *_, r in parts["tabs"]), parts["right"]]
                assert row[0].left >= frame.left and row[-1].right <= frame.right, (room, left)
                for a, b in zip(row, row[1:]):
                    assert a.right <= b.left, (room, left, a, b)
            app._draw()
    run(go())


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_hold_bar_stays_under_the_art_canvas(size):
    async def go():
        app = make_app(size)
        app._code_panel_enabled = True
        app.action_switch_room("art")
        app._draw()
        art = app.rooms["art"]
        canvas_bottom = art._origin[1] + ROWS * art._cell
        assert canvas_bottom <= app._viewport_rect().bottom - art.footer_h(app.g)
    run(go())


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_header_pills_and_arrow_hint_never_overlap(size, monkeypatch):
    pills = []
    real = ui.header_pill

    def spy(g, *args):
        pill, pad = real(g, *args)
        if g.surface.get_width() > 1:   # not a measuring pass
            pills.append(pill)
        return pill, pad
    monkeypatch.setattr(ui, "header_pill", spy)

    async def go():
        app = make_app(size)
        for room in ROOMS + ["write"]:
            app.action_switch_room(room)
            pills.clear()
            app._draw()
            row = sorted(pills, key=lambda r: r.x)
            assert row and (row[-1].right == app.room.header_row.right or not app.arrow_chip_hint()), room   # the arrow chip ends the row
            for a, b in zip(row, row[1:]):
                assert a.right <= b.left, (room, a, b)
    run(go())
