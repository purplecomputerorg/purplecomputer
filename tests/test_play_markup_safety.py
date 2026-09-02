"""Nothing a kid types may crash Play or put markup on screen.

Markup metacharacters ("[", "[/", "\\") once killed the whole app on submit, and
the color mixer once spelled its own tags out as letter blocks. The unit tests
here cover the shapes; the app-level test at the end runs the real widget widths,
because the wrap path renders differently at the real size than at the fallback.
"""

import asyncio
import os
import re

import pytest

# Set environment before app imports
os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from purple_tui.purple_tui import PurpleApp  # noqa: E402
from purple_tui.constants import REQUIRED_TERMINAL_ROWS  # noqa: E402
from purple_tui.rooms.play_room import (  # noqa: E402
    SimpleEvaluator, HistoryLine, _strip_markup, _escaped_width, _escape_markup,
)

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4

HOSTILE_INPUT = [
    "[", "[[[", "a[b[c", "[/]", "][", "cat[dog", "[cat] love [dog", "hello[",
    "a[/", "[/x", "cat [/ dog", "\\", "a\\b", "\\red", "\\\\red", "\\[",
    "[red blue", "red [ blue", "big [red dog", "2 [cats", "[3 dogs]", "purple blue[",
]

# A color code leaks spelled out as letter blocks ("o n # E D 1 C"), so it is
# matched with whitespace removed. A tag leaks as literal text, so it is matched
# as-is: squashing would join the "[/" and "]" a kid typed either side of a
# swatch and report that as a leak.
COLOR_CODE_ON_SCREEN = re.compile(r'on#[0-9A-Fa-f]{3,6}|#[0-9A-Fa-f]{6}')
TAG_ON_SCREEN = re.compile(r'\[/\]|\[bold|\[dim|\[on |\[#')


@pytest.fixture
def evaluator():
    return SimpleEvaluator()


def leaked_markup(plain: str, typed: str) -> list[str]:
    """Style syntax visible on screen that the kid did not type themselves."""
    hits = [m.group() for m in COLOR_CODE_ON_SCREEN.finditer(re.sub(r'\s+', '', plain))]
    hits += [m.group() for m in TAG_ON_SCREEN.finditer(plain)]
    typed_squashed = re.sub(r'\s+', '', typed)
    return sorted({h for h in hits if h not in typed and h not in typed_squashed})


def test_detector_sees_color_codes_spelled_out_as_letter_blocks():
    """Letter blocks render spaced out, which a naive contiguous match misses."""
    spaced = "    →    +  \\  [  [  o  n   #  E  D  1  C  2  4  ]    [  /  ] "
    assert leaked_markup(spaced, "[red blue")
    assert not re.search(r'on #[0-9A-Fa-f]{6}', spaced)  # why the squash is needed


def test_detector_does_not_squash_typed_brackets_around_a_swatch():
    """"[/red]" renders as "[", "/", swatch, "]": all typed, so not a leak."""
    assert not leaked_markup("    →  [ /   ] ", "[/red]")
    assert leaked_markup("    → [/] here", "hello")


def test_detector_allows_what_the_kid_typed():
    assert not leaked_markup("    → [/]", "[/]")
    assert leaked_markup("    → [/]", "hello")


@pytest.mark.parametrize("text", HOSTILE_INPUT)
def test_renders_without_crashing(evaluator, text):
    HistoryLine(text, line_type="ask").render()
    result = evaluator.evaluate(text)
    if isinstance(result, str):
        HistoryLine(result, line_type="answer").render()


@pytest.mark.parametrize("text", HOSTILE_INPUT)
def test_ask_line_echoes_exactly_what_was_typed(text):
    """The Ask line is the kid's own words: it must not drop or mangle them."""
    plain = HistoryLine(text, line_type="ask").render().plain
    assert plain.endswith(text), f"ask line showed {plain!r} for {text!r}"


@pytest.mark.parametrize("text", HOSTILE_INPUT)
def test_never_shows_raw_markup(evaluator, text):
    result = evaluator.evaluate(text)
    if not isinstance(result, str) or "COLOR_RESULT:" in result:
        return  # sentinel, swapped for swatches before it reaches a HistoryLine
    plain = HistoryLine(result, line_type="answer").render().plain
    leaked = leaked_markup(plain, text)
    assert not leaked, f"{text!r} showed markup {leaked}: {plain!r}"


