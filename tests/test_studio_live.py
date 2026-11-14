"""Studio's live Purple (studio/src/live/live.py) takes the files that changed in a pack without
starting again unless its family rooms changed: words, sounds, pictures and colors show up in the
running app, and a file Studio dropped goes away."""

import importlib.util
import json
from pathlib import Path

import pytest

from purplecomputer import content
from purplecomputer import palette as P
from purplecomputer import settings
from purplecomputer import theme
from purplecomputer.harness import make_app, run
from purplecomputer.rooms.art_room import shift_from
from purplecomputer.constants import OLD_ART_GRID
from purplecomputer.music_constants import instruments
from tests.test_packs import make_pack

LIVE = Path(__file__).parents[1] / "studio" / "src" / "live" / "live.py"
ID = "the-tests-pack"


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(content, "_content", None)
    spec = importlib.util.spec_from_file_location("studio_live", LIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    theme.apply({})


def files(root: Path) -> list:
    """A Studio-shaped pack as the (path, bytes) pairs Studio sends."""
    d = make_pack(root, ID)
    (d / "content" / "theme.json").write_text(json.dumps({"colors": {"bg": "#0d2233"}}))
    return [(str(p.relative_to(d)), p.read_bytes()) for p in sorted(d.rglob("*")) if p.is_file()]


def text(path: str, value) -> tuple:
    return path, (value if isinstance(value, str) else json.dumps(value)).encode()


def test_changed_files_reach_the_running_purple_and_rooms_start_it_again(live, tmp_path):
    async def go():
        assert live.install(ID, files(tmp_path / "pack"))  # no Purple yet: it starts
        live._app = app = make_app()
        assert P.BG == "#0d2233"
        app.rooms["music"].sounds._cache[("instrument", "kitchen")] = {"c4": "the old note"}

        assert not live.install(ID, [text("content/emoji.json", {"zorb": "🦑"})], ["content/theme.json"], fresh=False)
        app.rooms["art"]._dirty = set()
        live.refresh()
        assert app.rooms["art"]._dirty is None
        assert app.rooms["play"].evaluator.content.exact_emoji("zorb") == "🦑"
        assert P.BG == theme._DEFAULTS["roles"]["bg"]
        assert not app.rooms["music"].sounds._cache

        assert live.install(ID, [text("content/rooms/farm.py", 'from purple import *\n\ndef on_key(key):\n    say("moo")\n')], fresh=False)
    run(go())


def test_a_fresh_pack_replaces_the_last_one(live, tmp_path):
    live.install(ID, files(tmp_path / "pack"))
    live.install("another-pack", [text("manifest.json", {"id": "another-pack", "name": "Another", "version": "1.0.0", "type": "emoji"})])
    assert [p.name for p in live.PACKS.iterdir()] == ["another-pack"]


def test_each_page_sets_up_its_room_and_hears_where_purple_went(live, tmp_path):
    async def go():
        live.install(ID, files(tmp_path / "pack"))
        live._app = app = make_app()

        live.setup("music", letters=True, instrument="kitchen")
        assert live.place()["room"] == "music" and not live.place()["menu"]
        assert live.moved()["setup"] and live.moved() is None
        music = app.rooms["music"]
        assert music.letters_mode and live.place()["letters"] and not live.place()["looping"]
        music.loop.start_recording()
        assert live.place()["looping"]
        music._stop_loop()
        assert instruments()[music.instrument_index][0].endswith("kitchen")

        live.setup("art", picture={"ops": [[3, 2, "#ff0000"]], "letters": [[4, 2, "H", "#ffffff"]]})
        now = live.place()
        room, menu, code, at = now["room"], now["menu"], now["code"], now["at"]
        art = app.rooms["art"]
        assert (room, menu, code, now["letters"]) == ("art", False, False, False) and art._paint_mode
        dx, dy = shift_from(OLD_ART_GRID)
        assert art._grid[(3 + dx, 2 + dy)][2] == "#ff0000" and art._grid[(4 + dx, 2 + dy)][0] == "H"
        assert all(0 <= v <= 1 for v in at)
        assert live.moved()["setup"]

        await live.key("escape")
        assert live.place()["menu"]
        assert live.moved() == {**live.place(), "setup": False}
        # try.html's code key: the code line opens over the menu's place, and closes again.
        live.code(True)
        assert live.place()["code"] and not live.place()["menu"]
        live.code(False)
        assert not live.place()["code"]
        live.setup("play")
        assert live.place()["room"] == "play" and not live.place()["menu"]
    run(go())


def test_try_demos_start_in_the_mode_their_keys_are_for(live):
    async def go():
        live._app = app = make_app()
        live.setup("art")
        await live.key("tab")
        assert not app.rooms["art"]._paint_mode
        live.demo()
        assert app.rooms["art"]._paint_mode

        live.setup("music", letters=True)
        live.demo()
        assert not live.place()["letters"]

        live.setup("blocks")
        blocks = app.rooms["blocks"]
        blocks.turn_around()
        blocks._motion = None
        blocks._tilt(True)
        blocks._motion = None
        live.demo()
        assert not blocks._back and not blocks._peek
    run(go())


def test_the_familys_rooms_wait_in_the_esc_menu(live, tmp_path, monkeypatch):
    monkeypatch.setattr(live, "TRYING", tmp_path / "trying" / "content" / "rooms")
    say = 'from purple import *\n\ndef on_key(key):\n    say("{}")\n'

    async def go():
        live.install(ID, files(tmp_path / "pack") + [text("content/rooms/farm.py", say.format("moo"))])
        live._app = app = make_app()
        family = {"name": "zoo", "source": say.format("roar"), "icon": "", "pack": ID, "rooms": [["zoo", "old", ""], ["sea", say.format("splash"), ""]]}
        live.setup("play", family=family)
        assert type(app.top).__name__ == "FamilyRoom" and app.top.room.path.read_text() == family["source"]
        await live.key("escape")
        assert [r.name for r in app.top.family] == ["farm", "zoo", "sea"]
        assert not live.install(ID, [text("content/emoji.json", {"zorb": "🦑"})], fresh=False)
    run(go())


def test_a_room_partway_written_is_caught_before_it_runs(live):
    from purplecomputer.roomkit import purple
    names = [*purple.__all__, "on_key", "on_key_up"]
    for starter in (LIVE.parents[1] / "examples").glob("*.py"):
        assert live.check(starter.read_text(), names) is None, starter.name
    assert live.check('from purple import *\n\ndef on_key(key):\n    say(\n', names) == ["the ( needs its closing one", 4]
    assert live.check('from purple import *\nsa("hi")\n', names) == ["sa isn't a name Purple knows. Did you mean say?", 2]
    assert live.check('say("hi)\n', names)[0] == "the words need a closing quote"
    assert live.check('def on_key(key)\n    pass\n', names)[0] == "the line needs a : at the end"
    assert live.check('from random import *\nshuffle([1])\n', names) is None


def test_the_browser_speaks_with_purples_own_arguments():
    """browser.py replaces tts.speak_many; a call Purple makes with an argument it lacks would stop Purple."""
    import ast
    import inspect

    from purplecomputer import tts

    shim = ast.parse((LIVE.parent / "browser.py").read_text())
    ours = next(n for n in ast.walk(shim) if isinstance(n, ast.FunctionDef) and n.name == "speak_many")
    assert [a.arg for a in ours.args.args] == list(inspect.signature(tts.speak_many).parameters)
