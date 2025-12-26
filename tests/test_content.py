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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
