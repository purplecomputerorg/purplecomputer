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
        result = evaluator.evaluate("2 + 3")
        assert result.startswith("5\n") and "•••••" in result

    def test_subtraction(self, evaluator):
        result = evaluator.evaluate("10 - 4")
        assert result.startswith("6\n") and "••••••" in result

    def test_multiplication(self, evaluator):
        result = evaluator.evaluate("3 * 4")
        assert result.startswith("12\n") and result.count("•") == 12

    def test_division(self, evaluator):
        result = evaluator.evaluate("8 / 2")
        assert result.startswith("4\n") and "••••" in result

    def test_division_decimal(self, evaluator):
        # Decimals don't get dots
        assert evaluator.evaluate("2 / 3") == "0.667"

    def test_division_clean(self, evaluator):
        # Clean decimals don't get dots either
        assert evaluator.evaluate("1 / 4") == "0.25"

    def test_complex_expression(self, evaluator):
        result = evaluator.evaluate("2 + 3 * 4")
        assert result.startswith("14\n") and result.count("•") == 14

    def test_parentheses(self, evaluator):
        result = evaluator.evaluate("(2 + 3) * 4")
        assert result.startswith("20\n") and result.count("•") == 20


class TestWordOperators:
    """Test word-based operators"""

    def test_times(self, evaluator):
        result = evaluator.evaluate("3 times 4")
        assert result.startswith("12\n") and result.count("•") == 12

    def test_times_no_spaces(self, evaluator):
        result = evaluator.evaluate("3times4")
        assert result.startswith("12\n") and result.count("•") == 12

    def test_plus(self, evaluator):
        result = evaluator.evaluate("2 plus 3")
        assert result.startswith("5\n") and result.count("•") == 5

    def test_plus_no_spaces(self, evaluator):
        result = evaluator.evaluate("2plus3")
        assert result.startswith("5\n") and result.count("•") == 5

    def test_minus(self, evaluator):
        result = evaluator.evaluate("5 minus 2")
        assert result.startswith("3\n") and result.count("•") == 3

    def test_minus_no_spaces(self, evaluator):
        result = evaluator.evaluate("5minus2")
        assert result.startswith("3\n") and result.count("•") == 3

    def test_divided_by(self, evaluator):
        result = evaluator.evaluate("8 divided by 2")
        assert result.startswith("4\n") and result.count("•") == 4

    def test_x_as_times(self, evaluator):
        result = evaluator.evaluate("3 x 4")
        assert result.startswith("12\n") and result.count("•") == 12

    def test_x_no_spaces(self, evaluator):
        result = evaluator.evaluate("3x4")
        assert result.startswith("12\n") and result.count("•") == 12


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
        # Single emoji just returns the word (not "1 cat")
        result = evaluator._describe_emoji_result("cat", "🐱")
        assert result == "cat"

    def test_emoji_times_number(self, evaluator):
        result = evaluator._describe_emoji_result("cat * 3", "🐱🐱🐱")
        assert result == "3 cats"

    def test_number_times_emoji(self, evaluator):
        result = evaluator._describe_emoji_result("3 * cat", "🐱🐱🐱")
        assert result == "3 cats"

    def test_emoji_addition(self, evaluator):
        result = evaluator._describe_emoji_result("apple + banana", "🍎🍌")
        assert result == "apple and banana"

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
        assert result == "cat and dog"

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


class TestParenthesesGrouping:
    """Test parentheses for grouping expressions"""

    def test_simple_math_parens(self, evaluator):
        """Basic math with parentheses"""
        result = evaluator.evaluate("(2 + 3) * 4")
        assert result.startswith("20")  # May have dots

    def test_nested_parens(self, evaluator):
        """Nested parentheses"""
        result = evaluator.evaluate("((2 + 3) * 2)")
        assert result.startswith("10")

    def test_multiple_parens(self, evaluator):
        """Multiple parentheses groups"""
        result = evaluator.evaluate("(2 + 3) * (1 + 1)")
        assert result.startswith("10")

    def test_parens_with_emoji_multiply(self, evaluator):
        """Parentheses with emoji multiplication: (2+3) * cat"""
        result = evaluator.evaluate("(2 + 3) * cat")
        assert result == "🐱🐱🐱🐱🐱"

    def test_emoji_in_parens_multiply(self, evaluator):
        """Emoji inside parentheses then multiplied: (cat + dog) * 2"""
        result = evaluator.evaluate("(cat + dog) * 2")
        assert result == "🐱🐶🐱🐶"

    def test_multiply_emoji_in_parens(self, evaluator):
        """Number times emoji in parentheses: 2 * (cat + dog)"""
        result = evaluator.evaluate("2 * (cat + dog)")
        assert result == "🐱🐶🐱🐶"

    def test_number_plus_emoji_parens(self, evaluator):
        """Number plus emoji multiplication in parens: 5 + (5 * cat)"""
        result = evaluator.evaluate("5 + (5 * cat)")
        assert result == "5🐱🐱🐱🐱🐱"

    def test_emoji_parens_plus_number(self, evaluator):
        """Emoji in parens plus number: (cat * 3) + 2"""
        result = evaluator.evaluate("(cat * 3) + 2")
        assert result == "🐱🐱🐱2"

    def test_complex_emoji_parens(self, evaluator):
        """Complex expression: (2 * cat) + (3 * dog)"""
        result = evaluator.evaluate("(2 * cat) + (3 * dog)")
        assert result == "🐱🐱🐶🐶🐶"

    def test_parens_with_word_operators(self, evaluator):
        """Parentheses with word operators: (2 plus 3) times cat"""
        result = evaluator.evaluate("(2 plus 3) times cat")
        assert result == "🐱🐱🐱🐱🐱"

    def test_deeply_nested_math(self, evaluator):
        """Deeply nested parentheses: ((1 + 2) + (3 + 4))"""
        result = evaluator.evaluate("((1 + 2) + (3 + 4))")
        assert result.startswith("10")

    def test_single_emoji_in_parens(self, evaluator):
        """Single emoji in parentheses: (cat)"""
        result = evaluator.evaluate("(cat)")
        assert result == "🐱"


