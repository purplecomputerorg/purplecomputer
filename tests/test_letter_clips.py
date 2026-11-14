"""Say Letters: any grid key a pack recorded plays its clip, punctuation included."""

from purplecomputer.harness import make_app, run
from purplecomputer.rooms.music_room import MODE_LETTERS
from purplecomputer.sounds import CLIP_NAMES


def test_punctuation_has_a_file_name():
    assert CLIP_NAMES["/"] == "slash" and CLIP_NAMES["Q"] == "q"
    assert all("/" not in name for name in CLIP_NAMES.values())


def test_a_recorded_punctuation_key_speaks_and_an_unrecorded_one_plays_a_note(monkeypatch):
    async def go():
        app = make_app()
        app.action_switch_room("music")
        room = app.room
        said, notes = [], []
        monkeypatch.setattr(room.sounds, "letters", lambda: {"/": object()})
        monkeypatch.setattr(room, "play_letter", said.append)
        monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, inst: notes.append(key))
        room._play_key("/", MODE_LETTERS)
        room._play_key(";", MODE_LETTERS)
        assert said == ["/"] and notes == [";"]
    run(go())


def test_a_pack_letter_plays_after_purple_when_listed_and_alone_otherwise(tmp_path, monkeypatch):
    import json
    from purplecomputer import sounds
    from purplecomputer.content import get_content
    letters = tmp_path / "content" / "letters"
    letters.mkdir(parents=True)
    for name in ("d", "e"):
        (letters / f"{name}.wav").write_bytes(b"")
    (tmp_path / "content" / "letters.json").write_text(json.dumps({"after": ["d"]}))
    monkeypatch.setattr(sounds, "_load", lambda p: ("pack" if tmp_path in p.parents else p.parent.name, p.stem))
    monkeypatch.setattr(sounds, "mixer_ready_for_play", lambda: True)
    monkeypatch.setattr(get_content(), "pack_dirs", lambda sub: [letters])
    bank = sounds.SoundBank()
    names, phonics = bank.letters(), bank.letters(sounds=True)
    assert names["D"] == [("letters", "d"), ("pack", "d")] and names["E"] == [("pack", "e")] and names["F"] == [("letters", "f")]
    assert phonics["D"] == [("letter-sounds", "d"), ("pack", "d")] and phonics["E"] == [("pack", "e")] and phonics["1"] == [("letters", "1")]


def test_the_familys_clip_follows_purples_and_the_next_key_or_leaving_cuts_it_off(monkeypatch):
    import asyncio
    from purplecomputer.rooms import music_room
    played = []

    class Clip:
        def __init__(self, name):
            self.name = name

        def get_length(self):
            return 0.02

        def stop(self):
            pass

    monkeypatch.setattr(music_room, "play_safe", lambda clip: played.append(clip.name))
    monkeypatch.setattr(music_room, "LETTER_AFTER_GAP_S", 0)

    async def go():
        app = make_app(room="music")
        room = app.room
        monkeypatch.setattr(app, "_effective_volume", lambda: 1)
        monkeypatch.setattr(room.sounds, "letters", lambda sounds=False: {
            "D": [Clip("dee"), Clip("dad")], "E": [Clip("ee"), Clip("elephant")]})
        room.play_letter("D")
        await asyncio.sleep(0.1)
        room.play_letter("E")
        room.play_letter("D")
        room.stop_sound()
        await asyncio.sleep(0.1)
        assert played == ["dee", "dad", "ee", "dee"]
    run(go())