@pytest.mark.parametrize("text", ["\\", "a\\b", "x\\y\\z"])
def test_typed_backslash_does_not_leak_a_closing_tag(evaluator, text):
    """A backslash must not escape the "[/]" the wrapper re-emits around it."""
    result = evaluator.evaluate(text)
    if not isinstance(result, str):
        return
    plain = HistoryLine(result, line_type="answer").render().plain
    assert "[/]" not in plain, f"{text!r} leaked a closing tag: {plain!r}"
    assert "\\" in plain, f"{text!r} lost the backslash: {plain!r}"


@pytest.mark.parametrize("text", ["a[b", "[cat", "a[/"])
def test_typed_bracket_survives_to_the_code_panel(evaluator, text):
    """_strip_markup feeds the code panel and speech, so the "[" must survive."""
    result = evaluator.evaluate(text)
    if isinstance(result, str):
        assert '[' in _strip_markup(result)


@pytest.mark.parametrize("text", ["[]]]fwa", "[fe]wa]w", "[]few]af]ea", "a[b"])
def test_brackets_get_blocks_even_beside_words(evaluator, text):
    """Brackets stayed bare whenever anything else in the line was substituted."""
    result = evaluator.evaluate(text)
    for bracket in "[]":
        # The block holds the escaped form, so "[" sits in it as "\\[".
        blocks = result.count(f" {_escape_markup(bracket)} [/]")
        assert blocks == text.count(bracket), f"{text!r} -> {result!r}"


BRACKET_WITH_COLOR = ["red [bl", "[red blue", "blue [ red", "[red] blue", "red [", "red ]"]


@pytest.mark.parametrize("text", BRACKET_WITH_COLOR)
def test_bracket_beside_a_color_gets_a_block_on_both_sides_of_the_arrow(evaluator, text):
    """The mixer passed a bracket through bare whenever the chunk held a swatch."""
    result = evaluator.evaluate(text)
    for half in result.split(" → "):
        for bracket in set("[]") & set(text):
            assert f" {_escape_markup(bracket)} [/]" in half, f"{text!r} -> {result!r}"


@pytest.mark.parametrize("text", BRACKET_WITH_COLOR + ["red cat?", "red xyz?"])
def test_escaping_a_bracket_never_paints_a_backslash(evaluator, text):
    """Escaped text fed back to the block formatter drew its own "\\" as a letter."""
    plain = HistoryLine(evaluator.evaluate(text), line_type="answer").render().plain
    assert "\\" not in plain, f"{text!r} painted an escape: {plain!r}"


@pytest.mark.parametrize("text,emoji", [("red cat?", "🐱"), ("blue 2 dogs?", "🐶")])
def test_punctuation_does_not_knock_an_emoji_out_of_its_color(evaluator, text, emoji):
    """A trailing "?" used to make the whole chunk plain text, greying the emoji."""
    result = evaluator.evaluate(text)
    assert re.search(rf'\[on #[0-9A-Fa-f]{{6}}\] {emoji}+ \[/\]', result), result


@pytest.mark.parametrize("text,emoji,word", [
    ("red cat!", "🐱", "cat"),
    ("blue dog?", "🐶", "dog"),
    ("red 2 cats!", "🐱", "cats"),
    ("green sun!", "☀", "sun"),
])
def test_color_answer_shows_the_emoji_not_the_typed_word(evaluator, text, emoji, word):
    """Both halves of the arrow substitute: "red cat!" must not answer "cat!"."""
    plain = HistoryLine(evaluator.evaluate(text), line_type="answer").render().plain
    assert emoji in plain, f"{text!r} lost the emoji: {plain!r}"
    assert word not in plain, f"{text!r} answered with the letters: {plain!r}"


