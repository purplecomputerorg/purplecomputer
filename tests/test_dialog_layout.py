"""A dialog's hint line sits below everything its body draws, at any screen size."""

import pytest

from purplecomputer import ui
from purplecomputer.harness import make_app, run
from purplecomputer.rooms.parent_menu import (EmptyInstallOverScreen, InstallOverScreen, LanguageScreen, ParentVolumeModal,
                                              ReinstallConfirmScreen, SecondLanguageScreen)
from purplecomputer.ui import Confirm


def _body_bottom_and_hint_top(app, dialog):
    g = app.g
    drawn, hint_tops = [], []
    rect, text, markup, hint = g.rect, g.draw_text, g.draw_markup, ui.draw_key_lines

    def spy_markup(m, px, x, y, *a, **k):
        h = markup(m, px, x, y, *a, **k)
        drawn.append(y + h)
        return h

    def spy_hint(g_, t, px, cx, y, *a, **k):
        hint_tops.append(y)
        n = len(drawn)
        h = hint(g_, t, px, cx, y, *a, **k)
        del drawn[n:]
        return h

    def spy_text(*a, **k):
        r = text(*a, **k)
        drawn.append(r.bottom)
        return r

    def spy_rect(color, box, *a, **k):
        if not k.get("width"):
            drawn.append(box[1] + box[3])
        return rect(color, box, *a, **k)

    g.rect, g.draw_text, g.draw_markup, ui.draw_key_lines = spy_rect, spy_text, spy_markup, spy_hint
    try:
        dialog.draw(g)
    finally:
        g.rect, g.draw_text, g.draw_markup, ui.draw_key_lines = rect, text, markup, hint
    drawn = [y for y in drawn if y < dialog.box.bottom - 1]  # the window frame itself
    return max(drawn), hint_tops[0]


@pytest.mark.parametrize("size", [(1366, 768), (1024, 768), (1280, 800), (1920, 1080)])
@pytest.mark.parametrize("make", [SecondLanguageScreen, LanguageScreen, ParentVolumeModal,
                                  InstallOverScreen, EmptyInstallOverScreen, ReinstallConfirmScreen,
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


def test_a_note_under_one_option_leaves_the_others_one_line_tall():
    async def go():
        app = make_app()
        dialog, g = InstallOverScreen(app), app.g
        plain, noted = (dialog._row_height(g, o) for o in dialog.options[1:])
        assert plain == ui.Picker(app, [(1, "a")]).option_height(g) < noted
        rows = dialog.body_height(g) - dialog._desc_height(g) - dialog._gaps(g)
        assert rows == 2 * plain + noted + 3 * g.em(0.3)
    run(go())
