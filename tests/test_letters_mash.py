"""Letters drop only a whole hand landing at once; a new letter cuts off the one still speaking."""
from purplecomputer.rooms.music_room import LETTERS_MASH_S, MusicRoom


class _Stub:
    _last_letter_press_t = float("-inf")


def _accepted(presses):
    s = _Stub()
    return [k for k, t in presses if not MusicRoom._letters_mash_drop(s, t)]


def test_a_hand_landing_at_once_says_one_letter():
    assert _accepted([("A", 0.000), ("S", 0.008), ("D", 0.015), ("F", 0.022), ("G", 0.030)]) == ["A"]


def test_fast_sounding_out_passes_through():
    gap = LETTERS_MASH_S + 0.04
    presses = [(k, i * gap) for i, k in enumerate("CAT")]
    assert _accepted(presses) == ["C", "A", "T"]


def test_hammering_one_key_still_answers_quickly():
    assert len(_accepted([("A", i * 0.1) for i in range(10)])) == 10
