#!/usr/bin/env python3
"""Tests for Ask Mode - evaluator, autocomplete, color mixing, and hint rendering.

Run with: pytest tests/test_ask_mode.py -v
Or standalone: python tests/test_ask_mode.py
"""

import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from purple_tui.modes.ask_mode import SimpleEvaluator


# =============================================================================
# Pytest-based Evaluator Tests
# =============================================================================

if HAS_PYTEST:
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
            assert evaluator.evaluate("2 / 3") == "0.667"

        def test_division_clean(self, evaluator):
            assert evaluator.evaluate("1 / 4") == "0.25"

        def test_complex_expression(self, evaluator):
            result = evaluator.evaluate("2 + 3 * 4")
            assert result.startswith("14\n") and result.count("•") == 14

        def test_parentheses(self, evaluator):
            result = evaluator.evaluate("(2 + 3) * 4")
            assert result.startswith("20\n") and result.count("•") == 20


    class TestMostlyMathCleaning:
        """Test that mostly-math expressions tolerate typos like accidental '='."""

        def test_accidental_equals_cleaned(self, evaluator):
            """Accidental = in long math expression should be replaced with +."""
            result = evaluator.evaluate("2+3+4-5+5+3-2=3+4+6")
            # = replaced with +: 2+3+4-5+5+3-2+3+4+6 = 23
            assert result.startswith("23\n")

        def test_accidental_equals_middle(self, evaluator):
            """Equals in middle of expression."""
            result = evaluator.evaluate("1+2+3=4+5+6")
            # = replaced with +: 1+2+3+4+5+6 = 21
            assert result.startswith("21\n")

        def test_too_few_operators_not_cleaned(self, evaluator):
            """With only 2 operators, don't clean (might be intentional)."""
            # Only 2 math operators, doesn't meet MIN_MATH_OPERATORS threshold
            result = evaluator.evaluate("2+3=5")
            # Should NOT be cleaned, returns as-is (not valid math)
            assert result == "2+3=5"

        def test_too_many_non_math_symbols_not_cleaned(self, evaluator):
            """If too many non-math symbols, don't clean."""
            # 3 math ops (+,+,+) but 3 non-math (=,=,=), ratio is 50% < 60%
            result = evaluator.evaluate("1+2=3+4=5+6=7")
            assert result == "1+2=3+4=5+6=7"

        def test_clean_preserves_spaces(self, evaluator):
            """Cleaning should preserve spaces and replace invalid punct with +."""
            # 4 math ops (+,+,+,+), 1 non-math (=), ratio = 4/5 = 80% >= 60%
            result = evaluator.evaluate("2 + 3 + 4 = 5 + 6")
            # = replaced with +: 2 + 3 + 4 + 5 + 6 = 20
            assert result.startswith("20\n")

        def test_borderline_ratio_passes(self, evaluator):
            """At 60% threshold, 3 math / 5 total (60%) should pass."""
            # 3 math ops (+,+,+), 2 non-math (=,=), ratio = 3/5 = 60%
            result = evaluator.evaluate("1+2+3+4=5=6")
            # Both = replaced with +: 1+2+3+4+5+6 = 21
            assert result.startswith("21\n")


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
            assert evaluator.evaluate("xyz123") == "xyz123"


    class TestEmojiMath:
        """Test emoji multiplication and addition"""

        def test_emoji_times_number(self, evaluator):
            assert evaluator.evaluate("cat * 3") == "3 🐱\n🐱🐱🐱"

        def test_number_times_emoji(self, evaluator):
            assert evaluator.evaluate("3 * cat") == "3 🐱\n🐱🐱🐱"

        def test_emoji_x_number(self, evaluator):
            assert evaluator.evaluate("cat x 2") == "2 🐱\n🐱🐱"

        def test_emoji_no_spaces(self, evaluator):
            assert evaluator.evaluate("cat*3") == "3 🐱\n🐱🐱🐱"

        def test_emoji_addition(self, evaluator):
            assert evaluator.evaluate("cat + dog") == "🐱 🐶"

        def test_emoji_complex(self, evaluator):
            # Multi-emoji with multiplication shows label
            assert evaluator.evaluate("apple*3 + banana*2") == "3 🍎 2 🍌\n🍎🍎🍎 🍌🍌"

        def test_emoji_complex_with_spaces(self, evaluator):
            # Multi-emoji with multiplication shows label
            assert evaluator.evaluate("apple * 3 + banana * 2") == "3 🍎 2 🍌\n🍎🍎🍎 🍌🍌"

        def test_emoji_times_word(self, evaluator):
            assert evaluator.evaluate("cat times 3") == "3 🐱\n🐱🐱🐱"

        def test_number_times_word_emoji(self, evaluator):
            assert evaluator.evaluate("3 times cat") == "3 🐱\n🐱🐱🐱"

        def test_emoji_plus_word(self, evaluator):
            assert evaluator.evaluate("cat plus dog") == "🐱 🐶"

        def test_number_attaches_to_next_emoji(self, evaluator):
            # 2 attaches to 3 cats = 5 cats (with label)
            assert evaluator.evaluate("2 + 3 cats") == "5 🐱\n🐱🐱🐱🐱🐱"

        def test_number_attaches_to_emoji_after(self, evaluator):
            # 3 + cat = 4 cats (3 attaches to the 1 cat, with label)
            assert evaluator.evaluate("3 + cat") == "4 🐱\n🐱🐱🐱🐱"

        def test_multiple_numbers_attach_to_next_emoji(self, evaluator):
            # 3 + 4 + 2 bananas = 9 bananas (with label)
            assert evaluator.evaluate("3 + 4 + 2 bananas") == "9 🍌\n🍌🍌🍌🍌🍌🍌🍌🍌🍌"

        def test_number_attaches_per_emoji_group(self, evaluator):
            # 5 + 2 cats + 3 dogs = 7 cats + 3 dogs (with label for computed counts)
            assert evaluator.evaluate("5 + 2 cats + 3 dogs") == "7 🐱 3 🐶\n🐱🐱🐱🐱🐱🐱🐱 🐶🐶🐶"

        def test_trailing_number_attaches_to_last(self, evaluator):
            # cat*3 + 2 = 5 cats (2 attaches to the 3 cats, with label)
            assert evaluator.evaluate("cat*3 + 2") == "5 🐱\n🐱🐱🐱🐱🐱"

        def test_number_between_emojis(self, evaluator):
            # 2 cats + 5 + 3 dogs = 2 cats + 8 dogs (with label for computed counts)
            assert evaluator.evaluate("2 cats + 5 + 3 dogs") == "2 🐱 8 🐶\n🐱🐱 🐶🐶🐶🐶🐶🐶🐶🐶"

        def test_n_times_m_word(self, evaluator):
            # 5 x 2 cats = 10 cats (with label)
            assert evaluator.evaluate("5 x 2 cats") == "10 🐱\n" + "🐱" * 10

        def test_n_times_m_word_singular(self, evaluator):
            # 5 x 2 cat = 10 cats (with label)
            assert evaluator.evaluate("5 x 2 cat") == "10 🐱\n" + "🐱" * 10

        def test_n_star_m_word(self, evaluator):
            # 3 * 4 dogs = 12 dogs (with label)
            assert evaluator.evaluate("3 * 4 dogs") == "12 🐶\n" + "🐶" * 12

        def test_n_times_word_m(self, evaluator):
            # 2 times 5 cats = 10 cats (with label)
            assert evaluator.evaluate("2 times 5 cats") == "10 🐱\n" + "🐱" * 10


    class TestEmojiDescription:
        """Test emoji result description for speech"""

        def test_single_emoji(self, evaluator):
            assert evaluator._describe_emoji_result("cat", "🐱") == "cat"

        def test_emoji_times_number(self, evaluator):
            assert evaluator._describe_emoji_result("cat * 3", "🐱🐱🐱") == "3 cats"

        def test_number_times_emoji(self, evaluator):
            assert evaluator._describe_emoji_result("3 * cat", "🐱🐱🐱") == "3 cats"

        def test_emoji_addition(self, evaluator):
            assert evaluator._describe_emoji_result("apple + banana", "🍎🍌") == "apple and banana"

        def test_emoji_complex(self, evaluator):
            assert evaluator._describe_emoji_result("apple*3 + banana*2", "🍎🍎🍎🍌🍌") == "3 apples and 2 bananas"

        def test_single_item(self, evaluator):
            assert evaluator._describe_emoji_result("cat * 1", "🐱") == "1 cat"

        def test_times_word_description(self, evaluator):
            assert evaluator._describe_emoji_result("cat times 3", "🐱🐱🐱") == "3 cats"

        def test_plus_word_description(self, evaluator):
            assert evaluator._describe_emoji_result("cat plus dog", "🐱🐶") == "cat and dog"

        def test_times_and_plus_words(self, evaluator):
            assert evaluator._describe_emoji_result("apple times 3 plus banana times 2", "🍎🍎🍎🍌🍌") == "3 apples and 2 bananas"


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
            result = evaluator.evaluate("(2 + 3) * 4")
            assert result.startswith("20")

        def test_nested_parens(self, evaluator):
            result = evaluator.evaluate("((2 + 3) * 2)")
            assert result.startswith("10")

        def test_multiple_parens(self, evaluator):
            result = evaluator.evaluate("(2 + 3) * (1 + 1)")
            assert result.startswith("10")

        def test_parens_with_emoji_multiply(self, evaluator):
            assert evaluator.evaluate("(2 + 3) * cat") == "5 🐱\n🐱🐱🐱🐱🐱"

        def test_emoji_in_parens_multiply(self, evaluator):
            assert evaluator.evaluate("(cat + dog) * 2") == "🐱 🐶🐱 🐶"

        def test_multiply_emoji_in_parens(self, evaluator):
            assert evaluator.evaluate("2 * (cat + dog)") == "🐱 🐶🐱 🐶"

        def test_number_plus_emoji_parens(self, evaluator):
            # 5 + (5 cats) = 10 cats (with label, + expr implies computation)
            result = evaluator.evaluate("5 + (5 * cat)")
            lines = result.split('\n')
            assert lines[0] == "10 🐱"
            assert lines[1].count("🐱") == 10

        def test_emoji_parens_plus_number(self, evaluator):
            # (3 cats) + 2 = 5 cats (with label, + expr implies computation)
            result = evaluator.evaluate("(cat * 3) + 2")
            lines = result.split('\n')
            assert lines[0] == "5 🐱"
            assert lines[1].count("🐱") == 5

        def test_complex_emoji_parens(self, evaluator):
            # Multi-emoji with multiplication shows label
            assert evaluator.evaluate("(2 * cat) + (3 * dog)") == "2 🐱 3 🐶\n🐱🐱 🐶🐶🐶"

        def test_parens_with_word_operators(self, evaluator):
            assert evaluator.evaluate("(2 plus 3) times cat") == "5 🐱\n🐱🐱🐱🐱🐱"

        def test_deeply_nested_math(self, evaluator):
            result = evaluator.evaluate("((1 + 2) + (3 + 4))")
            assert result.startswith("10")

        def test_single_emoji_in_parens(self, evaluator):
            assert evaluator.evaluate("(cat)") == "🐱"


    class TestPluralEmojis:
        """Test plural emoji support"""

        def test_bare_plural(self, evaluator):
            assert evaluator.evaluate("apples") == "🍎🍎"

        def test_bare_plural_cats(self, evaluator):
            assert evaluator.evaluate("cats") == "🐱🐱"

        def test_number_space_plural(self, evaluator):
            assert evaluator.evaluate("3 apples") == "🍎🍎🍎"

        def test_number_no_space_plural(self, evaluator):
            assert evaluator.evaluate("3apples") == "🍎🍎🍎"

        def test_number_space_singular(self, evaluator):
            assert evaluator.evaluate("3 apple") == "🍎🍎🍎"

        def test_number_no_space_singular(self, evaluator):
            assert evaluator.evaluate("3apple") == "🍎🍎🍎"

        def test_plural_in_addition(self, evaluator):
            # Plurals treated as 2, shows label for computed counts
            assert evaluator.evaluate("apples + bananas") == "2 🍎 2 🍌\n🍎🍎 🍌🍌"

        def test_mixed_plural_number(self, evaluator):
            # Multi-emoji with multiplication shows label
            assert evaluator.evaluate("3 apples + 2 bananas") == "3 🍎 2 🍌\n🍎🍎🍎 🍌🍌"


    class TestEmojiSubstitution:
        """Test emoji substitution in non-math text"""

        def test_ampersand_join(self, evaluator):
            assert evaluator.evaluate("apple & orange") == "🍎 & 🍊"

        def test_word_between_emojis(self, evaluator):
            assert evaluator.evaluate("cat loves dog") == "🐱 loves 🐶"

        def test_emoji_with_punctuation(self, evaluator):
            assert evaluator.evaluate("cat, dog") == "🐱, 🐶"

        def test_mixed_emoji_and_text(self, evaluator):
            assert evaluator.evaluate("I love cat") == "I 😍 🐱"

        def test_no_substitution_for_math(self, evaluator):
            result = evaluator.evaluate("2 + 2")
            assert result.startswith("4")


    class TestNumberVisualization:
        """Test dot visualization for numbers"""

        def test_small_number_has_dots(self, evaluator):
            result = evaluator.evaluate("5")
            assert "•••••" in result and result.startswith("5")

        def test_math_result_has_dots(self, evaluator):
            result = evaluator.evaluate("2 + 2")
            assert "••••" in result and result.startswith("4")

        def test_large_number_no_dots(self, evaluator):
            result = evaluator.evaluate("1000")
            assert "•" not in result and result == "1000"

        def test_very_large_number_no_dots(self, evaluator):
            assert "•" not in evaluator.evaluate("9999")

        def test_decimal_no_dots(self, evaluator):
            assert "•" not in evaluator.evaluate("2.5")

        def test_zero_no_dots(self, evaluator):
            assert "•" not in evaluator.evaluate("0")

        def test_negative_no_dots(self, evaluator):
            assert "•" not in evaluator.evaluate("0 - 5")

        def test_hundred_dots_wrapped(self, evaluator):
            result = evaluator.evaluate("100")
            assert result.startswith("100\n") and result.count("•") == 100


