"""The parent menu's Voice row switches the speech engine and persists the choice."""

import asyncio
import os

os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from purple_tui import settings, tts
from purple_tui.constants import REQUIRED_TERMINAL_ROWS
from purple_tui.purple_tui import PurpleApp
from purple_tui.rooms.parent_menu import ParentMenu, ParentMenuItem, VoiceScreen

APP_SIZE = (146, REQUIRED_TERMINAL_ROWS)


async def _settle(pilot):
    await pilot.pause()
    await asyncio.sleep(0.3)
    await pilot.pause()


def test_voice_row_picks_quick(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(tts, "_voice_pref", None)
    monkeypatch.setattr(tts, "preload", lambda: None)

    async def run_test():
        app = PurpleApp()
        async with app.run_test(size=APP_SIZE) as pilot:
            await _settle(pilot)
            app.push_screen(ParentMenu())
            await _settle(pilot)
            parent = app.screen
            assert str(parent.query_one("#menu-voice", ParentMenuItem).render()) == "Voice: Natural"

            parent._open_voice()
            await _settle(pilot)
            assert isinstance(app.screen, VoiceScreen)
            app.screen.dismiss(tts.VOICE_QUICK)
            await _settle(pilot)

            assert settings.get_voice() == tts.VOICE_QUICK
            assert tts._engine() == tts.VOICE_QUICK
            assert str(parent.query_one("#menu-voice", ParentMenuItem).render()) == "Voice: Quick"

    asyncio.new_event_loop().run_until_complete(run_test())
