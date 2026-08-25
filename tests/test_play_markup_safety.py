"""Markup metacharacters ("[", "[/", "\\") once killed the whole app on submit,
and the color mixer once spelled its own tags out as letter blocks. The unit
tests cover the shapes through the evaluator and the markup parser; the
app-level tests at the end drive the real rooms through the dispatcher."""

import re

import pytest

from purple_tui.gfx import parse_markup, strip_markup
from purple_tui.harness import make_app, press, run, type_text
from purple_tui.play_eval import SimpleEvaluator, _escape_markup, _escaped_width, _strip_markup, parse_speech_trigger

HOSTILE_INPUT = [
    "[", "[[[", "a[b[c", "[/]", "][", "cat[dog", "[cat] love [dog", "hello[",
    "a[/", "[/x", "cat [/ dog", "\\", "a\\b", "\\red", "\\\\red", "\\[",
    "[red blue", "red [ blue", "big [red dog", "2 [cats", "[3 dogs]", "purple blue[",
]
COLOR_CODE_ON_SCREEN = re.compile(r'on#[0-9A-Fa-f]{3,6}|#[0-9A-Fa-f]{6}')
TAG_ON_SCREEN = re.compile(r'\[/\]|\[bold|\[dim|\[on |\[#')


@pytest.fixture
def evaluator():
    return SimpleEvaluator()


def plain(markup: str) -> str:
    """What the renderer would put on screen for a markup string."""
    return strip_markup(markup)


def leaked_markup(plain_text: str, typed: str) -> list:
    hits = [m.group() for m in COLOR_CODE_ON_SCREEN.finditer(re.sub(r'\s+', '', plain_text))]
    hits += [m.group() for m in TAG_ON_SCREEN.finditer(plain_text)]
    typed_squashed = re.sub(r'\s+', '', typed)
    return sorted({h for h in hits if h not in typed and h not in typed_squashed})


def test_detector_sees_color_codes_spelled_out_as_letter_blocks():
    spaced = "    →    +  \\  [  [  o  n   #  E  D  1  C  2  4  ]    [  /  ] "
    assert leaked_markup(spaced, "[red blue")
    assert not re.search(r'on #[0-9A-Fa-f]{6}', spaced)


def test_detector_does_not_squash_typed_brackets_around_a_swatch():
    assert not leaked_markup("    →  [ /   ] ", "[/red]")
    assert leaked_markup("    → [/] here", "hello")


def test_detector_allows_what_the_kid_typed():
    assert not leaked_markup("    → [/]", "[/]")
    assert leaked_markup("    → [/]", "hello")


@pytest.mark.parametrize("text", HOSTILE_INPUT)
def test_renders_without_crashing(evaluator, text):
    parse_markup(text)
    result = evaluator.evaluate(text)
    if isinstance(result, str):
        parse_markup(result)


@pytest.mark.parametrize("text", HOSTILE_INPUT)
def test_never_shows_raw_markup(evaluator, text):
    result = evaluator.evaluate(text)
    if not isinstance(result, str) or "COLOR_RESULT:" in result:
        return
    leaked = leaked_markup(plain(result), text)
    assert not leaked, f"{text!r} showed markup {leaked}: {plain(result)!r}"


@pytest.mark.parametrize("text", ["\\", "a\\b", "x\\y\\z"])
def test_typed_backslash_does_not_leak_a_closing_tag(evaluator, text):
    result = evaluator.evaluate(text)
    if not isinstance(result, str):
        return
    shown = plain(result)
    assert "[/]" not in shown, f"{text!r} leaked a closing tag: {shown!r}"
    assert "\\" in shown, f"{text!r} lost the backslash: {shown!r}"


@pytest.mark.parametrize("text", ["a[b", "[cat", "a[/"])
def test_typed_bracket_survives_to_the_code_panel(evaluator, text):
    result = evaluator.evaluate(text)
    if isinstance(result, str):
        assert '[' in _strip_markup(result)


@pytest.mark.parametrize("text", ["[]]]fwa", "[fe]wa]w", "[]few]af]ea", "a[b"])
def test_brackets_get_blocks_even_beside_words(evaluator, text):
    result = evaluator.evaluate(text)
    for bracket in "[]":
        blocks = result.count(f" {_escape_markup(bracket)} [/]")
        assert blocks == text.count(bracket), f"{text!r} -> {result!r}"


