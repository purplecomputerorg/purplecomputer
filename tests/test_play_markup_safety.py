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
    SimpleEvaluator, HistoryLine, _strip_markup, _escaped_width,
)

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4

HOSTILE_INPUT = [
    "[", "[[[", "a[b[c", "[/]", "][", "cat[dog", "[cat] love [dog", "hello[",
    "a[/", "[/x", "cat [/ dog", "\\", "a\\b", "\\red", "\\\\red", "\\[",
    "[red blue", "red [ blue", "big [red dog", "2 [cats", "[3 dogs]", "purple blue[",
]

# Style syntax that must never reach the screen. Matched against the rendered
# text with whitespace removed, because letter blocks render as "o n # E D 1 C".
MARKUP_ON_SCREEN = re.compile(r'on#[0-9A-Fa-f]{3,6}|#[0-9A-Fa-f]{6}|\[/\]|\[bold|\[dim')


@pytest.fixture
def evaluator():
    return SimpleEvaluator()


def _typed_by_kid(fragment: str, typed: str) -> bool:
    """True if the fragment's characters all appear, in order, in what was typed.

    Squashing whitespace can join text either side of a color swatch, so
    "[/red]" reads back as "[/]". Those characters really were typed.
    """
    it = iter(typed)
    return all(ch in it for ch in fragment)


def leaked_markup(plain: str, typed: str) -> list[str]:
    """Style syntax visible on screen that the kid did not type themselves."""
    squashed = re.sub(r'\s+', '', plain)
    typed_squashed = re.sub(r'\s+', '', typed)
    return [m.group() for m in MARKUP_ON_SCREEN.finditer(squashed)
            if not _typed_by_kid(m.group(), typed_squashed)]


def test_detector_sees_markup_spelled_out_as_letter_blocks():
    """Letter blocks render spaced out, which a naive contiguous match misses."""
    spaced = "    →    +  \\  [  [  o  n   #  E  D  1  C  2  4  ]    [  /  ] "
    assert leaked_markup(spaced, "[red blue")
    assert not re.search(r'on #[0-9A-Fa-f]{6}', spaced)  # why the squash is needed


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
