import pytest


@pytest.fixture(autouse=True)
def _drawing_never_asks_for_a_frame(monkeypatch):
    """The render loop sleeps until something asks for a frame, so a draw that asked for
    another would repaint an idle screen forever. Every canvas test that draws checks it."""
    from purple_tui.canvas.app import PurpleApp
    real = PurpleApp._draw

    def checked(self):
        before, self.g.dirty = self.g.dirty, False
        real(self)
        asked = self.g.dirty
        self.g.dirty = before or asked
        assert not asked, "drawing asked for another frame, so an idle screen would never stop redrawing"

    monkeypatch.setattr(PurpleApp, "_draw", checked)
