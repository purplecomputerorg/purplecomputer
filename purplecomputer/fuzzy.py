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


# QWERTY key positions, rows staggered half a key, for "did the finger slip?".
_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_KEY_POS = {ch: (r, i + r / 2) for r, row in enumerate(_ROWS) for i, ch in enumerate(row)}

# Length at which a missing or extra letter stops colliding with another word.
# Measured against the emoji vocabulary: 6 keeps "flowr", "hourse" and "spidr"
# working, while 7 buys a few fewer collisions and loses all three.
_COLLISION_SAFE_LEN = 6


def _neighbor_keys(a: str, b: str) -> bool:
    """Whether two letters sit next to each other on the keyboard."""
    if a not in _KEY_POS or b not in _KEY_POS:
        return False
    (row_a, x_a), (row_b, x_b) = _KEY_POS[a], _KEY_POS[b]
    return abs(row_a - row_b) <= 1 and abs(x_a - x_b) <= 1


def looks_like_a_slip(typed: str, candidate: str) -> bool:
    """Whether one edit between two words reads as a typing slip rather than a
    different word. Distance alone is far too loose against a 400+ word
    vocabulary: "words" is one edit from "worms", "print" from "paint", "start"
    from "star", and correcting those hands a kid the wrong picture for a word
    they spelled right.

    A swapped letter counts as a slip only when the two keys are neighbors: a
    finger hits the key next door, it does not travel the keyboard. Sounding a
    word out wrong ("elefant", "dolfin") is two or more edits away and out of
    reach here anyway, so allowing letters that merely sound alike buys nothing
    and costs real words ("check" became a chick, "heard" a heart).

    An added or dropped letter counts when it doubles its neighbor ("dinno"),
    when the typed word stops one letter short ("chocolat"), or when the word is
    long enough that a real collision is unlikely. A letter typed *onto* the end
    does not count: stopping early is a slip, pressing one more key is a word
    ("star" and "start" are both words). Transpositions ("unicron") always count.
    """
    if len(typed) == len(candidate):
        differ = [i for i, (t, c) in enumerate(zip(typed, candidate)) if t != c]
        if len(differ) != 1:
            return True  # transposition
        return _neighbor_keys(typed[differ[0]], candidate[differ[0]])

    longer, shorter = (typed, candidate) if len(typed) > len(candidate) else (candidate, typed)
    if len(longer) >= _COLLISION_SAFE_LEN:
        return True
    i = 0
    while i < len(shorter) and longer[i] == shorter[i]:
        i += 1
    doubles_neighbor = longer[i] in (longer[i - 1:i] + longer[i + 1:i + 2])
    stopped_short = i >= len(longer) - 1 and len(typed) < len(candidate)
    return doubles_neighbor or stopped_short


def fuzzy_match(word: str, vocabulary: Iterable[str], min_len: int = DEFAULT_MIN_LEN) -> str | None:
    """Find the closest vocabulary match using Damerau-Levenshtein distance.

    Threshold: DL distance <= 1 (single typo) and the edit must read as a slip
    rather than a different word (see looks_like_a_slip). Candidates must share the
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
        if d < best_dist and looks_like_a_slip(word_lower, v_lower):
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
