"""Tests for the Time Travel timeline: storage, persistence, and app scrubbing."""

import json

# Set environment before app imports

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
        assert parsed.pop("t") > 0
        assert parsed == {"d": {"b": 2}, "r": ["a"]}


# ---------------------------------------------------------------------------
# Time Travel bar track
# ---------------------------------------------------------------------------

from datetime import datetime
from types import SimpleNamespace

from purple_tui.canvas import panels
from purple_tui.canvas.harness import make_app, run, type_text

NOW = datetime(2026, 10, 13, 15, 0).timestamp()


class TestTimeTravelTrack:
    def test_a_long_pause_starts_a_new_stretch(self):
        times = [NOW - 3600, NOW - 3590, NOW - 60, NOW - 50, NOW - 40]
        assert panels.stretches(times, NOW) == [[0, 2, "Today"], [2, 5, "Today"]]

    def test_a_new_day_starts_a_new_stretch(self):
        times = [NOW - 86400, NOW - 10]
        assert [label for *_, label in panels.stretches(times, NOW)] == ["Yesterday", "Today"]

    def test_unstamped_steps_are_one_old_stretch(self):
        assert panels.stretches([None, None, NOW], NOW) == [[0, 2, "Earlier"], [2, 3, "Today"]]

    def test_oldest_stretches_merge_down_to_the_cap(self):
        times = [NOW - i * panels.SESSION_GAP_S * 2 for i in range(20, 0, -1)]
        runs = panels.stretches(times, NOW)
        assert len(runs) == panels.MAX_STRETCHES
        assert runs[0][0] == 0 and runs[-1] == [19, 20, "Today"]

    def test_time_ago_words(self):
        assert panels.time_ago(NOW - 20, NOW) == "Just now"
        assert panels.time_ago(NOW - 60, NOW) == "1 minute ago"
        assert panels.time_ago(NOW - 5 * 3600, NOW) == "5 hours ago"
        assert panels.time_ago(NOW - 3 * 86400, NOW) == "3 days ago"
        assert panels.time_ago(NOW - 20 * 86400, NOW) == "2 weeks ago"
        assert panels.time_ago(NOW - 100 * 86400, NOW) == "3 months ago"
        assert panels.time_ago(None, NOW) == "Earlier"

    def test_old_stretches_have_few_stops_and_the_newest_has_all(self):
        times = [NOW - 86400] * 40 + [NOW - 30] * 6
        marks = panels.stops(times, NOW)
        assert marks[0] == 0 and 39 in marks
        assert len([m for m in marks if m < 40]) <= panels.OLD_STRETCH_STOPS + 1
        assert marks[-6:] == list(range(40, 46))

    def test_draws_any_history(self):
        async def scenario():
            app = make_app()
            for index, times in ((0, [NOW]), (3, [None] * 5 + [NOW - 86400 * 2, NOW - 100, NOW])):
                bar = panels.TimeTravelBar(SimpleNamespace(time_travel_position=lambda: (index, times)))
                bar.draw(app.g, app._viewport_rect())
        run(scenario())


def test_art_state_round_trip():
    async def scenario():
        app = make_app()
        app.action_switch_room("art")
        art = app.rooms["art"]
        art.paint_at(3, 2, "f")
        art.paint_at(4, 2, "c")
        art.type_char("h")
        state = art.timeline_state()
        grid_before = dict(art._grid)
        painted_before = set(art._painted_positions)
        art.clear()
        assert not art._grid
        art.restore_timeline_state(state)
        assert art._grid == grid_before
        assert art._painted_positions == painted_before
        assert art.timeline_state() == state
    run(scenario())


def test_music_state_round_trip_and_reset():
    async def scenario():
        app = make_app()
        app.action_switch_room("music")
        music = app.rooms["music"]
        music.next_color("A")
        music.next_color("A")
        music.next_color("5")
        music.instrument_index = 2
        music.letters_mode = True
        state = music.timeline_state()
        music.clear()
        assert music.timeline_state() != state
        music.restore_timeline_state(state)
        assert music.timeline_state() == state
        assert music.instrument_index == 2
        assert music.letters_mode is True
    run(scenario())


def test_play_entries_replay_and_clear_records_steps(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = make_app()
        play = app.rooms["play"]
        await type_text(app, "2 + 2", enter=True)
        await type_text(app, "3 + 3", enter=True)
        tl = app._timelines["play"]
        state = tl.tip()
        assert sorted(state.values()) == ["2 + 2", "3 + 3"]
        steps_before_clear = len(tl)
        app._start_fresh("play")
        assert play.timeline_state() == {}
        assert tl.tip() == {}
        assert len(tl) > steps_before_clear
        play.restore_timeline_state(state)
        assert play.timeline_state() == state
        assert play.history
    run(scenario())


def test_room_state_survives_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def first_boot():
        app = make_app()
        app.action_switch_room("art")
        app.rooms["art"].paint_at(7, 4, "f")
        app.timeline_capture_now("art")
        return dict(app.rooms["art"]._grid)

    async def second_boot():
        app = make_app()
        app.action_switch_room("art")
        return dict(app.rooms["art"]._grid)
    painted = run(first_boot())
    assert painted
    assert run(second_boot()) == painted


def _two_paints(app):
    app.action_switch_room("art")
    art, tl = app.rooms["art"], app._timelines["art"]
    art.paint_at(1, 1, "f")
    app.timeline_capture_now("art")
    art.paint_at(2, 1, "c")
    app.timeline_capture_now("art")
    return art, tl


def test_scrub_previews_and_escape_restores(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = make_app()
        art, tl = _two_paints(app)
        total = len(tl)
        assert total >= 3  # baseline + two paints
        app._start_time_travel()
        assert app._time_travel is not None
        app._step_time_travel(-1)
        assert (2, 1) not in art._grid  # previewing the earlier step
        app._step_time_travel(-1)
        app._cancel_time_travel()
        assert app._time_travel is None
        assert (2, 1) in art._grid  # tip restored
        assert len(tl) == total  # cancel adds nothing
    run(scenario())


def test_scrub_land_appends_instead_of_truncating(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = make_app()
        art, tl = _two_paints(app)
        total = len(tl)
        app._start_time_travel()
        app._step_time_travel(-1)
        app._land_time_travel()
        assert app._time_travel is None
        assert len(tl) == total + 1  # landed state appended, nothing lost
        assert (2, 1) not in art._grid
        assert tl.state_at(total - 1) != tl.tip()  # old tip still reachable
    run(scenario())
