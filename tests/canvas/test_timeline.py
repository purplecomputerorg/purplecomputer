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
        big = {f"c:{i}": "x" for i in range(50)}
        for i in range(200):
            tl.record({**big, "n": i})
        snapshots = sum('"s"' in line for line in (tmp_path / "art.jsonl").read_text().splitlines())
        assert 1 < snapshots < 20       # a snapshot once the deltas since the last outweigh it
        for i in range(200):
            assert tl.state_at(i) == {**big, "n": i}

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

    def test_tags_survive_reload_and_compaction(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art")
        tl.record({"n": 0})
        tl.mark("first")
        tl.mark("first")
        assert RoomTimeline("art").tags() == [["first"]]
        monkeypatch.setattr(timeline_mod, "MAX_FILE_BYTES", 500)
        for i in range(1, 50):
            tl.record({"n": i, "pad": "x" * 20})
            if i == 48:
                tl.mark("late")
        fresh = RoomTimeline("art")
        tagged = {tags[0]: fresh.state_at(i)["n"] for i, tags in enumerate(fresh.tags()) if tags}
        assert tagged == {"first": 0, "late": 48}

    def test_compaction_thins_old_history_but_keeps_how_each_session_ended(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        clock = [NOW - 86400]
        monkeypatch.setattr(timeline_mod, "time", SimpleNamespace(time=lambda: clock[0]))
        tl = RoomTimeline("art")
        for i in range(30):
            tl.record({"n": i, "pad": "x" * 20})
        clock[0] = NOW
        monkeypatch.setattr(timeline_mod, "MAX_FILE_BYTES", 2000)
        for i in range(30, 60):
            tl.record({"n": i, "pad": "x" * 20})
        kept = [RoomTimeline("art").state_at(i)["n"] for i in range(len(tl))]
        assert 29 in kept and kept[-1] == 59          # yesterday's last picture and now
        assert kept == sorted(kept) and len(kept) < 60
        assert set(range(40, 60)) <= set(kept)        # recent steps all stay

    def test_a_dense_picture_keeps_hours_of_steps(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art")
        cells = {}
        for i in range(3000):
            cells[f"c:{i % 120},{i // 120 % 30}"] = [" ", None, "#e74c3c" if i % 2 else "#3498db", 1]
            tl.record(dict(cells))
        assert (tmp_path / "art.jsonl").stat().st_size < timeline_mod.MAX_FILE_BYTES
        assert len(RoomTimeline("art")) == 3000

    def test_dev_mode_without_override_writes_no_files(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PURPLE_TIMELINE_DIR", raising=False)
        monkeypatch.setenv("PURPLE_DEV_MODE", "1")
        monkeypatch.setenv("HOME", str(tmp_path))
        tl = RoomTimeline("art")
        tl.record({"a": 1})
        assert tl.tip() == {"a": 1}
        assert not list(tmp_path.rglob("*.jsonl"))

    def test_recent_steps_stay_fine_and_older_ones_thin_to_one_per_pause(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        clock = [NOW - 600]
        monkeypatch.setattr(timeline_mod, "time", SimpleNamespace(time=lambda: clock[0]))
        tl = RoomTimeline("art", fine_for_s=300)
        for burst in range(3):                  # five quick steps, then a pause, three times over
            for i in range(5):
                tl.record({"n": burst * 5 + i})
                clock[0] += 1
            clock[0] += 10
            if burst == 0:
                tl.mark("saved")
        clock[0] = NOW - 60
        for i in range(15, 25):
            tl.record({"n": i})
            clock[0] += 1
        clock[0] = NOW
        tl.coarsen()
        kept = [tl.state_at(i)["n"] for i in range(len(tl))]
        assert kept == [0, 3, 4, 9, 14] + list(range(15, 25))     # a saved step and the one before it stay
        assert tl.state_at(kept.index(4)) == {"n": 4} and tl.tags()[2] == ["saved"]
        assert [RoomTimeline("art", fine_for_s=300).state_at(i)["n"] for i in range(5)] == [0, 3, 4, 9, 14]

    def test_steady_play_keeps_a_coarse_step_every_so_often(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        clock = [NOW - 3600]
        monkeypatch.setattr(timeline_mod, "time", SimpleNamespace(time=lambda: clock[0]))
        tl = RoomTimeline("art", fine_for_s=300)
        for i in range(60):
            tl.record({"n": i})
            clock[0] += 1
        clock[0] = NOW
        tl.coarsen()
        assert [tl.state_at(i)["n"] for i in range(len(tl))] == [0, 15, 30, 45, 59]

    def test_a_past_runs_steps_thin_on_load(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
        tl = RoomTimeline("art", fine_for_s=300)
        for i in range(10):
            tl.record({"n": i})
        assert len(tl) == 10
        assert RoomTimeline("art", fine_for_s=300).tip() == {"n": 9}
        assert len(RoomTimeline("art", fine_for_s=300)) < 10
        assert len(RoomTimeline("art")) < 10, "the thinned file is what's on disk"

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
from purple_tui.canvas.app import JUMP_TAG
from purple_tui.canvas.harness import make_app, press, run, type_text

NOW = datetime(2026, 10, 13, 15, 0).timestamp()


class TestTimeTravelTrack:
    def test_a_long_pause_ends_a_session_but_not_the_days_stretch(self):
        times = [NOW - 3600, NOW - 3590, NOW - 60, NOW - 50, NOW - 40]
        assert panels.sessions(times, NOW) == [[0, 2, "Today"], [2, 5, "Today"]]
        assert panels.stretches(times, NOW) == [[0, 5, "Today"]]

    def test_a_new_day_starts_a_new_stretch(self):
        times = [NOW - 86400, NOW - 10]
        assert [label for *_, label in panels.stretches(times, NOW)] == ["Yesterday", "Today"]

    def test_unstamped_steps_are_one_old_stretch(self):
        assert panels.stretches([None, None, NOW], NOW) == [[0, 2, "Earlier"], [2, 3, "Today"]]

    def test_oldest_stretches_merge_down_to_the_cap(self):
        times = [NOW - i * 86400 for i in range(6, -1, -1)] + [NOW - i * 86400 * 30 for i in range(3, 0, -1)]
        times.sort()
        runs = panels.stretches(times, NOW)
        assert len(runs) == panels.MAX_STRETCHES
        assert runs[0][0] == 0 and runs[-1] == [9, 10, "Today"]

    def test_time_ago_words(self):
        assert panels.time_ago(NOW - 20, NOW) == "Just now"
        assert panels.time_ago(NOW - 60, NOW) == "1 minute ago"
        assert panels.time_ago(NOW - 5 * 3600, NOW) == "5 hours ago"
        assert panels.time_ago(NOW - 3 * 86400, NOW) == "3 days ago"
        assert panels.time_ago(NOW - 20 * 86400, NOW) == "2 weeks ago"
        assert panels.time_ago(NOW - 100 * 86400, NOW) == "3 months ago"
        assert panels.time_ago(None, NOW) == "Earlier"

    def test_merged_old_stretches_say_earlier(self):
        times = sorted([NOW - i * 86400 for i in range(10)])
        assert panels.stretches(times, NOW)[0][2] == "Earlier"

    def test_landmarks_are_the_start_each_session_end_and_extras(self):
        runs = panels.sessions([NOW - 86400] * 40 + [NOW - 30] * 6, NOW)
        assert panels.landmarks(runs, [17]) == [0, 17, 39, 45]

    def test_scrub_starts_slow_doubles_and_caps_at_one_session_crossing(self):
        assert panels.scrub_rate(0, 1000) == panels.SCRUB_SLOW
        assert panels.scrub_rate(panels.SCRUB_DOUBLE_S, 1000) == 2 * panels.SCRUB_SLOW
        assert panels.scrub_rate(60, 1000) == 1000 / panels.SCRUB_CROSS_S
        assert panels.scrub_rate(60, 2) == panels.SCRUB_SLOW

    def test_draws_any_history(self):
        async def scenario():
            app = make_app()
            for index, times in ((0, [NOW]), (3, [None] * 5 + [NOW - 86400 * 2, NOW - 100, NOW])):
                bar = panels.TimeTravelBar(SimpleNamespace(time_travel_position=lambda: (index, times, [1, index])))
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
        app = make_app(room="play")
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


def _two_sessions(monkeypatch, tmp_path, per=30):
    """An Art history of `per` steps yesterday then `per` today."""
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))
    clock = [NOW - 86400]
    monkeypatch.setattr(timeline_mod, "time", SimpleNamespace(time=lambda: clock[0]))
    tl = RoomTimeline("art")
    for i in range(2 * per):
        if i == per:
            clock[0] = NOW
        tl.record({f"c:{i},0": ["x", "#fff", None, 1]})
        clock[0] += timeline_mod.COARSE_PAUSE_S     # far enough apart that every step outlasts thinning
    return tl


def _held(app, monkeypatch, arrows):
    monkeypatch.setattr(app._keyboard_state_machine, "all_held_arrows", lambda: set(arrows))


def _tick_after(app, seconds):
    """Run one scrub tick as if the arrow had been held long and `seconds` passed since the last tick."""
    import time
    hold, now = app._time_travel["hold"], time.monotonic()
    hold["since"], hold["wait"], hold["last"] = now - 60, min(hold["wait"], now), now - seconds
    app._scrub_tick()


def test_holding_rewinds_and_rests_on_each_session_end(monkeypatch, tmp_path):
    _two_sessions(monkeypatch, tmp_path)

    async def scenario():
        app = make_app()
        app.action_switch_room("art")
        app._start_time_travel()
        _held(app, monkeypatch, {"left"})
        app._press_time_travel("left")
        assert app._time_travel["index"] == len(app._timelines["art"]) - 2   # the press itself is one step
        _tick_after(app, 1.0)
        assert app._time_travel["index"] == 29      # rests on how yesterday ended, not past it
        app._scrub_tick()
        assert app._time_travel["index"] == 29      # still resting
        _tick_after(app, 1.0)
        assert app._time_travel["index"] == 0       # the very start is a landmark too
        _held(app, monkeypatch, set())
        app._scrub_tick()
        assert app._time_travel["hold"] is None     # letting go stops right there
        app._cancel_time_travel()
    run(scenario())


def test_repeats_do_not_step_while_a_hold_drives(monkeypatch, tmp_path):
    _two_sessions(monkeypatch, tmp_path, per=3)

    async def scenario():
        app = make_app()
        app.action_switch_room("art")
        app._start_time_travel()
        await press(app, "left")
        for _ in range(3):
            await press(app, "left", is_repeat=True)
        assert app._time_travel["index"] == len(app._timelines["art"]) - 2
        await press(app, "up")
        assert app._time_travel["index"] == len(app._timelines["art"]) - 2
        app._cancel_time_travel()
    run(scenario())


def test_the_moment_before_a_clear_is_a_landmark(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = make_app()
        art, tl = _two_paints(app)
        before = len(tl) - 1
        app._start_fresh("art")
        app._start_time_travel()
        assert before in app._time_travel["landmarks"]
        app._cancel_time_travel()
    run(scenario())


def test_typing_keeps_the_moment_and_carries_on(monkeypatch, tmp_path):
    monkeypatch.setenv("PURPLE_TIMELINE_DIR", str(tmp_path))

    async def scenario():
        app = make_app()
        art, tl = _two_paints(app)
        left_at = len(tl) - 1
        app._start_time_travel()
        app._step_time_travel(-1)
        shown = dict(art._grid)
        await press(app, "a")
        assert app._time_travel is None
        assert (2, 1) not in art._grid                    # still the earlier picture,
        assert art._grid != shown                         # with the key's paint on it
        assert JUMP_TAG in tl.tags()[left_at + 1]          # where they left from is a landmark
    run(scenario())