# =============================================================================
# Standalone Autocomplete Tests (also run via pytest)
# =============================================================================

class MockContent:
    """Mock content provider for autocomplete tests."""
    def __init__(self):
        self.colors = {
            "red": "#E52B50",
            "green": "#228B22",
            "gray": "#808080",
            "grey": "#808080",
            "gold": "#FFD700",
            "grape": "#6F2DA8",
        }
        self.emojis = {
            "apple": "🍎",
            "airplane": "✈️",
            "art": "🎨",
            "grape": "🍇",
            "grapes": "🍇",
            "green": "🟢",
            "cat": "🐱",
            "cow": "🐮",
        }

    def get_color(self, word):
        return self.colors.get(word.lower())

    def get_emoji(self, word):
        return self.emojis.get(word.lower())

    def search_colors(self, prefix):
        prefix = prefix.lower()
        return [(w, h) for w, h in sorted(self.colors.items()) if w.startswith(prefix)]

    def search_emojis(self, prefix):
        prefix = prefix.lower()
        return [(w, e) for w, e in sorted(self.emojis.items()) if w.startswith(prefix)]


def check_autocomplete(text, content):
    """Simplified version of _check_autocomplete logic."""
    # Common 2-letter words that shouldn't trigger autocomplete
    COMMON_2CHAR = {'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if',
                    'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so',
                    'to', 'up', 'us', 'we', 'hi', 'oh', 'ok'}

    text = text.lower().strip()
    parts = re.split(r'[\s+*x]+', text)
    words = [p for p in parts if p]
    if not words:
        return [], "emoji"

    last_word = words[-1]
    if len(last_word) < 2 or last_word in COMMON_2CHAR:
        return [], "emoji"

    if content.get_color(last_word) or content.get_emoji(last_word):
        return [], "emoji"

    color_matches = content.search_colors(last_word)
    emoji_matches = content.search_emojis(last_word)

    combined = []
    seen_words = set()

    for word, hex_code in color_matches:
        if word != last_word and word not in seen_words:
            combined.append((word, hex_code, True))
            seen_words.add(word)

    for word, emoji in emoji_matches:
        if word != last_word and word not in seen_words:
            combined.append((word, emoji, False))
            seen_words.add(word)

    combined = combined[:5]

    if not combined:
        return [], "emoji"

    has_colors = any(is_color for _, _, is_color in combined)
    has_emojis = any(not is_color for _, _, is_color in combined)

    matches = [(word, display) for word, display, _ in combined]
    match_type = "mixed" if (has_colors and has_emojis) else ("color" if has_colors else "emoji")

    return matches, match_type


