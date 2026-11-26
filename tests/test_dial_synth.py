import numpy as np

from purplecomputer import dial_synth
from purplecomputer.harness import make_app, run, type_text
from purplecomputer.music_constants import instruments


def test_a_note_is_stereo_16_bit_and_never_clips():
    for shape in range(3):
        frames = np.frombuffer(dial_synth.render(130.81, (shape, 4, 0, 3), 44100, 2), dtype=np.int16)
        assert len(frames) % 2 == 0 and 0 < np.abs(frames).max() < 32767 * 0.6
        assert abs(int(frames[-1])) < 50   # it fades out, so it ends without a click


def test_without_numpy_plain_python_makes_the_same_note(monkeypatch):
    for dials, freq in (((0, 4, 2, 3), 65.4), ((1, 2, 1, 1), 261.6), ((2, 4, 4, 3), 659.3)):
        fast = dial_synth.render(freq, dials, 44100, 2)
        monkeypatch.setattr(dial_synth, "_has_numpy", lambda: False)
        assert dial_synth.render(freq, dials, 44100, 2) == fast
        monkeypatch.undo()


def test_a_note_the_mixer_refuses_is_skipped_not_raised(monkeypatch):
    import pygame
    from purplecomputer import sounds

    def refuse(*_, **__):
        raise pygame.error("no")
    monkeypatch.setattr(sounds, "mixer_ready_for_play", lambda: True)
    monkeypatch.setattr(sounds.pygame.mixer, "get_init", lambda: (44100, -16, 2))
    monkeypatch.setattr(sounds.pygame.mixer, "Sound", refuse)
    assert sounds.SoundBank().note("synth", "C", 4) is None


def test_long_makes_the_note_longer():
    lengths = [len(dial_synth.render(440, (0, 2, n, 0), 44100, 1)) for n in range(5)]
    assert lengths == sorted(lengths) and lengths[0] < lengths[-1]


def test_each_dial_steps_round_and_back_to_its_start():
    assert dial_synth.turn((0, 0, 0, 0), "2") == (0, 1, 0, 0)
    assert dial_synth.turn((2, 4, 4, 3), "1") == (0, 4, 4, 3)
    assert dial_synth.turn((2, 4, 4, 3), "4") == (2, 4, 4, 0)


def test_a_save_with_odd_dials_starts_them_over():
    assert dial_synth.setting([2, 4, 4, 3]) == (2, 4, 4, 3)
    for bad in (None, [9, 0, 0, 0], [0, 0, 0], "x", [0.5, 0, 0, 0]):
        assert dial_synth.setting(bad) == dial_synth.DEFAULT


def test_synth_comes_after_the_other_instruments():
    assert instruments()[-1] == (dial_synth.ID, dial_synth.NAME)


def test_the_picture_shows_every_dial():
    base = dial_synth.picture(dial_synth.DEFAULT, 262)
    assert max(map(abs, base)) <= 1.0
    for key in dial_synth.KEYS:
        assert dial_synth.picture(dial_synth.turn(dial_synth.DEFAULT, key), 262) != base
    short, long_ = (dial_synth.picture((2, 2, n, 0), 262) for n in (0, 4))
    assert max(map(abs, short[-50:])) < max(map(abs, long_[-50:]))


def test_a_higher_note_draws_its_waves_closer_together():
    def crossings(freq):
        line = dial_synth.picture((0, 2, 4, 0), freq)
        return sum(a < 0 <= b for a, b in zip(line, line[1:]))
    assert crossings(65.4) < crossings(262) < crossings(659)


def test_in_synth_1_to_4_turn_dials_off_the_song_and_the_rest_do_nothing(monkeypatch):
    played = []

    async def go():
        app = make_app(room="music")
        room = app.room
        monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, i, scale=1.0: played.append(key))
        room.instrument_index = len(instruments()) - 1
        await type_text(app, "g27")
        assert room.synth == (0, 3, 1, 0)
        assert played == ["G", "G"]   # the dial plays the last note again
        assert [k for k, *_ in room._tape] == ["G"]
        assert room.timeline_state()["synth"] == [0, 3, 1, 0]
        room.restore_timeline_state({"synth": [2, 0, 4, 1]})
        assert room.synth == (2, 0, 4, 1)
    run(go())
