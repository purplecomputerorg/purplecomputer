"""Speech content filter for Purple Computer.

Prevents TTS from speaking profanity while allowing arbitrary gibberish.
Matches against blocked words using lowercase + non-alpha removal.

No leet-speak normalization: digits in TTS are pronounced as numbers
(e.g. "F4CK" becomes "F four C K"), so they don't sound like profanity.

When a blocked word is detected, the word is scrubbed out. If there's not
enough left to speak, returns empty string (TTS silently skips it).

Design philosophy: explicit variant lists over fuzzy matching. Phonetic
algorithms (metaphone, soundex) produce too many false positives on common
short words. Since profanity misspellings are well-known and stable, an
explicit list gives zero false positives with comprehensive coverage.
"""

import base64
import re

# Blocked words and common misspellings, base64-encoded to keep plaintext
# profanity out of source code. Decoded at import time.
#
# Substring matching catches suffixed forms automatically (e.g. the root
# "xxxx" also catches "xxxxing", "xxxxer", etc.).
#
# To update, run:
#   python -c "import base64; words = ['word1','word2',...]; \
#     print(base64.b64encode(','.join(sorted(set(words))).encode()).decode())"
_BLOCKED_WORDS = frozenset(
    base64.b64decode(
        "YXJzZSxhc3MsYmFzdGFyZCxiZW90Y2gsYmlhdGNoLGJpY2gsYml0Y2gsYm9sbG9j"
        "a3MsYm9uZXIsYm9vYixib29icyxib290eSxieXRjaCxjb2NrLGNvayxjcmFwLGN1"
        "bnQsZGFtbixkaWNrLGRpayxkaWxkbyxkeWssZmFjayxmYWcsZmFnZ2V0LGZhZ2dv"
        "dCxmYWdvdCxmYXJ0LGZ1YyxmdWNrLGZ1ayxmdXEsaGVsbCxob3JlLGhvcm55LGpp"
        "enosa29rLGt1bnQsbmlnYSxuaWdlcixuaWdnYSxuaWdnZXIsbmlxcWEsbmlxcWVy"
        "LG9yZ2FzbSxwZW5pcyxwZW51cyxwaHVjLHBodWNrLHBodWsscGlzcyxwb28scG9v"
        "cCxwb3JuLHJldGFyZCxzZXh5LHNoYXQsc2hpdCxzaGl0ZSxzaHl0LHNsdXQsc3B1"
        "bmssc3RmdSxzdWNrLHRpdCx0aXRzLHR1cmQsdHdhdCx2YWdpbmEsd2Fuayx3aG9y"
        "ZSx3dGY="
    )
    .decode()
    .split(",")
)

# Words that are legitimate despite containing blocked substrings.
# For example, "class" contains a blocked word, "hello" contains another.
_ALLOWED_WORDS = frozenset({
    # Contains short blocked substrings (3-4 letter roots cause most collisions)
    "class", "pass", "grass", "glass", "bass", "mass", "brass", "lass",
    "classic", "classify", "passage", "passenger", "passion", "passive",
    "assist", "assemble", "assert", "assign", "assume", "associate",
    "cassette", "lasso", "molasses", "sassy", "ambassador", "compass",
    "embarrass", "harass", "sass", "assessment", "assess", "asset",
    "assets", "association", "massive", "bassoon", "hassle", "crass",
    "amass", "carcass", "morass", "trespass", "grasshopper",
    "arsenal",
    "hello", "shell", "seashell", "shelling", "nutshell", "eggshell",
    "shellfish", "bombshell",
    "damnation",
    "kitten", "title", "titan", "little", "glitter", "litter", "bitter",
    "butter", "twitter", "sitting", "hitting", "fitting", "knitting",
    "mittens", "appetite", "petite", "titanic", "altitude", "attitude",
    "constitution", "competition", "repetition", "partition",
    "stitch", "stitching",
    "peacock", "cockpit", "cocktail", "cockatoo", "cockroach",
    "dictionary",
    "mississippi",
    "shiitake",
    "scunthorpe",
    "flag",
    "swank", "swanky",
    "butt", "button", "butter", "butterfly", "butterscotch", "rebuttal",
    # Contains "poo"
    "pool", "poor", "poodle", "spoon", "spook", "spooky", "scoop",
    "shampoo", "harpoon", "cartoon", "drool",
    # Contains "suck"
    "honeysuckle", "sucker",
    # Contains "crap"
    "scrap", "scrappy", "scrape",
    # Contains "horn" (from "horny")
    "horn", "hornet", "unicorn", "acorn",
})


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip non-alpha."""
    text = text.lower()
    text = re.sub(r"[^a-z]", "", text)
    return text


# Minimum remaining characters after scrubbing for the result to be
# speakable. Below this threshold, the input was basically just the
# blocked word (possibly with minor padding), so silence it.
_MIN_SCRUBBED_LEN = 5


def _find_blocked(normalized: str) -> list[str]:
    """Return all blocked words found as substrings in normalized text.

    Returns longest matches first so scrubbing removes the most specific
    variant (e.g. "phuck" before "phu").
    """
    found = []
    for word in _BLOCKED_WORDS:
        if word in normalized:
            found.append(word)
    found.sort(key=len, reverse=True)
    return found


def _scrub(normalized: str, blocked_matches: list[str]) -> str:
    """Remove all blocked substrings from normalized text."""
    result = normalized
    for word in blocked_matches:
        result = result.replace(word, "")
    return result


def filter_speech(text: str) -> str:
    """Filter text before TTS synthesis.

    Returns the original text if clean. If blocked content is found:
    - If the input is an allowed word, returns it unchanged.
    - If the blocked word is a small part of longer text, scrubs it out.
    - If the input is mostly the blocked word, returns empty string
      (TTS will silently skip it).
    """
    if not text or not text.strip():
        return text

    normalized = _normalize(text)
    if not normalized:
        return text

    # Allowed words always pass (even if they contain blocked substrings)
    if normalized in _ALLOWED_WORDS:
        return text

    # Collect allowed words from the input so we don't scrub their substrings.
    # e.g. "hello" is allowed and contains "hell", so "hell" found inside a
    # concatenated multi-word string shouldn't trigger scrubbing.
    input_words = re.split(r"[^a-zA-Z]+", text.lower())
    allowed_in_input = {_normalize(w) for w in input_words
                        if w and _normalize(w) in _ALLOWED_WORDS}

    # Check the full normalized string
    blocked_matches = _find_blocked(normalized)
    if blocked_matches:
        # Keep only matches that aren't substrings of an allowed input word
        real_blocked = [bw for bw in blocked_matches
                        if not any(bw in aw for aw in allowed_in_input)]
        if real_blocked:
            scrubbed = _scrub(normalized, real_blocked)
            if len(scrubbed) >= _MIN_SCRUBBED_LEN:
                return scrubbed
            return ""

    # Check individual words (for multi-word input like "say <blocked>")
    words = re.split(r"[^a-zA-Z]+", text.lower())
    for word in words:
        if not word or len(word) < 2:
            continue
        word_normalized = _normalize(word)
        if not word_normalized or word_normalized in _ALLOWED_WORDS:
            continue
        word_blocked = _find_blocked(word_normalized)
        if word_blocked:
            scrubbed = _scrub(word_normalized, word_blocked)
            if len(scrubbed) >= _MIN_SCRUBBED_LEN:
                # Rebuild the text with the scrubbed word in place
                text = re.sub(
                    re.escape(word), scrubbed, text, count=1, flags=re.IGNORECASE
                )
            else:
                return ""

    return text
