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


@pytest.fixture(autouse=True)
def _family_rooms_end_with_the_test(monkeypatch):
    """Leaving a family room keeps its process running for the kid's return; a test's end is the app's."""
    from purple_tui.canvas.rooms.family_room import ProcessGuest
    started, real = [], ProcessGuest.__init__

    def init(self, *args):
        started.append(self)
        real(self, *args)

    monkeypatch.setattr(ProcessGuest, "__init__", init)
    yield
    for guest in started:
        guest.stop()
