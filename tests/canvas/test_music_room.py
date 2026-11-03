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


def test_enter_in_letters_switches_between_names_and_sounds(monkeypatch):
    from purple_tui.canvas.harness import press
    asked = []

    async def go():
        app = make_app(room="music")
        room = app.room
        monkeypatch.setattr(app, "_effective_volume", lambda: 1)
        monkeypatch.setattr(room.sounds, "letters", lambda sounds=False: asked.append(sounds) or {})
        instrument = room.instrument_index
        await press(app, "tab")
        await press(app, "enter")
        assert room.say_sounds and room.instrument_index == instrument
        room.play_letter("B")
        assert asked[-1] is True
        assert room.timeline_state()["sounds"] is True
        await press(app, "space")
        assert room.say_sounds
    run(go())


def test_letters_say_the_letter_without_an_instrument_under_it(monkeypatch):
    played = []

    async def go():
        app = make_app(room="music")
        room = app.room
        monkeypatch.setattr(room.sounds, "letters", lambda sounds=False: {"B": "clip"})
        monkeypatch.setattr(room, "play_letter", lambda key: played.append(("letter", key)))
        monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, i, scale=1.0: played.append(("note", key)))
        room._play_key("B", "letters")
        room._play_key("B", "music")
        assert played == [("letter", "B"), ("note", "B")]
    run(go())


def test_every_letter_has_a_sound_clip():
    from purple_tui.canvas.sounds import core_sounds
    assert {p.stem for p in (core_sounds() / "letter-sounds").glob("*.wav")} == set("abcdefghijklmnopqrstuvwxyz")


def test_every_fun_key_has_a_silly_sound():
    from purple_tui.canvas.sounds import core_sounds, find_sound
    assert all(find_sound(core_sounds() / "letters", n) for n in ("semicolon", "comma", "period", "slash"))



def test_switching_shows_one_toast_and_plays_a_sample(monkeypatch):
    from purple_tui.canvas.harness import press
    heard = []

    async def go():
        app = make_app(room="music")
        room = app.room
        monkeypatch.setattr(room, "play_letter", lambda key: heard.append("letter"))
        monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, i, scale=1.0: heard.append("note"))
        await press(app, "enter")
        await press(app, "enter")
        await press(app, "tab")
        await press(app, "enter")
        assert heard == ["note", "note", "letter", "letter"]
        assert [t.text.split()[-1] for t in app._toasts] == ["sounds"]
    run(go())


def test_note_names_use_flats_in_flat_keys():
    from purple_tui.canvas.rooms.music_room import note_name
    from purple_tui.music_constants import FRIENDLY_KEY_NAMES
    scale = {name: [note_name(col, i) for col in range(7)] for i, name in enumerate(FRIENDLY_KEY_NAMES)}
    assert scale["B♭"] == ["B♭", "C", "D", "E♭", "F", "G", "A"]
    assert scale["F"] == ["F", "G", "A", "B♭", "C", "D", "E"]
    assert scale["D"] == ["D", "E", "F♯", "G", "A", "B", "C♯"]


def test_instrument_initials_stay_short_and_tell_names_apart():
    from purple_tui.canvas.rooms.music_room import initials
    assert initials(["Marimba", "Ukulele", "Accordion", "Glockenspiel"]) == ["M", "U", "A", "G"]
    assert initials(["Marimba", "Ukulele", "Mom"]) == ["Ma", "U", "Mo"]


def test_arrows_toast_the_new_key_and_code_does_not():
    from purple_tui.canvas.harness import press
    from purple_tui.canvas.rooms.music_room import FRIENDLY_KEY_NAMES
    from purple_tui.constants import ICON_MUSIC

    async def go():
        app = make_app(room="music")
        room = app.room
        await press(app, "right")
        await press(app, "right")
        live = [t.text for t in app._toasts]
        assert live == [f"{ICON_MUSIC}  Key of {FRIENDLY_KEY_NAMES[room.root_index]}"]
        room.set_key(0)
        assert [t.text for t in app._toasts] == live
    run(go())
