#!/usr/bin/env python3
"""A correction must read as a typing slip, not as a different word.

Distance alone is far too loose against a 400+ word vocabulary: "words" is one
edit from "worms" and "print" one from "paint". See fuzzy.looks_like_a_slip.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from purple_tui.fuzzy import looks_like_a_slip, _neighbor_keys
from purple_tui.content import ContentManager


@pytest.fixture
def content():
    c = ContentManager()
    c.load_all()
    return c


@pytest.mark.parametrize("a,b", [("d", "f"), ("d", "e"), ("d", "c"), ("m", "n"), ("o", "i")])
def test_keys_next_to_each_other(a, b):
    assert _neighbor_keys(a, b) and _neighbor_keys(b, a)


@pytest.mark.parametrize("a,b", [("d", "m"), ("a", "r"), ("t", "p"), ("e", "i"), ("q", "l")])
def test_keys_far_apart(a, b):
    assert not _neighbor_keys(a, b)


@pytest.mark.parametrize("typed,candidate", [
    ("dinno", "dino"),          # doubled letter
    ("doggiess", "doggies"),
    ("chocolat", "chocolate"),  # dropped last letter
    ("unicron", "unicorn"),     # transposed pair
    ("dinosuar", "dinosaur"),
    ("unicorm", "unicorn"),     # finger hit the next key over
    ("flowr", "flower"),        # dropped letter, long enough word
    ("hourse", "horse"),
])
def test_slips_are_still_corrected(typed, candidate):
    assert looks_like_a_slip(typed, candidate)


@pytest.mark.parametrize("typed,candidate", [
    ("words", "worms"),   # letter swapped for one across the keyboard
    ("print", "paint"),
    ("sheet", "sheep"),
    ("timer", "tiger"),
    ("grade", "grape"),
    ("start", "star"),    # extra letter typed onto the end of a short word
    ("stick", "sick"),
    ("three", "tree"),
])
def test_different_words_are_not_corrections(typed, candidate):
    assert not looks_like_a_slip(typed, candidate)


@pytest.mark.parametrize("word", ["print", "sheet", "start", "sting", "stick", "three",
                                  "timer", "grade", "steal"])
def test_the_matcher_alone_leaves_these_words_alone(content, monkeypatch, word):
    """Holds without the common-word list, which is the other layer. Words whose
    lookalike differs by a neighboring key ("trick"/"truck") are that layer's
    job, not this one."""
    monkeypatch.setattr("purple_tui.content.is_real_word", lambda w: False)
    content._emoji_fuzzy_cache.clear()
    content._color_fuzzy_cache.clear()
    assert content.resolve(word).kind is None
