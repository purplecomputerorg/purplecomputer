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
            assert evaluator.evaluate("cat * 3") == "🐱🐱🐱"

        def test_number_times_emoji(self, evaluator):
            assert evaluator.evaluate("3 * cat") == "🐱🐱🐱"

        def test_emoji_x_number(self, evaluator):
            assert evaluator.evaluate("cat x 2") == "🐱🐱"

        def test_emoji_no_spaces(self, evaluator):
            assert evaluator.evaluate("cat*3") == "🐱🐱🐱"

        def test_emoji_addition(self, evaluator):
            assert evaluator.evaluate("cat + dog") == "🐱🐶"

        def test_emoji_complex(self, evaluator):
            assert evaluator.evaluate("apple*3 + banana*2") == "🍎🍎🍎🍌🍌"

        def test_emoji_complex_with_spaces(self, evaluator):
            assert evaluator.evaluate("apple * 3 + banana * 2") == "🍎🍎🍎🍌🍌"

        def test_emoji_times_word(self, evaluator):
            assert evaluator.evaluate("cat times 3") == "🐱🐱🐱"

        def test_number_times_word_emoji(self, evaluator):
            assert evaluator.evaluate("3 times cat") == "🐱🐱🐱"

        def test_emoji_plus_word(self, evaluator):
            assert evaluator.evaluate("cat plus dog") == "🐱🐶"

        def test_emoji_plus_number(self, evaluator):
            assert evaluator.evaluate("cat*3 + 2") == "🐱🐱🐱2"

        def test_emoji_mixed_with_number(self, evaluator):
            assert evaluator.evaluate("apple times 2 plus 5") == "🍎🍎5"

        def test_number_plus_emoji(self, evaluator):
            assert evaluator.evaluate("3 + cat") == "3🐱"


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
            assert evaluator.evaluate("(2 + 3) * cat") == "🐱🐱🐱🐱🐱"

        def test_emoji_in_parens_multiply(self, evaluator):
            assert evaluator.evaluate("(cat + dog) * 2") == "🐱🐶🐱🐶"

        def test_multiply_emoji_in_parens(self, evaluator):
            assert evaluator.evaluate("2 * (cat + dog)") == "🐱🐶🐱🐶"

        def test_number_plus_emoji_parens(self, evaluator):
            assert evaluator.evaluate("5 + (5 * cat)") == "5🐱🐱🐱🐱🐱"

        def test_emoji_parens_plus_number(self, evaluator):
            assert evaluator.evaluate("(cat * 3) + 2") == "🐱🐱🐱2"

        def test_complex_emoji_parens(self, evaluator):
            assert evaluator.evaluate("(2 * cat) + (3 * dog)") == "🐱🐱🐶🐶🐶"

        def test_parens_with_word_operators(self, evaluator):
            assert evaluator.evaluate("(2 plus 3) times cat") == "🐱🐱🐱🐱🐱"

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
            assert evaluator.evaluate("apples + bananas") == "🍎🍎🍌🍌"

        def test_mixed_plural_number(self, evaluator):
            assert evaluator.evaluate("3 apples + 2 bananas") == "🍎🍎🍎🍌🍌"


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
    text = text.lower().strip()
    parts = re.split(r'[\s+*x]+', text)
    words = [p for p in parts if p]
    if not words:
        return [], "emoji"

    last_word = words[-1]
    if len(last_word) < 2:
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

    def test_go_suggests_gold(self):
        content = MockContent()
        matches, match_type = check_autocomplete("go", content)
        assert [w for w, _ in matches] == ["gold"]
        assert match_type == "color"

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


class TestColorMixingComponents:
    """Test color mixing with multiplication."""

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

    def test_invalid_color_returns_none(self):
        colors = {"red": "#E52B50"}
        assert self._eval_color_mixing("red * cat", colors) is None


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
        ("go suggests gold", lambda: [w for w, _ in check_autocomplete("go", content)[0]] == ["gold"]),
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
