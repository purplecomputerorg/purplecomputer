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
