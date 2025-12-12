"""
Purple Computer - Power Management

Handles idle detection, lid monitoring, screen dimming, and shutdown.
Designed to be robust and fail gracefully - no errors, just fallbacks.

Demo mode: Set PURPLE_SLEEP_DEMO=1 to use accelerated timings for testing.
"""

import os
import subprocess
import time
from typing import Callable, Optional


def _get_timing(normal: int, demo: int) -> int:
    """Get timing value - uses demo value if PURPLE_SLEEP_DEMO is set."""
    if os.environ.get("PURPLE_SLEEP_DEMO"):
        return demo
    return normal


# Timing constants (seconds)
# Normal values / Demo values (for quick testing)
IDLE_SLEEP_UI = _get_timing(3 * 60, 2)        # 3 min / 2 sec - show sleeping face
IDLE_SCREEN_DIM = _get_timing(10 * 60, 6)     # 10 min / 6 sec - dim screen
IDLE_SCREEN_OFF = _get_timing(15 * 60, 10)    # 15 min / 10 sec - screen off
IDLE_SHUTDOWN_WARN = _get_timing(25 * 60, 15) # 25 min / 15 sec - shutdown warning
IDLE_SHUTDOWN = _get_timing(30 * 60, 20)      # 30 min / 20 sec - shutdown

LID_SHUTDOWN_DELAY = _get_timing(5, 3)        # 5 sec / 3 sec - lid close warning


