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
