"""Play's code panel builds a toy: reading the keys and steps forgivingly, and playing them."""

import asyncio

import pytest

from purplecomputer import toy, tts
from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.panels import RECIPES


@pytest.mark.parametrize("line, key, rest", [
    ("a: cow", "a", "cow"),
    ("A : cow", "a", "cow"),
    ("space: 3 cats", "space", "3 cats"),
    ("space -> 3 cats", "space", "3 cats"),
    ("1 = 1 star", "1", "1 star"),
    ("s pig say oink", "s", "pig say oink"),
    ("space cow", "space", "cow"),
    ("enter say hi", "enter", "say hi"),
    ("when a cow", "a", "cow"),
    ("press 1 star", "1", "star"),
    ("on space: 3 cats", "space", "3 cats"),
])
def test_a_line_with_a_key_waits_for_it(line, key, rest):
    assert toy.label(line) == (key, rest)


@pytest.mark.parametrize("line", ["a cow", "1 star", "i like cats", "cow", "3 cats", "hello: cat", "a:", "red + blue",
                                  "2 - 1", "when", "space"])
def test_a_line_play_already_reads_runs_now(line):
    assert toy.label(line) == (None, line)


@pytest.mark.parametrize("text, want", [
    ("cow", [("play", "cow")]),
    ("cow, say moo, drum cowbell", [("play", "cow"), ("play", "say moo"), ("drum", "cowbell")]),
    ("cow say moo drum cowbell", [("play", "cow"), ("play", "say moo"), ("drum", "cowbell")]),
    ("drum", [("drum", toy.DEFAULT_DRUM)]),
    ("drum hat; drum bell", [("drum", "hi-hat"), ("drum", "cowbell")]),
    ("drum cat", [("drum", toy.DEFAULT_DRUM), ("play", "cat")]),
    ("drum gong 3 cats", [("drum", "gong"), ("play", "3 cats")]),
    ("3 drums", [("play", "3 drums")]),
    ("", []),
])
def test_steps_split_at_commas_and_at_say_or_drum(text, want):
    assert toy.steps(text) == want


def test_a_key_typed_again_keeps_its_place_and_takes_the_newer_line():
    lines = ["a: cow", "cow", "s: pig", "a: dog", "play"]
    assert toy.toy_from(lines) == {"a": "dog", "s": "pig"}


@pytest.mark.parametrize("code", [code for code, _, _ in RECIPES["play"]])
def test_every_recipe_puts_something_on_a_key(code):
    key, rest = toy.label(code)
    assert key and toy.steps(rest)


async def _play():
    app = make_app(room="play")
    room = app.rooms["play"]
    room.open_code_panel()
    return app, room


def _shown(entries):
    return [e.markup for e in entries if e.kind == "answer"]


def test_a_line_with_a_key_joins_the_toy_and_shows_nothing_yet():
    async def go():
        app, room = await _play()
        await type_text(app, "a: cow", enter=True)
        await asyncio.sleep(0)
        assert room.history == []
        assert toy.toy_from(app.code_lines("play")) == {"a": "cow"}
    run(go())


def test_a_line_without_a_key_runs_now_with_its_drums(monkeypatch):
    monkeypatch.setattr(toy, "STEP_S", 0)

    async def go():
        app, room = await _play()
        await room.run_code(["cow, drum gong"])
        assert _shown(room.history) == ["🐮", "🥁 gong"]
        await room.run_code(["2 red, 3 blue"])   # no drum: Play reads the whole line, commas and all
        assert [e.markup for e in room.history if e.kind == "ask"][-1] == "2 red, 3 blue"
    run(go())


def test_play_opens_the_toy_and_a_key_shows_its_steps(monkeypatch):
    monkeypatch.setattr(toy, "STEP_S", 0)
    said = []
    monkeypatch.setattr(tts, "speak_many", lambda texts, **_: said.append(texts) or True)

    async def go():
        app, room = await _play()
        await type_text(app, "a: cat, say hi, drum kick", enter=True)
        await type_text(app, "play", enter=True)
        screen = app.top
        assert isinstance(screen, toy.ToyScreen)
        await press(app, "a")
        await screen._task
        assert _shown(screen.entries) == ["🐱", "👋", "🥁 kick"]
        assert said
        await press(app, "z")   # no step on Z: what A showed stays
        assert _shown(screen.entries)[0] == "🐱"
        await press(app, "escape")
        assert app.top is not screen and room.code_panel is not None
        assert room.history == []
    run(go())


def test_code_opens_holding_the_last_play_line_on_space():
    async def go():
        app = make_app(room="play")
        room = app.rooms["play"]
        await type_text(app, "3 cats", enter=True)
        room.open_code_panel()
        assert room.code_panel.note[0] == "space: 3 cats"
    run(go())