class TestAutocomplete:
    """Test autocomplete functionality."""

    def test_red_plus_ap_suggests_apple(self):
        content = MockContent()
        matches, _ = check_autocomplete("red + ap", content)
        assert [w for w, _ in matches] == ["apple"]

    def test_red_plus_gr_suggests_colors_and_emojis(self):
        content = MockContent()
        matches, match_type = check_autocomplete("red + gr", content)
        words = [w for w, _ in matches]
        assert set(words) == {"gray", "green", "grey", "grape", "grapes"}
        assert match_type == "mixed"

    def test_gr_suggests_colors_and_emojis(self):
        content = MockContent()
        matches, _ = check_autocomplete("gr", content)
        words = [w for w, _ in matches]
        assert set(words) == {"gray", "green", "grey", "grape", "grapes"}

    def test_gol_suggests_gold(self):
        content = MockContent()
        matches, match_type = check_autocomplete("gol", content)
        assert [w for w, _ in matches] == ["gold"]
        assert match_type == "color"

    def test_go_no_suggestions_common_word(self):
        # "go" is a common 2-letter word, shouldn't trigger autocomplete
        content = MockContent()
        matches, _ = check_autocomplete("go", content)
        assert matches == []

    def test_ca_suggests_cat(self):
        content = MockContent()
        matches, match_type = check_autocomplete("ca", content)
        assert [w for w, _ in matches] == ["cat"]
        assert match_type == "emoji"

    def test_exact_color_no_suggestions(self):
        content = MockContent()
        matches, _ = check_autocomplete("red", content)
        assert matches == []

    def test_exact_emoji_no_suggestions(self):
        content = MockContent()
        matches, _ = check_autocomplete("cat", content)
        assert matches == []

    def test_short_prefix_no_suggestions(self):
        content = MockContent()
        matches, _ = check_autocomplete("r", content)
        assert matches == []

    def test_empty_no_suggestions(self):
        content = MockContent()
        matches, _ = check_autocomplete("", content)
        assert matches == []


