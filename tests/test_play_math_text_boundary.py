"""Characterization matrix for Play's math/text boundary.

One table documenting exactly how combos of digits, letters, words, colors,
and emoji words evaluate: as math, as a text prefix + math, as emoji, as
color mixing, or as plain letter blocks. Each row also pins down whether a
typo correction is tracked (shown to the kid in the recall hint).

Kinds:
- math:   evaluated arithmetic; expect substring appears in the plain result
- prefix: leading text kept as blocks, trailing expression evaluated;
          expect equals the whitespace-normalized first line
- emoji:  emoji substitution/counting; expect substring appears
- color:  COLOR_RESULT (color mixing)
- boxes:  colored boxes only (plain text strips to whitespace); expect hex
- blocks: letter-block fallback, nothing evaluated; expect equals the
          whitespace-normalized first line
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from purple_tui.rooms.play_room import SimpleEvaluator


def strip_markup(text: str) -> str:
    return re.sub(r'\[[^\]]*\]', '', text)


@pytest.fixture
def evaluator():
    return SimpleEvaluator()


# (input, kind, expect, correction_tracked) — correction None = don't care
CASES = [
    # --- Stray single letters: dropped only when adjacent to a digit AND the
    # --- rest is pure math (finger slip). Correction always shown.
    ("2 + 9a", "math", "= 11", True),
    ("2 + a9", "math", "= 11", True),
    ("2 + a 9", "math", "= 11", True),
    ("9a + 2", "math", "= 11", True),
    ("2 + 3 d", "math", "= 5", True),
    # Leading letter becomes a text prefix; trailing one is stripped
    ("e 2 + 2 e", "prefix", "e 4", True),

    # --- Single letters NOT adjacent to a digit: never stripped
    ("i + 2", "blocks", "i + 2", False),
    ("2 + b", "blocks", "2 + b", False),
    ("b 4 u", "blocks", "b 4 u", False),
    # x is multiplication between digits, plain text elsewhere
    ("2 x 3", "math", "= 6", False),
    ("2x3x4", "math", "= 24", False),
    ("x + 2", "blocks", "x + 2", False),
    ("2 + x", "blocks", "2 + x", False),
    # No operator: lone letter stays as a text prefix to the number
    ("a 9", "prefix", "a 9", False),
    ("a 5 + 5", "prefix", "a 10", False),
    ("c 3 + 4", "prefix", "c 7", False),

    # --- Multi-letter words are never stripped: emoji or text paths win
    ("2 + 3 cats", "emoji", "🐱🐱 + 🐱🐱🐱", None),
    ("2 cats + 3 dogs", "emoji", "🐱🐱 + 🐶🐶🐶", None),
    ("I ate 9 cookies", "emoji", "🍪🍪🍪🍪🍪🍪🍪🍪🍪", None),
    ("I have 5 apples", "emoji", "🍎🍎🍎🍎🍎", None),
    ("my 3 friends have 2 dogs", "emoji", "🐶🐶", None),
    ("we got 3 + 2 dogs", "prefix", "w e g o t 5 🐶", None),
    ("what is 2 + 3", "prefix", "w h a t i s 5", None),
    ("i am 6", "prefix", "i a m 6", None),
    ("u r 2 cool", "emoji", "😎😎", None),
    ("zibzab", "blocks", "z i b z a b", False),
    ("game over", "blocks", "g a m e o v e r", False),

    # --- Division words: only between numbers (or via "divided by")
    ("6 divided by 2", "math", "= 3", False),
    ("6 divide by 2", "math", "= 3", False),
    ("6 divide 2", "math", "= 3", False),
    ("6 divided 2", "math", "= 3", False),
    ("6 over 2", "math", "= 3", False),
    ("6 divded 2", "math", "= 3", True),
    ("6/2 dogs", "math", "= 3 🐶", None),
    ("6 over 2 dogs", "math", "= 3 🐶", None),
    # "over" next to a word is just text
    ("6 over cats", "emoji", "🐱", None),

    # --- Word operators and fuzzy typos between digits
    ("2 times 3", "math", "= 6", False),
    ("2 plus 3", "math", "= 5", False),
    ("5 minus 2", "math", "= 3", False),
    ("3 timess 2", "math", "= 6", True),
    ("2 pluss 3", "math", "= 5", True),
    # Real words sandwiched between two bare digits read as operator typos
    ("2 timer 3", "math", "= 6", True),
    ("4 oven 2", "math", "= 2", True),

    # --- Number words
    ("two plus three", "math", "= 5", False),
    ("five cats", "emoji", "🐱🐱🐱🐱🐱", None),

    # --- Colors with numbers
    ("red + blue", "color", "", None),
    ("red + 2", "color", "", None),
    ("2 + red", "color", "", None),
    ("yellow + 3 periwinkles", "color", "", None),
    ("3 reds", "boxes", "#ED1C24", None),

    # --- "and" as a joiner: strong (number/pure color neighbor) or
    # --- all-visual input; any plain word keeps "and" visible
    ("2 and 3", "math", "= 5", False),
    ("red and blue", "color", "", None),
    ("3 cats and 2 dogs", "emoji", "🐱🐱🐱 + 🐶🐶", None),
    ("cat and dog", "emoji", "🐱 + 🐶", None),
    ("star and moon", "emoji", "⭐ + 🌙", None),
    ("cat and me", "prefix", "🐱 a n d m e", None),
    ("I love cat and dog", "prefix", "I ❤️ 🐱 a n d 🐶", None),

    # --- Numeric edges
    ("8 / 0", "math", "🤷", None),
    ("-5", "blocks", "- 5", False),
    ("552 monkeys", "math", "= 552 🐵", None),
    ("cat=dog", "emoji", "🐱=🐶", None),
]


@pytest.mark.parametrize("text,kind,expect,corr", CASES, ids=[c[0] for c in CASES])
def test_boundary(evaluator, text, kind, expect, corr):
    evaluator._last_math_correction = None
    result = evaluator.evaluate(text)
    plain = strip_markup(result)
    line1 = " ".join(plain.split("\n")[0].split())

    if kind == "math":
        assert expect in plain
    elif kind == "prefix":
        assert line1 == expect
    elif kind == "emoji":
        assert expect in plain
    elif kind == "color":
        assert result.startswith("COLOR_RESULT:")
    elif kind == "boxes":
        assert plain.strip() == "" and expect.lower() in result.lower()
    elif kind == "blocks":
        assert line1 == expect
        assert "●" not in plain and "= " not in plain

    if corr is not None:
        assert bool(evaluator._last_math_correction) == corr


def test_stray_letter_correction_shows_what_changed(evaluator):
    evaluator.evaluate("2 + 9a")
    assert evaluator._last_math_correction == ("2 + 9a", "2 + 9")


def test_division_typo_correction_shows_symbol(evaluator):
    evaluator.evaluate("6 divded 2")
    assert evaluator._last_math_correction == ("6 divded 2", "6 / 2")
