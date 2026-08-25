"""Every screen draws without raising, at a few sizes, after real key traffic."""

import pytest

from purple_tui.harness import make_app, press, run, type_text

SIZES = [(1024, 768), (1366, 768), (1440, 900)]


@pytest.mark.parametrize("size", SIZES)
def test_rooms_draw_after_typing(size):
    async def go():
        app = make_app(size)
        await type_text(app, "cat", enter=True)
        await type_text(app, "2 + 2", enter=True)
        await type_text(app, "red + blue", enter=True)
        await type_text(app, "5 x 5 ducks", enter=True)
        app._draw()
        app.action_switch_room("music")
        for ch in "asdf1":
            await press(app, ch)
        await press(app, "right")
        await press(app, "tab")
        app._draw()
        app.action_switch_room("art")
        await type_text(app, "qwerty")
        await press(app, "space")
        await press(app, "right")
        await press(app, "down")
        await press(app, "tab")
        await type_text(app, "hi")
        app._draw()
        assert app.g.surface.get_size() == size
    run(go())


def test_overlays_and_panels_draw():
    async def go():
        app = make_app()
        app._show_room_picker()
        app._draw()
        app.top.close(None)
        app.action_parent_menu()
        app._draw()
        from purple_tui.rooms.parent_menu import (ComputerNameScreen, DisplaySettingsScreen, InstallConfirmScreen,
                                                   LittlesModeScreen, ParentVolumeModal, PinEntry, TerminalScreen)
        from purple_tui.rooms.help_videos import HelpVideosScreen
        from purple_tui.rooms.sleep_screen import FirstBootPowerCycleScreen, LiveBootSplash, ShutdownConfirmScreen, SleepScreen
        from purple_tui.rooms.support_info import SupportInfoScreen
        for overlay in (LittlesModeScreen(app), ComputerNameScreen(app), InstallConfirmScreen(app), PinEntry(app),
                        ParentVolumeModal(app), DisplaySettingsScreen(app), HelpVideosScreen(app),
                        SupportInfoScreen(app), FirstBootPowerCycleScreen(app), LiveBootSplash(app),
                        ShutdownConfirmScreen(app), SleepScreen(app), TerminalScreen(app)):
            app.push(overlay)
            app._draw()
            overlay.close()
        app.top.close()
        app.action_switch_room("art")
        app.room.open_code_panel()
        await type_text(app, "red forward 5", enter=True)
        app._draw()
        app.room.close_code_panel()
        app._start_time_travel()
        app._draw()
        app._cancel_time_travel()
        app.action_switch_room("music")
        await press(app, "enter", hold=1.0)   # start recording
        await press(app, "a")
        app._draw()
        app.rooms["music"].stop_sound()
        app._draw()
    run(go())


def test_all_caps_uppercases_drawn_text():
    async def go():
        app = make_app()
        app.g.all_caps = True
        s = app.g.text("hello", 20)
        assert s.get_width() == app.g.text("HELLO", 20).get_width()
        app._draw()
    run(go())


def test_littles_mode_draws():
    async def go():
        app = make_app()
        for mode in ("music", "music_noscreen", "art", None):
            app._apply_littles_mode(mode)
            await press(app, "a")
            app._draw()
    run(go())
