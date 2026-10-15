from purple_tui.canvas.ui import HintRotator, TextField


def test_traced_idea_only_while_the_text_starts_it():
    f = TextField()
    assert f.traced(("cat", "trex!")) == ""
    f.set("TR")
    assert f.traced(("cat", "trex!")) == "trex!"
    f.set("tra")
    assert f.traced(("cat", "trex!")) == ""
    f.set("tr")
    f.move(-1)
    assert f.traced(("cat", "trex!")) == ""


def test_held_idea_does_not_rotate_mid_typing():
    h = HintRotator([("cat",), ("trex!",)])
    h._stamp -= HintRotator.CYCLE_SECONDS + 1
    assert h.current(hold=True) == ("cat",)
    assert h.current() == ("trex!",)
