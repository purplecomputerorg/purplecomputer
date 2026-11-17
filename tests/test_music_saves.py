"""A Music save keeps the picture and the tape's tune: opening it shows the picture as saved and plays the tune once.
Hold Enter loops the tape."""

import asyncio

import pytest

from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.loop_station import IDLE, LOOPING
from purplecomputer.panels import LoopPanel
from purplecomputer.rooms import music_room
from purplecomputer.rooms.music_room import MusicRoom


@pytest.fixture(autouse=True)
def saves_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_SAVES_DIR", str(tmp_path))


def _listen(room, monkeypatch) -> list:
    played = []
    monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, instrument, volume_scale=1.0: played.append(key))
    return played


async def _music_with_a_save(keys="qwq"):
    app = make_app(room="music")
    await type_text(app, keys)
    save = app.save_room()
    app._start_fresh("music")
    return app, save


def test_a_save_keeps_the_tape_as_its_tune():
    async def go():
        app, save = await _music_with_a_save()
        assert [n[0] for n in save.state["tune"]] == ["Q", "W", "Q"]
        assert "replay" not in save.state and "loop" not in save.state
    run(go())


def test_opening_shows_the_picture_as_saved_and_plays_the_tune_once_onto_the_tape(monkeypatch):
    async def go():
        app, save = await _music_with_a_save()
        room = app.room
        played = _listen(room, monkeypatch)
        app.open_save(save)
        assert room.color_state["Q"] == 1 and room.color_state["W"] == 0, "the picture shows right away"
        assert [k for k, *_ in room._tape] == ["Q", "W", "Q"]
        await room._tape_task
        assert played == ["Q", "W", "Q"] and room.color_state["Q"] == 1
        assert app.save_room() is None   # it is still exactly what was saved
    run(go())


def test_an_older_save_plays_its_minute_as_the_tune(monkeypatch):
    async def go():
        app, save = await _music_with_a_save()
        room = app.room
        state = {k: v for k, v in save.state.items() if k != "tune"}
        state["replay"] = {"from": {}, "notes": [["A", "music", "marimba", 0], ["S", "music", "marimba", 300]]}
        state["loop"] = {"ms": 1000, "notes": [["Z", "music", "marimba", 0]]}
        played = _listen(room, monkeypatch)
        app.apply_room_state("music", state)
        room.on_open_save()
        await room._tape_task
        assert played == ["A", "S"] and room.loop.state == IDLE
    run(go())


def test_time_travel_never_plays_music_back():
    async def go():
        app, save = await _music_with_a_save()
        app.apply_room_state("music", save.state)
        assert app.room._tape_task is None and app.room.loop.state == IDLE
    run(go())


def test_hold_enter_loops_the_tape_and_notes_played_along_join_it(monkeypatch):
    monkeypatch.setattr(music_room, "TUNE_GAP_MAX_S", 0.05)

    async def go():
        app = make_app(room="music")
        app._music_looping_enabled = True
        room = app.room
        room._enter_hold_fired()
        assert room.loop.state == IDLE, "nothing to loop yet"
        await type_text(app, "as")
        room._enter_hold_fired()
        assert room.loop.state == LOOPING and isinstance(app._panel, LoopPanel)
        assert [e[0] for e in room.loop.loop_events] == ["A", "S"]
        await press(app, "z")
        assert sorted(e[0] for e in room.loop.loop_events) == ["A", "S", "Z"]
        room._enter_hold_fired()
        assert room.loop.state == IDLE and [k for k, *_ in room._tape] == ["A", "S"], "the tape stays to loop again"
    run(go())


def test_a_long_tape_loops_its_last_stretch():
    async def go():
        room = make_app(room="music").room
        for i in range(30):
            room._tape_add("A", i * 1.0)
        room._loop_tune()
        assert room.loop.loop_duration <= room.loop.max_duration + music_room.TUNE_GAP_MAX_S
        room._stop_loop()
    run(go())


def test_space_while_looping_starts_the_sound_over_with_the_bar():
    async def go():
        app = make_app(room="music")
        room = app.room
        room._tape_add("A", 0.0)
        room._tape_add("S", 0.2)
        room._loop_tune()
        await asyncio.sleep(0.1)
        playing = room._loop_task
        room._space_tap()
        await asyncio.sleep(0)
        assert room._loop_task is not playing and playing.done()
        assert room.loop.loop_progress() < 0.1
        room._stop_loop()
    run(go())


def test_an_instrument_from_a_removed_pack_plays_as_the_first():
    assert MusicRoom._instrument_index("no-such-pack-instrument") == 0


def test_a_loop_going_around_leaves_the_picture_alone(monkeypatch):
    monkeypatch.setattr(music_room, "TUNE_GAP_MAX_S", 0.01)

    async def go():
        app = make_app(room="music")
        room = app.room
        await type_text(app, "qw")
        colors = dict(room.color_state)
        room._loop_tune()
        await asyncio.sleep(0.15)
        room._stop_loop()
        assert room.color_state == colors
    run(go())
