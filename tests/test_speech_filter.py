"""Tests for the speech content filter.

Blocked word test data is base64-encoded to keep plaintext profanity
out of the source. Use _decode() to read test word lists.
"""

import base64

import pytest
from purple_tui.speech_filter import (
    _normalize,
    filter_speech,
)


def _decode(encoded: str, sep: str = "|") -> list[str]:
    """Decode a base64-encoded, separator-delimited word list."""
    return base64.b64decode(encoded).decode().split(sep)


# Pre-decoded test word lists (profanity kept out of source)
_DIRECT_WORDS = _decode(
    "ZnVja3xzaGl0fGFzc3xkYW1ufGhlbGx8Yml0Y2h8ZGlja3xjb2NrfGN1bnR8"
    "cGlzc3x3aG9yZXxzbHV0fGJhc3RhcmR8bmlnZ2VyfG5pZ2dhfGZhZ2dvdHxm"
    "YWd8cmV0YXJkfHR3YXR8d2Fua3xib2xsb2Nrc3xhcnNlfHRpdHx0aXRzfGJv"
    "b2J8Ym9vYnN8cGVuaXN8dmFnaW5h"
)
_CASE_VARS = _decode("RlVDS3xTaGl0fEFTU3xCaVRjSHxOSUdHRVJ8REFNTnxIRUxM")
_SPACED = _decode("ZiB1IGMga3xzIGggaSB0fGYudS5jLmt8cy1oLWktdA==")
_VARIANTS = _decode(
    "cGh1Y2t8cGh1a3xwaHVjfGZ1a3xmdWN8ZnVxfHNoeXR8c2hpdGV8YmljaHxi"
    "aWF0Y2h8Ynl0Y2h8YmVvdGNofGRpa3xkeWt8Y29rfGtva3xrdW50fGhvcmV8"
    "bmlnZXJ8bmlnYXxmYWdvdHxmYWdnZXR8cGVudXM="
)
_LEET = _decode("ZjRja3wkaGl0fGEkJHxiMXRjaHxkMWNrfCRsdTd8bjFnZzNy")
_SUFFIXED = _decode(
    "ZnVja2luZ3xzaGl0dHl8YXNzaG9sZXxiaXRjaHl8ZGlja2hlYWR8cGlzc2Vy"
    "fHdhbmtlcnxyZXRhcmRlZHxzbHV0dHk="
)
_SENTENCES = _decode("c2F5IHRoZSBmdWNrIHdvcmR8c2F5IHNoaXQ=")


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("HELLO") == "hello"

    def test_strips_spaces_and_punctuation(self):
        assert _normalize("h.e" + ".l.l.o") == "hello"
        assert _normalize("h-e-l-l-o") == "hello"

    def test_empty(self):
        assert _normalize("") == ""


class TestBlockedWords:
    """Test that profanity is caught."""

    @pytest.mark.parametrize("word", _DIRECT_WORDS)
    def test_direct_blocked(self, word):
        result = filter_speech(word)
        assert result == "", f"should be blocked"

    @pytest.mark.parametrize("word", _CASE_VARS)
    def test_case_variations_blocked(self, word):
        result = filter_speech(word)
        assert result == "", f"should be blocked"

    @pytest.mark.parametrize("word", _SPACED)
    def test_spaced_out_blocked(self, word):
        result = filter_speech(word)
        assert result == "", f"should be blocked"

    @pytest.mark.parametrize("word", _VARIANTS)
    def test_spelling_variants_blocked(self, word):
        result = filter_speech(word)
        assert result == "", f"should be blocked"

    @pytest.mark.parametrize("word", _LEET)
    def test_leet_speak_passes_through(self, word):
        # Leet-speak passes through because TTS pronounces digits as numbers,
        # so "f4ck" sounds like "f four c k", not the blocked word
        result = filter_speech(word)
        assert result == word, f"leet-speak should pass through TTS filter"

    @pytest.mark.parametrize("word", _SUFFIXED)
    def test_suffixed_forms_blocked(self, word):
        result = filter_speech(word)
        assert result == "", f"should be blocked"

    def test_sentence_with_blocked_word_scrubbed(self):
        # "say the <blocked> word" → scrubbed to "saytheword" (long enough)
        result = filter_speech(_SENTENCES[0])
        assert result != ""
        assert result == "saytheword"

    def test_short_sentence_with_blocked_word_replaced(self):
        # "say <blocked>" → per-word check catches the blocked word
        result = filter_speech(_SENTENCES[1])
        assert result == ""

    def test_replacement_is_from_silly_list(self):
        result = filter_speech(_DIRECT_WORDS[0])
        assert result == ""


