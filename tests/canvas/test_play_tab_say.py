"""Tab in Play finishes a partial word, and otherwise says the line aloud."""

import purple_tui.tts as tts
from purple_tui.canvas.harness import make_app, press, run, type_text


def _play(monkeypatch):
    said = []
    monkeypatch.setattr(tts, "speak_many", lambda texts, **kw: said.append(texts) or True)
    app = make_app()
    app.action_switch_room("play")
    return app, app.rooms["play"], said


def test_tab_says_a_finished_line_without_submitting(monkeypatch):
    async def go():
        app, room, said = _play(monkeypatch)
        await type_text(app, "3+4")
        await press(app, "tab")
        assert said == [["3 plus 4 equals 7"]]
        assert room.field.value == "3 + 4" and room.history == []
    run(go())


def test_tab_completes_first_then_says(monkeypatch):
    async def go():
        app, room, said = _play(monkeypatch)
        await type_text(app, "ele")
        await press(app, "tab")
        assert room.field.value == "elephant " and said == []
        await press(app, "tab")
        assert said == [["elephant"]]
    run(go())


def test_tab_on_an_empty_line_replays_the_last_one(monkeypatch):
    async def go():
        app, room, said = _play(monkeypatch)
        await type_text(app, "repeat 2 cat")
        await press(app, "enter")
        await press(app, "tab")
        assert said == [["cat", "cat"]]
    run(go())
