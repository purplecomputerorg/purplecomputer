"""Parent Menu's Purple Packs list: each installed pack, removable."""

import json

from purple_tui import pack_manager, settings
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.rooms.parent_menu import PurplePacksScreen, _get_menu_items


def test_a_parent_removes_a_purple_pack_and_it_is_gone_at_once(tmp_path, monkeypatch):
    packs = tmp_path / "packs"
    d = packs / "pack-1a2b3c4d"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"id": "pack-1a2b3c4d", "name": "Grandma's Pack", "version": "1.0.0", "type": "emoji"}))
    monkeypatch.setattr(pack_manager, "get_installer", lambda: pack_manager.PackInstaller(packs))
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    settings.set_pack_added("pack-1a2b3c4d", "abc")

    async def go():
        app = make_app()
        assert ("menu-purple-packs", "Purple Packs: 1") in _get_menu_items(app)
        screen = PurplePacksScreen(app)
        app.push(screen)
        assert [o[1] for o in screen.options] == ["Grandma's Pack", "Done"]
        app._draw()
        await press(app, "enter")
        await press(app, "up")
        await press(app, "enter")
        assert not d.exists()
        assert [o[1] for o in screen.options] == ["Done"]
        assert settings.get_packs_added() == {}
        assert "menu-purple-packs" not in dict(_get_menu_items(app))
    run(go())