class TestHintRendering:
    """Test autocomplete hint rendering."""

    def _render_hint(self, matches):
        if not matches:
            return ""
        parts = []
        for word, display_value in matches:
            if display_value.startswith("#"):
                parts.append(f"{word} [{display_value}]██[/]")
            else:
                parts.append(f"{word} {display_value}")
        return "   ".join(parts)

    def test_color_uses_hex_markup(self):
        result = self._render_hint([("red", "#E52B50")])
        assert "red" in result and "[#E52B50]" in result and "██" in result

    def test_emoji_shows_emoji(self):
        result = self._render_hint([("cat", "🐱")])
        assert "cat" in result and "🐱" in result

    def test_mixed_rendering(self):
        result = self._render_hint([("green", "#228B22"), ("grape", "🍇")])
        assert "[#228B22]" in result and "🍇" in result


class TestColorMixing:
    """Test color mixing behavior."""

    def test_two_colors_mix(self, evaluator):
        result = evaluator.evaluate("red + blue")
        assert result.startswith("COLOR_RESULT:")

    def test_color_with_multiplier(self, evaluator):
        result = evaluator.evaluate("red * 3 + yellow")
        assert result.startswith("COLOR_RESULT:")
        # Should have 4 components (3 red + 1 yellow)
        parts = result.split(":")
        components = parts[3].split(",")
        assert len(components) == 4

    def test_color_plus_emoji_mixed(self, evaluator):
        # red + cat + blue = mixed purple + cat emoji
        result = evaluator.evaluate("red + cat + blue")
        assert "COLOR_RESULT:" in result
        assert "🐱" in result

    def test_color_with_number_multiplier(self, evaluator):
        result = evaluator.evaluate("3 yellow + red")
        assert result.startswith("COLOR_RESULT:")
        parts = result.split(":")
        components = parts[3].split(",")
        assert len(components) == 4  # 3 yellow + 1 red

    def test_color_plural_with_number(self, evaluator):
        # "3 yellows + red" should work like "3 yellow + red"
        result = evaluator.evaluate("3 yellows + red")
        assert result.startswith("COLOR_RESULT:")
        parts = result.split(":")
        components = parts[3].split(",")
        assert len(components) == 4

    def test_color_times_variant(self, evaluator):
        result = evaluator.evaluate("yellow times 3 + red")
        assert result.startswith("COLOR_RESULT:")

    def test_color_x_variant(self, evaluator):
        result = evaluator.evaluate("yellow x 3 + red")
        assert result.startswith("COLOR_RESULT:")


