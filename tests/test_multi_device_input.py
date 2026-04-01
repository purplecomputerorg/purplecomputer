#!/usr/bin/env python3
"""Tests for multi-device keyboard and power button input handling.

Verifies that EvdevReader and PowerButtonReader correctly handle
multiple input devices. This is critical because laptops often expose
the same physical keyboard or power button as multiple evdev devices,
and which one delivers events varies by hardware and USB state.

Run with: pytest tests/test_multi_device_input.py -v
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from purple_tui.input import (
    EvdevReader,
    KeyCode,
    PowerButtonReader,
    PowerButtonEvent,
    RawKeyEvent,
)


# =============================================================================
# Fake evdev objects for testing without real /dev/input devices
# =============================================================================

EV_KEY = 1
EV_REP = 0x14
EV_MSC = 4
MSC_SCAN = 4


@dataclass
class FakeEvent:
    """Mimics an evdev InputEvent."""
    type: int
    code: int
    value: int
    _timestamp: float = 0.0

    def timestamp(self):
        return self._timestamp


class FakeInputDevice:
    """Mimics evdev.InputDevice for testing."""

    def __init__(self, path: str, name: str = "Fake Device",
                 key_caps: Optional[set] = None,
                 has_ev_rep: bool = True):
        self.path = path
        self.name = name
        self._key_caps = key_caps or set()
        self._has_ev_rep = has_ev_rep
        self._events: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._grabbed = False
        self.fd = id(self)

    def capabilities(self):
        caps = {}
        if self._key_caps:
            caps[EV_KEY] = list(self._key_caps)
        if self._has_ev_rep:
            caps[EV_REP] = [0, 1]
        return caps

    def grab(self):
        if self._grabbed:
            raise IOError("Already grabbed")
        self._grabbed = True

    def ungrab(self):
        self._grabbed = False

    def close(self):
        self._closed = True
        self._events.put_nowait(None)

    def read_one(self):
        return None

    async def async_read_loop(self):
        while not self._closed:
            event = await self._events.get()
            if event is None:
                break
            yield event

    def inject_event(self, event: FakeEvent):
        if not self._closed:
            self._events.put_nowait(event)


def _full_keyboard_caps():
    """Key capabilities of a real keyboard."""
    caps = set(range(KeyCode.KEY_A, KeyCode.KEY_Z + 1))
    caps |= {KeyCode.KEY_ENTER, KeyCode.KEY_SPACE, KeyCode.KEY_LEFTSHIFT}
    caps |= set(range(KeyCode.KEY_1, KeyCode.KEY_0 + 1))
    caps |= {KeyCode.KEY_ESC, KeyCode.KEY_BACKSPACE, KeyCode.KEY_TAB}
    return caps


class AsyncCallback:
    """Async callable that records calls."""
    def __init__(self):
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append(args[0] if args else None)


def _run(coro):
    """Run an async function in a new event loop."""
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# =============================================================================
# Multi-Device Lifecycle Tests
# =============================================================================

class TestMultiDeviceLifecycle:
    """Test start/stop/grab with multiple keyboard devices."""

    def test_start_grabs_all_devices(self):
        async def _test():
            kbd1 = FakeInputDevice("/dev/input/event0", "KB1", _full_keyboard_caps())
            kbd2 = FakeInputDevice("/dev/input/event1", "KB2", _full_keyboard_caps())

            reader = EvdevReader(callback=AsyncCallback(), grab=True)
            with patch.object(reader, '_find_keyboards', return_value=[kbd1, kbd2]):
                await reader.start()

            assert kbd1._grabbed
            assert kbd2._grabbed
            assert len(reader._tasks) == 2
            assert len(reader._devices) == 2
            await reader.stop()

        _run(_test())

    def test_stop_ungrabs_and_closes_all(self):
        async def _test():
            kbd1 = FakeInputDevice("/dev/input/event0", "KB1", _full_keyboard_caps())
            kbd2 = FakeInputDevice("/dev/input/event1", "KB2", _full_keyboard_caps())

            reader = EvdevReader(callback=AsyncCallback(), grab=True)
            with patch.object(reader, '_find_keyboards', return_value=[kbd1, kbd2]):
                await reader.start()
            await reader.stop()

            assert kbd1._closed
            assert kbd2._closed
            assert not kbd1._grabbed
            assert not kbd2._grabbed
            assert reader._tasks == []
            assert reader._devices == []

        _run(_test())

    def test_release_and_reacquire_all_grabs(self):
        async def _test():
            kbd1 = FakeInputDevice("/dev/input/event0", "KB1", _full_keyboard_caps())
            kbd2 = FakeInputDevice("/dev/input/event1", "KB2", _full_keyboard_caps())

            reader = EvdevReader(callback=AsyncCallback(), grab=True)
            with patch.object(reader, '_find_keyboards', return_value=[kbd1, kbd2]):
                await reader.start()

            assert kbd1._grabbed and kbd2._grabbed

            reader.release_grab()
            assert not kbd1._grabbed and not kbd2._grabbed

            reader.reacquire_grab()
            assert kbd1._grabbed and kbd2._grabbed

            await reader.stop()

        _run(_test())

    def test_start_raises_when_no_keyboards(self):
        async def _test():
            reader = EvdevReader(callback=AsyncCallback())
            with patch.object(reader, '_find_keyboards', return_value=[]):
                with pytest.raises(RuntimeError, match="Could not find your keyboard"):
                    await reader.start()

        _run(_test())

    def test_no_grab_mode(self):
        async def _test():
            kbd = FakeInputDevice("/dev/input/event0", "KB", _full_keyboard_caps())
            reader = EvdevReader(callback=AsyncCallback(), grab=False)
            with patch.object(reader, '_find_keyboards', return_value=[kbd]):
                await reader.start()
            assert not kbd._grabbed
            await reader.stop()

        _run(_test())

    def test_single_device_still_works(self):
        """Most common case: one keyboard."""
        async def _test():
            kbd = FakeInputDevice("/dev/input/event0", "KB", _full_keyboard_caps())
            reader = EvdevReader(callback=AsyncCallback(), grab=True)
            with patch.object(reader, '_find_keyboards', return_value=[kbd]):
                await reader.start()
            assert len(reader._devices) == 1
            assert len(reader._tasks) == 1
            assert kbd._grabbed
            await reader.stop()

        _run(_test())

    def test_three_keyboards(self):
        """Edge case: three keyboard devices."""
        async def _test():
            kbds = [
                FakeInputDevice(f"/dev/input/event{i}", f"KB{i}", _full_keyboard_caps())
                for i in range(3)
            ]
            reader = EvdevReader(callback=AsyncCallback(), grab=True)
            with patch.object(reader, '_find_keyboards', return_value=kbds):
                await reader.start()
            assert len(reader._devices) == 3
            assert len(reader._tasks) == 3
            assert all(k._grabbed for k in kbds)
            await reader.stop()
            assert all(k._closed for k in kbds)

        _run(_test())


# =============================================================================
# Multi-Device Event Delivery Tests
# =============================================================================

class TestMultiDeviceEvents:
    """Test that events from any keyboard device are delivered."""

    def test_events_from_either_device_delivered(self):
        async def _test():
            cb = AsyncCallback()
            kbd1 = FakeInputDevice("/dev/input/event0", "KB1", _full_keyboard_caps())
            kbd2 = FakeInputDevice("/dev/input/event1", "KB2", _full_keyboard_caps())

            reader = EvdevReader(callback=cb, grab=False)
            with patch.object(reader, '_find_keyboards', return_value=[kbd1, kbd2]):
                await reader.start()

            kbd1.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_A, 1, 1.0))
            await asyncio.sleep(0.05)
            kbd2.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_B, 1, 2.0))
            await asyncio.sleep(0.05)

            await reader.stop()

            assert len(cb.calls) == 2
            assert cb.calls[0].keycode == KeyCode.KEY_A
            assert cb.calls[1].keycode == KeyCode.KEY_B

        _run(_test())

    def test_scancodes_tracked_per_device(self):
        """Scancodes should be independent per device (no cross-contamination)."""
        async def _test():
            cb = AsyncCallback()
            kbd1 = FakeInputDevice("/dev/input/event0", "KB1", _full_keyboard_caps())
            kbd2 = FakeInputDevice("/dev/input/event1", "KB2", _full_keyboard_caps())

            reader = EvdevReader(callback=cb, grab=False)
            with patch.object(reader, '_find_keyboards', return_value=[kbd1, kbd2]):
                await reader.start()

            kbd1.inject_event(FakeEvent(EV_MSC, MSC_SCAN, 0x1E, 1.0))
            kbd1.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_A, 1, 1.0))
            await asyncio.sleep(0.05)

            kbd2.inject_event(FakeEvent(EV_MSC, MSC_SCAN, 0x30, 2.0))
            kbd2.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_B, 1, 2.0))
            await asyncio.sleep(0.05)

            await reader.stop()

            assert len(cb.calls) == 2
            assert cb.calls[0].scancode == 0x1E
            assert cb.calls[1].scancode == 0x30

        _run(_test())

    def test_device_close_doesnt_crash_other(self):
        """One device closing (simulating unplug) should not affect the other."""
        async def _test():
            cb = AsyncCallback()
            kbd1 = FakeInputDevice("/dev/input/event0", "KB1", _full_keyboard_caps())
            kbd2 = FakeInputDevice("/dev/input/event1", "KB2", _full_keyboard_caps())

            reader = EvdevReader(callback=cb, grab=False)
            with patch.object(reader, '_find_keyboards', return_value=[kbd1, kbd2]):
                await reader.start()

            kbd1.close()
            await asyncio.sleep(0.05)

            kbd2.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_C, 1, 3.0))
            await asyncio.sleep(0.05)

            await reader.stop()

            assert len(cb.calls) == 1
            assert cb.calls[0].keycode == KeyCode.KEY_C

        _run(_test())

    def test_key_up_and_repeat(self):
        """Up and repeat events should be delivered correctly."""
        async def _test():
            cb = AsyncCallback()
            kbd = FakeInputDevice("/dev/input/event0", "KB", _full_keyboard_caps())

            reader = EvdevReader(callback=cb, grab=False)
            with patch.object(reader, '_find_keyboards', return_value=[kbd]):
                await reader.start()

            kbd.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_A, 1, 1.0))  # down
            await asyncio.sleep(0.02)
            kbd.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_A, 2, 1.1))  # repeat
            await asyncio.sleep(0.02)
            kbd.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_A, 0, 1.2))  # up
            await asyncio.sleep(0.02)

            await reader.stop()

            assert len(cb.calls) == 3
            assert cb.calls[0].is_down is True
            assert cb.calls[0].is_repeat is False
            assert cb.calls[1].is_down is True
            assert cb.calls[1].is_repeat is True
            assert cb.calls[2].is_down is False

        _run(_test())

    def test_non_key_events_ignored(self):
        """Events that aren't EV_KEY or EV_MSC should be silently ignored."""
        async def _test():
            cb = AsyncCallback()
            kbd = FakeInputDevice("/dev/input/event0", "KB", _full_keyboard_caps())

            reader = EvdevReader(callback=cb, grab=False)
            with patch.object(reader, '_find_keyboards', return_value=[kbd]):
                await reader.start()

            kbd.inject_event(FakeEvent(0, 0, 0, 1.0))   # EV_SYN
            kbd.inject_event(FakeEvent(2, 0, 1, 1.0))   # EV_REL
            kbd.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_A, 1, 1.0))
            await asyncio.sleep(0.05)

            await reader.stop()

            assert len(cb.calls) == 1

        _run(_test())