class TestPluralEmojis:
    """Test plural emoji support"""

    def test_bare_plural(self, evaluator):
        """Bare plural word: apples -> 2 apples"""
        result = evaluator.evaluate("apples")
        assert result == "🍎🍎"

    def test_bare_plural_cats(self, evaluator):
        """Another bare plural: cats -> 2 cats"""
        result = evaluator.evaluate("cats")
        assert result == "🐱🐱"

    def test_number_space_plural(self, evaluator):
        """Number with space and plural: 3 apples"""
        result = evaluator.evaluate("3 apples")
        assert result == "🍎🍎🍎"

    def test_number_no_space_plural(self, evaluator):
        """Number directly attached to plural: 3apples"""
        result = evaluator.evaluate("3apples")
        assert result == "🍎🍎🍎"

    def test_number_space_singular(self, evaluator):
        """Number with singular: 3 apple"""
        result = evaluator.evaluate("3 apple")
        assert result == "🍎🍎🍎"

    def test_number_no_space_singular(self, evaluator):
        """Number attached to singular: 3apple"""
        result = evaluator.evaluate("3apple")
        assert result == "🍎🍎🍎"

    def test_plural_in_addition(self, evaluator):
        """Plurals in addition: apples + bananas"""
        result = evaluator.evaluate("apples + bananas")
        assert result == "🍎🍎🍌🍌"

    def test_mixed_plural_number(self, evaluator):
        """Mixed: 3 apples + 2 bananas"""
        result = evaluator.evaluate("3 apples + 2 bananas")
        assert result == "🍎🍎🍎🍌🍌"


class TestEmojiSubstitution:
    """Test emoji substitution in non-math text"""

    def test_ampersand_join(self, evaluator):
        """Emoji substitution with &: apple & orange"""
        result = evaluator.evaluate("apple & orange")
        assert result == "🍎 & 🍊"

    def test_word_between_emojis(self, evaluator):
        """Word between emojis: cat loves dog"""
        result = evaluator.evaluate("cat loves dog")
        assert result == "🐱 loves 🐶"

    def test_emoji_with_punctuation(self, evaluator):
        """Emoji with punctuation: cat, dog"""
        result = evaluator.evaluate("cat, dog")
        assert result == "🐱, 🐶"

    def test_mixed_emoji_and_text(self, evaluator):
        """Mixed emoji and regular text: I love cat"""
        result = evaluator.evaluate("I love cat")
        assert result == "I 😍 🐱"

    def test_no_substitution_for_math(self, evaluator):
        """Math expressions should not do text substitution"""
        result = evaluator.evaluate("2 + 2")
        assert result.startswith("4")  # Should be math result, not substitution


class TestNumberVisualization:
    """Test dot visualization for numbers"""

    def test_small_number_has_dots(self, evaluator):
        """Small numbers should show dots"""
        result = evaluator.evaluate("5")
        assert "•••••" in result
        assert result.startswith("5")

    def test_math_result_has_dots(self, evaluator):
        """Math result should show dots"""
        result = evaluator.evaluate("2 + 2")
        assert "••••" in result
        assert result.startswith("4")

    def test_large_number_no_dots(self, evaluator):
        """Numbers >= 1000 should not show dots"""
        result = evaluator.evaluate("1000")
        assert "•" not in result
        assert result == "1000"

    def test_very_large_number_no_dots(self, evaluator):
        """Very large numbers should not show dots"""
        result = evaluator.evaluate("9999")
        assert "•" not in result

    def test_decimal_no_dots(self, evaluator):
        """Decimal numbers should not show dots"""
        result = evaluator.evaluate("2.5")
        assert "•" not in result

    def test_zero_no_dots(self, evaluator):
        """Zero should not show dots"""
        result = evaluator.evaluate("0")
        assert "•" not in result

    def test_negative_no_dots(self, evaluator):
        """Negative numbers should not show dots"""
        result = evaluator.evaluate("0 - 5")
        assert "•" not in result

    def test_hundred_dots_wrapped(self, evaluator):
        """100 dots should wrap to multiple lines"""
        result = evaluator.evaluate("100")
        assert result.startswith("100\n")
        # Should have 100 dots total
        assert result.count("•") == 100