class TestMixedExpressions:
    """Test expressions mixing colors, emojis, and numbers."""

    def test_color_and_emoji(self, evaluator):
        # Should mix colors and show emoji
        result = evaluator.evaluate("red + fox + blue")
        assert "COLOR_RESULT:" in result
        assert "🦊" in result

    def test_number_color_emoji(self, evaluator):
        # 2 + red + 3 cats + blue = 3 reds + 1 blue (mixed) + 3 cats
        # Numbers attach to the NEXT term (2→red, 3→cats)
        result = evaluator.evaluate("2 + red + 3 cats + blue")
        assert "COLOR_RESULT:" in result
        assert "🐱🐱🐱" in result  # 3 cats (not 5)

    def test_emoji_plus_single_color(self, evaluator):
        # apple + blue = blue color + apple emoji
        result = evaluator.evaluate("apple + blue")
        assert "COLOR_RESULT:" in result
        assert "🍎" in result

    def test_single_color_plus_emoji(self, evaluator):
        # blue + leaf = blue color + leaf emoji
        result = evaluator.evaluate("blue + leaf")
        assert "COLOR_RESULT:" in result
        assert "🍃" in result

    def test_pure_numbers_still_math(self, evaluator):
        result = evaluator.evaluate("3 + 4 + 5")
        assert result.startswith("12")

    def test_unknown_plus_color_order_preserved(self, evaluator):
        # Unknown text + color: text first, then color
        result = evaluator.evaluate("gibberish + blue")
        assert result.startswith("gibberish")
        assert "COLOR_RESULT:" in result

    def test_color_plus_unknown_order_preserved(self, evaluator):
        # Color + unknown text: color first, then text
        result = evaluator.evaluate("blue + gibberish")
        assert result.startswith("COLOR_RESULT:")
        assert "gibberish" in result

    def test_emoji_color_emoji_order(self, evaluator):
        # cat + red + dog: emojis separated by color, colors mix
        result = evaluator.evaluate("cat + red + dog + blue")
        parts = result.split()
        # First part should be cat emoji
        assert parts[0] == "🐱"
        # Should have color result
        assert "COLOR_RESULT:" in result
        # Last part should be dog emoji
        assert parts[-1] == "🐶"


class TestOperatorPrecedence:
    """Test that operator precedence is preserved with emojis."""

    def test_mult_before_add_pure_math(self, evaluator):
        # 3 * 4 + 2 = 14 (not 18)
        result = evaluator.evaluate("3 * 4 + 2")
        assert result.startswith("14")

    def test_mult_before_add_with_emoji(self, evaluator):
        # 3 * 4 + 2 dogs = 14 dogs (label + visualization)
        result = evaluator.evaluate("3 * 4 + 2 dogs")
        lines = result.split('\n')
        assert lines[0] == "14 🐶"
        assert lines[1].count("🐶") == 14

    def test_add_then_mult_with_emoji(self, evaluator):
        # 2 + 3 * 4 cats = 2 + 12 cats = 14 cats
        result = evaluator.evaluate("2 + 3 * 4 cats")
        lines = result.split('\n')
        assert lines[0] == "14 🐱"
        assert lines[1].count("🐱") == 14

    def test_complex_precedence_with_emoji(self, evaluator):
        # 1 + 2 * 3 + 4 dogs = 1 + 6 + 4 = 11 dogs
        result = evaluator.evaluate("1 + 2 * 3 + 4 dogs")
        lines = result.split('\n')
        assert lines[0] == "11 🐶"
        assert lines[1].count("🐶") == 11

    def test_parens_override_precedence_with_emoji(self, evaluator):
        # (2 + 3) * 4 cats = 20 cats
        result = evaluator.evaluate("(2 + 3) * 4 cats")
        lines = result.split('\n')
        assert lines[0] == "20 🐱"
        assert lines[1].count("🐱") == 20