# =============================================================================
# Power Button Multi-Device Tests
# =============================================================================

class TestPowerButtonLifecycle:
    """Test PowerButtonReader start/stop with multiple devices."""

    def test_starts_task_per_device(self):
        async def _test():
            pb1 = FakeInputDevice("/dev/input/event0", "LNXPWRBN",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)
            pb2 = FakeInputDevice("/dev/input/event1", "PNP0C0C",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)

            reader = PowerButtonReader(callback=AsyncCallback(), hold_seconds=3)
            with patch.object(reader, '_find_power_buttons', return_value=[pb1, pb2]):
                await reader.start()
            assert len(reader._tasks) == 2
            await reader.stop()

        _run(_test())

    def test_stop_closes_all_devices(self):
        async def _test():
            pb1 = FakeInputDevice("/dev/input/event0", "LNXPWRBN",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)
            pb2 = FakeInputDevice("/dev/input/event1", "PNP0C0C",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)

            reader = PowerButtonReader(callback=AsyncCallback(), hold_seconds=3)
            with patch.object(reader, '_find_power_buttons', return_value=[pb1, pb2]):
                await reader.start()
            await reader.stop()

            assert pb1._closed and pb2._closed
            assert reader._tasks == []
            assert reader._devices == []

        _run(_test())

    def test_no_devices_doesnt_crash(self):
        async def _test():
            reader = PowerButtonReader(callback=AsyncCallback())
            with patch.object(reader, '_find_power_buttons', return_value=[]):
                await reader.start()
            assert reader._tasks == []
            await reader.stop()

        _run(_test())


