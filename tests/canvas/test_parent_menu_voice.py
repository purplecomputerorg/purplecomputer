"""The parent menu's Voice row switches the speech engine and persists the choice."""

from purple_tui import settings, tts
from purple_tui.canvas.harness import make_app, run
from purple_tui.canvas.rooms.parent_menu import VoiceScreen


def test_voice_row_picks_quick(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(tts, "_voice_pref", None)
    monkeypatch.setattr(tts, "preload", lambda: None)

    async def go():
        app = make_app()
        app.action_parent_menu()
        menu = app.top
        assert ("menu-voice", "Voice: Natural") in menu.items

        menu._open_voice()
        assert isinstance(app.top, VoiceScreen) and app.top.selected == 0
        app._draw()
        app.top.close(tts.VOICE_QUICK)

        assert settings.get_voice() == tts.VOICE_QUICK
        assert tts._engine() == tts.VOICE_QUICK
        assert ("menu-voice", "Voice: Quick") in menu.items
    run(go())
