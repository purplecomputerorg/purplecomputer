"""Tests for the Time Travel timeline: storage, persistence, and app scrubbing."""

import asyncio
import json
import os

# Set environment before app imports
os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

from purple_tui import timeline as timeline_mod
from purple_tui.timeline import RoomTimeline


# ---------------------------------------------------------------------------
# Storage layer
# ---------------------------------------------------------------------------

class TestRoomTimeline:
    def test_record_and_tip(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art")
        assert tl.record({"a": 1}) is True
        assert tl.record({"a": 1, "b": 2}) is True
        assert tl.tip() == {"a": 1, "b": 2}
        assert len(tl) == 2

    def test_unchanged_state_is_not_recorded(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art")
        tl.record({"a": 1})
        assert tl.record({"a": 1}) is False
        assert len(tl) == 1

    def test_state_at_replays_deltas_and_removals(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art")
        tl.record({"a": 1, "b": 2})
        tl.record({"a": 5})          # b removed, a changed
        tl.record({"a": 5, "c": 3})  # c added
        assert tl.state_at(0) == {"a": 1, "b": 2}
        assert tl.state_at(1) == {"a": 5}
        assert tl.state_at(2) == {"a": 5, "c": 3}

    def test_state_at_across_snapshot_boundary(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art")
        count = timeline_mod.SNAPSHOT_EVERY * 2 + 3
        for i in range(count):
            tl.record({"n": i})
        for i in (0, timeline_mod.SNAPSHOT_EVERY, count - 1):
            assert tl.state_at(i) == {"n": i}

    def test_reload_from_disk(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("music")
        tl.record({"a": 1})
        tl.record({"a": 2, "b": [1, 2]})

        fresh = RoomTimeline("music")
        assert fresh.tip() == {"a": 2, "b": [1, 2]}
        assert len(fresh) == 2

    def test_torn_last_line_is_dropped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("play")
        tl.record({"a": 1})
        tl.record({"a": 2})
        path = tmp_path / "play.jsonl"
        path.write_text(path.read_text() + '{"d": {"a"')  # torn append

        fresh = RoomTimeline("play")
        assert len(fresh) == 2
        assert fresh.tip() == {"a": 2}

    def test_compaction_keeps_newest_history(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        monkeypatch.setattr(timeline_mod, "MAX_FILE_BYTES", 500)
        tl = RoomTimeline("art")
        for i in range(50):
            tl.record({"n": i, "pad": "x" * 20})
        assert len(tl) < 50
        assert tl.tip() == {"n": 49, "pad": "x" * 20}
        # File still replays cleanly after compaction
        fresh = RoomTimeline("art")
        assert fresh.tip() == tl.tip()

    def test_dev_mode_without_override_writes_no_files(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PURPLE_TIMELINE_DIR", raising=False)
        monkeypatch.setenv("PURPLE_DEV_MODE", "1")
        monkeypatch.setenv("HOME", str(tmp_path))
        tl = RoomTimeline("art")
        tl.record({"a": 1})
        assert tl.tip() == {"a": 1}
        assert not list(tmp_path.rglob("*.jsonl"))

    def test_file_is_valid_ndjson(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art")
        tl.record({"a": 1})
        tl.record({"b": 2})
        lines = (tmp_path / "art.jsonl").read_text().splitlines()
        assert len(lines) == 2
        assert "s" in json.loads(lines[0])
        parsed = json.loads(lines[1])
        assert parsed == {"d": {"b": 2}, "r": ["a"]}


# ---------------------------------------------------------------------------
# Room adapters + scrubbing (app harness)
# ---------------------------------------------------------------------------

from purple_tui.purple_tui import PurpleApp
from purple_tui.constants import REQUIRED_TERMINAL_ROWS, ROOM_ART, ROOM_MUSIC

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)
SETTLE = 0.4


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _settle(pilot):
    await pilot.pause()
    await asyncio.sleep(SETTLE)
    await pilot.pause()


def test_art_state_round_trip():
    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            app.action_switch_room(ROOM_ART[0])
            await _settle(pilot)

            from purple_tui.rooms.art_room import ArtMode, ArtCanvas
            art = app.query_one(ArtMode)
            canvas = art.query_one("#art-canvas", ArtCanvas)
            canvas.paint_at(3, 2, "f")
            canvas.paint_at(4, 2, "c")
            canvas.type_char("h")

            state = art.timeline_state()
            grid_before = dict(canvas._grid)
            painted_before = set(canvas._painted_positions)

            art.clear_canvas()
            assert not canvas._grid

            art.restore_timeline_state(state)
            assert canvas._grid == grid_before
            assert canvas._painted_positions == painted_before
            assert art.timeline_state() == state

    _run(scenario())


def test_music_state_round_trip_and_reset():
    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            app.action_switch_room(ROOM_MUSIC[0])
            await _settle(pilot)

            from purple_tui.rooms.music_room import MusicMode
            music = app.query_one(MusicMode)
            music.grid.next_color("A")
            music.grid.next_color("A")
            music.grid.next_color("5")
            music._instrument_index = 2
            music._letters_mode = True

            state = music.timeline_state()
            music.reset_state()
            assert music.timeline_state() != state

            music.restore_timeline_state(state)
            assert music.timeline_state() == state
            assert music._instrument_index == 2
            assert music._letters_mode is True

    _run(scenario())


def test_play_entries_replay_and_clear_records_steps(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)

            from purple_tui.rooms.play_room import PlayMode, InlineInput
            play = app.query_one(PlayMode)
            play.query_one("#play-input").post_message(InlineInput.Submitted("2 + 2"))
            await _settle(pilot)
            play.query_one("#play-input").post_message(InlineInput.Submitted("3 + 3"))
            await _settle(pilot)

            tl = app._timelines["play"]
            state = tl.tip()
            assert sorted(state.values()) == ["2 + 2", "3 + 3"]

            steps_before_clear = len(tl)
            app._start_fresh("play")
            await _settle(pilot)
            assert play.timeline_state() == {}
            assert tl.tip() == {}
            assert len(tl) > steps_before_clear

            play.restore_timeline_state(state)
            await _settle(pilot)
            assert play.timeline_state() == state
            scroll = play.query_one("#history-scroll")
            assert len(scroll.children) > 0

    _run(scenario())


def test_room_state_survives_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def first_boot():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            app.action_switch_room(ROOM_ART[0])
            await _settle(pilot)
            from purple_tui.rooms.art_room import ArtMode, ArtCanvas
            canvas = app.query_one(ArtMode).query_one("#art-canvas", ArtCanvas)
            canvas.paint_at(7, 4, "f")
            app.timeline_capture_now("art")
            return dict(canvas._grid)

    async def second_boot():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            app.action_switch_room(ROOM_ART[0])
            await _settle(pilot)
            from purple_tui.rooms.art_room import ArtMode, ArtCanvas
            canvas = app.query_one(ArtMode).query_one("#art-canvas", ArtCanvas)
            return dict(canvas._grid)

    painted = _run(first_boot())
    assert painted
    assert _run(second_boot()) == painted


def test_scrub_previews_and_escape_restores(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            app.action_switch_room(ROOM_ART[0])
            await _settle(pilot)

            from purple_tui.rooms.art_room import ArtMode, ArtCanvas
            art = app.query_one(ArtMode)
            canvas = art.query_one("#art-canvas", ArtCanvas)

            tl = app._timelines["art"]
            canvas.paint_at(1, 1, "f")
            app.timeline_capture_now("art")
            canvas.paint_at(2, 1, "c")
            app.timeline_capture_now("art")
            total = len(tl)
            assert total >= 3  # baseline + two paints

            app._start_time_travel()
            assert app._time_travel is not None
            await _settle(pilot)

            app._step_time_travel(-1)
            assert (2, 1) not in canvas._grid  # previewing the earlier step
            app._step_time_travel(-1)

            app._cancel_time_travel()
            await _settle(pilot)
            assert app._time_travel is None
            assert (2, 1) in canvas._grid  # tip restored
            assert len(tl) == total  # cancel adds nothing

    _run(scenario())


def test_scrub_land_appends_instead_of_truncating(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            app.action_switch_room(ROOM_ART[0])
            await _settle(pilot)

            from purple_tui.rooms.art_room import ArtMode, ArtCanvas
            art = app.query_one(ArtMode)
            canvas = art.query_one("#art-canvas", ArtCanvas)

            tl = app._timelines["art"]
            canvas.paint_at(1, 1, "f")
            app.timeline_capture_now("art")
            canvas.paint_at(2, 1, "c")
            app.timeline_capture_now("art")
            total = len(tl)

            app._start_time_travel()
            app._step_time_travel(-1)
            app._land_time_travel()
            await _settle(pilot)

            assert app._time_travel is None
            assert len(tl) == total + 1  # landed state appended, nothing lost
            assert (2, 1) not in canvas._grid
            assert tl.state_at(total - 1) != tl.tip()  # old tip still reachable

    _run(scenario())