class TestPowerButtonEvents:
    """Test power button tap detection across multiple devices."""

    def test_tap_from_second_device(self):
        async def _test():
            cb = AsyncCallback()
            pb1 = FakeInputDevice("/dev/input/event0", "LNXPWRBN",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)
            pb2 = FakeInputDevice("/dev/input/event1", "PNP0C0C",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)

            reader = PowerButtonReader(callback=cb, hold_seconds=3)
            with patch.object(reader, '_find_power_buttons', return_value=[pb1, pb2]):
                await reader.start()

            pb2.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_POWER, 1, 100.0))
            await asyncio.sleep(0.05)
            pb2.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_POWER, 0, 100.1))
            await asyncio.sleep(0.05)

            await reader.stop()

            assert len(cb.calls) == 1
            assert cb.calls[0].action == "tap"

        _run(_test())

    def test_tap_from_first_device(self):
        async def _test():
            cb = AsyncCallback()
            pb1 = FakeInputDevice("/dev/input/event0", "LNXPWRBN",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)
            pb2 = FakeInputDevice("/dev/input/event1", "PNP0C0C",
                                  {KeyCode.KEY_POWER}, has_ev_rep=False)

            reader = PowerButtonReader(callback=cb, hold_seconds=3)
            with patch.object(reader, '_find_power_buttons', return_value=[pb1, pb2]):
                await reader.start()

            pb1.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_POWER, 1, 200.0))
            await asyncio.sleep(0.05)
            pb1.inject_event(FakeEvent(EV_KEY, KeyCode.KEY_POWER, 0, 200.1))
            await asyncio.sleep(0.05)

            await reader.stop()

            assert len(cb.calls) == 1
            assert cb.calls[0].action == "tap"

        _run(_test())