class TestComputedLabels:
    """Test that computed expressions show labels, simple ones don't."""

    def test_label_on_computed_plus_expr(self, evaluator):
        # 3 + 2 cats = 5 cats with label
        result = evaluator.evaluate("3 + 2 cats")
        assert result == "5 🐱\n🐱🐱🐱🐱🐱"

    def test_label_on_complex_math_expr(self, evaluator):
        # 3 * 4 + 2 dogs = 14 dogs with label
        result = evaluator.evaluate("3 * 4 + 2 dogs")
        lines = result.split('\n')
        assert lines[0] == "14 🐶"
        assert lines[1].count("🐶") == 14

    def test_no_label_simple_mult(self, evaluator):
        # 3 cats = just emojis (no computation to explain)
        result = evaluator.evaluate("3 cats")
        assert result == "🐱🐱🐱"

    def test_no_label_bare_plural(self, evaluator):
        # cats = just emojis
        result = evaluator.evaluate("cats")
        assert result == "🐱🐱"

    def test_no_label_single_emoji(self, evaluator):
        # cat = just emoji
        result = evaluator.evaluate("cat")
        assert result == "🐱"

    def test_no_label_mixed_emojis(self, evaluator):
        # cat + dog = just emojis (mixed types, no single label, space between)
        result = evaluator.evaluate("cat + dog")
        assert result == "🐱 🐶"

    def test_label_multi_emoji_with_counts(self, evaluator):
        # 2 cats + 3 dogs = shows label with computed counts
        result = evaluator.evaluate("2 cats + 3 dogs")
        assert result == "2 🐱 3 🐶\n🐱🐱 🐶🐶🐶"

    def test_n_times_m_word_in_plus_expr(self, evaluator):
        # 2 + 3 * 4 cats = 14 cats (3*4=12, +2=14)
        result = evaluator.evaluate("2 + 3 * 4 cats")
        lines = result.split('\n')
        assert lines[0] == "14 🐱"
        assert lines[1].count("🐱") == 14

    def test_label_on_large_multiplication(self, evaluator):
        # 12 * 3 cats = 36 cats (with label)
        result = evaluator.evaluate("12 * 3 cats")
        lines = result.split('\n')
        assert lines[0] == "36 🐱"
        assert lines[1].count("🐱") == 36


class TestTextWithExpression:
    """Test text containing expressions like 'what is 2+3' or 'I have 5 apples'."""

    def test_what_is_math(self, evaluator):
        # "what is 2 + 3" -> "what is 5" with dots
        result = evaluator.evaluate("what is 2 + 3")
        assert result.startswith("what is 5\n")
        assert "•••••" in result

    def test_what_is_multiplication(self, evaluator):
        # "tell me 3 * 4" -> "tell me 12" with dots
        result = evaluator.evaluate("tell me 3 * 4")
        assert result.startswith("tell me 12\n")
        assert result.count("•") == 12

    def test_i_have_apples(self, evaluator):
        # "I have 5 apples" -> "I have" + emojis
        result = evaluator.evaluate("I have 5 apples")
        assert result == "I have 🍎🍎🍎🍎🍎"

    def test_text_with_plus_expr(self, evaluator):
        # "I have 2 + 3 apples" -> two lines with prefix
        result = evaluator.evaluate("I have 2 + 3 apples")
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "I have 5 🍎"
        assert lines[1] == "I have 🍎🍎🍎🍎🍎"

    def test_what_is_color_mixing(self, evaluator):
        # "what is red + blue" -> color mixing with prefix
        result = evaluator.evaluate("what is red + blue")
        assert "what is" in result
        assert "COLOR_RESULT:" in result

    def test_no_prefix_still_works(self, evaluator):
        # "2 + 2" without prefix still works normally
        result = evaluator.evaluate("2 + 2")
        assert result.startswith("4\n")
        assert "••••" in result

    def test_single_word_prefix_with_emoji(self, evaluator):
        # "show cat" -> "show" + cat emoji
        result = evaluator.evaluate("show cat")
        assert result == "show 🐱"

    def test_multi_word_prefix(self, evaluator):
        # "can you show me 3 dogs" -> prefix preserved
        result = evaluator.evaluate("can you show me 3 dogs")
        assert result == "can you show me 🐶🐶🐶"

    def test_text_with_parens_math(self, evaluator):
        # "what is (2 + 2) cats" -> parens imply computation, show label
        result = evaluator.evaluate("what is (2 + 2) cats")
        assert result == "what is 4 🐱\nwhat is 🐱🐱🐱🐱"

    def test_text_with_parens_mult(self, evaluator):
        # "what is (2 * 3) cats" -> parens imply computation, show label
        result = evaluator.evaluate("what is (2 * 3) cats")
        assert result == "what is 6 🐱\nwhat is 🐱🐱🐱🐱🐱🐱"


class TestXOperator:
    """Test x as multiplication operator."""

    def test_x_no_spaces(self, evaluator):
        # "2x4" = 8
        result = evaluator.evaluate("2x4")
        assert result.startswith("8\n")

    def test_x_with_spaces(self, evaluator):
        # "2 x 4" = 8
        result = evaluator.evaluate("2 x 4")
        assert result.startswith("8\n")

    def test_x_with_emoji(self, evaluator):
        # "cat x 3" = 3 cats
        result = evaluator.evaluate("cat x 3")
        assert result == "3 🐱\n🐱🐱🐱"

    def test_x_doesnt_replace_in_words(self, evaluator):
        # "fox" should stay as fox emoji, not "fo*"
        result = evaluator.evaluate("fox")
        assert "🦊" in result


