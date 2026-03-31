#!/usr/bin/env python3
"""Tests for ContentManager word lookup and validation.

Run with: pytest tests/test_content.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from purple_tui.content import ContentManager


@pytest.fixture
def content():
    cm = ContentManager()
    cm.load_all()
    return cm


class TestGetWord:
    """Test unified word lookup for emojis and colors."""

    def test_emoji_exact_match(self, content):
        result = content.get_word("cat")
        assert result == ("🐱", "emoji")

    def test_color_exact_match(self, content):
        result = content.get_word("red")
        assert result is not None
        assert result[1] == "color"
        assert result[0].startswith("#")

    def test_emoji_plural(self, content):
        result = content.get_word("cats")
        assert result == ("🐱", "emoji")

    def test_emoji_plural_bananas(self, content):
        result = content.get_word("bananas")
        assert result == ("🍌", "emoji")

    def test_unknown_word(self, content):
        assert content.get_word("xyzzy") is None

    def test_case_insensitive(self, content):
        assert content.get_word("CAT") == ("🐱", "emoji")
        assert content.get_word("Cat") == ("🐱", "emoji")

    def test_short_s_word_not_plural(self, content):
        # "as" should not try to look up "a" as singular
        assert content.get_word("as") is None

    def test_color_plural(self, content):
        # "reds" should match "red"
        result = content.get_word("reds")
        assert result is not None
        assert result[1] == "color"


class TestIsValidWord:
    """Test word validation."""

    def test_valid_emoji(self, content):
        assert content.is_valid_word("cat") is True

    def test_valid_color(self, content):
        assert content.is_valid_word("blue") is True

    def test_valid_plural(self, content):
        assert content.is_valid_word("dogs") is True

    def test_invalid_word(self, content):
        assert content.is_valid_word("asdfgh") is False

    def test_empty_string(self, content):
        assert content.is_valid_word("") is False


class TestFuzzyEmoji:
    """Fuzzy matching in get_emoji (DL distance, min 5 chars)."""

    def test_typo_dinno(self, content):
        assert content.get_emoji("dinno") is not None  # → dino

    def test_typo_rabit(self, content):
        assert content.get_emoji("rabit") is not None  # → rabbit

    def test_typo_monky(self, content):
        assert content.get_emoji("monky") is not None  # → monkey

    def test_typo_pengin(self, content):
        assert content.get_emoji("pengin") is not None  # → penguin

    def test_short_word_no_fuzzy(self, content):
        """4-char words should NOT fuzzy match (too many false positives)."""
        # "barn" should not match "bear"
        result = content.get_emoji("barn")
        assert result is None

    def test_exact_still_works(self, content):
        assert content.get_emoji("cat") is not None

    def test_plural_still_works(self, content):
        assert content.get_emoji("cats") is not None

    def test_correction_tracked(self, content):
        content._last_correction = None
        content.get_emoji("dinno")
        assert content._last_correction is not None
        orig, corrected = content._last_correction
        assert orig == "dinno"

    def test_no_correction_on_exact(self, content):
        content._last_correction = None
        content.get_emoji("cat")
        assert content._last_correction is None


class TestFuzzyColor:
    """Fuzzy matching in get_color (DL distance, min 5 chars)."""

    def test_typo_purpel(self, content):
        assert content.get_color("purpel") is not None

    def test_typo_oragne(self, content):
        assert content.get_color("oragne") is not None

    def test_typo_yellw(self, content):
        assert content.get_color("yellw") is not None

    def test_short_word_no_fuzzy(self, content):
        """4-char words should NOT fuzzy match."""
        # "bleu" (4 chars) should not fuzzy match at content layer
        result = content.get_color("bleu")
        assert result is None

    def test_exact_still_works(self, content):
        assert content.get_color("red") is not None

    def test_yellow_not_hello(self, content):
        """'yellow' must not fuzzy match 'hello' emoji."""
        content._last_correction = None
        content.get_color("yellow")
        assert content._last_correction is None  # exact match, no fuzzy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
