from purplecomputer.harness import make_app, run, type_text


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
    from purplecomputer import app as app_mod
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
    from purplecomputer.harness import press
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
    from purplecomputer.sounds import core_sounds
    assert {p.stem for p in (core_sounds() / "letter-sounds").glob("*.wav")} == set("abcdefghijklmnopqrstuvwxyz")


def test_every_fun_key_has_a_silly_sound():
    from purplecomputer.sounds import core_sounds, find_sound
    assert all(find_sound(core_sounds() / "letters", n) for n in ("semicolon", "comma", "period", "slash"))



def test_switching_shows_one_toast_and_plays_a_sample(monkeypatch):
    from purplecomputer.harness import press
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
    from purplecomputer.rooms.music_room import note_name
    from purplecomputer.music_constants import FRIENDLY_KEY_NAMES
    scale = {name: [note_name(col, i) for col in range(7)] for i, name in enumerate(FRIENDLY_KEY_NAMES)}
    assert scale["B♭"] == ["B♭", "C", "D", "E♭", "F", "G", "A"]
    assert scale["F"] == ["F", "G", "A", "B♭", "C", "D", "E"]
    assert scale["D"] == ["D", "E", "F♯", "G", "A", "B", "C♯"]


def test_instruments_show_their_picture_a_packs_emoji_or_their_bases_picture(tmp_path, monkeypatch):
    import json
    from purplecomputer import content as content_mod
    from purplecomputer.rooms.music_room import instrument_icon
    from purplecomputer.constants import ICON_MUSIC
    from purplecomputer.content import ContentManager, is_word_picture
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
    from purplecomputer.harness import press
    from purplecomputer.rooms.music_room import FRIENDLY_KEY_NAMES
    from purplecomputer.constants import ICON_MUSIC

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
    from purplecomputer.rooms import music_room
    monkeypatch.setattr(music_room, "LETTERS_MASH_S", 0)
    app = make_app(room="music")
    app.room.letters_mode = True
    return app


def test_letters_that_spell_a_word_show_it_and_space_says_it(monkeypatch):
    from purplecomputer import tts
    from purplecomputer.harness import press
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
    from purplecomputer.content import get_content
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
    from purplecomputer.harness import press
    from purplecomputer.rooms import music_room

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
    from purplecomputer.content import ContentManager
    monkeypatch.setattr(ContentManager, "is_known_word", lambda self, w: True)

    async def go():
        app = _letters_room(monkeypatch)
        blocked = base64.b64decode("cG9vcA==").decode()
        await type_text(app, blocked)
        assert app.room.word != blocked
    run(go())


def test_music_words_are_known_and_every_one_is_spoken():
    import base64
    from purplecomputer.content import _music_words, get_content
    from purplecomputer.speech_filter import is_clean
    known = get_content().is_known_word
    assert all(known(w) for w in ("the", "go", "run", "cat", "blue", "hog", "judge", "spoonful", "classes"))
    assert not any(known(w) for w in ("thy", "ans", "ofs", base64.b64decode("bXVyZGVy").decode()))
    assert [w for w in _music_words() if not is_clean(w)] == []


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
    from purplecomputer.rooms.music_room import MODE_LETTERS

    async def go():
        room = _letters_room(monkeypatch).room
        seen = []
        monkeypatch.setattr(room, "_play_key", lambda key, mode, instrument=None: seen.append(room.word))
        room.loop.play([(k, MODE_LETTERS, i * 0.01) for i, k in enumerate("CATDOG")], 0.1)
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


def test_every_key_names_its_note_faintly_and_brighter_while_it_sounds(monkeypatch):
    async def go():
        app = make_app(room="music")
        inks = {}
        real = app.g.draw_text
        monkeypatch.setattr(app.g, "draw_text", lambda text, px, x, y, face="sans", color="#ffffff", *a, **k:
                            inks.setdefault(text, []).append(color) or real(text, px, x, y, face, color, *a, **k))
        app._draw()
        assert len(inks["♪ F"]) == 3, "R, F and V all play F"
        quiet = inks["♪ F"][1]
        await type_text(app, "f")
        inks.clear()
        app._draw()
        assert inks["♪ F"][1] != quiet and inks["♪ F"][0] == quiet, "only the F key that sounds lights up"
    run(go())


def test_only_a_phrase_rest_shows_on_the_song_as_a_space():
    from purplecomputer.rooms.music_room import ECHO_PAUSE_S

    async def go():
        room = make_app(room="music").room
        for key, at in (("Q", 0.0), ("W", 0.2), ("E", 1.2), ("R", 1.2 + ECHO_PAUSE_S)):
            room._tape_add(key, at)
        texts, _, rests, *_ = room._tape_parts()
        assert texts == ["C", "D", "E", "F"] and rests == [0, 0, 0, 1]
    run(go())


