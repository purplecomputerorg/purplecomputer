"""
Purple Computer: Power Management

Handles idle detection, lid monitoring, screen control, and shutdown.
Designed to be robust and fail gracefully. No errors, just fallbacks.

Demo mode: Set PURPLE_SLEEP_DEMO=1 to use accelerated timings for testing.
"""

import os
import subprocess
import time
from typing import Optional


def _get_timing(normal: int, demo: int) -> int:
    """Get timing value. Uses demo value if PURPLE_SLEEP_DEMO is set."""
    if os.environ.get("PURPLE_SLEEP_DEMO"):
        return demo
    return normal


# Timing constants (seconds)
# Normal values / Demo values (for quick testing)
IDLE_SLEEP_UI = _get_timing(3 * 60, 2)        # 3 min / 2 sec: show sleeping face
IDLE_SCREEN_OFF = _get_timing(15 * 60, 10)    # 15 min / 10 sec: screen off
IDLE_SHUTDOWN = _get_timing(25 * 60, 15)      # 25 min / 15 sec: shutdown

LID_SHUTDOWN_DELAY = _get_timing(30, 5)       # 30 sec / 5 sec: lid close to shutdown

# Power button timing
POWER_HOLD_SHUTDOWN = _get_timing(3, 2)       # 3 sec / 2 sec: hold power to shut down

LOGIND_CONF_PATH = "/etc/systemd/logind.conf.d/purple-power.conf"


def set_logind_power_key(mode: str) -> bool:
    """Switch logind HandlePowerKey between 'ignore' and 'poweroff'.

    Used to let logind handle shutdown directly when the TUI is suspended
    (e.g., parent menu bash shell), then restore TUI control after.

    Returns True on success. Fails silently (best effort).
    """
    try:
        with open(LOGIND_CONF_PATH, "r") as f:
            content = f.read()
    except OSError:
        return False

    if mode == "poweroff":
        new_content = content.replace("HandlePowerKey=ignore", "HandlePowerKey=poweroff")
    elif mode == "ignore":
        new_content = content.replace("HandlePowerKey=poweroff", "HandlePowerKey=ignore")
    else:
        return False

    if new_content == content:
        return True  # Already in the desired state

    try:
        with open(LOGIND_CONF_PATH, "w") as f:
            f.write(new_content)
    except OSError:
        # No write permission, try via sudo
        try:
            subprocess.run(
                ["sudo", "tee", LOGIND_CONF_PATH],
                input=new_content.encode(),
                stdout=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            return False

    # Signal logind to re-read config (HUP reloads without killing sessions)
    try:
        subprocess.run(
            ["sudo", "systemctl", "kill", "-s", "HUP", "systemd-logind"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass  # Config is written, logind will pick it up on next restart

    return True


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

    def record_activity(self) -> None:
        """Call this on any user input to reset idle timer."""
        self._last_activity = time.time()

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
        level: "on" or "off"
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


# Singleton instance
_power_manager: Optional[PowerManager] = None


def get_power_manager() -> PowerManager:
    """Get the global power manager instance."""
    global _power_manager
    if _power_manager is None:
        _power_manager = PowerManager()
    return _power_manager
