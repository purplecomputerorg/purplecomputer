"""The parent menu's Features row turns Code Space and Music Looping on and off in one list."""

from purple_tui import settings
from purple_tui.canvas.harness import make_app, press, run
from purple_tui.canvas.rooms.parent_menu import FeaturesScreen


def test_features_toggle_in_place(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")

    async def go():
        app = make_app()
        app.action_parent_menu()
        menu = app.top
        assert ("menu-features", "Features: Code Yes, Looping Yes") in menu.items
        menu.selected = [i for i, _ in menu.items].index("menu-features")
        await press(app, "enter")
        screen = app.top
        assert isinstance(screen, FeaturesScreen)
        app._draw()
        await press(app, "down")
        await press(app, "enter")
        assert app.top is screen and screen.options[1][1] == "Music Looping: No"
        assert not settings.get_music_looping() and not app._music_looping_enabled
        await press(app, "escape")
        assert ("menu-features", "Features: Code Yes, Looping No") in menu.items
    run(go())