def test_backspace_erases_a_note_at_a_time_then_held_whole_phrases():
    from purplecomputer.keyboard import ControlAction
    from purplecomputer.rooms import music_room

    async def go():
        app = make_app(room="music")
        room = app.room
        for key, at in (("Q", 0.0), ("W", 0.1), ("E", 5.0), ("R", 5.1), ("T", 5.2)):
            room._tape_add(key, at)
        held = ControlAction(action="backspace", is_down=True, is_repeat=True)
        await room.handle(ControlAction(action="backspace", is_down=True))
        await room.handle(held)
        assert [k for k, *_ in room._tape] == ["Q", "W", "E", "R"], "key repeat doesn't race through the notes"
        room._erasing_since -= music_room.ERASE_MORE_S
        room._erased_at -= music_room.ERASE_EVERY_S[1]
        await room.handle(held)
        await room.handle(held)
        assert [k for k, *_ in room._tape] == ["Q", "W"], "the rest of its phrase goes at once, and only it"
        await room.handle(ControlAction(action="backspace", is_down=False))
        assert room._erasing_since is None
    run(go())


def test_backspace_in_letters_takes_a_letter_and_the_word_follows():
    from purplecomputer.keyboard import ControlAction

    async def go():
        room = make_app(room="music").room
        room.letters_mode = True
        for i, key in enumerate("CATS"):
            room._spell(key, i * 0.1)
        await room.handle(ControlAction(action="backspace", is_down=True))
        assert room._spelled == "cat" and room.word == "cat"
    run(go())


def test_space_plays_the_tape_back_without_touching_the_colors_the_save_or_the_tape(monkeypatch):
    from purplecomputer.harness import press
    from purplecomputer.rooms import music_room
    monkeypatch.setattr(music_room, "TUNE_GAP_MAX_S", 0.01)

    async def go():
        app = make_app(room="music")
        room = app.room
        played = []
        monkeypatch.setattr(room, "play_sound_with_instrument", lambda key, instrument, volume_scale=1.0: played.append(key))
        await type_text(app, "qwe")
        colors, tape = dict(room.color_state), list(room._tape)
        played.clear()
        await press(app, "space")
        await room._tape_task
        assert played == ["Q", "W", "E"]
        assert room.color_state == colors and room._tape == tape
        await press(app, "space")
        await press(app, "a")
        assert room._tape_task is None, "any other key stops it"
    run(go())


def test_the_letters_tape_underlines_the_word_dims_as_the_rest_grows_and_clears_with_it(monkeypatch):
    import asyncio
    import time
    from purplecomputer import palette as P
    from purplecomputer.gfx import rgb
    from purplecomputer.rooms import music_room

    async def go():
        room = make_app(room="music").room
        room.letters_mode = True
        now = time.monotonic()
        for i, key in enumerate("ZQCAT"):
            room._spell(key, now + i * 0.1)
        texts, *_, word_at = room._tape_parts()
        assert texts == list("ZQCAT") and room.word == "cat" and word_at == 2
        assert rgb(room._tape_ink()) == rgb(P.TEXT)
        room._active_at = now - music_room.TAPE_FADE[0] * music_room.WORD_REST_S - 0.1
        dimmer = room._tape_ink()
        room._active_at = now - music_room.TAPE_FADE[1] * music_room.WORD_REST_S - 0.1
        assert rgb(P.TEXT) != rgb(dimmer) != rgb(room._tape_ink())
        monkeypatch.setattr(music_room, "WORD_REST_S", 0.05)
        room._spell("S", time.monotonic())
        await asyncio.sleep(0.15)
        assert room._spelled == "" and room.word is None and room._tape_parts()[0] == []
    run(go())


def test_a_word_typed_since_the_last_rest_wins_but_a_slow_speller_still_gets_theirs():
    from purplecomputer.rooms.music_room import WORD_GAP_S

    async def go():
        room = make_app(room="music").room
        room.letters_mode = True
        for i, key in enumerate("T"):
            room._spell(key, float(i))
        for i, key in enumerate("HAT"):
            room._spell(key, 1 + WORD_GAP_S + i * 0.1)
        assert room.word == "hat", "the rest on the tape splits 'that'"
        room._forget_word()
        for i, key in enumerate("CAT"):
            room._spell(key, i * (WORD_GAP_S + 0.5))
        assert room.word == "cat", "nothing since the last rest is a word, so the word spans the rests"
    run(go())


