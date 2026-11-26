import random

import numpy as np

from purplecomputer import dial_synth
from purplecomputer.harness import make_app, run, type_text
from purplecomputer.music_constants import instruments


def test_a_note_is_stereo_16_bit_and_never_clips():
    for shape in range(3):
        frames = np.frombuffer(dial_synth.render(130.81, (shape, 4, 0, 3), 44100, 2), dtype=np.int16)
        assert len(frames) % 2 == 0 and 0 < np.abs(frames).max() < 32767 * 0.6
        assert abs(int(frames[-1])) < 50   # it fades out, so it ends without a click


def test_long_makes_the_note_longer():
    lengths = [len(dial_synth.render(440, (0, 2, n, 0), 44100, 1)) for n in range(5)]
    assert lengths == sorted(lengths) and lengths[0] < lengths[-1]


def test_dials_stop_at_their_ends_and_surprise_rolls_them_all():
    assert dial_synth.turn((0, 0, 0, 0), *dial_synth.dial_for_key("1"), random) == (0, 0, 0, 0)
    assert dial_synth.turn((2, 4, 4, 3), *dial_synth.dial_for_key("8"), random) == (2, 4, 4, 3)
    assert dial_synth.turn((0, 0, 0, 0), *dial_synth.dial_for_key("4"), random) == (0, 1, 0, 0)
    rolled = {dial_synth.turn(dial_synth.DEFAULT, *dial_synth.dial_for_key("0"), random.Random(seed)) for seed in range(20)}
    assert len(rolled) > 1


def test_a_save_with_odd_dials_starts_them_over():
    assert dial_synth.setting([2, 4, 4, 3]) == (2, 4, 4, 3)
    for bad in (None, [9, 0, 0, 0], [0, 0, 0], "x", [0.5, 0, 0, 0]):
        assert dial_synth.setting(bad) == dial_synth.DEFAULT


def test_synth_comes_after_the_other_instruments():
    assert instruments()[-1] == (dial_synth.ID, dial_synth.NAME)


def test_in_synth_the_number_keys_turn_dials_and_stay_off_the_song(monkeypatch):
    played = []

    async def go():
        app = make_app(room="music")
        room = app.room
        monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, i, scale=1.0: played.append(key))
        room.instrument_index = len(instruments()) - 1
        await type_text(app, "g4")
        assert room.synth == (0, 3, 1, 0)
        assert played == ["G", "G"]   # the dial plays the last note again
        assert [k for k, *_ in room._tape] == ["G"]
        assert room.timeline_state()["synth"] == [0, 3, 1, 0]
        room.restore_timeline_state({"synth": [2, 0, 4, 1]})
        assert room.synth == (2, 0, 4, 1)
    run(go())
