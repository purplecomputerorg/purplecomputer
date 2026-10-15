"""Tab in Play finishes a partial word, and otherwise turns `say` on or off for the line."""

import pytest

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.play_room import speech_marks, toggled_say


@pytest.mark.parametrize("text, marks", [
    ("cat", []),
    ("say cat", [(0, 3)]),
    ("talk to me!", [(0, 4), (10, 11)]),
    ("cat! dog!", [(3, 4), (8, 9)]),
    ("wow!!!", [(3, 6)]),
    ("I say hi", []),
])
def test_speech_marks_find_what_makes_a_line_talk(text, marks):
    assert speech_marks(text) == marks


@pytest.mark.parametrize("before, after", [
    (("cat", 3), ("say cat", 7)),
    (("", 0), ("say ", 4)),
    (("say cat", 7), ("cat", 3)),
    (("speak  cat!", 11), ("cat", 3)),
    (("cat! dog", 1), ("cat dog", 1)),
])
def test_tab_toggles_say(before, after):
    assert toggled_say(*before) == after


def test_tab_completes_first_then_adds_say():
    async def go():
        app = make_app()
        app.action_switch_room("play")
        room = app.rooms["play"]
        await type_text(app, "ele")
        await press(app, "tab")
        assert room.field.value == "elephant "
        await press(app, "tab")
        assert room.field.value == "say elephant " and room.history == []
    run(go())
