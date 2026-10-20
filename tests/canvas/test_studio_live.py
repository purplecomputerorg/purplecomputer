"""Studio's live Purple (studio/src/live/live.py) takes the files that changed in a pack without
starting again unless its family rooms changed: words, sounds, pictures and colors show up in the
running app, and a file Studio dropped goes away."""

import importlib.util
import json
from pathlib import Path

import pytest

from purple_tui import palette as P
from purple_tui import settings
from purple_tui.canvas import theme
from purple_tui.canvas.harness import make_app, run
from purple_tui.music_constants import instruments
from tests.test_packs import make_pack

LIVE = Path(__file__).parents[2] / "studio" / "src" / "live" / "live.py"
ID = "the-tests-pack"


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
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

        assert live.setup("music", letters=True, instrument="kitchen")[:2] == ["music", False]
        music = app.rooms["music"]
        assert music.letters_mode
        assert instruments()[music.instrument_index][0].endswith("kitchen")

        room, menu, at = live.setup("art", picture={"ops": [[3, 2, "#ff0000"]], "letters": [[4, 2, "H", "#ffffff"]]})
        art = app.rooms["art"]
        assert (room, menu) == ("art", False) and art._paint_mode
        assert art._grid[(3, 2)][2] == "#ff0000" and art._grid[(4, 2)][0] == "H"
        assert all(0 <= v <= 1 for v in at)

        assert (await live.key("escape"))[1]
        assert live.setup("play")[:2] == ["play", False]
    run(go())


def test_the_familys_rooms_wait_in_the_esc_menu(live, tmp_path, monkeypatch):
    monkeypatch.setattr(live, "TRYING", tmp_path / "trying" / "content" / "rooms")
    say = 'from purple import *\n\ndef on_key(key):\n    say("{}")\n'

    async def go():
        live.install(ID, files(tmp_path / "pack") + [text("content/rooms/farm.py", say.format("moo"))])
        live._app = app = make_app()
        family = {"name": "zoo", "source": say.format("roar"), "pack": ID, "rooms": [["zoo", "old"], ["sea", say.format("splash")]]}
        live.setup("play", family=family)
        assert type(app.top).__name__ == "FamilyRoom" and app.top.room.path.read_text() == family["source"]
        await live.key("escape")
        await live.key("escape")
        assert [r.name for r in app.top.family] == ["farm", "zoo", "sea"]
        assert not live.install(ID, [text("content/emoji.json", {"zorb": "🦑"})], fresh=False)
    run(go())
