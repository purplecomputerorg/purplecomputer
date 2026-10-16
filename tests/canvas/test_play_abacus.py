from purple_tui.canvas.harness import make_app, run, type_text
from purple_tui.canvas.rooms.play_room import PlayEvaluator, abacus_rows, answer_parts


def test_big_counts_become_an_abacus_part_and_small_ones_stay_text():
    e = PlayEvaluator()
    assert answer_parts(e.evaluate("321223 trex")) == ["= 321223 🦖", (321223, "🦖")]
    assert answer_parts(e.evaluate("600 + 600")) == ["= 1200", (1200, "●")]
    assert all(isinstance(p, str) for p in answer_parts(e.evaluate("2 + 3")))


def test_rods_run_from_the_biggest_place_down():
    assert [(name, d) for name, d, _ in abacus_rows(1203)] == [
        ("thousands", 1), ("hundreds", 2), ("tens", 0), ("ones", 3)]


def test_abacus_answer_draws_and_paper_prints_it():
    async def scenario():
        app = make_app(room="play")
        play = app.rooms["play"]
        await type_text(app, "321223 trex", enter=True)
        app._draw()
        assert play.paper(app.g, (800, 600)) is not None

    run(scenario())