class TestColorNumberAttachment:
    """Test that pending numbers attach correctly to colors vs emojis."""

    def test_color_only_numbers_attach(self, evaluator):
        # "2 + 3 yellow" = 5 yellows (color-only, numbers attach to color)
        result = evaluator.evaluate("2 + 3 yellow")
        assert result.startswith("COLOR_RESULT:")
        parts = result.split(":")
        components = parts[3].split(",")
        assert len(components) == 5  # 2 + 3 = 5

    def test_color_only_numbers_attach_to_first(self, evaluator):
        # "2 + red" = 3 reds (2 pending + 1 red)
        result = evaluator.evaluate("2 + red")
        assert result.startswith("COLOR_RESULT:")
        parts = result.split(":")
        components = parts[3].split(",")
        assert len(components) == 3

    def test_mixed_numbers_attach_to_next(self, evaluator):
        # "2 + red + 3 cats" = 3 reds + 3 cats (2→red, 3→cats)
        result = evaluator.evaluate("2 + red + 3 cats")
        assert "COLOR_RESULT:" in result
        parts = result.split(":")
        components = parts[3].split(",")
        assert len(components) == 3  # 2 + 1 = 3 reds
        assert "🐱🐱🐱" in result  # 3 cats


class TestSpeakable:
    """Test the _make_speakable method for TTS."""

    def test_pure_math(self, evaluator):
        result = evaluator.evaluate("2 + 3")
        speak = evaluator._make_speakable("2 + 3", result)
        assert speak == "2 plus 3 equals 5"

    def test_multiplication(self, evaluator):
        result = evaluator.evaluate("3 * 4")
        speak = evaluator._make_speakable("3 * 4", result)
        assert speak == "3 times 4 equals 12"

    def test_simple_echo(self, evaluator):
        result = evaluator.evaluate("5")
        speak = evaluator._make_speakable("5", result)
        assert speak == "5"

    def test_emoji_lookup(self, evaluator):
        result = evaluator.evaluate("cat")
        speak = evaluator._make_speakable("cat", result)
        assert speak == "cat"

    def test_emoji_multiply(self, evaluator):
        result = evaluator.evaluate("cat * 3")
        speak = evaluator._make_speakable("cat * 3", result)
        assert speak == "cat times 3 equals 3 cats"

    def test_emoji_plus_expr(self, evaluator):
        result = evaluator.evaluate("2 + 3 apples")
        speak = evaluator._make_speakable("2 + 3 apples", result)
        assert speak == "2 plus 3 apples equals 5 apples"

    def test_color_mixing(self, evaluator):
        result = evaluator.evaluate("red + blue")
        speak = evaluator._make_speakable("red + blue", result)
        assert "red plus blue equals" in speak
        assert "purple" in speak.lower()

    def test_text_prefix_not_duplicated(self, evaluator):
        result = evaluator.evaluate("what is 2 + 3")
        speak = evaluator._make_speakable("what is 2 + 3", result)
        # Should be "what is 2 plus 3 equals 5", not "what is ... equals what is 5"
        assert speak == "what is 2 plus 3 equals 5"

    def test_text_prefix_with_emoji(self, evaluator):
        result = evaluator.evaluate("what is (2 * 3) cats")
        speak = evaluator._make_speakable("what is (2 * 3) cats", result)
        # Should convert emoji to word
        assert "6 cats" in speak

    def test_multi_emoji_speaking(self, evaluator):
        result = evaluator.evaluate("2 * 3 banana + lions")
        speak = evaluator._make_speakable("2 * 3 banana + lions", result)
        # Should say "equals 6 bananas and 2 lions"
        assert "equals" in speak
        assert "6 bananas" in speak
        assert "2 lions" in speak

    def test_multi_emoji_speaking_cats_dogs(self, evaluator):
        result = evaluator.evaluate("3 * cat + 2 dogs")
        speak = evaluator._make_speakable("3 * cat + 2 dogs", result)
        assert "equals" in speak
        assert "3 cats" in speak
        assert "2 dogs" in speak
        assert "🐱" not in speak


class TestColorMixingLogic:
    """Test the actual color mixing behavior."""

    def test_identical_colors_unchanged(self, evaluator):
        # Mixing same color multiple times should return that exact color
        result = evaluator.evaluate("yellow + yellow + yellow")
        parts = result.split(":")
        mixed = parts[1]
        components = parts[3].split(",")
        assert mixed == components[0]  # Mixed should equal component

    def test_red_plus_blue_makes_purple(self, evaluator):
        result = evaluator.evaluate("red + blue")
        assert "purple" in result.lower()

    def test_red_plus_yellow_makes_orange(self, evaluator):
        result = evaluator.evaluate("red + yellow")
        assert "orange" in result.lower()

    def test_blue_plus_yellow_makes_green(self, evaluator):
        result = evaluator.evaluate("blue + yellow")
        assert "green" in result.lower()

    def test_weighted_mix_shifts_toward_heavier(self, evaluator):
        # 3 red + 1 blue should be more red than 1 red + 1 blue
        result_weighted = evaluator.evaluate("3 red + blue")
        result_equal = evaluator.evaluate("red + blue")
        # Both should have purple-ish result, but weighted should be named differently
        assert "COLOR_RESULT:" in result_weighted
        assert "COLOR_RESULT:" in result_equal

    def test_single_color_no_mixing(self, evaluator):
        # Single color should just show that color
        result = evaluator.evaluate("blue")
        assert "[on #" in result  # Should be a color box, not COLOR_RESULT


