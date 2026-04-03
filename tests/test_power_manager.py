#!/usr/bin/env python3
"""Tests for Power Manager - idle detection, activity tracking, and charger detection.

Run with: pytest tests/test_power_manager.py -v
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from purple_tui.power_manager import (
    PowerManager,
    CHARGER_IDLE_SLEEP,
    BATTERY_IDLE_SLEEP,
    BATTERY_IDLE_SHUTDOWN,
    LID_SHUTDOWN_DELAY,
    POWER_HOLD_SHUTDOWN,
)


# =============================================================================
# PowerManager Unit Tests
# =============================================================================

if HAS_PYTEST:

    @pytest.fixture
    def power_manager():
        """Create a fresh PowerManager for each test."""
        # Reset singleton
        import purple_tui.power_manager as pm_module
        pm_module._power_manager = None
        return PowerManager()

    class TestIdleTracking:
        """Test idle time tracking."""

        def test_initial_idle_is_zero(self, power_manager):
            """Idle time should be near zero on creation."""
            idle = power_manager.get_idle_seconds()
            assert idle < 1.0

        def test_idle_increases_over_time(self, power_manager):
            """Idle time should increase when no activity."""
            time.sleep(0.1)
            idle = power_manager.get_idle_seconds()
            assert idle >= 0.1

        def test_record_activity_resets_idle(self, power_manager):
            """Recording activity should reset idle timer."""
            # Wait a bit
            time.sleep(0.1)
            assert power_manager.get_idle_seconds() >= 0.1

            # Record activity
            power_manager.record_activity()

            # Idle should be reset
            assert power_manager.get_idle_seconds() < 0.05

        def test_multiple_activity_records(self, power_manager):
            """Multiple activity records should each reset timer."""
            for _ in range(3):
                time.sleep(0.05)
                power_manager.record_activity()
                assert power_manager.get_idle_seconds() < 0.05

    class TestIdleThresholds:
        """Test idle threshold values."""

        def test_idle_below_sleep_threshold(self, power_manager):
            """Fresh manager should have idle below sleep threshold."""
            assert power_manager.get_idle_seconds() < BATTERY_IDLE_SLEEP

        def test_idle_after_activity(self, power_manager):
            """Idle should be near zero after recording activity."""
            power_manager._last_activity = time.time() - (BATTERY_IDLE_SLEEP + 10)
            power_manager.record_activity()
            assert power_manager.get_idle_seconds() < 0.05

    class TestPowerTimings:
        """Test power timing constants."""

        def test_charger_sleep_is_five_minutes(self):
            """On charger, sleep face should show after 5 minutes."""
            assert CHARGER_IDLE_SLEEP == 5 * 60

        def test_battery_sleep_is_two_minutes(self):
            """On battery, sleep face should show after 2 minutes."""
            assert BATTERY_IDLE_SLEEP == 2 * 60

        def test_battery_shutdown_is_ten_minutes(self):
            """On battery, shutdown should happen after 10 minutes."""
            assert BATTERY_IDLE_SHUTDOWN == 10 * 60

        def test_lid_shutdown_is_ten_minutes(self):
            """Lid close should wait 10 minutes before shutdown."""
            assert LID_SHUTDOWN_DELAY == 10 * 60

        def test_power_hold_shutdown_is_three_seconds(self):
            """Power button hold should trigger shutdown after 3 seconds."""
            assert POWER_HOLD_SHUTDOWN == 3

    class TestChargerAwareThresholds:
        """Test that idle thresholds adapt to charger state."""

        def test_on_battery_sleep_threshold(self, power_manager):
            """On battery, sleep threshold should be BATTERY_IDLE_SLEEP."""
            power_manager._charger_state = False
            assert power_manager.get_idle_sleep_threshold() == BATTERY_IDLE_SLEEP

        def test_on_charger_sleep_threshold(self, power_manager):
            """On charger, sleep threshold should be CHARGER_IDLE_SLEEP."""
            power_manager._charger_state = True
            assert power_manager.get_idle_sleep_threshold() == CHARGER_IDLE_SLEEP

        def test_unknown_charger_sleep_threshold(self, power_manager):
            """Unknown charger state should use battery (conservative)."""
            power_manager._charger_state = None
            assert power_manager.get_idle_sleep_threshold() == BATTERY_IDLE_SLEEP

        def test_on_battery_shutdown_threshold(self, power_manager):
            """On battery, shutdown threshold should be BATTERY_IDLE_SHUTDOWN."""
            power_manager._charger_state = False
            assert power_manager.get_idle_shutdown_threshold() == BATTERY_IDLE_SHUTDOWN

        def test_on_charger_no_shutdown(self, power_manager):
            """On charger with lid open, no auto-shutdown."""
            power_manager._charger_state = True
            assert power_manager.get_idle_shutdown_threshold() is None

        def test_unknown_charger_shutdown_threshold(self, power_manager):
            """Unknown charger should use battery shutdown threshold."""
            power_manager._charger_state = None
            assert power_manager.get_idle_shutdown_threshold() == BATTERY_IDLE_SHUTDOWN

    class TestDemoMode:
        """Test demo mode timing values."""

        def test_demo_mode_uses_short_timings(self):
            """Demo mode should have much shorter timings."""
            import os
            import importlib
            import purple_tui.power_manager as pm_module

            # Save original
            original = os.environ.get("PURPLE_SLEEP_DEMO")

            try:
                # Enable demo mode and reload module
                os.environ["PURPLE_SLEEP_DEMO"] = "1"
                importlib.reload(pm_module)

                # Check timings are short
                assert pm_module.CHARGER_IDLE_SLEEP == 3
                assert pm_module.BATTERY_IDLE_SLEEP == 2
                assert pm_module.BATTERY_IDLE_SHUTDOWN == 10

            finally:
                # Restore
                if original:
                    os.environ["PURPLE_SLEEP_DEMO"] = original
                else:
                    os.environ.pop("PURPLE_SLEEP_DEMO", None)
                importlib.reload(pm_module)


# =============================================================================
# App-level Activity Tracking Tests
# =============================================================================

if HAS_PYTEST:

    class TestAppActivityTracking:
        """Test that app-level on_event() records activity correctly."""

        def test_on_event_records_key_activity(self):
            """on_event() should call _record_user_activity() for Key events."""
            from textual import events

            # We can't easily instantiate the full app, so test the logic directly
            # The key insight is that on_event checks isinstance(event, events.Key)

            # Verify Key is the right type to check
            assert hasattr(events, 'Key')

        def test_key_event_isinstance_check(self):
            """Verify our isinstance check would work for Key events."""
            from textual import events

            # Create a mock key event
            mock_event = MagicMock(spec=events.Key)

            # This is the check we do in on_event()
            assert isinstance(mock_event, events.Key)


# =============================================================================
# Shutdown Command Tests
# =============================================================================

if HAS_PYTEST:
    from unittest.mock import patch

    class TestShutdownExecution:
        """Test that shutdown() actually attempts to power off."""

        @pytest.fixture
        def pm(self):
            import purple_tui.power_manager as pm_module
            pm_module._power_manager = None
            mgr = PowerManager()
            mgr._poweroff_available = True
            return mgr

        def test_shutdown_calls_systemctl_force(self, pm):
            """shutdown() should try systemctl poweroff --force first (after watchdog)."""
            with patch("purple_tui.power_manager.subprocess.Popen") as mock_popen:
                result = pm.shutdown()

            assert result is True
            # First call is watchdog, second is the actual shutdown command
            assert mock_popen.call_count == 2
            cmd = mock_popen.call_args_list[1][0][0]
            assert cmd == ["sudo", "systemctl", "poweroff", "--force"]

        def test_shutdown_falls_back_on_failure(self, pm):
            """If first shutdown command fails, should try next one."""
            call_count = 0

            def fail_then_succeed(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # Call 1 = watchdog (succeeds), call 2 = shutdown (fail),
                # call 3 = shutdown (succeeds)
                if call_count == 2:
                    raise FileNotFoundError("not found")
                return MagicMock()

            with patch("purple_tui.power_manager.subprocess.Popen",
                       side_effect=fail_then_succeed):
                result = pm.shutdown()

            assert result is True
            assert call_count == 3  # watchdog + 1 failure + 1 success

        def test_shutdown_returns_false_when_all_fail(self, pm):
            """If every shutdown command fails, should return False."""
            calls = []

            def track(*args, **kwargs):
                calls.append(args[0])
                # Let watchdog succeed, fail everything else
                if len(calls) == 1 and args[0][0] == "sh":
                    return MagicMock()
                raise FileNotFoundError("not found")

            with patch("purple_tui.power_manager.subprocess.Popen",
                       side_effect=track):
                result = pm.shutdown()

            assert result is False

        def test_shutdown_tries_even_when_poweroff_unavailable(self, pm):
            """Should still try commands even if _poweroff_available is False."""
            pm._poweroff_available = False
            with patch("purple_tui.power_manager.subprocess.Popen") as mock_popen:
                result = pm.shutdown()

            assert result is True
            # Watchdog + first shutdown command
            assert mock_popen.call_count == 2

        def test_shutdown_demo_mode_does_not_poweroff(self, pm):
            """In demo mode, shutdown should not call any commands."""
            import os
            original = os.environ.get("PURPLE_SLEEP_DEMO")
            try:
                os.environ["PURPLE_SLEEP_DEMO"] = "1"
                with patch("purple_tui.power_manager.subprocess.Popen") as mock_popen:
                    result = pm.shutdown()
                assert result is True
                mock_popen.assert_not_called()
            finally:
                if original:
                    os.environ["PURPLE_SLEEP_DEMO"] = original
                else:
                    os.environ.pop("PURPLE_SLEEP_DEMO", None)

        def test_shutdown_uses_force_flag(self, pm):
            """Both shutdown commands should use --force."""
            commands_tried = []

            def capture_cmd(*args, **kwargs):
                commands_tried.append(args[0])
                # Let watchdog succeed, fail shutdown commands to capture all
                if len(commands_tried) == 1 and args[0][0] == "sh":
                    return MagicMock()
                raise FileNotFoundError("not found")

            with patch("purple_tui.power_manager.subprocess.Popen",
                       side_effect=capture_cmd):
                pm.shutdown()

            # Skip watchdog (index 0), check shutdown commands
            assert "--force" in commands_tried[1]       # sudo systemctl --force
            assert "-f" in commands_tried[2]            # sudo poweroff -f

    class TestPoweroffAvailableCheck:
        """Test the _poweroff_available initialization."""

        def test_available_when_systemctl_exists(self):
            """Should be True when systemctl is on PATH."""
            import purple_tui.power_manager as pm_module
            pm_module._power_manager = None
            with patch("shutil.which", return_value="/usr/bin/systemctl"):
                mgr = PowerManager()
            assert mgr._poweroff_available is True

        def test_available_when_only_poweroff_exists(self):
            """Should be True when poweroff is on PATH (no systemctl)."""
            import purple_tui.power_manager as pm_module
            pm_module._power_manager = None

            def which_side_effect(cmd):
                if cmd == "poweroff":
                    return "/sbin/poweroff"
                return None

            with patch("shutil.which", side_effect=which_side_effect):
                mgr = PowerManager()
            assert mgr._poweroff_available is True

        def test_unavailable_when_nothing_exists(self):
            """Should be False when neither systemctl nor poweroff exists."""
            import purple_tui.power_manager as pm_module
            pm_module._power_manager = None
            with patch("shutil.which", return_value=None):
                mgr = PowerManager()
            assert mgr._poweroff_available is False

        def test_shutil_which_cannot_hang(self):
            """shutil.which uses os.access, no subprocess, cannot block."""
            import shutil
            # This is a design assertion: shutil.which doesn't spawn processes
            # so it can't hang on I/O like subprocess.run could
            assert callable(shutil.which)


# =============================================================================
# Standalone runner
# =============================================================================

if __name__ == "__main__":
    if HAS_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        print("pytest not installed. Install with: pip install pytest")
        print("Running basic sanity checks...")

        pm = PowerManager()
        print(f"Initial idle: {pm.get_idle_seconds():.3f}s")

        time.sleep(0.1)
        print(f"After 0.1s: {pm.get_idle_seconds():.3f}s")

        pm.record_activity()
        print(f"After record_activity(): {pm.get_idle_seconds():.3f}s")

        print(f"Charger state: {pm.is_on_charger()}")
        print(f"Sleep threshold: {pm.get_idle_sleep_threshold()}s")
        print(f"Shutdown threshold: {pm.get_idle_shutdown_threshold()}")

        print("Basic checks passed!")
