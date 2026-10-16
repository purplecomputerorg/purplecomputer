"""A dialog's hint line sits below everything its body draws, at any screen size."""

import pytest

from purple_tui.canvas.harness import make_app, run
from purple_tui.canvas.rooms.parent_menu import LanguageScreen, ParentVolumeModal, SecondLanguageScreen
from purple_tui.canvas.ui import Confirm


def _body_bottom_and_hint_top(app, dialog):
    g = app.g
    drawn, hint_tops = [], []
    rect, text, markup = g.rect, g.draw_text, g.draw_markup

    def spy_markup(m, px, x, y, *a, **k):
        h = markup(m, px, x, y, *a, **k)
        (hint_tops if m == dialog.hint else drawn).append(y if m == dialog.hint else y + h)
        return h

    def spy_text(*a, **k):
        r = text(*a, **k)
        drawn.append(r.bottom)
        return r

    def spy_rect(color, box, *a, **k):
        if not k.get("width"):
            drawn.append(box[1] + box[3])
        return rect(color, box, *a, **k)

    g.rect, g.draw_text, g.draw_markup = spy_rect, spy_text, spy_markup
    try:
        dialog.draw(g)
    finally:
        g.rect, g.draw_text, g.draw_markup = rect, text, markup
    drawn = [y for y in drawn if y < dialog.box.bottom - 1]  # the window frame itself
    return max(drawn), hint_tops[0]


@pytest.mark.parametrize("size", [(1366, 768), (1024, 768), (1280, 800), (1920, 1080)])
@pytest.mark.parametrize("make", [SecondLanguageScreen, LanguageScreen, ParentVolumeModal,
                                  lambda app: Confirm(app, "Erase everything?", "This cannot be undone, and every saved drawing goes away too.")])
def test_hint_never_overlaps_body(size, make):
    async def go():
        app = make_app(size)
        dialog = make(app)
        if hasattr(dialog, "selected"):
            dialog.selected = len(dialog.options) - 1
        bottom, hint_top = _body_bottom_and_hint_top(app, dialog)
        assert bottom <= hint_top
    run(go())
