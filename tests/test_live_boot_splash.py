"""The USB welcome screen tells the parent a chime is coming while the sound check runs."""

import asyncio

from textual.app import App
from textual.widgets import Static

from purple_tui.rooms.sleep_screen import LiveBootSplash


class Host(App):
    audio_ok = None
    _sound_check_running = True


def test_splash_mentions_the_chime_only_while_the_check_runs():
    asyncio.run(_run())


async def _run():
    app = Host()
    async with app.run_test() as pilot:
        app.push_screen(LiveBootSplash())
        await pilot.pause()
        note = app.screen.query_one("#splash-sound-check", Static)
        assert "Listen for a chime" in str(note.render())
        app._sound_check_running = False
        await pilot.pause(0.4)
        assert str(note.render()) == ""
