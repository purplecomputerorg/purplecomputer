"""Studio's in-browser Purple draws emoji from pictures `just studio-bundle` pulls out of the ISO's Noto
(purplecomputer/emoji_pictures.py); they must look like pygame drawing that font, as Purple does."""

import json
from pathlib import Path

import numpy as np
import pygame
import pytest

from purplecomputer import harness  # noqa: F401  (sets SDL dummy drivers)
from purplecomputer.emoji_pictures import EmojiPictures
from purplecomputer.gfx import EMOJI_NATIVE_PX

CACHE = Path(__file__).resolve().parents[1] / "studio" / ".cache"
EMOJI = CACHE / "emoji"
if not (EMOJI / "map.json").exists():
    pytest.skip("no emoji pictures: run `just studio-bundle`", allow_module_level=True)
VERSION = json.loads((EMOJI / "map.json").read_text())["version"]
FONT = CACHE / "noto" / f"{VERSION}.ttf"


@pytest.fixture(scope="module")
def pictures():
    pygame.display.set_mode((1, 1))
    pygame.font.init()
    return EmojiPictures(EMOJI)


def premultiplied(surface: pygame.Surface) -> np.ndarray:
    rgba = np.dstack([pygame.surfarray.array3d(surface), pygame.surfarray.array_alpha(surface)]).astype(int)
    return np.dstack([rgba[..., :3] * rgba[..., 3:] // 255, rgba[..., 3]])


@pytest.mark.parametrize("run", ["⭐", "👍🏽", "👨‍👩‍👧", "🇺🇸", "❤️", "🏳️‍🌈", "🦸‍♀️", "🦸‍♀", "⭐🦊🏠", "🫹🏻", "✅"])
def test_pictures_draw_like_pygame_draws_the_font(pictures, run):
    font = pygame.font.Font(str(FONT), EMOJI_NATIVE_PX)
    expected = font.render(run, True, (255, 255, 255)).convert_alpha()
    drawn = pictures.render(run)
    assert drawn.get_size() == expected.get_size()
    # Only rounding where SDL converts the color bitmap's edges differs.
    assert np.abs(premultiplied(drawn) - premultiplied(expected)).mean() < 1


def test_an_emoji_sequence_is_one_picture_with_or_without_vs16(pictures):
    assert len(pictures.glyphs_for("🦸‍♀️")) == len(pictures.glyphs_for("🦸‍♀")) == 1
    assert pictures.glyphs_for("🦸‍♀️") == pictures.glyphs_for("🦸‍♀")


def test_keycaps_stay_text_as_on_purple():
    from purplecomputer.gfx import split_runs

    assert split_runs("1️⃣") == [("1️⃣", False)]
