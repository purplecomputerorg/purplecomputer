"""Shared fuzzy matching for typo tolerance across all rooms.

Two strategies:
- damerau_levenshtein: exact edit distance (counts transpositions as 1 edit)
- fuzzy_match: find closest vocabulary match within DL distance threshold

Content-layer fuzzy (get_emoji/get_color) uses min 5 chars to avoid false
positives on short words (with 400+ emojis, any 3-4 char word collides).
Command-layer fuzzy uses min 3 chars on small curated vocabularies.
"""

import difflib


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


def fuzzy_match(word: str, vocabulary: list[str], min_len: int = 5) -> str | None:
    """Find the closest vocabulary match using Damerau-Levenshtein distance.

    Args:
        word: input word to match
        vocabulary: list of valid words to match against
        min_len: minimum word length to attempt fuzzy matching (default 5
                 for content lookups, use 3 for small curated vocabularies)

    Returns:
        Best matching word, or None if no match within threshold.
        Threshold: DL distance <= 1 (single typo: one insertion, deletion,
        substitution, or transposition). Conservative to avoid false positives
        like "yellow" matching "hello" (DL=2).
    """
    if len(word) < min_len:
        return None
    max_dist = 1
    best, best_dist = None, max_dist + 1
    word_lower = word.lower()
    for v in vocabulary:
        if abs(len(v) - len(word)) > max_dist:
            continue
        d = damerau_levenshtein(word_lower, v.lower())
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
