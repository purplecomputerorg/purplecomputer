"""Language packs: interface text looked up by its English when drawn, the second
language beside English words in Play, and pinyin picked with the number keys."""

import json
from pathlib import Path

import pytest

from purple_tui import content, i18n, settings, tts
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.rooms.parent_menu import LanguageScreen, SecondLanguageScreen
from purple_tui.canvas.rooms.play_room import echo_markup, pinyin_candidates
from purple_tui.canvas.ui import TextField
from purple_tui.pack_manager import check_pack


SPANISH_SPEECH = json.loads((Path(__file__).resolve().parents[2] / "packs/lang-es/content/language.json").read_text())["speech"]


def make_pack(root, code, strings=None, words=None, typing=None, voice=None, speech=None):
    pack = root / f"lang-{code}"
    (pack / "content").mkdir(parents=True)
    (pack / "manifest.json").write_text(json.dumps({"id": pack.name, "name": code, "version": "1.0.0", "type": "language"}))
    files = {"language.json": {"code": code, "name": code.upper(), "english_name": code, "voice": voice, "speech": speech or {}},
             "strings.json": strings or {}, "words.json": words or {}, "input.json": typing or {}}
    for name, data in files.items():
        (pack / "content" / name).write_text(json.dumps(data, ensure_ascii=False))
    return pack


@pytest.fixture
def langs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    for name, value in (("_memo", {}), ("_interface", None), ("_second", None), ("_loaded_choice", False)):
        monkeypatch.setattr(i18n, name, value)
    monkeypatch.setattr(content, "_content", None)
    es = make_pack(tmp_path, "es", strings={"Volume": "Volumen", "{0} blocks left": "quedan {0} bloques",
                                            "Hold {0} longer to {1}": "Mantén {0} para {1}", "Off": "No", "Save": "Guardar",
                                            "Clear a Room": "Borrar un cuarto",
                                            "Type": "Escribe"},
                   words={"dog": "perro", "red": "rojo", "mouse": "ratón", "potato": "papa"}, speech=SPANISH_SPEECH)
    zh = make_pack(tmp_path, "zh", words={"dog": ["狗", "gǒu"], "panda": ["熊猫", "xióng māo"]},
                   typing={"gou": ["够", "狗", "沟"], "ni": ["你", "呢"]})
    monkeypatch.setattr(i18n, "_languages", {"es": i18n.load_language(es), "zh": i18n.load_language(zh)})
    return tmp_path


def test_english_is_untouched(langs):
    assert i18n.translate("Volume") == "Volume"


@pytest.mark.parametrize("text, out", [
    ("Volume", "Volumen"),
    ("  Volume ", "  Volumen "),
    (" Volume", " Volumen"),
    ("● Off", "● No"),
    ("3 blocks left", "quedan 3 bloques"),
    ("Hold Space longer to Save", "Mantén Space para Guardar"),
    ("Something new", "Something new"),
])
def test_interface_text_is_looked_up_by_its_english(langs, text, out):
    i18n.set_languages("es", None)
    assert i18n.translate(text) == out


def test_a_template_needs_text_around_its_slots():
    assert i18n._template("{0}") is None and i18n._template("{0} {1}") is None
    assert i18n._template("{1} then {0}") is None
    assert i18n._template("{0} left").fullmatch("2 left")


def test_drawn_text_translates_but_typed_text_does_not(langs):
    i18n.set_languages("es", None)

    async def go():
        g = make_app().g
        assert g.measure("Volume", 20) == g.measure("Volumen", 20, tr=False)
        assert g.measure("Volume", 20, tr=False) != g.measure("Volumen", 20, tr=False)
        assert g.markup_size("Volume", 20) == g.markup_size("Volumen", 20, tr=False)
    run(go())


def test_typed_text_starts_after_a_translated_label(langs):
    i18n.set_languages("es", None)

    async def go():
        g = make_app().g
        assert TextField().text_x(g, 0, 30, gap=0) >= g.measure("Escribe →", 30, "mono-bold", tr=False)[0]
    run(go())


