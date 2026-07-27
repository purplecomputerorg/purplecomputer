"""What kids actually type in Play, in the shapes they type it.

Broad invariants rather than pinned strings: every line answers something, the
answer never leaks markup or overflows the view, a color the kid typed reaches
the answer, and a word Purple has a picture for shows the picture. The exact
wording of any single answer belongs in test_play_mode.py; this file is the net
that catches a rule change nobody meant to make.
"""

import os
import re

import pytest

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from purple_tui.rooms.play_room import (  # noqa: E402
    SimpleEvaluator, HistoryLine, _strip_markup,
)
from tests.test_play_markup_safety import leaked_markup  # noqa: E402

# Tallest an answer may be. The history view is 21 rows, so anything past this
# buries the question the kid just asked.
MAX_ANSWER_LINES = 6

KID_INPUT = [
    # one word
    "cat", "dog", "red", "blue", "hello", "mom", "dad", "me", "you", "yes", "no",
    "cats", "dogs", "hi", "ok", "wow", "love", "sun", "moon", "star",
    # a color and a thing, either way round
    "red cat", "cat red", "blue dog", "dog blue", "green frog", "frog green",
    "purple cat", "pink pig", "yellow sun", "orange cat", "brown bear",
    # sentences
    "my cat is blue", "the dog is red", "my dog is big", "the cat is small",
    "i love cats", "i love you", "i like dogs", "i want a cat", "i have 2 cats",
    "the sky is blue", "grass is green", "the sun is yellow", "snow is white",
    "my name is adam", "i am 5", "i love my mom", "mom is nice", "cats are cute",
    "the cat sat on the mat", "the dog ran fast", "i see a blue bird",
    "the cat is not blue", "my cat is very blue", "is my cat blue",
    # counting
    "3 cats", "2 dogs", "10 cats", "1 cat", "100 cats", "2 cats and 3 dogs",
    "3 cats + 2 dogs", "5 red cats", "2 blue dogs", "3 cats 2 dogs",
    "i have 3 red apples", "my two blue dogs", "some cats", "two cats",
    # math
    "1 + 1", "2 + 2", "5 + 5", "10 - 3", "3 x 3", "2 times 3",
    "10 divided by 2", "what is 2 + 2", "100 + 100", "9 - 9", "2 + 3 + 4",
    # colors together
    "red and blue", "red + blue", "red blue", "blue red", "red blue green",
    "dark blue", "light red", "bright green", "red red red", "pink and purple",
    # colors and things, longer
    "red cat blue dog", "blue cat and red dog", "3 blue cats and 2 red dogs",
    "a red cat and a blue dog", "my red cat", "my blue dog is big",
    # a color typed last
    "cat blue", "dog red", "cat dog blue", "cat is blue", "red cat blue",
    "2 + 3 cats blue", "the ball is red", "cats are blue",
    # punctuation and shouting
    "cat!", "cat?", "cat.", "cat!!!", "i love you!", "hi!", "wow!", "yay!",
    "cat,", "dog, cat", "cat and dog", "why?", "no!!",
    # typos and mashing
    "catt", "dogg", "i luv cats", "helo", "teh cat", "asdf", "qwerty", "aaaa",
    "abc", "abcdefg", "zzz", "hjkl",
    # faces and symbols
    ":)", ":(", "<3", ":D", "i love you <3", "cat :)",
    # bare numbers
    "5", "42", "100", "0", "-5", "2.5", "1000",
    # saying the same thing twice
    "cat cat cat", "dog dog", "repeat 3 cat", "cat and cat",
    # stray spaces
    "  cat  ", "cat  dog", " red cat ",
]

# None of something is still an answer. Zero copies of an emoji is an empty
# string, which used to print nothing at all or leave a stray "+" behind.
NONE_OF_SOMETHING = [
    "0 cats", "0 dogs", "zero cats", "0 hearts", "0 times cat", "2 - 2 cats",
]

