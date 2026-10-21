"""TextField recall hint: a typo correction outlives repaints."""

from purple_tui.canvas.ui import TextField


def test_correction_survives_repaints_until_next_edit():
    f = TextField()
    f.set_correction("greem", "green")
    assert f.recall_text() == "greem → green"
    assert f.recall_text() == "greem → green"
    f.insert("r")
    f.clear()
    assert f.recall_text() == "Enter to try again: green"