def test_the_rest_clock_empties_a_step_a_second_until_the_letters_clear():
    import time
    from purplecomputer.rooms.music_room import REST_STEPS, WORD_REST_S
    tick = WORD_REST_S / REST_STEPS

    async def go():
        room = make_app(room="music").room
        room.letters_mode = True
        room._spell("A", time.monotonic())
        assert room._rest_left() == 1.0
        room._active_at = time.monotonic() - 2.5 * tick
        assert room._rest_left() == 1 - 2 / REST_STEPS
        room._active_at = time.monotonic() - WORD_REST_S
        assert room._rest_left() == 0
    run(go())


def test_the_hints_after_the_tape_hold_still_whatever_it_holds(monkeypatch):
    import time
    from purplecomputer.rooms import music_room

    async def go():
        app = make_app(room="music")
        room = app.room
        at = []
        real = music_room.draw_key_hint
        monkeypatch.setattr(music_room, "draw_key_hint", lambda g, text, px, x, y, *a, **k: at.append((text, x, y)) or real(g, text, px, x, y, *a, **k))

        def hints(tape=None, letters=None):
            room._tape, room.letters_mode = tape or [], letters is not None
            room._spelled, room._typed_at = letters or "", [time.monotonic()] * len(letters or "")
            at.clear()
            app._draw()
            return [h for h in at if "Backspace" in h[0]]

        notes = [hints([(k, "music", i * 0.1) for i, k in enumerate(keys)]) for keys in ("QQQ", "RYR", "PPP")]
        assert notes[0] and notes[0] == notes[1] == notes[2]
        assert hints(letters="iii") and hints(letters="iii") == hints(letters="www") == hints(letters="mmm")
    run(go())


def test_a_long_tape_shows_its_end_and_playback_scrolls_to_the_note_playing():
    async def go():
        room = make_app(room="music").room
        spans = [10] * 20
        assert room._tape_window(spans, 100, 10) == (11, 19), "its end, with … before it"
        room._tape_at = 3
        assert room._tape_window(spans, 100, 10) == (3, 10), "from the note playing, with … on both sides"
        room._tape_at = 15
        assert room._tape_window(spans, 100, 10) == (11, 19)
        assert room._tape_window([10] * 5, 100, 10) == (0, 4), "a tape that fits shows whole"
    run(go())


def test_letters_has_no_key_to_change():
    from purplecomputer.keyboard import NavigationAction

    async def go():
        app = make_app(room="music")
        room = app.room
        room.letters_mode = True
        root = room.root_index
        await room.handle(NavigationAction(direction="right"))
        assert room.root_index == root and room.arrow_hint() == ""
        room.letters_mode = False
        assert room.arrow_hint()
    run(go())


def test_letters_has_no_loop_and_a_hold_of_enter_is_a_tap():
    async def go():
        app = make_app(room="music")
        app._music_looping_enabled = True
        room = app.room
        room._tape_add("Q", 0.0)
        room.letters_mode = True
        room._spell("C", 0.0)
        sounds = room.say_sounds
        room._enter_hold_fired()
        assert room.loop.state == "idle" and room.say_sounds != sounds and "loop" not in room._hint_text()
        assert room.hold_progress() is None
    run(go())


def test_a_quiet_song_clears_but_never_while_it_plays_or_after_new_sound(monkeypatch):
    import asyncio
    from purplecomputer.rooms import music_room

    async def go():
        monkeypatch.setattr(music_room, "SONG_REST_S", 0.1)
        app = make_app(room="music")
        room = app.room
        await type_text(app, "qw")
        await asyncio.sleep(0.06)
        await type_text(app, "e")
        await asyncio.sleep(0.06)
        assert [k for k, *_ in room._tape] == ["Q", "W", "E"], "a new note starts the quiet over"
        app._music_looping_enabled = True
        room._loop_tune()
        await asyncio.sleep(0.2)
        assert room._tape, "a loop playing isn't quiet"
        room._stop_loop()
        await asyncio.sleep(0.2)
        assert room._tape == [] and "t:0" not in app._timelines["music"].tip()
    run(go())


def test_erasing_starts_the_letters_quiet_over():
    import time
    from purplecomputer.keyboard import ControlAction

    async def go():
        room = make_app(room="music").room
        room.letters_mode = True
        for key in "CATS":
            room._spell(key, time.monotonic())
        room._active_at -= 5
        await room.handle(ControlAction(action="backspace", is_down=True))
        assert room._rest_left() == 1.0
    run(go())
