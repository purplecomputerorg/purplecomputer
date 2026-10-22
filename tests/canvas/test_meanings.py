"""A family's word can say what it is when Play is asked: content/meanings.json."""

import json

import pytest

from purple_tui import content as content_mod
from purple_tui import tts
from purple_tui.canvas.harness import make_app, run
from purple_tui.canvas.rooms.play_room import asked_meaning
from purple_tui.content import MEANING_MAX, ContentManager
from purple_tui.pack_manager import check_pack

GRANDMA = "Grandma lives in Ohio [and] grows tomatoes."


@pytest.fixture
def meanings(tmp_path, monkeypatch):
    pack = tmp_path / "packs" / "family"
    (pack / "content").mkdir(parents=True)
    (pack / "manifest.json").write_text(json.dumps({"id": "family", "name": "F", "version": "1.0.0", "type": "emoji"}))
    (pack / "content" / "emoji.json").write_text(json.dumps({"grandma": "👵"}))
    (pack / "content" / "meanings.json").write_text(json.dumps(
        {"Grandma": f"  {GRANDMA} ", "biscuit": "x" * 300, "blank": "  ", "bad": 3}))
    cm = ContentManager(packs_dir=tmp_path / "packs")
    cm.load_all()
    monkeypatch.setattr(content_mod, "_content", cm)
    return cm, pack


def test_meanings_load_trimmed_capped_and_found_by_plural(meanings):
    cm, _ = meanings
    assert cm.meaning("grandma") == cm.meaning("GRANDMAS") == GRANDMA
    assert len(cm.meaning("biscuit")) == MEANING_MAX
    assert cm.meaning("blank") is cm.meaning("bad") is cm.meaning("cat") is None


@pytest.mark.parametrize("text", ["who is grandma", "what's grandma?", "whats a grandma", "what grandma",
                                  "Who is the Grandma??", "what are grandmas"])
def test_every_way_of_asking_finds_the_meaning(meanings, text):
    assert asked_meaning(text) == ("👵", GRANDMA)


@pytest.mark.parametrize("text", ["grandma", "who is cat", "what is 2 + 3", "who is grandma now"])
def test_anything_else_is_not_a_question(meanings, text):
    assert asked_meaning(text) is None


def test_play_shows_the_picture_and_meaning_and_says_it(meanings, monkeypatch):
    said = []
    monkeypatch.setattr(tts, "speak_many", lambda texts, **_: said.append(texts) or True)

    async def scenario():
        play = make_app(room="play").rooms["play"]
        play._submit_line("who is grandma!")
        assert [(e.kind, e.markup) for e in play.history[-3:]] == [
            ("ask", "who is grandma"), ("answer", "👵"), ("answer", GRANDMA.replace("[", "\\["))]
    run(scenario())
    assert said == [[GRANDMA]]


def test_the_installer_refuses_a_meaning_that_is_not_text(meanings):
    _, pack = meanings
    assert any("meanings.json" in p for p in check_pack(pack))