# =============================================================================
# Shutdown Watchdog Tests
# =============================================================================

class TestShutdownWatchdog:
    """Test that PowerManager.shutdown() spawns a detached shutdown watchdog.

    The watchdog is a background process that force-powers-off after 5 seconds,
    ensuring shutdown completes even if the TUI event loop is killed first.
    All watchdog tests live here (centralized in PowerManager, not ByeScreen).
    """

    def test_watchdog_uses_start_new_session(self):
        """Watchdog must detach from TUI's process group."""
        from purple_tui.power_manager import PowerManager
        pm = PowerManager()
        calls = []

        def capture(*args, **kwargs):
            calls.append((args, kwargs))
            raise FileNotFoundError("not found")

        with patch("purple_tui.power_manager.subprocess.Popen", side_effect=capture):
            pm.shutdown()

        # First call is the watchdog
        assert calls[0][1].get("start_new_session") is True

    def test_watchdog_command_has_force_poweroff(self):
        from purple_tui.power_manager import PowerManager
        pm = PowerManager()
        calls = []

        def capture(*args, **kwargs):
            calls.append((args, kwargs))
            raise FileNotFoundError("not found")

        with patch("purple_tui.power_manager.subprocess.Popen", side_effect=capture):
            pm.shutdown()

        cmd = calls[0][0][0]
        assert cmd[0] == "sh"
        assert cmd[1] == "-c"
        assert "poweroff --force" in cmd[2]

    def test_watchdog_uses_single_force(self):
        """Watchdog uses single --force to preserve ACPI power-off sequence.

        Double --force bypasses ACPI and can leave keyboard backlights on
        and devices in limbo on Modern Standby hardware (Surface, Macs).
        """
        from purple_tui.power_manager import PowerManager
        pm = PowerManager()
        calls = []

        def capture(*args, **kwargs):
            calls.append((args, kwargs))
            raise FileNotFoundError("not found")

        with patch("purple_tui.power_manager.subprocess.Popen", side_effect=capture):
            pm.shutdown()

        cmd_str = calls[0][0][0][2]
        assert "--force" in cmd_str
        assert "--force --force" not in cmd_str

    def test_watchdog_swallows_exceptions(self):
        """Watchdog spawn failure should not prevent shutdown attempt."""
        from purple_tui.power_manager import PowerManager
        pm = PowerManager()

        with patch("purple_tui.power_manager.subprocess.Popen",
                   side_effect=OSError("spawn failed")):
            pm.shutdown()  # Should not raise

    def test_watchdog_includes_sudo_fallback(self):
        """Watchdog should try sudo in case user lacks direct permissions."""
        from purple_tui.power_manager import PowerManager
        pm = PowerManager()
        calls = []

        def capture(*args, **kwargs):
            calls.append((args, kwargs))
            raise FileNotFoundError("not found")

        with patch("purple_tui.power_manager.subprocess.Popen", side_effect=capture):
            pm.shutdown()

        cmd_str = calls[0][0][0][2]
        assert "sudo" in cmd_str

    def test_watchdog_sleep_allows_acpi(self):
        """Watchdog delay is 15s to let ACPI power-off complete on slow hardware."""
        from purple_tui.power_manager import PowerManager
        pm = PowerManager()
        calls = []

        def capture(*args, **kwargs):
            calls.append((args, kwargs))
            raise FileNotFoundError("not found")

        with patch("purple_tui.power_manager.subprocess.Popen", side_effect=capture):
            pm.shutdown()

        cmd_str = calls[0][0][0][2]
        assert cmd_str.startswith("sleep 15")


