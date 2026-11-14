"""The in-browser Purple's trimmed icon font and glyph lookup (scripts/studio_bundle.py, studio/src/live/browser.py)."""

import io
from bisect import bisect_right

from fontTools.ttLib import TTFont

from purplecomputer import constants
from purplecomputer import gfx
from scripts.studio_bundle import cmap_bounds, loaded_strings, trimmed_font

NERD = gfx.FONT_DIR / gfx.FACES["nerd"]


def kept(text: str) -> set[int]:
    return set(TTFont(io.BytesIO(trimmed_font(NERD, text))).getBestCmap())


def test_icon_built_at_run_time_is_kept(monkeypatch):
    monkeypatch.setattr(constants, "ICON_BUILT", chr(0xF0001), raising=False)
    assert 0xF0001 in kept(loaded_strings())


def test_every_icon_constant_is_kept():
    icons = {ord(c) for name in dir(constants) if name.startswith("ICON_") for c in str(getattr(constants, name))}
    full = set(TTFont(NERD).getBestCmap())
    assert icons & full <= kept(loaded_strings())


def test_bounds_answer_like_the_font():
    data = (gfx.FONT_DIR / gfx.FACES["mono"]).read_bytes()
    bounds, cmap = cmap_bounds(data), set(TTFont(gfx.FONT_DIR / gfx.FACES["mono"]).getBestCmap())
    assert all(bool(bisect_right(bounds, c) % 2) == (c in cmap) for c in range(0x3000))
