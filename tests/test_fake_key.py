"""Dev and debug builds can send hardware keys a VM drops from the Parent Menu."""
import asyncio

import pytest

from purplecomputer import settings
from purplecomputer.harness import make_app, press, run
from purplecomputer.rooms.parent_menu import ParentMenu


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")


def test_press_a_key_closes_the_menu_then_sends_volume_up():
    async def go():
        app = make_app()
        before = app.volume_level
        menu = ParentMenu(app)
        app.push(menu)
        assert "menu-fake-key" in dict(menu.items)
        menu._open_fake_key()
        await press(app, "enter")  # Volume Up
        assert app.top is None
        await asyncio.sleep(0.5)
        assert app.volume_level > before
    run(go())