class TestAllowedWords:
    """Test that legitimate words are NOT blocked (false positives)."""

    @pytest.mark.parametrize("word", [
        "class", "pass", "grass", "glass", "bass", "mass", "brass",
        "classic", "classify", "passage", "passenger", "passion", "passive",
        "assist", "assemble", "assert", "assign", "assume", "associate",
        "compass", "embarrass", "harass", "sass", "assessment", "assess",
        "assets", "association", "massive", "bassoon", "hassle",
        "grasshopper", "trespass", "carcass",
    ])
    def test_blocked_substring_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "hello", "shell", "seashell", "shellfish", "nutshell", "eggshell",
    ])
    def test_shell_hello_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "peacock", "cockpit", "cocktail", "cockatoo", "cockroach",
    ])
    def test_compound_words_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "kitten", "title", "little", "glitter", "mittens", "titanic",
        "attitude", "competition", "repetition",
    ])
    def test_tit_substring_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "dictionary", "mississippi", "arsenal", "shiitake", "scunthorpe",
        "flag", "swank", "damnation", "stitch",
    ])
    def test_other_substrings_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "dam", "damp", "damage",
    ])
    def test_dam_words_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"


class TestCommonWordsNotBlocked:
    """Comprehensive test that common English words pass through."""

    @pytest.mark.parametrize("word", [
        "cat", "dog", "pig", "cow", "hen", "bat", "bug", "ant", "bee",
        "fox", "owl", "rat", "fish", "frog", "duck", "bird", "bear",
        "deer", "goat", "lamb", "lion", "seal", "wolf", "horse", "mouse",
        "snake", "whale", "shark", "tiger", "zebra", "panda", "monkey",
        "rabbit", "turtle", "penguin", "dolphin", "elephant", "chicken",
        "puppy", "kitten", "bunny", "hamster", "spider", "butterfly",
    ])
    def test_animals_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "mom", "dad", "mama", "papa", "baby", "sister", "brother",
        "grandma", "grandpa", "nana", "aunt", "uncle", "cousin",
    ])
    def test_family_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "arm", "leg", "hand", "foot", "head", "face", "nose", "ear",
        "eye", "mouth", "tooth", "tongue", "chin", "neck", "back",
        "chest", "tummy", "belly", "knee", "elbow", "finger", "toe",
        "heel", "hair", "skin", "bone",
    ])
    def test_body_parts_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "red", "blue", "green", "yellow", "orange", "purple", "pink",
        "brown", "black", "white", "gray", "gold", "silver",
    ])
    def test_colors_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "apple", "banana", "grape", "lemon", "peach", "pear", "plum",
        "cherry", "melon", "bread", "butter", "cheese", "milk", "egg",
        "rice", "pizza", "soup", "salad", "sandwich", "cookie", "cake",
        "pie", "candy", "chocolate", "popcorn", "taco", "hamburger",
    ])
    def test_food_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "sun", "moon", "star", "sky", "cloud", "rain", "snow", "wind",
        "storm", "thunder", "rainbow", "tree", "flower", "grass", "leaf",
        "rock", "mountain", "hill", "river", "lake", "ocean", "sea",
        "beach", "sand", "dirt", "mud", "forest", "desert", "island",
    ])
    def test_nature_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "ball", "book", "box", "bag", "cup", "hat", "shoe", "sock",
        "shirt", "pants", "dress", "coat", "bell", "key", "door",
        "window", "table", "chair", "bed", "lamp", "clock", "phone",
        "car", "bus", "truck", "train", "boat", "ship", "plane",
        "bike", "wheel", "house", "castle", "robot", "rocket",
    ])
    def test_objects_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "run", "jump", "hop", "skip", "dance", "sing", "play", "swim",
        "fly", "climb", "slide", "swing", "throw", "catch", "kick",
        "push", "pull", "walk", "dig", "build", "draw", "paint",
        "write", "read", "eat", "drink", "cook", "wash", "clean",
        "open", "close", "hide", "find", "give", "take", "share",
        "help", "hug", "wave", "clap",
    ])
    def test_actions_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "big", "small", "tall", "short", "long", "fast", "slow",
        "hot", "cold", "warm", "cool", "wet", "dry", "hard", "soft",
        "loud", "quiet", "bright", "dark", "heavy", "new", "old",
        "young", "happy", "sad", "angry", "silly", "funny", "scary",
        "brave", "kind", "nice", "smart", "strong", "pretty", "sweet",
        "sour", "salty", "spicy", "yummy", "full", "empty", "clean",
    ])
    def test_adjectives_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"

    @pytest.mark.parametrize("word", [
        "hello", "goodbye", "please", "thank", "sorry", "welcome",
        "yes", "no", "maybe", "where", "when", "what", "why", "how",
        "ice cream", "class", "school", "pencil",
    ])
    def test_misc_common_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"


