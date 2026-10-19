"""Studio's live Purple (studio/src/live/live.py) takes a new pack without starting again unless
its family rooms changed: words, sounds, pictures and colors show up in the running app."""

import importlib.util
import json
from pathlib import Path

import pytest

from purple_tui import palette as P
from purple_tui import settings
from purple_tui.canvas import theme
from purple_tui.canvas.harness import make_app, run
from scripts.purplepack import build_pack
from tests.test_packs import make_pack

LIVE = Path(__file__).parents[2] / "studio" / "src" / "live" / "live.py"


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    spec = importlib.util.spec_from_file_location("studio_live", LIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    theme.apply({})


def pack(root: Path, emoji: str, bg: str, cow: str = "cow") -> str:
    d = make_pack(root)
    (d / "content" / "emoji.json").write_text(json.dumps({"zorb": emoji}))
    (d / "content" / "theme.json").write_text(json.dumps({"colors": {"bg": bg}}))
    (d / "content" / "rooms" / "farm.py").write_text(f'from purple import *\n\ndef on_key(key):\n    say("{cow}")\n')
    return str(build_pack(d))


def test_a_pack_without_room_changes_refreshes_the_running_purple(live, tmp_path):
    async def go():
        assert live.install(pack(tmp_path / "a", "🐙", "#0d2233"))  # no Purple yet: it starts
        live._app = app = make_app()
        app.rooms["music"].sounds._cache[("instrument", "kitchen")] = {"c4": "the old note"}
        assert not live.install(pack(tmp_path / "b", "🦑", "#10241a"))
        live.refresh()
        assert app.rooms["play"].evaluator.content.exact_emoji("zorb") == "🦑"
        assert P.BG == "#10241a"
        assert not app.rooms["music"].sounds._cache
        assert live.install(pack(tmp_path / "c", "🦑", "#10241a", cow="moo"))
    run(go())
