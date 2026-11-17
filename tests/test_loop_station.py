"""The loop station plays a phrase over and over; notes played along join it."""

import pytest

from purplecomputer.loop_station import IDLE, LOOPING, MAX_LOOP_DURATION, LoopStation
from purplecomputer.rooms.music_room import MODE_LETTERS, MODE_MUSIC


def _looping(now=2.0, duration=2.0):
    """A loop of A half a second in, two seconds long, its cycle starting at `now`."""
    loop = LoopStation()
    loop.play([("A", MODE_MUSIC, 0.5, 0)], duration, now=now)
    return loop


def test_play_loops_and_stop_goes_back_to_idle():
    loop = LoopStation()
    assert loop.state == IDLE
    loop.play([("B", MODE_MUSIC, 1.0, 0), ("A", MODE_MUSIC, 0.2, 0)], 2.0, now=0.0)
    assert loop.state == LOOPING and [e[0] for e in loop.loop_events] == ["A", "B"]
    loop.stop()
    assert loop.state == IDLE and loop.loop_events == [] and loop.loop_duration == 0.0


def test_a_note_while_idle_is_ignored():
    loop = LoopStation()
    loop.record_event("A", MODE_MUSIC, now=1.0)
    assert loop.loop_events == []


def test_a_note_played_along_joins_where_it_falls_in_the_cycle():
    loop = _looping()
    loop.record_event("B", MODE_LETTERS, now=2.3, instrument=2)
    assert [e[0] for e in loop.loop_events] == ["B", "A"]
    assert loop.loop_events[0] == pytest.approx(("B", MODE_LETTERS, 0.3, 2))
    assert loop.loop_duration == 2.0


def test_a_note_past_the_cycle_wraps_around():
    loop = _looping()
    loop.record_event("B", MODE_MUSIC, now=4.5)
    assert [e[2] for e in loop.loop_events if e[0] == "B"] == [pytest.approx(0.5)]


def test_a_new_cycle_moves_where_notes_land():
    loop = _looping()
    loop.start_new_cycle(now=4.0)
    loop.record_event("B", MODE_MUSIC, now=4.3)
    assert [e[2] for e in loop.loop_events if e[0] == "B"] == [pytest.approx(0.3)]


def test_progress_runs_through_each_cycle():
    loop = _looping()
    assert LoopStation().loop_progress() == 0.0
    assert loop.loop_progress(now=2.0) == pytest.approx(0.0)
    assert loop.loop_progress(now=3.0) == pytest.approx(0.5)
    assert loop.loop_progress(now=7.0) == pytest.approx(0.5)


def test_loop_events_is_a_copy_and_max_duration_has_a_default():
    loop = _looping()
    loop.loop_events.clear()
    assert len(loop.loop_events) == 1
    assert LoopStation().max_duration == MAX_LOOP_DURATION
    assert LoopStation(max_duration=15.0).max_duration == 15.0


def test_opening_code_while_looping_stops_the_loop():
    from purplecomputer.harness import make_app, run
    from purplecomputer.panels import CodePanel

    async def _test():
        app = make_app()
        app._code_panel_enabled = True
        app.action_switch_room("music")
        music = app.rooms["music"]
        music._tape_add("A", 0.0)
        music._loop_tune()
        assert music.loop.state == LOOPING
        music.open_code_panel()
        assert music.loop.state == IDLE
        assert isinstance(app._panel, CodePanel)
    run(_test())


def test_the_loop_panel_keeps_the_grid_size():
    from purplecomputer.harness import make_app, run

    async def _test():
        app = make_app()
        app.action_switch_room("music")
        music = app.rooms["music"]
        grids = []
        music._draw_grid = lambda g, r, on_paper=False: grids.append(r)
        app._draw()
        music._tape_add("A", 0.0)
        music._loop_tune()
        app._draw()
        assert grids[0] == grids[1]
        music._stop_loop()
    run(_test())