@pytest.mark.parametrize("text", ["red blue", "red and blue", "purple blue"])
def test_color_mix_sentinel_never_reaches_the_screen(evaluator, text):
    """COLOR_RESULT is swapped for swatches; an unparsed one would be shown raw."""
    result = evaluator.evaluate(text)
    if not isinstance(result, str) or "COLOR_RESULT:" not in result:
        return
    for part in result.split():
        if part.startswith("COLOR_RESULT:"):
            assert evaluator._parse_color_result(part) is not None, \
                f"{text!r} would mount the raw sentinel: {part!r}"


@pytest.mark.parametrize("text,expected", [
    ("cat, dog", "🐱, 🐶"),          # separators stay plain glue between emoji
    ("cat + dog", "🐱 + 🐶"),
])
def test_separators_stay_plain_next_to_emoji(evaluator, text, expected):
    assert evaluator.evaluate(text) == expected


@pytest.mark.parametrize("text", ["[", "]", "[[", "]]", "[]", "((", "@@", "[[["])
def test_punctuation_all_gets_letter_blocks(evaluator, text):
    """A typed "[" is a character like any other: it gets a colored block too.

    Escaping it used to read as "something was substituted", which skipped the
    block fallback, so "]]" came back colored and "[[" came back bare.
    """
    result = evaluator.evaluate(text)
    assert isinstance(result, str)
    assert result.count("[/]") == len(text), f"{text!r} -> {result!r}"


def test_escaped_bracket_is_one_cell_wide():
    """An escaped "\\[" is one cell, not two, or answers wrap early."""
    assert _escaped_width("\\[") == 1
    assert _escaped_width("ab") == 2
    tokens = HistoryLine._tokenize_markup("[#fff on #000] \\[ [/]")
    assert sum(w for _, w in tokens) == 3


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _submit(app, pilot, text):
    for char in text:
        await app._execute_dev_command({"action": "key", "value": char})
    await app._execute_dev_command({"action": "key", "value": "enter"})
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()


def test_other_rooms_survive_hostile_typing():
    """Art and Music paint through Strip/Segment, which never parses markup.

    That is why a "[" cannot open a tag there. This pins it: the rooms are
    driven with the same input that used to kill Play.
    """
    from purple_tui.constants import ROOM_ART, ROOM_MUSIC
    from purple_tui.rooms.art_room import ArtCanvas

    async def type_hostile(app, pilot):
        for char in "[]\\[/]a":
            await app._execute_dev_command({"action": "key", "value": char})
        await pilot.pause()
        await asyncio.sleep(SETTLE)
        await pilot.pause()

    async def enter_room(app, pilot, room_id):
        app.action_switch_room(room_id)
        await pilot.pause()
        await asyncio.sleep(SETTLE)
        await pilot.pause()

    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.pause()
            await asyncio.sleep(SETTLE)
            await pilot.pause()

            await enter_room(app, pilot, ROOM_ART[0])
            await type_hostile(app, pilot)
            canvas = app.query_one(ArtCanvas)
            assert canvas._painted_positions, "keys never reached the Art canvas"

            await enter_room(app, pilot, ROOM_MUSIC[0])
            grid = app.query_one("#room-music").grid
            played = []
            painted = grid.flash_note
            grid.flash_note = lambda *a, **k: (played.append(a), painted(*a, **k))[1]
            await type_hostile(app, pilot)
            assert played, "keys never reached the Music grid"
            # A markup error in either room would have surfaced as an exception
            # out of run_test before reaching here.

    _run(scenario())


def test_real_app_never_puts_markup_on_screen():
    """Drive the mounted app: the wrap path differs at the real widget width."""
    checked = ["[red blue", "a[b", "\\red", "a[/", "[cat", "red [ blue"]

    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await pilot.pause()
            await asyncio.sleep(SETTLE)
            await pilot.pause()
            seen = set()
            widths = set()
            for text in checked:
                await _submit(app, pilot, text)
                # Only the lines this input produced, so the "kid typed it"
                # allowance stays scoped to one entry.
                for widget in app.query(HistoryLine):
                    if id(widget) in seen:
                        continue
                    seen.add(id(widget))
                    widths.add(widget.size.width)
                    leaked = leaked_markup(widget.render().plain, text)
                    assert not leaked, f"{text!r} showed markup {leaked}"
            assert seen, "no history lines were rendered"
            assert widths and max(widths) > 108, f"widths {widths} look like the fallback"

    _run(scenario())