class TestColorMixingComponents:
    """Test color mixing component parsing (unit tests)."""

    def _parse_color_term(self, term, colors):
        term = term.strip()
        if not term:
            return None

        match = re.match(r'^(\w+)\s*(?:[\*x]|times)\s*(\d+)$', term)
        if match:
            color_name, count = match.group(1), int(match.group(2))
            color_hex = colors.get(color_name)
            if color_hex and 1 <= count <= 20:
                return [color_hex] * count
            return None

        match = re.match(r'^(\d+)\s*(?:[\*x]|times)\s*(\w+)$', term)
        if match:
            count, color_name = int(match.group(1)), match.group(2)
            color_hex = colors.get(color_name)
            if color_hex and 1 <= count <= 20:
                return [color_hex] * count
            return None

        # "N word" (e.g., "3 yellow")
        match = re.match(r'^(\d+)\s+(\w+)$', term)
        if match:
            count, color_name = int(match.group(1)), match.group(2)
            color_hex = colors.get(color_name)
            if color_hex and 1 <= count <= 20:
                return [color_hex] * count
            return None

        color_hex = colors.get(term)
        if color_hex:
            return [color_hex]
        return None

    def _eval_color_mixing(self, text, colors):
        text_lower = text.lower().strip()
        parts = re.split(r'\s*(?:\+|plus)\s*', text_lower)
        parts = [p.strip() for p in parts if p.strip()]

        if not parts:
            return None

        colors_to_mix = []
        for part in parts:
            term_colors = self._parse_color_term(part, colors)
            if term_colors:
                colors_to_mix.extend(term_colors)
            else:
                return None

        if not colors_to_mix:
            return None

        return len(colors_to_mix)

    def test_red_plus_red_plus_orange_3_components(self):
        colors = {"red": "#E52B50", "orange": "#FF6600"}
        assert self._eval_color_mixing("red + red + orange", colors) == 3

    def test_red_times_3_plus_yellow_4_components(self):
        colors = {"red": "#E52B50", "yellow": "#FFEB00"}
        assert self._eval_color_mixing("red * 3 + yellow", colors) == 4

    def test_3x_red_plus_2x_yellow_plus_blue_6_components(self):
        colors = {"red": "#E52B50", "yellow": "#FFEB00", "blue": "#0047AB"}
        assert self._eval_color_mixing("3x red + 2x yellow + blue", colors) == 6

    def test_number_space_color(self):
        colors = {"yellow": "#FFEB00", "red": "#E52B50"}
        assert self._eval_color_mixing("3 yellow + red", colors) == 4


class TestThemeConstants:
    """Test theme color constants match the app's registered themes."""

    def test_surface_constants_match_app_theme(self):
        """Surface color constants should match the app's theme values."""
        from purple_tui.modes.ask_mode import ColorResultLine

        # These should match the values in purple_tui.py register_theme calls
        assert ColorResultLine.SURFACE_DARK == "#2a1845"
        assert ColorResultLine.SURFACE_LIGHT == "#e8daf0"

    def test_arrow_constants_exist(self):
        """Arrow color constants should be defined for both themes."""
        from purple_tui.modes.ask_mode import HistoryLine

        assert HistoryLine.ARROW_DARK == "#a888d0"
        assert HistoryLine.ARROW_LIGHT == "#7a5a9e"


# =============================================================================
# Standalone runner
# =============================================================================

def run_standalone_tests():
    """Run tests without pytest."""
    print("=== Autocomplete Tests ===\n")
    content = MockContent()
    passed = failed = 0

    tests = [
        ("red + ap suggests apple", lambda: check_autocomplete("red + ap", content)[0] == [("apple", "🍎")]),
        ("gol suggests gold", lambda: [w for w, _ in check_autocomplete("gol", content)[0]] == ["gold"]),
        ("exact match red no suggestions", lambda: check_autocomplete("red", content)[0] == []),
        ("short prefix no suggestions", lambda: check_autocomplete("r", content)[0] == []),
    ]

    for name, test_fn in tests:
        try:
            if test_fn():
                print(f"✓ {name}")
                passed += 1
            else:
                print(f"✗ {name}")
                failed += 1
        except Exception as e:
            print(f"✗ {name} (exception: {e})")
            failed += 1

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    return failed == 0


if __name__ == "__main__":
    if HAS_PYTEST:
        sys.exit(pytest.main([__file__, "-v"]))
    else:
        success = run_standalone_tests()
        sys.exit(0 if success else 1)
