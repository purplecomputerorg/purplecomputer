"""The renderer's text pipeline: markup parsing, emoji splitting, wrapping."""

import pytest

from purple_tui.canvas.gfx import Gfx, is_emoji, parse_markup, split_runs, strip_markup
from purple_tui.palette import contrast_text


@pytest.fixture(scope="module")
def g():
    return Gfx(size=(800, 600), headless=True)


def test_parse_markup_styles_and_pops():
    spans = parse_markup("a [bold #ff0000]b[/] c [on #00ff00]  [/]")
    assert [t for t, _ in spans] == ["a ", "b", " c ", "  "]
    assert spans[1][1] == {"bold": True, "fg": "#ff0000"}
    assert spans[3][1] == {"bg": "#00ff00"}


def test_unknown_tags_and_escapes_are_literal():
    assert strip_markup("cat[dog") == "cat[dog"
    assert strip_markup("\\[x\\]") == "[x\\]"
    assert strip_markup("[red blue") == "[red blue"
    assert strip_markup("[/]") == ""


def test_split_runs_isolates_emoji():
    assert split_runs("cat 🐱 dog") == [("cat ", False), ("🐱", True), (" dog", False)]
    assert split_runs("👨‍👩‍👧🇺🇸") == [("👨‍👩‍👧🇺🇸", True)]
    assert is_emoji("🐱🦖")
    assert not is_emoji("a🐱")


def test_text_and_emoji_render(g):
    assert g.text("Purple", 24).get_width() > 0
    assert g.text("🐱", 24).get_height() > 0
    assert g.text("", 24).get_width() == 0


def test_symbol_fallback_face_covers_arrows(g):
    assert g._covers("symbols", "←⇥▲●░♪")
    assert g.text("← Key C →", 20).get_width() > g.text("Key C", 20).get_width()


def test_layout_wraps_breaks_and_keeps_swatches(g):
    lines = g.layout("one two three four five six", 20, max_width=120)
    assert len(lines) > 1
    lines = g.layout("a\nb\nc", 20)
    assert len(lines) == 3
    lines = g.layout("[on #ff0000]   [/] x", 20)
    assert lines[0][2][0][2] == "#ff0000"   # swatch keeps its background at line start


def test_draw_markup_returns_height(g):
    h = g.draw_markup("hello [bold]world[/]", 20, 10, 10, max_width=400)
    assert h >= g.line_height(20)


def test_contrast_text():
    assert contrast_text("#ffffff") == "#000000"
    assert contrast_text("#000000") == "#FFFFFF"


def test_text_default_symbols_are_emoji_only_with_vs16():
    assert split_runs("◀ back ▶") == [("◀ back ▶", False)]
    assert split_runs("❤️⭐☕") == [("❤️⭐☕", True)]
    assert split_runs("☀") == [("☀", False)]


def test_colored_letters_are_contiguous_square_tiles(g):
    (_, _, pieces), = g.layout("[#000000 on #ffcc00] f [/][#000000 on #ff8888] w [/]", 20)
    assert [bg for _, _, bg in pieces] == ["#ffcc00", "#ff8888"]
    (s1, x1, _), (s2, x2, _) = pieces
    assert s1.get_width() == s1.get_height() == s2.get_width() and x1 + s1.get_width() == x2


def test_wrapped_letter_tiles_stay_whole_and_aligned(g):
    letters = "".join(f"[#000000 on #ffcc00] {c} [/]" for c in "abcdefgh")
    side = g.layout("[#000000 on #ffcc00] a [/]", 20)[0][2][0][0].get_width()
    lines = g.layout(letters, 20, max_width=side * 3 + 1)
    assert [len(p) for _, _, p in lines] == [3, 3, 2]
    assert all(x == i * side for _, _, pieces in lines for i, (_, x, _) in enumerate(pieces))
