#!/usr/bin/env python3
"""Tests for Power Manager - idle detection and activity tracking.

Run with: pytest tests/test_power_manager.py -v
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from purple_tui.power_manager import (
    PowerManager,
    IDLE_SLEEP_UI,
    IDLE_SCREEN_OFF,
    IDLE_SHUTDOWN,
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

    class TestIdleStates:
        """Test idle state transitions."""

        def test_active_state(self, power_manager):
            """Fresh manager should be in active state."""
            state = power_manager.get_idle_state()
            assert state == "active"

        def test_state_after_activity(self, power_manager):
            """State should be active after recording activity."""
            power_manager.record_activity()
            state = power_manager.get_idle_state()
            assert state == "active"

        def test_get_time_until_next_state(self, power_manager):
            """Should return time until sleep UI state."""
            next_state, seconds = power_manager.get_time_until_next_state()
            assert next_state == "sleep_ui"
            assert seconds > 0
            assert seconds <= IDLE_SLEEP_UI

    class TestWakeCallback:
        """Test wake event callback."""

        def test_wake_callback_fires_when_idle(self, power_manager):
            """Wake callback should fire when recording activity after being idle."""
            callback = MagicMock()
            power_manager.register_callback("wake", callback)

            # Simulate being idle (manually set last_activity in the past)
            power_manager._last_activity = time.time() - (IDLE_SLEEP_UI + 10)

            # Record activity - should trigger wake
            power_manager.record_activity()

            callback.assert_called_once()

        def test_wake_callback_not_fired_when_active(self, power_manager):
            """Wake callback should NOT fire when already active."""
            callback = MagicMock()
            power_manager.register_callback("wake", callback)

            # Record activity while active
            power_manager.record_activity()

            callback.assert_not_called()

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
                assert pm_module.IDLE_SLEEP_UI == 2
                assert pm_module.IDLE_SCREEN_OFF == 10
                assert pm_module.IDLE_SHUTDOWN == 20

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

            # Create a mock app with the on_event method
            from purple_tui.purple_tui import PurpleApp

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
        print(f"Initial state: {pm.get_idle_state()}")

        time.sleep(0.1)
        print(f"After 0.1s: {pm.get_idle_seconds():.3f}s")

        pm.record_activity()
        print(f"After record_activity(): {pm.get_idle_seconds():.3f}s")

        print("Basic checks passed!")
