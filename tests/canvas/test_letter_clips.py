"""Say Letters: any grid key a pack recorded plays its clip, punctuation included."""

from purple_tui.canvas.harness import make_app, run
from purple_tui.canvas.rooms.music_room import MODE_LETTERS
from purple_tui.canvas.sounds import CLIP_NAMES


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
        monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, inst, scale: notes.append((key, scale)))
        room._play_key("/", MODE_LETTERS)
        room._play_key(";", MODE_LETTERS)
        assert said == ["/"] and notes == [("/", 0.2), (";", 1.0)]
    run(go())