def test_chinese_wraps_between_characters(langs):
    async def go():
        g = make_app().g
        one = g.measure("狗", 20)[0]
        assert len(g.layout("狗狗狗狗狗狗", 20, max_width=one * 3 + one // 2)) == 2
    run(go())


def test_second_language_words_type_the_same_emoji(langs):
    i18n.set_languages("en", "es")
    c = content.get_content()
    assert c.exact_emoji("perro") == c.exact_emoji("dog")
    assert c.exact_emoji("perros") == c.exact_emoji("dog")
    assert c.exact_emoji("raton") == c.exact_emoji("mouse")
    assert c.exact_color("rojo") == c.exact_color("red")
    i18n.set_languages("en", "zh")
    assert c.exact_emoji("狗") == c.exact_emoji("gou") == c.exact_emoji("dog")
    assert c.exact_emoji("xiongmao") == c.exact_emoji("panda")
    assert c.exact_emoji("perro") is None


def test_echo_shows_the_second_language_beside_english(langs):
    assert echo_markup("3 dogs") == ("", "")
    i18n.set_languages("en", "es")
    dog = content.get_content().exact_emoji("dog")
    assert echo_markup("3 dogs + red") == (f"{dog} perro   [on {content.get_content().exact_color('red')}]   [/] rojo", "perro rojo")
    i18n.set_languages("en", "zh")
    assert echo_markup("dog dog") == (f"{dog} 狗 [dim]gǒu[/]", "狗")


def test_play_adds_the_echo_line_and_says_it_in_the_second_language(langs, monkeypatch):
    said = []
    monkeypatch.setattr(tts, "speak_many", lambda texts, **kw: said.append(texts) or True)
    i18n.set_languages("en", "es")

    async def go():
        app = make_app()
        app.action_switch_room("play")
        room = app.rooms["play"]
        await type_text(app, "say dog")
        await press(app, "enter")
        assert [e.markup for e in room.history][-1].endswith("perro")
        assert said[-1][-1] == ("perro", i18n.languages()["es"])
    run(go())


def test_the_interface_language_takes_over_a_word_it_shares_with_english(langs):
    c = content.get_content()
    i18n.set_languages("en", "es")
    assert c.exact_emoji("papa") == c.exact_emoji("dad")
    i18n.set_languages("es", None)
    assert c.exact_emoji("papa") == c.exact_emoji("potato")


def test_english_is_a_second_language_only_beside_another(langs):
    async def go():
        app = make_app()
        assert i18n.ENGLISH not in [o[0] for o in SecondLanguageScreen(app).options]
        i18n.set_languages("es", None)
        assert [o[0] for o in SecondLanguageScreen(app).options] == [None, i18n.ENGLISH, "zh"]
    run(go())
    i18n.set_languages("es", i18n.ENGLISH)
    dog = content.get_content().exact_emoji("dog")
    assert echo_markup("perros dog hola") == (f"{dog} dog", "dog")


def test_play_speaks_in_the_interface_language(langs, monkeypatch):
    said = []
    monkeypatch.setattr(tts, "speak_many", lambda texts, **kw: said.append(texts) or True)
    es = i18n.languages()["es"]
    monkeypatch.setattr(es, "voice", "es-voice")
    i18n.set_languages("es", i18n.ENGLISH)

    async def go():
        app = make_app()
        app.action_switch_room("play")
        await type_text(app, "say perro")
        await press(app, "enter")
        assert said[-1] == [("perro", es), ("dog", i18n.ENGLISH_LANGUAGE)]
    run(go())


@pytest.mark.parametrize("code, line, out", [
    ("es", "dog plus perro equals 2 dogs", "perro más perro es igual a 2 perros"),
    ("es", "what is 10 divided by 2 equals 5", "cuánto es 10 entre 2 es igual a 5"),
    ("es", "1 fish and 3 fish and 2 mice", "1 pez y 3 peces y 2 ratones"),
    ("es", "2 starfish", "2 estrellas de mar"),
    ("es", "hello papa", "hello papa"),
    ("zh", "dog plus 狗 equals 2 dogs", "狗 加 狗 等于 两只狗"),
    ("zh", "3 trees and 3 apples", "3棵树 和 3个苹果"),
])
def test_the_spoken_line_is_said_in_the_language(shipped, code, line, out):
    assert i18n.spoken(shipped[code], line) == out


def test_english_and_chinese_text_pick_their_own_voice(langs, monkeypatch):
    clips, engines = [], []
    monkeypatch.setattr(tts, "_ensure_mixer", lambda: True)
    monkeypatch.setattr(tts, "_get_voice_clip", lambda text: clips.append(text))
    monkeypatch.setattr(tts, "_get_cached", lambda text, engine: engines.append(engine) or "cached")
    monkeypatch.setattr(tts, "_play_clip", lambda path, *a: path == "cached")
    monkeypatch.setattr(tts, "find_voice_model", lambda model=None: "model")
    monkeypatch.setattr(i18n.languages()["zh"], "voice", "zh-voice")
    assert tts._speak_sync("dog", tts._speech_id, lang=i18n.ENGLISH_LANGUAGE)
    assert tts._speak_sync("狗", tts._speech_id, lang=i18n.languages()["es"])
    assert clips == ["dog"] and engines[-1] == tts._LANG_ENGINE + "zh-voice"


def test_number_keys_pick_the_character_for_typed_pinyin(langs):
    assert pinyin_candidates("gou", 3) == (3, [])
    i18n.set_languages("en", "zh")
    assert pinyin_candidates("i love gou", 10) == (7, ["狗", "够", "沟"])
    assert pinyin_candidates("gou", 1) == (1, [])

    async def go():
        app = make_app()
        app.action_switch_room("play")
        room = app.rooms["play"]
        await type_text(app, "3 gou")
        app._draw()
        await type_text(app, "1")
        assert room.field.value == "3 狗"
        await type_text(app, "2")
        assert room.field.value == "3 狗2"
    run(go())


def test_chinese_text_speaks_in_the_chinese_voice(langs):
    assert i18n.speech_language("hello") is None
    assert i18n.speech_language("你好").code == "zh"


def test_language_packs_pass_the_installer(langs, tmp_path):
    assert check_pack(tmp_path / "lang-es") == []
    bad = make_pack(tmp_path / "bad", "en")
    assert any("language.json" in p for p in check_pack(bad))


def test_a_later_pack_adds_to_the_same_language(langs, tmp_path):
    fix = i18n.load_language(make_pack(tmp_path / "family", "es", strings={"Volume": "Sonido", "Save": "Guardar"}))
    merged = i18n._merge(i18n.languages()["es"], fix)
    assert merged.strings["Volume"] == "Sonido" and merged.strings["Off"] == "No"
    assert merged.words["dog"] == ("perro", "")


def test_parent_menu_switches_languages(langs):
    async def go():
        app = make_app()
        app.action_parent_menu()
        menu = app.top
        assert ("menu-language", "Language: English") in menu.items
        menu._open_second_language()
        assert isinstance(app.top, SecondLanguageScreen)
        app.top.close("zh")
        assert settings.get_second_language() == "zh"
        assert ("menu-second-language", "Second Language: ZH") in menu.items
        menu._open_language()
        assert isinstance(app.top, LanguageScreen)
        app.top.close("es")
        assert i18n.interface_language().code == "es" and i18n.second_language().code == "zh"
        app._draw()
    run(go())


@pytest.mark.parametrize("code", ["es", "zh"])
def test_shipped_packs_load(code):
    lang = i18n.load_language(i18n.Path(__file__).resolve().parents[2] / "packs" / f"lang-{code}")
    assert lang and lang.code == code and lang.voice


@pytest.fixture
def shipped(monkeypatch):
    monkeypatch.setattr(i18n, "_languages", None)
    monkeypatch.setattr(i18n.Path, "home", lambda: i18n.Path("/nonexistent"))
    return i18n.languages()


def test_every_blocked_word_is_silent_alone(shipped):
    from purple_tui.speech_filter import filter_speech
    for lang in shipped.values():
        assert lang.blocked, lang.code
        for word in lang.blocked:
            assert filter_speech(word) == "", (lang.code, word.encode())
            assert filter_speech(word.upper()) == "", (lang.code, word.encode())


def test_blocked_words_are_scrubbed_from_a_sentence(shipped):
    from purple_tui.speech_filter import filter_speech
    word = sorted(w for w in shipped["es"].blocked if w.isascii())[0]
    assert filter_speech(f"the purple dragon {word} flies") == "the purple dragon flies"
    hanzi = sorted(w for w in shipped["zh"].blocked if i18n.has_cjk(w) and len(w) > 1)[0]
    assert filter_speech(f"我的熊猫{hanzi}在吃竹子") == "我的熊猫在吃竹子"


def test_every_play_word_can_still_be_said(shipped):
    from purple_tui.speech_filter import filter_speech
    for lang in shipped.values():
        for word, reading in lang.words.values():
            assert filter_speech(word) == word, (lang.code, word)
    assert filter_speech("computadora") == "computadora"
    assert filter_speech("操场很大") == "操场很大"


def test_bomb_is_gone():
    assert content.ContentManager().exact_emoji("bomb") is None