# =============================================================================
# Backward Compatibility Tests
# =============================================================================

class TestBackwardCompat:
    """Test backward compatibility of the _device property."""

    def test_device_property_returns_first(self):
        async def _test():
            kbd1 = FakeInputDevice("/dev/input/event0", "KB1", _full_keyboard_caps())
            kbd2 = FakeInputDevice("/dev/input/event1", "KB2", _full_keyboard_caps())

            reader = EvdevReader(callback=AsyncCallback(), grab=False)
            with patch.object(reader, '_find_keyboards', return_value=[kbd1, kbd2]):
                await reader.start()

            assert reader._device is kbd1
            await reader.stop()

        _run(_test())

    def test_device_property_none_when_empty(self):
        reader = EvdevReader(callback=AsyncCallback())
        assert reader._device is None


# =============================================================================
# Keyboard Detection Criteria Tests (validation logic, no evdev dependency)
# =============================================================================

class TestKeyboardValidation:
    """Test the keyboard validation criteria used by _find_keyboards."""

    def _letter_keys(self):
        """The letter key range used in detection code."""
        return set(range(KeyCode.KEY_A, KeyCode.KEY_Z + 1))

    def _required_keys(self):
        return self._letter_keys() | {
            KeyCode.KEY_ENTER, KeyCode.KEY_SPACE, KeyCode.KEY_LEFTSHIFT,
        }

    def test_full_keyboard_passes_strict(self):
        caps = _full_keyboard_caps()
        assert self._required_keys().issubset(caps)

    def test_partial_hid_fails_strict(self):
        """A USB HID device with only a few keys fails."""
        caps = {KeyCode.KEY_A, KeyCode.KEY_B, KeyCode.KEY_ENTER, KeyCode.KEY_POWER}
        assert not self._required_keys().issubset(caps)

    def test_missing_enter_fails(self):
        caps = self._letter_keys() | {KeyCode.KEY_SPACE, KeyCode.KEY_LEFTSHIFT}
        assert not self._required_keys().issubset(caps)

    def test_missing_space_fails(self):
        caps = self._letter_keys() | {KeyCode.KEY_ENTER, KeyCode.KEY_LEFTSHIFT}
        assert not self._required_keys().issubset(caps)

    def test_missing_shift_included_in_letter_range(self):
        """KEY_LEFTSHIFT (42) is within KEY_A..KEY_Z range, so it's
        automatically included. This test documents that behavior."""
        assert KeyCode.KEY_LEFTSHIFT >= KeyCode.KEY_A
        assert KeyCode.KEY_LEFTSHIFT <= KeyCode.KEY_Z

    def test_no_ev_rep_fails_strict(self):
        """A device without EV_REP fails the strict check."""
        dev = FakeInputDevice("/dev/input/event0", "NoRepeat",
                              _full_keyboard_caps(), has_ev_rep=False)
        assert EV_REP not in dev.capabilities()

    def test_ev_rep_present_passes(self):
        dev = FakeInputDevice("/dev/input/event0", "RealKB",
                              _full_keyboard_caps(), has_ev_rep=True)
        assert EV_REP in dev.capabilities()

    def test_power_button_caps_too_few_keys(self):
        """Power button has < 20 keys (classified as dedicated)."""
        caps = {KeyCode.KEY_POWER}
        assert len(caps) < 20

    def test_keyboard_with_power_has_many_keys(self):
        """Keyboard + KEY_POWER has >= 20 keys (classified as keyboard)."""
        caps = _full_keyboard_caps() | {KeyCode.KEY_POWER}
        assert len(caps) >= 20

    def test_loose_match_uses_letter_range(self):
        """Loose match checks letter key range (KEY_A to KEY_Z)."""
        letter_keys = self._letter_keys()
        # Must be a non-empty range covering the main keyboard rows
        assert len(letter_keys) > 0
        assert KeyCode.KEY_A in letter_keys
        assert KeyCode.KEY_Z in letter_keys

    def test_loose_match_rejects_small_cap_set(self):
        """A device with only a few letter keys should fail loose match too."""
        small = {KeyCode.KEY_A, KeyCode.KEY_B}
        letter_keys = self._letter_keys()
        assert not letter_keys.issubset(small)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
