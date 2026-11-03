"""The canvas Support info screen offers the same Sound check as the shipping screen, and its pages wrap long lines inside their box."""
import pytest

from purple_tui import sound_check
from purple_tui.canvas.harness import make_app, run
from purple_tui.canvas.rooms.support_info import SoundCheckScreen, SupportInfoScreen


def test_support_info_offers_a_sound_check():
    assert [label for _, label in SupportInfoScreen.OPTIONS] == ["Device info", "Audio info", "Sound check"]


def test_sound_check_screen_shows_the_report(monkeypatch):
    async def go():
        app = make_app()
        screen = SoundCheckScreen(app)
        assert screen.lines[0].startswith("Playing the chime")
        hot = sound_check.SoundCheck(heard=True, tone_db=(-5.0,) * 3, snr_db=40, sink_pct=58, sink_db=-14.0, source_pct=20, source_db=-42.0)
        screen._show(sound_check.report(hot, ["  take one"]))
        assert "heard the chime" in screen.lines[0]
        assert screen.lines[-1] == "  take one"
    run(go())


LONG = ("Readings:\n  sink 58% (-14.2 dB), source 20% (-41.9 dB, base +0.0 dB): tones -79.4 -79.1 -107.1 dBFS"
        " at mic, floor -119.3 dBFS, SNR 16 dB, and then some more words to be sure it wraps twice")


@pytest.mark.parametrize("size", [(1024, 768), (1366, 768), (1920, 1080)])
def test_sound_check_report_stays_in_its_box(size):
    async def go():
        app = make_app(size)
        page = SoundCheckScreen(app)
        page._show(LONG)
        g, drawn, orig = app.g, [], app.g.draw_text
        g.draw_text = lambda *a, **k: drawn.append(orig(*a, **k)) or drawn[-1]
        page.draw(g)
        g.draw_text = orig
        assert all(page.box.contains(r) for r in drawn)
        assert any("SNR" in line for line in page.lines) and len(page.lines) > LONG.count("\n") + 1
    run(go())
