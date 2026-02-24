"""Tests for play_words: word recognition from replay data."""

from purple_tui.play_words import WORDS, extract_word
from purple_tui.play_session import SUBMODE_LETTERS, SUBMODE_MUSIC


def test_recognized_word():
    """Letters spelling a known word are recognized."""
    replay = [
        ("D", SUBMODE_LETTERS, 0.0),
        ("O", SUBMODE_LETTERS, 0.3),
        ("G", SUBMODE_LETTERS, 0.3),
    ]
    assert extract_word(replay) == "dog"


def test_recognized_word_cat():
    replay = [
        ("C", SUBMODE_LETTERS, 0.0),
        ("A", SUBMODE_LETTERS, 0.2),
        ("T", SUBMODE_LETTERS, 0.2),
    ]
    assert extract_word(replay) == "cat"


def test_unknown_word_returns_none():
    """Letters not forming a known word return None."""
    replay = [
        ("X", SUBMODE_LETTERS, 0.0),
        ("Y", SUBMODE_LETTERS, 0.3),
        ("Z", SUBMODE_LETTERS, 0.3),
    ]
    assert extract_word(replay) is None


def test_music_mode_events_ignored():
    """Events in music mode are filtered out."""
    replay = [
        ("D", SUBMODE_MUSIC, 0.0),
        ("O", SUBMODE_MUSIC, 0.3),
        ("G", SUBMODE_MUSIC, 0.3),
    ]
    assert extract_word(replay) is None


def test_mixed_modes_only_letters():
    """Only letters-mode alphabetic keys contribute to the word."""
    replay = [
        ("D", SUBMODE_LETTERS, 0.0),
        ("X", SUBMODE_MUSIC, 0.2),    # music mode, ignored
        ("O", SUBMODE_LETTERS, 0.3),
        ("G", SUBMODE_LETTERS, 0.3),
    ]
    assert extract_word(replay) == "dog"


def test_non_alpha_keys_ignored():
    """Number keys in letters mode are filtered out."""
    replay = [
        ("5", SUBMODE_LETTERS, 0.0),
        ("G", SUBMODE_LETTERS, 0.2),
        ("O", SUBMODE_LETTERS, 0.3),
    ]
    assert extract_word(replay) == "go"


def test_empty_replay():
    """Empty replay data returns None."""
    assert extract_word([]) is None


def test_single_letter_not_a_word():
    """A single letter isn't in the word list."""
    replay = [("A", SUBMODE_LETTERS, 0.0)]
    assert extract_word(replay) is None


def test_two_letter_word():
    """Short words like 'go' are recognized."""
    replay = [
        ("G", SUBMODE_LETTERS, 0.0),
        ("O", SUBMODE_LETTERS, 0.3),
    ]
    assert extract_word(replay) == "go"


def test_word_list_is_all_lowercase():
    """Every word in WORDS should be lowercase."""
    for word in WORDS:
        assert word == word.lower(), f"Word '{word}' is not lowercase"


def test_word_list_has_basics():
    """Sanity check that common kids' words are present."""
    basics = {"cat", "dog", "mom", "dad", "sun", "red", "big", "run", "play"}
    missing = basics - WORDS
    assert not missing, f"Missing basic words: {missing}"


def test_word_list_size():
    """Word list should have a reasonable number of entries."""
    assert len(WORDS) >= 80
