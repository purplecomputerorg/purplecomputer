"""Tests for Ask Mode evaluator and speech"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.modes.ask_mode import SimpleEvaluator


@pytest.fixture
def evaluator():
    return SimpleEvaluator()


class TestBasicMath:
    """Test basic arithmetic"""

    def test_addition(self, evaluator):
        assert evaluator.evaluate("2 + 3") == "5"

    def test_subtraction(self, evaluator):
        assert evaluator.evaluate("10 - 4") == "6"

    def test_multiplication(self, evaluator):
        assert evaluator.evaluate("3 * 4") == "12"

    def test_division(self, evaluator):
        assert evaluator.evaluate("8 / 2") == "4"

    def test_division_decimal(self, evaluator):
        assert evaluator.evaluate("2 / 3") == "0.667"

    def test_division_clean(self, evaluator):
        assert evaluator.evaluate("1 / 4") == "0.25"

    def test_complex_expression(self, evaluator):
        assert evaluator.evaluate("2 + 3 * 4") == "14"

    def test_parentheses(self, evaluator):
        assert evaluator.evaluate("(2 + 3) * 4") == "20"


class TestWordOperators:
    """Test word-based operators"""

    def test_times(self, evaluator):
        assert evaluator.evaluate("3 times 4") == "12"

    def test_times_no_spaces(self, evaluator):
        assert evaluator.evaluate("3times4") == "12"

    def test_plus(self, evaluator):
        assert evaluator.evaluate("2 plus 3") == "5"

    def test_plus_no_spaces(self, evaluator):
        assert evaluator.evaluate("2plus3") == "5"

    def test_minus(self, evaluator):
        assert evaluator.evaluate("5 minus 2") == "3"

    def test_minus_no_spaces(self, evaluator):
        assert evaluator.evaluate("5minus2") == "3"

    def test_divided_by(self, evaluator):
        assert evaluator.evaluate("8 divided by 2") == "4"

    def test_x_as_times(self, evaluator):
        assert evaluator.evaluate("3 x 4") == "12"

    def test_x_no_spaces(self, evaluator):
        assert evaluator.evaluate("3x4") == "12"


class TestEmojiLookup:
    """Test emoji lookup"""

    def test_simple_emoji(self, evaluator):
        assert evaluator.evaluate("cat") == "🐱"

    def test_emoji_case_insensitive(self, evaluator):
        assert evaluator.evaluate("CAT") == "🐱"

    def test_unknown_word(self, evaluator):
        # Unknown words just echo back
        assert evaluator.evaluate("xyz123") == "xyz123"


class TestEmojiMath:
    """Test emoji multiplication and addition"""

    def test_emoji_times_number(self, evaluator):
        result = evaluator.evaluate("cat * 3")
        assert result == "🐱🐱🐱"

    def test_number_times_emoji(self, evaluator):
        result = evaluator.evaluate("3 * cat")
        assert result == "🐱🐱🐱"

    def test_emoji_x_number(self, evaluator):
        result = evaluator.evaluate("cat x 2")
        assert result == "🐱🐱"

    def test_emoji_no_spaces(self, evaluator):
        result = evaluator.evaluate("cat*3")
        assert result == "🐱🐱🐱"

    def test_emoji_addition(self, evaluator):
        result = evaluator.evaluate("cat + dog")
        assert result == "🐱🐶"

    def test_emoji_complex(self, evaluator):
        result = evaluator.evaluate("apple*3 + banana*2")
        assert result == "🍎🍎🍎🍌🍌"

    def test_emoji_complex_with_spaces(self, evaluator):
        result = evaluator.evaluate("apple * 3 + banana * 2")
        assert result == "🍎🍎🍎🍌🍌"

    def test_emoji_times_word(self, evaluator):
        """Test 'cat times 3' format"""
        result = evaluator.evaluate("cat times 3")
        assert result == "🐱🐱🐱"

    def test_number_times_word_emoji(self, evaluator):
        """Test '3 times cat' format"""
        result = evaluator.evaluate("3 times cat")
        assert result == "🐱🐱🐱"

    def test_emoji_plus_word(self, evaluator):
        """Test 'cat plus dog' format"""
        result = evaluator.evaluate("cat plus dog")
        assert result == "🐱🐶"

    def test_emoji_plus_number(self, evaluator):
        """Test 'cat*3 + 2' gives emoji followed by number"""
        result = evaluator.evaluate("cat*3 + 2")
        assert result == "🐱🐱🐱2"

    def test_emoji_mixed_with_number(self, evaluator):
        """Test 'apple times 2 plus 5' gives emoji followed by number"""
        result = evaluator.evaluate("apple times 2 plus 5")
        assert result == "🍎🍎5"

    def test_number_plus_emoji(self, evaluator):
        """Test '3 + cat' gives number followed by emoji"""
        result = evaluator.evaluate("3 + cat")
        assert result == "3🐱"


class TestEmojiDescription:
    """Test emoji result description for speech"""

    def test_single_emoji(self, evaluator):
        result = evaluator._describe_emoji_result("cat", "🐱")
        assert result == "1 cat"

    def test_emoji_times_number(self, evaluator):
        result = evaluator._describe_emoji_result("cat * 3", "🐱🐱🐱")
        assert result == "3 cats"

    def test_number_times_emoji(self, evaluator):
        result = evaluator._describe_emoji_result("3 * cat", "🐱🐱🐱")
        assert result == "3 cats"

    def test_emoji_addition(self, evaluator):
        result = evaluator._describe_emoji_result("apple + banana", "🍎🍌")
        assert result == "1 apple and 1 banana"

    def test_emoji_complex(self, evaluator):
        result = evaluator._describe_emoji_result("apple*3 + banana*2", "🍎🍎🍎🍌🍌")
        assert result == "3 apples and 2 bananas"

    def test_single_item(self, evaluator):
        result = evaluator._describe_emoji_result("cat * 1", "🐱")
        assert result == "1 cat"

    def test_times_word_description(self, evaluator):
        """Test description with 'times' word"""
        result = evaluator._describe_emoji_result("cat times 3", "🐱🐱🐱")
        assert result == "3 cats"

    def test_plus_word_description(self, evaluator):
        """Test description with 'plus' word"""
        result = evaluator._describe_emoji_result("cat plus dog", "🐱🐶")
        assert result == "1 cat and 1 dog"

    def test_times_and_plus_words(self, evaluator):
        """Test description with both 'times' and 'plus' words"""
        result = evaluator._describe_emoji_result("apple times 3 plus banana times 2", "🍎🍎🍎🍌🍌")
        assert result == "3 apples and 2 bananas"


class TestNumberFormatting:
    """Test number formatting"""

    def test_integer(self, evaluator):
        assert evaluator._format_number(42) == "42"

    def test_float_whole(self, evaluator):
        assert evaluator._format_number(3.0) == "3"

    def test_float_decimal(self, evaluator):
        assert evaluator._format_number(3.14159) == "3.142"

    def test_float_short_decimal(self, evaluator):
        assert evaluator._format_number(0.5) == "0.5"

    def test_float_trailing_zeros(self, evaluator):
        assert evaluator._format_number(1.100) == "1.1"