class TestGibberish:
    """Test that random gibberish passes through (the fun part)."""

    @pytest.mark.parametrize("word", [
        "blorpnax", "zizzle", "wompus", "grizzlefax", "snorkelberry",
        "flimflam", "bazinga", "kablooey", "razzmatazz", "splork",
        "xylophones", "quizzical", "zigzag", "wobble", "noodle",
        "glorp", "snazzberry", "flibberdoo", "zoomwhistle", "plonk",
    ])
    def test_gibberish_allowed(self, word):
        assert filter_speech(word) == word, f"'{word}' should NOT be blocked"


class TestScrubbing:
    """Test that blocked words are scrubbed from gibberish rather than
    replacing the entire string.

    Test inputs are base64-encoded to keep profanity out of source.
    """

    def test_gibberish_with_embedded_blocked_scrubbed(self):
        inp = base64.b64decode("YmxvcnBmdWNremF4").decode()
        expected = base64.b64decode("YmxvcnB6YXg=").decode()
        assert filter_speech(inp) == expected

    def test_gibberish_with_embedded_blocked_at_start(self):
        inp = base64.b64decode("ZnVja3pvcnBsZQ==").decode()
        expected = base64.b64decode("em9ycGxl").decode()
        assert filter_speech(inp) == expected

    def test_gibberish_with_embedded_blocked_at_end(self):
        inp = base64.b64decode("c25venpsZWZ1Y2s=").decode()
        expected = base64.b64decode("c25venpsZQ==").decode()
        assert filter_speech(inp) == expected

    def test_short_remainder_gets_silly_replacement(self):
        inp = base64.b64decode("ZnVja3g=").decode()
        assert filter_speech(inp) == ""

    def test_exact_blocked_word_gets_silly_replacement(self):
        result = filter_speech(_DIRECT_WORDS[0])
        assert result == ""

    def test_suffixed_blocked_gets_silly_replacement(self):
        inp = base64.b64decode("c2hpdHR5").decode()
        assert filter_speech(inp) == ""

    def test_allowed_word_not_scrubbed(self):
        assert filter_speech("class") == "class"

    def test_multiple_blocked_in_gibberish(self):
        inp = base64.b64decode("em9yZnVja2Jsb3JwYXNzd3VtcA==").decode()
        expected = base64.b64decode("em9yYmxvcnB3dW1w").decode()
        assert filter_speech(inp) == expected

    def test_scrubbed_result_is_speakable(self):
        inp = base64.b64decode("eHl6YXNzeHl6YXNzeHl6").decode()
        expected = base64.b64decode("eHl6eHl6eHl6").decode()
        assert filter_speech(inp) == expected

    def test_multiword_scrub(self):
        inp = base64.b64decode("c2F5IHpvcmZ1Y2tibG9ycA==").decode()
        assert "blorp" in filter_speech(inp)


class TestEdgeCases:
    def test_empty_string(self):
        assert filter_speech("") == ""

    def test_whitespace_only(self):
        assert filter_speech("   ") == "   "

    def test_single_letters(self):
        for c in "abcdefghijklmnopqrstuvwxyz":
            assert filter_speech(c) == c

    def test_numbers(self):
        assert filter_speech("123") == "123"
        assert filter_speech("42") == "42"

    def test_math_expressions_pass(self):
        assert filter_speech("2 plus 3 equals 5") == "2 plus 3 equals 5"
        assert filter_speech("10 times 4 equals 40") == "10 times 4 equals 40"
