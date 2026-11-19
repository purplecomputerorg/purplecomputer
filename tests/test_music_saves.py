"""A Music save keeps the picture and the tape's tune: opening it shows the picture as saved and plays the tune once.
Time Travel keeps the song with each step. Hold Enter loops the tape."""

import asyncio
import time

import pytest

from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.loop_station import IDLE, LOOPING, RECORDING
from purplecomputer.panels import LoopPanel
from purplecomputer.rooms import music_room


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
        assert [save.state[f"t:{i}"][0] for i in range(3)] == ["Q", "W", "Q"]
        assert not {"replay", "loop", "tune"} & save.state.keys()
    run(go())


def test_a_letters_save_keeps_its_letters():
    async def go():
        app = make_app(room="music")
        app.room.letters_mode = True
        for i, key in enumerate("CAT"):
            app.room._spell(key, time.monotonic() + i * 0.1)
        state = app.save_state("music")
        app._start_fresh("music")
        app.apply_room_state("music", state)
        assert app.room._spelled == "cat" and app.room.word == "cat"
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
        state = {k: v for k, v in save.state.items() if not k.startswith("t:")}
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
        assert room.loop.state == RECORDING, "nothing to loop yet: it records"
        room._stop_loop()
        await type_text(app, "as")
        room._enter_hold_fired()
        assert room.loop.state == LOOPING and isinstance(app._panel, LoopPanel)
        assert [e[0] for e in room.loop.loop_events] == ["A", "S"]
        await press(app, "z")
        assert sorted(e[0] for e in room.loop.loop_events) == ["A", "S", "Z"]
        room._enter_hold_fired()
        assert room.loop.state == IDLE and [k for k, *_ in room._tape] == ["A", "S"], "the tape stays to loop again"
    run(go())


def test_with_nothing_to_loop_hold_enter_records_then_loops_what_was_played(monkeypatch):
    monkeypatch.setattr(music_room, "RECORD_S", 0.3)

    async def go():
        app = make_app(room="music")
        app._music_looping_enabled = True
        room = app.room
        assert room._hint_text(), "hold Enter loops even with nothing played yet"
        room._enter_hold_fired()
        assert room.loop.state == RECORDING and isinstance(app._panel, LoopPanel)
        await type_text(app, "as")
        assert [k for k, *_ in room._tape] == ["A", "S"], "the recording fills the tape"
        await asyncio.sleep(0.45)
        assert room.loop.state == LOOPING and [e[0] for e in room.loop.loop_events] == ["A", "S"]
        room._stop_loop()
    run(go())


def test_space_ends_a_recording_esc_stops_it_and_nothing_played_ends_it_quietly(monkeypatch):
    monkeypatch.setattr(music_room, "RECORD_S", 0.1)

    async def go():
        app = make_app(room="music")
        app._music_looping_enabled = True
        room = app.room
        room._enter_hold_fired()
        await type_text(app, "a")
        await press(app, "space")
        assert room.loop.state == LOOPING
        room._stop_loop()
        room._tape = []
        room._enter_hold_fired()
        await press(app, "escape")
        assert room.loop.state == IDLE and app.room is room
        room._enter_hold_fired()
        await asyncio.sleep(0.3)
        assert room.loop.state == IDLE and app._panel is None, "nothing played: back as it was"
    run(go())


def test_backspace_on_an_empty_tape_clears_the_last_song_so_hold_enter_records():
    async def go():
        app = make_app(room="music")
        app._music_looping_enabled = True
        room = app.room
        await type_text(app, "qw")
        room._quiet()
        assert room._last_song
        await press(app, "backspace")
        assert room._last_song is None
        room._enter_hold_fired()
        assert room.loop.state == RECORDING
        room._stop_loop()
    run(go())


def test_a_long_tape_loops_whole_just_as_space_plays_it():
    async def go():
        room = make_app(room="music").room
        for i in range(30):
            room._tape_add("A", i * 1.0)
        room._loop_tune()
        assert len(room.loop.loop_events) == 30
        assert room.loop.loop_duration == pytest.approx(29 + 1.0), "the whole tape, then its usual gap"
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


def test_a_loop_going_around_moves_its_keys_colors_on_as_playing_them_does(monkeypatch):
    monkeypatch.setattr(music_room, "TUNE_GAP_MAX_S", 0.01)

    async def go():
        app = make_app(room="music")
        room = app.room
        await type_text(app, "qw")
        colors = dict(room.color_state)
        room._loop_tune()
        await asyncio.sleep(0.15)
        room._stop_loop()
        assert room.color_state["Q"] != colors["Q"] and room.color_state["W"] != colors["W"]
    run(go())


def _keys(room) -> list:
    return [k for k, *_ in room._tape]


def test_time_travel_shows_each_moment_with_its_song_and_backing_out_keeps_the_song():
    async def go():
        app = make_app(room="music")
        room = app.room
        await type_text(app, "qw")
        app.timeline_capture_now("music")
        await type_text(app, "er")
        app._start_time_travel()
        app._step_time_travel(-1)
        assert _keys(room) == ["Q", "W"]
        app._cancel_time_travel()
        assert _keys(room) == ["Q", "W", "E", "R"]
    run(go())


def test_landing_on_a_moment_brings_back_its_song_to_play_and_add_to():
    async def go():
        app = make_app(room="music")
        room = app.room
        await type_text(app, "qw")
        app.timeline_capture_now("music")
        await type_text(app, "er")
        app._start_time_travel()
        app._step_time_travel(-1)
        app._land_time_travel()
        await type_text(app, "a")
        assert _keys(room) == ["Q", "W", "A"]
    run(go())


def test_an_erased_song_comes_back_through_time_travel():
    async def go():
        app = make_app(room="music")
        room = app.room
        await type_text(app, "qwe")
        app.timeline_capture_now("music")
        room._erase(len(room._tape))
        app.timeline_capture_now("music")
        assert room._tape == []
        app._start_time_travel()
        app._step_time_travel(-1)
        app._land_time_travel()
        assert _keys(room) == ["Q", "W", "E"]
    run(go())


def test_a_step_adds_only_its_new_notes_even_once_the_song_is_full(monkeypatch):
    monkeypatch.setattr(music_room, "TAPE_MAX", 3)

    async def go():
        room = make_app(room="music").room
        for i, key in enumerate("QWE"):
            room._tape_add(key, i * 0.5)
        before = room.timeline_state()
        room._tape_add("R", 1.5)
        after = room.timeline_state()
        changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
        assert changed == {"t:0", "t:3"}, "the first note drops off and the new one joins; the rest stay as they were"
    run(go())


def test_restoring_a_song_records_it_as_it_was():
    async def go():
        app = make_app(room="music")
        await type_text(app, "qwe")
        state = app.room_state("music")
        app.apply_room_state("music", state)
        assert app.room_state("music") == state
    run(go())


def test_the_song_plays_back_on_the_instrument_set_now(monkeypatch):
    async def go():
        app = make_app(room="music")
        room = app.room
        await type_text(app, "qw")
        room.instrument_index = 1
        heard = []
        monkeypatch.setattr(room, "play_sound_with_instrument",
                            lambda key, instrument, volume_scale=1.0: heard.append(instrument))
        room._play_tape()
        await room._tape_task
        assert heard == [1, 1]
    run(go())
