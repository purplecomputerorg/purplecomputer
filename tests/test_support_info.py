"""The canvas Support info screen offers the same Sound check as the shipping screen, and its pages wrap long lines inside their box."""
import pytest

from purplecomputer import sound_check
from purplecomputer.harness import make_app, press, run
from purplecomputer.rooms.support_info import SoundCheckScreen, SupportInfoScreen


def test_support_info_offers_a_sound_check():
    assert [label for _, label in SupportInfoScreen.OPTIONS] == ["Device info", "Audio info", "Sound check", "Printer check"]


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



def _printer_check(report_lines, monkeypatch):
    """A Printer check whose test page didn't print, drawn once with a report of that many lines."""
    from purplecomputer.rooms.support_info import PrinterCheckScreen
    monkeypatch.setattr(PrinterCheckScreen, "on_open", lambda self: None)
    app = make_app((1366, 768))
    page = PrinterCheckScreen(app)
    app.push(page)
    page.printed = False
    page._show("\n".join(f"line {i}" for i in range(report_lines)))
    g, drawn, orig = app.g, [], app.g.draw_text
    g.draw_text = lambda text, *a, **k: drawn.append(text) or orig(text, *a, **k)
    page.draw(g)
    page.draw(g)  # the banner follows what the first draw found fits
    g.draw_text = orig
    return page, drawn


def test_printer_check_shrinks_its_report_to_fit_one_photo(monkeypatch):
    async def go():
        page, drawn = _printer_check(30, monkeypatch)
        assert "line 29" in drawn and page.headline()[1].startswith("Take a photo") and not page.pager
    run(go())


def test_a_report_too_long_for_a_photo_asks_for_a_video_and_turns_its_pages(monkeypatch):
    async def go():
        page, drawn = _printer_check(80, monkeypatch)
        assert "line 79" not in drawn and page.pager
        pages = -(-79 // (page.rows - 1))
        assert page.headline()[1].startswith(f"Record a {pages * 5}-second video")
        seen = set()
        for _ in range(pages):
            seen.update(page.lines[page.offset:page.offset + page.rows])
            page._next_page()
        assert len(seen) == 80 and page.offset == 0
        await press(page.app, "down")
        page.draw(page.app.g)
        assert not page.pager  # the arrows take over
    run(go())
