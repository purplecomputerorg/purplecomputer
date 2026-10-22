"""A pack's word can be one of its own pictures in Play: content/word-pictures.json."""

import json

import pygame
import pytest

from purple_tui import content as content_mod
from purple_tui.canvas.gfx import Gfx
from purple_tui.content import ContentManager, is_word_picture
from purple_tui.play_eval import SimpleEvaluator


@pytest.fixture
def pictures(tmp_path, monkeypatch):
    """A pack mapping biscuit to a red picture, the loaded content, and the path of that picture."""
    content = tmp_path / "packs" / "family" / "content"
    (content / "images").mkdir(parents=True)
    (content.parent / "manifest.json").write_text(json.dumps({"id": "family", "name": "F", "version": "1.0.0", "type": "emoji"}))
    (content / "word-pictures.json").write_text(json.dumps({"biscuit": "biscuit", "ghost": "nope"}))
    (content / "synonyms.json").write_text(json.dumps({"bisky": "biscuit"}))
    red = pygame.Surface((4, 2))
    red.fill((255, 0, 0))
    pygame.image.save(red, str(content / "images" / "biscuit.png"))

    def load():
        cm = ContentManager(packs_dir=tmp_path / "packs")
        cm.load_all()
        monkeypatch.setattr(content_mod, "_content", cm)
        return cm
    return load, content / "images" / "biscuit.png"


def test_a_picture_word_is_a_character_play_treats_like_an_emoji(pictures):
    load, png = pictures
    cm = load()
    char = cm.get_emoji("biscuit")
    assert is_word_picture(char) and cm.word_pictures[char] == png
    assert cm.get_emoji("bisky") == char and cm.get_emoji("ghost") == "👻"
    assert load().get_emoji("biscuit") == char
    assert SimpleEvaluator().evaluate("biscuit * 3") == SimpleEvaluator().evaluate("cat * 3").replace("🐱", char)


def test_the_picture_is_drawn_at_emoji_size_and_a_missing_one_as_a_frame(pictures, monkeypatch):
    load, png = pictures
    char = load().get_emoji("biscuit")
    g = Gfx(size=(800, 600), headless=True)
    drawn = g.text(f"a{char}", 40, tr=False)
    side = round(40 * 1.2)
    assert drawn.get_height() == side
    assert drawn.get_at((drawn.get_width() - side // 2, side // 2))[:3] == (255, 0, 0)
    monkeypatch.setattr(content_mod.get_content(), "word_pictures", {})
    frame = g.emoji(char, 40)
    assert frame.get_size() == g.emoji("🖼️", 40).get_size()
