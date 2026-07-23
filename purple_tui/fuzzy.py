"""Shared fuzzy matching for typo tolerance across all rooms.

Two strategies:
- damerau_levenshtein: exact edit distance (counts transpositions as 1 edit)
- fuzzy_match: find closest vocabulary match within DL distance threshold

Content-layer fuzzy (get_emoji/get_color) uses min 5 chars to avoid false
positives on short words (with 400+ emojis, any 3-4 char word collides).
Command-layer fuzzy uses min 3 chars on small curated vocabularies.
"""

import difflib
from typing import Iterable


def damerau_levenshtein(s1: str, s2: str) -> int:
    """Damerau-Levenshtein distance: insertions, deletions, substitutions, transpositions."""
    len1, len2 = len(s1), len(s2)
    d = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    for i in range(len1 + 1):
        d[i][0] = i
    for j in range(len2 + 1):
        d[0][j] = j
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and s1[i - 1] == s2[j - 2] and s1[i - 2] == s2[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len1][len2]


DEFAULT_MIN_LEN = 5


def fuzzy_match(word: str, vocabulary: Iterable[str], min_len: int = DEFAULT_MIN_LEN) -> str | None:
    """Find the closest vocabulary match using Damerau-Levenshtein distance.

    Threshold: DL distance <= 1 (single typo). Candidates must share the
    input's first character — first-char typos are far rarer than middle/
    trailing slips, and dropping this constraint causes confusions like
    "yello" resolving to "hello" (synonym for 👋) instead of "yellow".
    Trade-off: dropped-first-letter typos (e.g. "ello"→"hello") aren't
    corrected, which is acceptable for kid typing.
    """
    if len(word) < min_len:
        return None
    max_dist = 1
    word_lower = word.lower()
    first = word_lower[0]
    best, best_dist = None, max_dist + 1
    for v in vocabulary:
        if abs(len(v) - len(word)) > max_dist:
            continue
        v_lower = v.lower()
        if v_lower[0] != first:
            continue
        d = damerau_levenshtein(word_lower, v_lower)
        if d < best_dist:
            best, best_dist = v, d
    return best if best_dist <= max_dist else None


def fuzzy_match_small(word: str, vocabulary: list[str], cutoff: float = 0.6) -> str | None:
    """Fuzzy match for small curated vocabularies (commands, operators).

    Uses difflib for flexibility on small sets where false positives
    are unlikely. Min 3 chars to avoid keymash matches.
    """
    if len(word) < 3:
        return None
    matches = difflib.get_close_matches(word.lower(), vocabulary, n=1, cutoff=cutoff)
    return matches[0] if matches else None
