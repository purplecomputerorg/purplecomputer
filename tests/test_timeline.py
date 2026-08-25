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
        assert parsed == {"d": {"b": 2}, "r": ["a"]}


# ---------------------------------------------------------------------------
# Time Travel bar dot track
# ---------------------------------------------------------------------------

from types import SimpleNamespace

from purple_tui import panels
from purple_tui.harness import make_app, run, type_text


class TestTimeTravelDots:
    def _markup(self, index, total):
        bar = panels.TimeTravelBar(SimpleNamespace(time_travel_position=lambda: (index, total)))
        return bar.dots_markup()

    def test_short_history_is_one_dot_per_step(self):
        markup = self._markup(2, 3)
        assert markup.count("●") == 3
        assert "○" not in markup
        assert "⋯" not in markup
        assert "forward" in markup and "back in time" in markup

    def test_each_step_back_clears_exactly_one_dot(self):
        total = panels.MAX_DOTS * 4
        for presses in range(1, 4):
            markup = self._markup(total - 1 - presses, total)
            assert markup.count("○") == presses

    def test_long_history_shows_more_marker(self):
        markup = self._markup(99, 100)
        assert markup.count("●") == panels.MAX_DOTS
        assert "⋯" in markup

    def test_window_slides_when_scrubbed_past_left_edge(self):
        markup = self._markup(10, 100)
        assert markup.count("●") == 1
        assert markup.count("⋯") == 2

    def test_endpoints_are_dimmed(self):
        assert "[dim]◀ back in time[/]" in self._markup(0, 5)
        assert "[dim]forward ▶[/]" in self._markup(4, 5)


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