class PowerManager:
    """
    Manages power states for Purple Computer.

    Robust design:
    - All operations have try/except with fallbacks
    - Prefers staying awake over crashing
    - Works across different laptop models
    """

    def __init__(self):
        self._last_activity = time.time()
        self._lid_path: Optional[str] = None
        self._dpms_available = False
        self._poweroff_available = False
        self._callbacks: dict[str, list[Callable]] = {
            "idle_sleep": [],      # Show sleep UI
            "idle_dim": [],        # Dim screen
            "idle_screen_off": [], # Screen off
            "shutdown_warning": [],# Show shutdown warning
            "shutdown": [],        # Actually shutdown
            "lid_close": [],       # Lid closed
            "lid_open": [],        # Lid opened
            "wake": [],            # Any wake event
        }

        # Probe capabilities on init
        self._probe_capabilities()

    def _probe_capabilities(self) -> None:
        """Check what power features are available on this system."""
        # Check for lid state file
        lid_paths = [
            "/proc/acpi/button/lid/LID0/state",
            "/proc/acpi/button/lid/LID/state",
            "/proc/acpi/button/lid/LID1/state",
        ]
        for path in lid_paths:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        f.read()
                    self._lid_path = path
                    break
                except (IOError, OSError, PermissionError):
                    continue

        # Check if xset is available for DPMS
        try:
            result = subprocess.run(
                ["which", "xset"],
                capture_output=True,
                timeout=2
            )
            self._dpms_available = result.returncode == 0
        except Exception:
            self._dpms_available = False

        # Check if we can poweroff (systemctl)
        try:
            result = subprocess.run(
                ["which", "systemctl"],
                capture_output=True,
                timeout=2
            )
            self._poweroff_available = result.returncode == 0
        except Exception:
            self._poweroff_available = False

    def register_callback(self, event: str, callback: Callable) -> None:
        """Register a callback for a power event."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _fire_event(self, event: str, *args) -> None:
        """Fire all callbacks for an event. Never raises."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args)
            except Exception:
                pass  # Swallow all errors

    def record_activity(self) -> None:
        """Call this on any user input to reset idle timer."""
        was_idle = self.get_idle_seconds() > IDLE_SLEEP_UI
        self._last_activity = time.time()
        if was_idle:
            self._fire_event("wake")

    def get_idle_seconds(self) -> float:
        """Get seconds since last activity."""
        return time.time() - self._last_activity

    def get_lid_state(self) -> Optional[bool]:
        """
        Check if lid is open.
        Returns: True if open, False if closed, None if unknown/error.
        """
        if not self._lid_path:
            return None

        try:
            with open(self._lid_path) as f:
                content = f.read().strip().lower()
                if "open" in content:
                    return True
                elif "closed" in content:
                    return False
                return None
        except Exception:
            return None

    def set_screen_brightness(self, level: str) -> bool:
        """
        Control screen brightness via DPMS.
        level: "on", "dim", "off"
        Returns True on success.
        """
        if not self._dpms_available:
            return False

        try:
            if level == "off":
                # Force screen off
                subprocess.run(
                    ["xset", "dpms", "force", "off"],
                    capture_output=True,
                    timeout=5
                )
            elif level == "on":
                # Re-enable and force on
                subprocess.run(
                    ["xset", "dpms", "force", "on"],
                    capture_output=True,
                    timeout=5
                )
            return True
        except Exception:
            return False

    def enable_dpms(self, standby: int = 600, suspend: int = 900, off: int = 900) -> bool:
        """Enable DPMS with specified timeouts (seconds)."""
        if not self._dpms_available:
            return False

        try:
            subprocess.run(
                ["xset", "+dpms"],
                capture_output=True,
                timeout=5
            )
            subprocess.run(
                ["xset", "dpms", str(standby), str(suspend), str(off)],
                capture_output=True,
                timeout=5
            )
            return True
        except Exception:
            return False

    def disable_dpms(self) -> bool:
        """Disable DPMS (screen stays on forever)."""
        if not self._dpms_available:
            return False

        try:
            subprocess.run(["xset", "s", "off"], capture_output=True, timeout=5)
            subprocess.run(["xset", "-dpms"], capture_output=True, timeout=5)
            subprocess.run(["xset", "s", "noblank"], capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def shutdown(self) -> bool:
        """
        Initiate system shutdown.
        Returns True if command was sent (doesn't mean it worked).
        Falls back through multiple methods for maximum compatibility.

        In demo mode (PURPLE_SLEEP_DEMO=1), just prints a message instead.
        """
        # In demo mode, don't actually shut down!
        if os.environ.get("PURPLE_SLEEP_DEMO"):
            print("\n" + "=" * 50)
            print("  DEMO MODE: Would shut down here")
            print("  (Press Ctrl+C to exit)")
            print("=" * 50 + "\n")
            return True

        if not self._poweroff_available:
            return False

        # Try multiple shutdown methods in order of preference
        commands = [
            ["systemctl", "poweroff"],           # Direct (if user has permission)
            ["sudo", "systemctl", "poweroff"],   # Via sudo (configured in sudoers)
            ["sudo", "poweroff"],                # Traditional poweroff command
        ]

        for cmd in commands:
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                continue

        return False

    def get_idle_state(self) -> str:
        """
        Get the current idle state based on time.
        Returns: "active", "sleep_ui", "dim", "screen_off", "shutdown_warning", "shutdown"
        """
        idle = self.get_idle_seconds()

        if idle >= IDLE_SHUTDOWN:
            return "shutdown"
        elif idle >= IDLE_SHUTDOWN_WARN:
            return "shutdown_warning"
        elif idle >= IDLE_SCREEN_OFF:
            return "screen_off"
        elif idle >= IDLE_SCREEN_DIM:
            return "dim"
        elif idle >= IDLE_SLEEP_UI:
            return "sleep_ui"
        else:
            return "active"

    def get_time_until_next_state(self) -> tuple[str, int]:
        """
        Get the next state transition and seconds until it happens.
        Returns: (next_state, seconds_until)
        """
        idle = self.get_idle_seconds()

        thresholds = [
            (IDLE_SLEEP_UI, "sleep_ui"),
            (IDLE_SCREEN_DIM, "dim"),
            (IDLE_SCREEN_OFF, "screen_off"),
            (IDLE_SHUTDOWN_WARN, "shutdown_warning"),
            (IDLE_SHUTDOWN, "shutdown"),
        ]

        for threshold, state in thresholds:
            if idle < threshold:
                return (state, int(threshold - idle))

        return ("shutdown", 0)


# Singleton instance
_power_manager: Optional[PowerManager] = None


def get_power_manager() -> PowerManager:
    """Get the global power manager instance."""
    global _power_manager
    if _power_manager is None:
        _power_manager = PowerManager()
    return _power_manager