# Looked up rather than written down, so a palette change doesn't break the test.
# "orange", "peach" and "rose" are here on purpose: they name a color and a
# thing at once, which is where a grouping rule is most likely to pick wrong.
COLORS = ["red", "blue", "green", "yellow", "purple", "pink", "brown",
          "orange", "peach", "rose"]
NOUNS = ["cat", "dog", "frog", "star", "apple", "car"]

# Ways a kid says one color, past a bare color word.
COLOR_PHRASES = ["blue", "dark blue", "light green", "bright red", "red blue",
                 "very blue", "so red"]

# A sentence that names one thing and one color, whatever else it says.
SENTENCES = [
    ("my cat is blue", "cat", "blue"),
    ("the dog is red", "dog", "red"),
    ("i have a green frog", "frog", "green"),
    ("my apple is red", "apple", "red"),
    ("the star is yellow", "star", "yellow"),
    ("i want a purple cat", "cat", "purple"),
    ("the ball is red", "ball", "red"),
    ("i see a blue bird", "bird", "blue"),
    ("my fish is orange", "fish", "orange"),
    ("a red apple", "apple", "red"),
    ("my blue cat", "cat", "blue"),
    ("i love my red dog", "dog", "red"),
    ("the big blue whale", "whale", "blue"),
    ("my cat is very blue", "cat", "blue"),
    ("is my cat blue", "cat", "blue"),
    ("the cat is not blue", "cat", "blue"),
    ("cats are blue", "cat", "blue"),
    ("2 blue cats", "cat", "blue"),
    ("my two blue dogs", "dog", "blue"),
    ("i have 3 red apples", "apple", "red"),
]


@pytest.fixture
def evaluator():
    return SimpleEvaluator()


def answer_of(result: str) -> str:
    """The half of a two-sided answer that shows the outcome."""
    return result.split(" → ")[-1]


def rendered(result: str) -> tuple[str, int]:
    """What reaches the screen, and how many rows it takes."""
    line = HistoryLine(result, line_type="answer")
    return line.render().plain, len(line._build_markup().split("\n"))


def painted(evaluator, noun: str, color: str) -> re.Pattern:
    """Matches the noun's picture sitting on the color, however many there are."""
    emoji = evaluator._get_emoji(noun)
    return re.compile(
        re.escape(f"[on {evaluator._get_color(color)}] ") + re.escape(emoji) + r"+ \[/\]"
    )


def tinted(evaluator, noun: str, answer: str) -> str | None:
    """The noun's picture with whatever color it landed on, or None if plain."""
    m = re.search(r"\[on #[0-9A-Fa-f]{6}\] " + re.escape(evaluator._get_emoji(noun))
                  + r"+ \[/\]", answer)
    return m.group(0) if m else None


@pytest.mark.parametrize("text", KID_INPUT + NONE_OF_SOMETHING)
def test_every_line_answers_something(evaluator, text):
    """An empty answer shows nothing at all, which reads as being ignored."""
    assert evaluator.evaluate(text), f"{text!r} answered nothing"


@pytest.mark.parametrize("text", NONE_OF_SOMETHING)
def test_none_of_something_answers_zero(evaluator, text):
    assert _strip_markup(evaluator.evaluate(text)).strip() == "0"


@pytest.mark.parametrize("text,answer", [
    ("i have 0 cats", "0"),  # the sentence renders as letter blocks, then "0"
    ("0 cats and 0 dogs", "0 + 0"),
    ("0 cats and 3 dogs", "0 + 🐶🐶🐶"),
])
def test_none_of_something_still_counts_beside_the_rest(evaluator, text, answer):
    """A zero group used to vanish, leaving a "+" joining nothing to anything."""
    plain = re.sub(r"\s+", " ", _strip_markup(evaluator.evaluate(text))).strip()
    assert plain.endswith(answer), f"{text!r} -> {plain!r}"


