"""Tests for the first-installed-boot power cycle offer.

The offer must only fire for the warm-reboot codec wedge: audio that worked
in the live session but has no sound card now. Machines that never had sound
(CS8409 Macs, missing firmware) must never see it.
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Set environment before app imports
os.environ['PURPLE_NO_EVDEV'] = '1'
os.environ['PURPLE_DEV_MODE'] = '1'
os.environ['PURPLE_NO_AUDIO'] = '1'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('ORT_LOGGING_LEVEL', '3')

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.rooms.sleep_screen import first_boot_power_cycle_needed


def _gate(audio_ok, *, live=False, marker=None, reason="no-card"):
    with patch("purple_tui.rooms.sleep_screen.is_live_boot", return_value=live), \
         patch("purple_tui.rooms.sleep_screen.LIVE_AUDIO_MARKER",
               str(marker) if marker else "/nonexistent/marker"), \
         patch("purple_tui.mixer._silence_reason", return_value=reason):
        return first_boot_power_cycle_needed(audio_ok)


class TestFirstBootPowerCycleGate:

    def test_offers_when_worked_in_live_but_no_card_now(self, tmp_path):
        marker = tmp_path / "audio-worked-in-live"
        marker.touch()
        assert _gate(False, marker=marker) is True

    def test_no_offer_while_probing_or_working(self, tmp_path):
        marker = tmp_path / "audio-worked-in-live"
        marker.touch()
        assert _gate(None, marker=marker) is False
        assert _gate(True, marker=marker) is False

    def test_no_offer_without_marker(self):
        assert _gate(False, marker=None) is False

    def test_no_offer_on_live_boot(self, tmp_path):
        marker = tmp_path / "audio-worked-in-live"
        marker.touch()
        assert _gate(False, live=True, marker=marker) is False

    def test_no_offer_for_known_silent_codec(self, tmp_path):
        """A CS8409 Mac with a USB speaker in live boot writes the marker,
        but a power cycle won't help its internal codec."""
        marker = tmp_path / "audio-worked-in-live"
        marker.touch()
        assert _gate(False, marker=marker, reason="silent-codec") is False

    def test_no_offer_when_card_present_but_mixer_broken(self, tmp_path):
        marker = tmp_path / "audio-worked-in-live"
        marker.touch()
        assert _gate(False, marker=marker, reason=None) is False


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _app_check(tmp_path, audio_ok, reason="no-card"):
    """Run _check_first_boot_audio in a live app. Returns (screen_shown, marker_exists)."""
    from purple_tui.purple_tui import PurpleApp
    from purple_tui.constants import REQUIRED_TERMINAL_ROWS
    from purple_tui.rooms.sleep_screen import FirstBootPowerCycleScreen

    marker = tmp_path / "audio-worked-in-live"
    marker.touch()

    async def _test():
        app = PurpleApp()
        with patch("purple_tui.constants.LIVE_AUDIO_MARKER", str(marker)), \
             patch("purple_tui.rooms.sleep_screen.LIVE_AUDIO_MARKER", str(marker)), \
             patch("purple_tui.rooms.sleep_screen.is_live_boot", return_value=False), \
             patch("purple_tui.mixer._silence_reason", return_value=reason):
            async with app.run_test(size=(146, REQUIRED_TERMINAL_ROWS)) as pilot:
                await pilot.pause()
                app.audio_ok = audio_ok
                app._check_first_boot_audio()
                await pilot.pause()
                shown = isinstance(app.screen, FirstBootPowerCycleScreen)
                return shown, marker.exists()

    return _run(_test())


class TestFirstBootAppFlow:
    """Marker consumption: the offer happens at most once, ever."""

    def test_wedge_shows_screen_and_consumes_marker(self, tmp_path):
        shown, marker_left = _app_check(tmp_path, audio_ok=False)
        assert shown and not marker_left

    def test_working_audio_consumes_marker_silently(self, tmp_path):
        shown, marker_left = _app_check(tmp_path, audio_ok=True)
        assert not shown and not marker_left

    def test_still_probing_keeps_marker_for_recheck(self, tmp_path):
        shown, marker_left = _app_check(tmp_path, audio_ok=None)
        assert not shown and marker_left

    def test_undiagnosed_failure_keeps_marker_for_next_boot(self, tmp_path):
        shown, marker_left = _app_check(tmp_path, audio_ok=False, reason=None)
        assert not shown and marker_left

    def test_evdev_enter_powers_off(self, tmp_path):
        """The evdev path (real hardware) must power off on ENTER too."""
        from purple_tui.purple_tui import PurpleApp
        from purple_tui.constants import REQUIRED_TERMINAL_ROWS
        from purple_tui.keyboard import ControlAction
        from purple_tui.rooms.sleep_screen import (ByeScreen,
                                                   FirstBootPowerCycleScreen)

        async def _test():
            app = PurpleApp()
            async with app.run_test(size=(146, REQUIRED_TERMINAL_ROWS)) as pilot:
                await pilot.pause()
                app.push_screen(FirstBootPowerCycleScreen())
                await pilot.pause()
                with patch("purple_tui.power_manager.PowerManager.shutdown",
                           return_value=True) as shutdown:
                    await app.screen.handle_keyboard_action(
                        ControlAction(action='enter', is_down=True))
                    await pilot.pause()
                    assert isinstance(app.screen, ByeScreen)
                    assert shutdown.called

        _run(_test())
