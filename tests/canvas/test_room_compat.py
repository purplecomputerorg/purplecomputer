"""Rooms Studio makes must keep running on Purples already out there. Each room here runs on a
Purple's host with a room library shipped beside it in the pack, as Studio ships it. By default
that's this checkout's host and library; scripts/room_compat.sh runs this same file inside an
older release with this checkout's library and rooms (PURPLE_ROOM_LIB, PURPLE_ROOM_CORPUS)."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from purple_tui import content as content_mod
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.content import ContentManager

HERE = Path(__file__).resolve().parents[2]
LIB = Path(os.environ.get("PURPLE_ROOM_LIB", HERE / "purple_tui" / "roomkit" / "purple.py"))
CORPUS = [Path(p) for p in os.environ.get("PURPLE_ROOM_CORPUS", f"{HERE / 'tests' / 'rooms'}:{HERE / 'studio' / 'src' / 'examples'}").split(":")]
ROOMS = sorted(p for d in CORPUS for p in d.glob("*.py"))


@pytest.mark.parametrize("source", ROOMS, ids=lambda p: p.stem)
def test_room_runs_on_this_purple(source, tmp_path, monkeypatch):
    rooms = tmp_path / "packs" / "compat" / "content" / "rooms"
    rooms.mkdir(parents=True)
    (rooms.parents[1] / "manifest.json").write_text(json.dumps({"id": "compat", "name": "C", "version": "1.0.0", "type": "emoji"}))
    (rooms / "purple.py").write_text(LIB.read_text())
    (rooms / "room.py").write_text(source.read_text())
    monkeypatch.setenv("PURPLE_ROOMS_DIR", str(tmp_path / "kept"))
    cm = ContentManager(packs_dir=tmp_path / "packs")
    cm.load_all()
    monkeypatch.setattr(content_mod, "_content", cm)

    async def go():
        app = make_app()
        app.open_family_room("room")
        room = app.top
        for _ in range(250):
            if room.scene or room.fault:
                break
            await asyncio.sleep(0.02)
        for key in ["t", "space", "r", "e", "x", "enter", "down", "a"]:
            await press(app, key)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.5)
        app._draw()
        assert room.fault is None and room.scene
        room.close()
    run(go())