@pytest.mark.parametrize("text", KID_INPUT)
def test_the_ask_line_echoes_what_was_typed(text):
    """The Ask line is the kid's own words: never reordered, dropped, or escaped."""
    plain = HistoryLine(text, line_type="ask").render().plain
    assert plain.endswith(text), f"ask line showed {plain!r}"


@pytest.mark.parametrize("text", KID_INPUT)
def test_the_answer_reaches_the_screen_clean(evaluator, text):
    """No crash, no style syntax on screen, and no escape the kid did not type."""
    result = evaluator.evaluate(text)
    if not isinstance(result, str) or "COLOR_RESULT:" in result:
        return  # sentinel, swapped for swatches before it reaches a HistoryLine
    plain, lines = rendered(result)
    assert not leaked_markup(plain, text), f"{text!r} showed markup: {plain!r}"
    assert "\\" not in plain or "\\" in text, f"{text!r} showed an escape: {plain!r}"
    assert lines <= MAX_ANSWER_LINES, f"{text!r} answered {lines} rows tall"


@pytest.mark.parametrize("noun", NOUNS)
@pytest.mark.parametrize("color", COLORS)
@pytest.mark.parametrize("order", ["{color} {noun}", "{noun} {color}"])
def test_a_color_and_a_thing_paint_the_same_either_way_round(
    evaluator, color, noun, order
):
    """Word order decides nothing here: both readings are "a colored thing"."""
    text = order.format(color=color, noun=noun)
    assert painted(evaluator, noun, color).search(answer_of(evaluator.evaluate(text))), \
        f"{text!r} -> {evaluator.evaluate(text)!r}"


@pytest.mark.parametrize("color", COLORS)
@pytest.mark.parametrize("order", ["{n} {color} {noun}s", "{color} {n} {noun}s",
                                   "{n} {noun}s {color}"])
def test_a_count_a_color_and_a_thing_agree_in_every_natural_order(
    evaluator, color, order
):
    """"3 blue cats", "blue 3 cats" and "3 cats blue" are the same three cats."""
    text = order.format(n=3, color=color, noun="cat")
    answer = answer_of(evaluator.evaluate(text))
    assert answer == f"[on {evaluator._get_color(color)}] 🐱🐱🐱 [/]", f"{text!r} -> {answer!r}"


@pytest.mark.parametrize("noun", ["cat", "dog"])
@pytest.mark.parametrize("phrase", COLOR_PHRASES)
def test_a_color_phrase_paints_the_same_before_or_after_the_thing(
    evaluator, phrase, noun
):
    """Whatever color the phrase works out to, both orders land on the same one."""
    before = tinted(evaluator, noun, answer_of(evaluator.evaluate(f"{phrase} {noun}")))
    after = tinted(evaluator, noun, answer_of(evaluator.evaluate(f"{noun} {phrase}")))
    assert before and before == after, f"{phrase!r} + {noun!r}: {before!r} vs {after!r}"


@pytest.mark.parametrize("word", ["orange", "peach", "rose", "chocolate"])
def test_a_word_that_is_a_color_and_a_thing_counts_the_noun_after_it(evaluator, word):
    """"3 orange cats" is three cats: the count belongs to the noun, not the fruit."""
    answer = answer_of(evaluator.evaluate(f"3 {word} cats"))
    assert answer == f"[on {evaluator._get_color(word)}] 🐱🐱🐱 [/]", answer


@pytest.mark.parametrize("word,emoji", [("orange", "🍊"), ("peach", "🍑"), ("rose", "🌹")])
def test_a_word_that_is_a_color_and_a_thing_stays_the_thing_on_its_own(
    evaluator, word, emoji
):
    """No noun follows "3 oranges", so it is still three pieces of fruit."""
    assert evaluator.evaluate(f"3 {word}s") == emoji * 3
    assert evaluator.evaluate(f"3 {word}") == emoji * 3


