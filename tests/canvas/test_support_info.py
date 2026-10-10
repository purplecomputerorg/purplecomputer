"""The canvas Support info screen offers the same Sound check as the shipping screen."""
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
