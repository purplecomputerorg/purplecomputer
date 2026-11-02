from purple_tui.canvas.harness import make_app, run, type_text


def test_music_shows_the_sticker_keyboard_and_pops_the_last_key():
    async def go():
        app = make_app()
        app.action_switch_room("music")
        assert app._legend_visible and app._legend_key is None
        await type_text(app, "a")
        assert app._legend_key == "a"
    run(go())


def test_the_popped_key_drops_back_after_a_moment(monkeypatch):
    import asyncio
    from purple_tui.canvas import app as app_mod
    monkeypatch.setattr(app_mod, "LEGEND_POP_S", 0.05)

    async def go():
        app = make_app()
        app.action_switch_room("music")
        await type_text(app, "a")
        assert app._legend_key == "a"
        await asyncio.sleep(0.15)
        assert app._legend_key is None
    run(go())


def test_space_in_abc_switches_letters_between_names_and_sounds(monkeypatch):
    from purple_tui.canvas.harness import press
    asked = []

    async def go():
        app = make_app(room="music")
        room = app.room
        monkeypatch.setattr(app, "_effective_volume", lambda: 1)
        monkeypatch.setattr(room.sounds, "letters", lambda sounds=False: asked.append(sounds) or {})
        await press(app, "tab")
        await press(app, "space")
        assert room.say_sounds and not room.show_labels
        assert room._space_chip(True)[1:3] == (("Names", "Sounds"), 1)
        room.play_letter("B")
        assert asked[-1] is True
        assert room.timeline_state()["sounds"] is True
        await press(app, "tab")
        await press(app, "space")
        assert room.show_labels and room.say_sounds
    run(go())


def test_every_letter_has_a_sound_clip():
    from purple_tui.canvas.sounds import core_sounds
    assert {p.stem for p in (core_sounds() / "letter-sounds").glob("*.wav")} == set("abcdefghijklmnopqrstuvwxyz")


def test_the_space_switch_keeps_one_width_in_sounds_and_letters():
    from purple_tui.canvas.ui import _hold_switch_widths

    async def go():
        app = make_app(room="music")
        sets = [app.room._header_chips("Marimba", letters) for letters in (False, True)]
        assert len({_hold_switch_widths(app.g, 30, chips, sets)[1][4] for chips in sets}) == 1
    run(go())