@pytest.mark.parametrize("text,noun,count,color", [
    ("i have 3 blue cats", "cat", 3, "blue"),
    ("i want 2 red apples", "apple", 2, "red"),
    ("my 3 blue cats are big", "cat", 3, "blue"),
    ("i see 5 green frogs", "frog", 5, "green"),
    ("can i have 2 pink pigs", "pig", 2, "pink"),
    ("there are 4 yellow stars", "star", 4, "yellow"),
    ("i found 3 orange cats", "cat", 3, "orange"),
])
def test_a_sentence_keeps_both_the_count_and_the_color(
    evaluator, text, noun, count, color
):
    block = (f"[on {evaluator._get_color(color)}] "
             + evaluator._get_emoji(noun) * count + " [/]")
    assert block in answer_of(evaluator.evaluate(text)), f"{text!r} lost {block!r}"


@pytest.mark.parametrize("joiner", ["and", "+", ""])
def test_two_colored_groups_each_keep_their_own_count_and_color(evaluator, joiner):
    answer = answer_of(evaluator.evaluate(f"2 red cats {joiner} 3 blue dogs"))
    assert f"[on {evaluator._get_color('red')}] 🐱🐱 [/]" in answer, answer
    assert f"[on {evaluator._get_color('blue')}] 🐶🐶🐶 [/]" in answer, answer


@pytest.mark.parametrize("word,digit", [("three", 3), ("five", 5), ("two", 2)])
def test_a_number_word_counts_the_same_as_its_digit(evaluator, word, digit):
    assert (evaluator.evaluate(f"{word} blue cats")
            == evaluator.evaluate(f"{digit} blue cats"))


@pytest.mark.parametrize("text,painted_noun,plain_noun", [
    # The color reaches one thing, the nearest, from either side. English would
    # spread it over both; Purple deliberately does not.
    ("red cat dog", "cat", "dog"),
    ("cat dog red", "dog", "cat"),
    ("my cat and dog are blue", "dog", "cat"),
])
def test_only_the_nearest_thing_takes_the_color(
    evaluator, text, painted_noun, plain_noun
):
    answer = answer_of(evaluator.evaluate(text))
    assert tinted(evaluator, painted_noun, answer), f"{text!r} -> {answer!r}"
    assert not tinted(evaluator, plain_noun, answer), f"{text!r} -> {answer!r}"


@pytest.mark.parametrize("text", KID_INPUT)
def test_the_same_line_answers_the_same_way_every_time(evaluator, text):
    """One evaluator serves a whole session: no line may color the next one."""
    first = evaluator.evaluate(text)
    for noise in ("red cat", "2 + 2", "repeat 3 dog"):
        evaluator.evaluate(noise)
    assert evaluator.evaluate(text) == first == SimpleEvaluator().evaluate(text)


@pytest.mark.parametrize("text,noun,color", SENTENCES)
def test_a_sentence_paints_the_thing_it_names(evaluator, text, noun, color):
    """The picture the kid named comes back in the color they asked for."""
    assert painted(evaluator, noun, color).search(answer_of(evaluator.evaluate(text))), \
        f"{text!r} -> {evaluator.evaluate(text)!r}"


@pytest.mark.parametrize("text", [
    "1000 cats", "1000 blues", "9999 cats", "600 dots",
    # A color word used to skip the cutoff and draw every bead: "1000 blue cats"
    # filled all 21 rows of the view, and "9999 blue cats" ran to 81.
    "1000 blue cats", "1000 cats blue", "9999 blue cats", "600 red dogs",
    "501 blue cats", "1000 cats and 3 blue dogs",
])
def test_a_big_count_switches_to_the_abacus_instead_of_filling_the_view(
    evaluator, text
):
    """Counts past INLINE_MAX get counted, not drawn one bead at a time."""
    _, lines = rendered(evaluator.evaluate(text))
    assert lines <= MAX_ANSWER_LINES + 1, f"{text!r} answered {lines} rows tall"


def test_a_big_count_keeps_its_color(evaluator):
    """The abacus beads are the colored thing the kid asked to count."""
    assert f"[on {evaluator._get_color('blue')}] 🐱 [/]" in \
        evaluator.evaluate("1000 blue cats")
