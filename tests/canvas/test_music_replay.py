"""Music saves keep the last minute of playing (and a loop) and play it back when opened."""

import asyncio

import pytest

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.music_replay import KEEP_S, MAX_GAP_S, Recording
from purple_tui.canvas.panels import LoopPanel, ReplayPanel
from purple_tui.canvas.rooms.music_room import MusicRoom
from purple_tui.loop_station import IDLE, LOOPING
from purple_tui.music_constants import ALL_KEYS, COLORS


@pytest.fixture(autouse=True)
def saves_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_SAVES_DIR", str(tmp_path))


def _blank():
    return {k: -1 for k in ALL_KEYS}


def test_pauses_are_cut_short_and_the_oldest_notes_move_into_the_start():
    rec = Recording(_blank())
    rec.add("A", "music", "piano", 0.0)
    rec.add("B", "music", "piano", 0.2)
    rec.add("C", "music", "piano", 30.0)
    assert [n[3] for n in rec.notes] == [0, 200, 200 + round(MAX_GAP_S * 1000)]
    for i in range(int(KEEP_S / MAX_GAP_S) + 2):
        rec.add("D", "music", "piano", 40.0 + i * 5)
    assert rec.seconds <= KEEP_S and rec.notes[0][0] == "D"
    assert rec.start["A"] == 0 and rec.start["B"] == 0 and rec.start["C"] == 0


def test_the_start_plus_the_notes_is_the_pattern():
    colors, rec = _blank(), Recording(_blank())
    for i, key in enumerate("ABABCA" * 40):
        colors[key] = (colors[key] + 1) % len(COLORS)
        rec.add(key, "music", "piano", i * 0.9)
    replayed = Recording.load(rec.data(), {}).start
    for key, *_ in rec.notes:
        replayed[key] = (replayed[key] + 1) % len(COLORS)
    assert replayed == colors


async def _music_with_a_save(keys="qwq"):
    app = make_app(room="music")
    await type_text(app, keys)
    save = app.save_room()
    app._start_fresh("music")
    return app, save


def test_opening_music_plays_it_from_where_it_began_up_to_the_saved_pattern():
    async def go():
        app, save = await _music_with_a_save()
        room = app.room
        app.open_save(save)
        assert isinstance(app._panel, ReplayPanel)
        assert all(v == -1 for v in room.color_state.values())
        assert room.timeline_state()["k:Q"] == 1
        await asyncio.sleep(0.1)
        assert room._replay is None and app._panel is None
        assert room.color_state["Q"] == 1 and room.color_state["W"] == 0
        assert app.save_room() is None   # it is still exactly what was saved
    run(go())


def test_a_key_stops_the_replay_on_the_saved_pattern_and_plays_too():
    async def go():
        app, save = await _music_with_a_save()
        room = app.room
        save.data["state"]["replay"]["notes"][-1][3] = 5000
        app.open_save(save)
        await press(app, "q")
        assert room._replay is None and app._panel is None
        assert room.color_state["Q"] == 2 and room.color_state["W"] == 0
    run(go())


def test_esc_only_stops_the_replay():
    async def go():
        app, save = await _music_with_a_save()
        save.data["state"]["replay"]["notes"][-1][3] = 5000
        app.open_save(save)
        await press(app, "escape")
        assert app.room._replay is None and app.top is None
        assert app.room.color_state["Q"] == 1
    run(go())


def test_a_saved_loop_keeps_looping_after_the_replay():
    async def go():
        app = make_app(room="music")
        room = app.room
        room._advance_loop_state()
        await type_text(app, "as")
        room._advance_loop_state()
        assert room.loop.state == LOOPING
        save = app.save_room()
        assert save.state["loop"]["notes"]
        app._start_fresh("music")
        assert room.loop.state == IDLE
        app.open_save(save)
        await press(app, "z")
        assert room.loop.state == LOOPING and isinstance(app._panel, LoopPanel)
        assert [e[0] for e in room.loop.loop_events] == ["A", "S"]
    run(go())


def test_time_travel_never_plays_music_back():
    async def go():
        app, save = await _music_with_a_save()
        app.apply_room_state("music", save.state)
        assert app.room._replay is None and app.room.loop.state == IDLE
    run(go())


def test_an_instrument_from_a_removed_pack_plays_as_the_first():
    assert MusicRoom._instrument_index("no-such-pack-instrument") == 0