BRACKET_WITH_COLOR = ["red [bl", "[red blue", "blue [ red", "[red] blue", "red [", "red ]"]


@pytest.mark.parametrize("text", BRACKET_WITH_COLOR)
def test_bracket_beside_a_color_gets_a_block_on_both_sides_of_the_arrow(evaluator, text):
    result = evaluator.evaluate(text)
    for half in result.split(" → "):
        for bracket in set("[]") & set(text):
            assert f" {_escape_markup(bracket)} [/]" in half, f"{text!r} -> {result!r}"


@pytest.mark.parametrize("text", BRACKET_WITH_COLOR + ["red cat?", "red xyz?"])
def test_escaping_a_bracket_never_paints_a_backslash(evaluator, text):
    shown = plain(evaluator.evaluate(text))
    assert "\\" not in shown, f"{text!r} painted an escape: {shown!r}"


@pytest.mark.parametrize("text,emoji", [("red cat?", "🐱"), ("blue 2 dogs?", "🐶")])
def test_punctuation_does_not_knock_an_emoji_out_of_its_color(evaluator, text, emoji):
    result = evaluator.evaluate(text)
    assert re.search(rf'\[on #[0-9A-Fa-f]{{6}}\] {emoji}+ \[/\]', result), result


@pytest.mark.parametrize("text,emoji,word", [
    ("red cat!", "🐱", "cat"),
    ("blue dog?", "🐶", "dog"),
    ("red 2 cats!", "🐱", "cats"),
    ("green sun!", "☀", "sun"),
])
def test_color_answer_shows_the_emoji_not_the_typed_word(evaluator, text, emoji, word):
    shown = plain(evaluator.evaluate(text))
    assert emoji in shown, f"{text!r} lost the emoji: {shown!r}"
    assert word not in shown, f"{text!r} answered with the letters: {shown!r}"


@pytest.mark.parametrize("text", ["red blue", "red and blue", "purple blue"])
def test_color_mix_sentinel_never_reaches_the_screen(evaluator, text):
    result = evaluator.evaluate(text)
    if not isinstance(result, str) or "COLOR_RESULT:" not in result:
        return
    for part in result.split():
        if part.startswith("COLOR_RESULT:"):
            assert evaluator._parse_color_result(part) is not None, f"{text!r} would show the raw sentinel: {part!r}"


@pytest.mark.parametrize("text,expected", [("cat, dog", "🐱, 🐶"), ("cat + dog", "🐱 + 🐶")])
def test_separators_stay_plain_next_to_emoji(evaluator, text, expected):
    assert evaluator.evaluate(text) == expected


@pytest.mark.parametrize("text", ["[", "]", "[[", "]]", "[]", "((", "@@", "[[["])
def test_punctuation_all_gets_letter_blocks(evaluator, text):
    result = evaluator.evaluate(text)
    assert isinstance(result, str)
    assert result.count("[/]") == len(text), f"{text!r} -> {result!r}"


def test_escaped_bracket_is_one_cell_wide():
    assert _escaped_width("\\[") == 1
    assert _escaped_width("ab") == 2


def test_other_rooms_survive_hostile_typing():
    async def scenario():
        app = make_app()
        app.action_switch_room("art")
        await type_text(app, "[]\\[/]a")
        assert app.rooms["art"]._painted_positions, "keys never reached the Art canvas"
        app.action_switch_room("music")
        played = []
        music = app.rooms["music"]
        original = music.flash_note
        music.flash_note = lambda k: (played.append(k), original(k))[1]
        await type_text(app, "[]\\[/]a")
        assert played, "keys never reached the Music grid"
    run(scenario())


def test_real_app_never_puts_markup_on_screen():
    checked = ["[red blue", "a[b", "\\red", "a[/", "[cat", "red [ blue"]

    async def scenario():
        app = make_app()
        play = app.rooms["play"]
        for text in checked:
            await type_text(app, text)
            typed = play.field.value          # what the kid sees (÷ for /, spaced operators)
            await press(app, "enter")
            ask, answer = play.history[-2], play.history[-1]
            assert ask.kind == "ask" and ask.markup == parse_speech_trigger(typed)[1]
            app._draw()   # the real renderer lays the answer out
            leaked = leaked_markup(plain(answer.markup), text)
            assert not leaked, f"{text!r} showed markup {leaked}"
        await press(app, "escape")
    run(scenario())
