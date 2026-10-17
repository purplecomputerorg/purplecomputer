"""A pack's theme.json recolors the canvas UI (the screen's palette, the Art canvas, the letter
rows and their legend) when Purple starts; a pack without one, or a malformed one, leaves
Purple's own colors, and the number row always stays gray."""

import json

import pytest

from purple_tui import content as content_mod
from purple_tui import palette as P
from purple_tui import settings
from purple_tui.canvas import theme, ui
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.rooms import art_room
from purple_tui.content import ContentManager

DEFAULT_Q, DEFAULT_BG, DEFAULT_TEXT, DEFAULT_CANVAS = P.KEY_COLORS["q"], P.BG, P.TEXT, art_room.CANVAS_BG


@pytest.fixture
def themed(tmp_path, monkeypatch):
    """Writes a pack with the given theme.json (or none) and loads it as Purple would."""
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")

    def install(data):
        pack_dir = tmp_path / "packs" / "family"
        (pack_dir / "content").mkdir(parents=True, exist_ok=True)
        (pack_dir / "manifest.json").write_text(json.dumps({"id": "family", "name": "F", "version": "1.0.0", "type": "emoji"}))
        if data is not None:
            (pack_dir / "content" / "theme.json").write_text(json.dumps(data))
        cm = ContentManager(packs_dir=tmp_path / "packs")
        cm.load_all()
        monkeypatch.setattr(content_mod, "_content", cm)
    yield install
    theme.apply({})


def test_a_theme_recolors_the_rows_ground_and_canvas(themed):
    themed({"colors": {"bg": "#0d2233", "text": "#eeeeff"}, "canvas": "#112c40", "keys": {"q": "#11aa22", "a": "#2233cc"}})

    async def go():
        app = make_app()
        assert (P.BG, P.TEXT, P.SURFACE, art_room.CANVAS_BG) == ("#0d2233", "#eeeeff", "#251845", "#112c40")
        assert P.get_key_color("q") == "#11aa22" and P.get_key_color("1") == P.GRAYSCALE["1"]
        app.action_switch_room("art")
        await press(app, "q")
        assert app.rooms["art"]._last_key_color == "#11aa22"
        assert app._legend_key == "q"
    run(go())


def test_no_theme_or_a_bad_one_keeps_purples_colors(themed):
    themed({"colors": {"bg": "red", "text": 7, "banner": "#000000"}, "canvas": "blue", "keys": {"q": "nope", "1": "#000000"}})
    run(_start())
    assert (P.KEY_COLORS["q"], P.BG, P.TEXT, art_room.CANVAS_BG, P.KEY_COLORS["1"]) == (DEFAULT_Q, DEFAULT_BG, DEFAULT_TEXT, DEFAULT_CANVAS, P.GRAYSCALE["1"])
    themed(None)
    run(_start())
    assert P.KEY_COLORS["q"] == DEFAULT_Q


def test_starting_again_without_the_theme_puts_purples_colors_back(themed):
    themed({"colors": {"bg": "#0d2233"}, "keys": {"q": "#11aa22"}})
    run(_start())
    assert P.KEY_COLORS["q"] == "#11aa22"
    theme.apply({})
    assert P.KEY_COLORS["q"] == DEFAULT_Q and P.BG == DEFAULT_BG and P.ROW_LEGEND_COLORS[1] == ["#DF7070", "#BF4040", "#802020"]


def test_keycaps_and_hints_drawn_with_default_colors_follow_the_theme(themed):
    themed({"colors": {"text": "#eeeeff", "dim": "#552233"}})

    async def go():
        g = make_app().g
        cap = ui.draw_key(g, "Tab", 20, 10, 40)
        hint = ui.draw_key_hint(g, "{hold Enter} loop", 20, 10, 100)
        assert tuple(g.surface.get_at((cap.x + 3, cap.centery)))[:3] == P.rgb("#eeeeff")
        assert tuple(g.surface.get_at((hint.x + 3, hint.centery)))[:3] == P.rgb("#552233")
    run(go())


async def _start():
    make_app()
