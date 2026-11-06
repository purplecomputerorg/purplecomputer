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


def test_instruments_show_their_picture_a_packs_emoji_or_their_bases_picture(tmp_path, monkeypatch):
    import json
    from purple_tui import content as content_mod
    from purple_tui.canvas.rooms.music_room import instrument_icon
    from purple_tui.constants import ICON_MUSIC
    from purple_tui.content import ContentManager, is_word_picture
    content = tmp_path / "family" / "content"
    (content / "instruments").mkdir(parents=True)
    (content.parent / "manifest.json").write_text(json.dumps({"id": "family", "name": "F", "version": "1.0.0", "type": "emoji"}))
    for name, spec in (("kazoo", {"base": "accordion", "icon": "🎺"}), ("harp", {"base": "ukulele"}), ("odd", {"base": "marimba", "icon": "no"})):
        (content / name).mkdir()
        (content / "instruments" / f"{name}.json").write_text(json.dumps({"name": name, "params": {}, **spec}))
    cm = ContentManager(packs_dir=tmp_path)
    cm.load_all()
    monkeypatch.setattr(content_mod, "_content", cm)
    marimba = instrument_icon("marimba")
    assert is_word_picture(marimba) and cm.word_pictures[marimba].stem == "marimba"
    assert instrument_icon("kazoo") == "🎺"
    assert instrument_icon("harp") == instrument_icon("ukulele") != marimba
    assert instrument_icon("odd") == ICON_MUSIC


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


def _letters_room(monkeypatch):
    from purple_tui.canvas.rooms import music_room
    monkeypatch.setattr(music_room, "LETTERS_MASH_S", 0)
    app = make_app(room="music")
    app.room.letters_mode = True
    return app


def test_letters_that_spell_a_word_show_it_and_space_says_it(monkeypatch):
    from purple_tui import tts
    from purple_tui.canvas.harness import press
    said = []
    monkeypatch.setattr(tts, "speak_many", lambda texts, **kw: said.append((texts, kw)) or True)

    async def go():
        app = _letters_room(monkeypatch)
        await type_text(app, "ca")
        assert app.room.word is None
        await type_text(app, "t")
        assert app.room.word == "cat"
        await press(app, "space")
        assert said == [(["cat"], {"family": False})]
        await type_text(app, "x")
        assert app.room.word is None
    run(go())


def test_a_familys_pack_word_spells_too(monkeypatch):
    from purple_tui.content import get_content
    monkeypatch.setitem(get_content().emojis, "zorb", "🐙")

    async def go():
        app = _letters_room(monkeypatch)
        await type_text(app, "zorb")
        assert app.room.word == "zorb"
    run(go())


def test_a_word_is_found_at_the_end_of_whatever_came_before(monkeypatch):
    async def go():
        app = _letters_room(monkeypatch)
        await type_text(app, "qzdog")
        assert app.room.word == "dog"
        await type_text(app, "cat")
        assert app.room.word == "cat"
        await type_text(app, "s")
        assert app.room.word == "cats"
        await type_text(app, "go")
        assert app.room.word is None
    run(go())


def test_a_two_letter_word_needs_a_rest_before_it(monkeypatch):
    async def go():
        app = _letters_room(monkeypatch)
        room = app.room
        await type_text(app, "go")
        assert room.word == "go"
        await type_text(app, "x")
        room._typed_at[-1] -= 2
        await type_text(app, "hi")
        assert room.word == "hi"
        await type_text(app, "xhi")
        assert room.word is None
    run(go())


def test_a_long_rest_or_a_mode_switch_starts_a_new_word(monkeypatch):
    from purple_tui.canvas.harness import press
    from purple_tui.canvas.rooms import music_room

    async def go():
        app = _letters_room(monkeypatch)
        await type_text(app, "the")
        assert app.room.word == "the"
        await press(app, "tab")
        assert app.room.word is None and app.room._spelled == ""
        await press(app, "tab")
        monkeypatch.setattr(music_room, "WORD_REST_S", 0)
        await type_text(app, "the")
        assert app.room.word is None
    run(go())


def test_a_blocked_word_is_never_shown(monkeypatch):
    import base64
    from purple_tui.content import ContentManager
    monkeypatch.setattr(ContentManager, "is_known_word", lambda self, w: True)

    async def go():
        app = _letters_room(monkeypatch)
        blocked = base64.b64decode("cG9vcA==").decode()
        await type_text(app, blocked)
        assert app.room.word != blocked
    run(go())


def test_short_everyday_words_are_known_and_clean():
    from purple_tui.content import get_content, is_real_word
    from purple_tui.speech_filter import is_clean
    assert all(get_content().is_known_word(w) for w in ("the", "go", "run", "cat", "blue", "jump"))
    short = [w for w in open("purple_tui/common_words.txt").read().split() if len(w) < 5 and is_real_word(w)]
    assert short and all(is_clean(w) for w in short)


def test_the_same_letter_over_and_over_fades_out_but_still_spells(monkeypatch):
    async def go():
        app = _letters_room(monkeypatch)
        room = app.room
        volumes = [room._letter_volume(k, i * 0.1) for i, k in enumerate("OOGGGGGGG")]
        assert volumes == [1, 1, 1, 1, 0.6, 0.35, 0.15, 0, 0]
        assert room._letter_volume("G", 2.0) == 1
        await type_text(app, "ccccccat")
        assert room.word == "cat"
    run(go())


def test_a_looping_word_shows_each_time_it_comes_around(monkeypatch):
    import asyncio
    from purple_tui.canvas.rooms.music_room import MODE_LETTERS

    async def go():
        room = _letters_room(monkeypatch).room
        seen = []
        monkeypatch.setattr(room, "next_color", lambda key: seen.append(room.word))
        room.loop.play([(k, MODE_LETTERS, i * 0.01, 0) for i, k in enumerate("CATDOG")], 0.1)
        room._start_loop_playback()
        await asyncio.sleep(0.08)
        room._stop_loop()
        assert seen[2] == "cat" and seen[5] == "dog"
    run(go())


def test_choosing_an_instrument_or_key_in_code_leaves_letters(monkeypatch):
    async def go():
        app = _letters_room(monkeypatch)
        played = []
        monkeypatch.setattr(app.room, "_play_key", lambda key, mode, instrument=None: played.append(mode))
        await app.room.run_code(["choose ukulele asd"])
        assert not app.room.letters_mode and played == ["music"] * 3
        app.room.letters_mode = True
        await app.room.run_code(["key g"])
        assert not app.room.letters_mode
    run(go())
