from purple_tui.canvas.ui import HintRotator, TextField


def test_trace_shows_the_rest_only_while_the_text_starts_the_idea():
    f = TextField()
    assert f.trace_rest(("cat", "trex!")) == ""
    f.set("TR")
    assert f.trace_rest(("cat", "trex!")) == "ex!"
    f.set("tra")
    assert f.trace_rest(("cat", "trex!")) == ""
    f.set("tr")
    f.move(-1)
    assert f.trace_rest(("cat", "trex!")) == ""


def test_held_idea_does_not_rotate_mid_typing():
    h = HintRotator([("cat",), ("trex!",)])
    h._stamp -= HintRotator.CYCLE_SECONDS + 1
    assert h.current(hold=True) == ("cat",)
    assert h.current() == ("trex!",)
