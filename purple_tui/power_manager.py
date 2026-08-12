"""
Purple Computer: Power Management

Handles idle detection, lid monitoring, charger detection, and shutdown.
Designed to be robust and fail gracefully. No errors, just fallbacks.

Power states (2-tier):
  Awake: normal operation
  Sleep face: sleeping face shown, any key wakes

Timing varies by charger and lid state:
  On charger, lid open:  5 min idle -> sleep face, 60 min idle -> shutdown
  On battery, lid open:  2 min idle -> sleep face, 10 min idle -> shutdown
  Lid closed (any):      immediate sleep face, 10 min -> shutdown

Demo mode: Set PURPLE_SLEEP_DEMO=1 to use accelerated timings for testing.
Diagnostic logging: rare events (shutdowns, power button scans) always log to
/tmp/purple-power.log + /var/log/purple/power.log. Verbose power decisions log
only on the debug ISO (when /opt/purple/debug exists) or with PURPLE_POWER_LOG=1.
"""

import os
import subprocess
import time
from datetime import datetime
from typing import Optional


# /var/log/purple survives reboot on installed systems and the debug ISO
# (same convention as boot_log.py); rotated per boot by purple-wait-display.sh.
_LOG_PATHS = ("/tmp/purple-power.log", "/var/log/purple/power.log")
_log_enabled: Optional[bool] = None
_header_written = False


def _append(msg: str) -> None:
    """Timestamped append to tmpfs + persistent log. Never raises."""
    global _header_written
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    text = f"[{ts}] {msg}\n"
    if not _header_written:
        _header_written = True
        text = (f"\n{'=' * 60}\n"
                f"Power log started at {datetime.now().isoformat()}\n"
                f"{'=' * 60}\n") + text
    for path in _LOG_PATHS:
        try:
            with open(path, "a") as f:
                f.write(text)
        except Exception:
            pass


def _power_diag(msg: str) -> None:
    """Always-on log for rare, high-value events (shutdowns, power button
    scans and adoption). Chatty streams belong in _power_log instead."""
    _append(msg)


def _power_log(msg: str) -> None:
    """Log a power management event with timestamp.

    Auto-enabled on debug ISO. Can also be forced with PURPLE_POWER_LOG=1.
    """
    global _log_enabled
    if _log_enabled is None:
        from .constants import is_debug
        _log_enabled = is_debug() or os.environ.get("PURPLE_POWER_LOG") == "1"
    if _log_enabled:
        _append(msg)


def _get_timing(normal: int, demo: int) -> int:
    """Get timing value. Uses demo value if PURPLE_SLEEP_DEMO is set."""
    if os.environ.get("PURPLE_SLEEP_DEMO"):
        return demo
    return normal


# Timing constants (seconds)
# Normal values / Demo values (for quick testing)

# On charger, lid open
CHARGER_IDLE_SLEEP = _get_timing(5 * 60, 3)     # 5 min / 3 sec: show sleeping face
# On charger, lid open: auto-shutdown after 60 min idle
CHARGER_IDLE_SHUTDOWN = _get_timing(60 * 60, 15)  # 60 min / 15 sec: shutdown

# On battery (or unknown), lid open
BATTERY_IDLE_SLEEP = _get_timing(2 * 60, 2)     # 2 min / 2 sec: show sleeping face
BATTERY_IDLE_SHUTDOWN = _get_timing(10 * 60, 10) # 10 min / 10 sec: shutdown

# Lid closed (regardless of charger)
LID_SHUTDOWN_DELAY = _get_timing(10 * 60, 8)    # 10 min / 8 sec: shutdown after lid close

# Power button timing
POWER_HOLD_SHUTDOWN = _get_timing(3, 2)          # 3 sec / 2 sec: hold power to shut down

LOGIND_CONF_PATH = "/etc/systemd/logind.conf.d/purple-power.conf"

# Number of consecutive reads before changing charger state (smoothing)
_CHARGER_SMOOTH_COUNT = 2


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
    - Charger unknown = treated as battery (conservative)
    """

    # Cadence of the background ACPI refresher. Charger/lid every tick,
    # battery every 6th (30s), matching the old main-thread cadences.
    _REFRESH_INTERVAL = 5.0

    def __init__(self):
        self._last_activity = time.time()
        self._lid_path: Optional[str] = None
        self._mains_path: Optional[str] = None
        self._battery_path: Optional[str] = None
        self._poweroff_available = False

        # Charger state smoothing: require _CHARGER_SMOOTH_COUNT consecutive
        # reads of the same value before changing state. Prevents flicker
        # from firmware noise during plug/unplug.
        self._charger_state: Optional[bool] = None  # None = unknown, True = on charger
        self._charger_pending: Optional[bool] = None
        self._charger_pending_count = 0

        # Probe capabilities on init
        self._probe_capabilities()

        # ACPI reads (charger online, lid state, battery capacity) go
        # through the EC on many cheap laptops and can occasionally block
        # for 100ms+. The UI thread must never pay that, so a daemon
        # thread refreshes these caches and the getters return them.
        self._lid_open_cached = self._read_lid_raw()
        self._battery_status: Optional[tuple[int, bool]] = self._read_battery_raw()
        import threading
        threading.Thread(target=self._refresh_loop, daemon=True,
                         name="power-refresh").start()

    def _refresh_loop(self) -> None:
        tick = 0
        while True:
            time.sleep(self._REFRESH_INTERVAL)
            tick += 1
            try:
                self._refresh_charger()
                self._lid_open_cached = self._read_lid_raw()
                if tick % 6 == 0:
                    self._battery_status = self._read_battery_raw()
            except Exception:
                pass

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

        # Find AC mains power supply (charger detection) and battery
        self._find_mains()
        self._find_battery()

        _power_log(f"INIT: lid_path={self._lid_path}, mains_path={self._mains_path}, "
                    f"initial_charger={self._charger_state}")

        # Check if systemctl exists. Use shutil.which (no subprocess, can't hang).
        import shutil
        self._poweroff_available = shutil.which("systemctl") is not None
        if not self._poweroff_available:
            # Also check for plain poweroff as fallback
            self._poweroff_available = shutil.which("poweroff") is not None

    def _find_mains(self) -> None:
        """Find an AC mains power supply in /sys/class/power_supply/.

        Scans by type rather than name, since naming varies across hardware
        (AC, AC0, ADP0, ADP1, ACAD, etc.).
        """
        try:
            power_supply_path = "/sys/class/power_supply"
            if not os.path.exists(power_supply_path):
                return

            for entry in os.listdir(power_supply_path):
                entry_path = os.path.join(power_supply_path, entry)
                type_file = os.path.join(entry_path, "type")
                try:
                    with open(type_file) as f:
                        if f.read().strip() == "Mains":
                            online_file = os.path.join(entry_path, "online")
                            if os.path.exists(online_file):
                                self._mains_path = entry_path
                                # Read initial state without smoothing
                                self._charger_state = self._read_mains_online()
                                return
                except (IOError, OSError, PermissionError):
                    continue
        except (IOError, OSError, PermissionError):
            pass

    def _read_mains_online(self) -> Optional[bool]:
        """Read the raw online state of the AC mains. Returns None on error."""
        if not self._mains_path:
            return None
        try:
            online_file = os.path.join(self._mains_path, "online")
            with open(online_file) as f:
                return f.read().strip() == "1"
        except (IOError, OSError, PermissionError, ValueError):
            return None

    def _find_battery(self) -> None:
        """Find a battery in /sys/class/power_supply/ (naming varies)."""
        try:
            power_supply_path = "/sys/class/power_supply"
            if not os.path.exists(power_supply_path):
                return
            for entry in os.listdir(power_supply_path):
                entry_path = os.path.join(power_supply_path, entry)
                try:
                    with open(os.path.join(entry_path, "type")) as f:
                        if f.read().strip() == "Battery":
                            if os.path.exists(os.path.join(entry_path, "capacity")):
                                self._battery_path = entry_path
                                return
                except (IOError, OSError, PermissionError):
                    continue
        except (IOError, OSError, PermissionError):
            pass

    def _read_battery_raw(self) -> Optional[tuple[int, bool]]:
        """Read battery (percentage, charging). Returns None on error."""
        if not self._battery_path:
            return None
        try:
            with open(os.path.join(self._battery_path, "capacity")) as f:
                capacity = int(f.read().strip())
            charging = False
            status_file = os.path.join(self._battery_path, "status")
            if os.path.exists(status_file):
                with open(status_file) as f:
                    charging = f.read().strip().lower() in ("charging", "full")
            return (capacity, charging)
        except (IOError, OSError, PermissionError, ValueError):
            return None

    @property
    def battery_available(self) -> bool:
        return self._battery_path is not None

    def get_battery_status(self) -> Optional[tuple[int, bool]]:
        """Cached battery (percentage, charging); refreshed every 30s."""
        return self._battery_status

    def record_activity(self) -> None:
        """Call this on any user input to reset idle timer."""
        idle_was = self.get_idle_seconds()
        self._last_activity = time.time()
        if idle_was > 5:
            _power_log(f"ACTIVITY: idle reset (was {idle_was:.1f}s idle)")

    def get_idle_seconds(self) -> float:
        """Get seconds since last activity."""
        return time.time() - self._last_activity

    def get_lid_state(self) -> Optional[bool]:
        """Cached lid state: True if open, False if closed, None unknown.
        Refreshed by the background thread every 5s."""
        return self._lid_open_cached

    def _read_lid_raw(self) -> Optional[bool]:
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

    def is_on_charger(self) -> Optional[bool]:
        """Cached charger state: True on charger, False on battery, None
        unknown. Refreshed (with smoothing) by the background thread."""
        return self._charger_state

    def _refresh_charger(self) -> None:
        """Read mains state and apply smoothing: requires multiple
        consecutive identical reads before changing state, to avoid
        flicker from firmware noise during plug/unplug."""
        raw = self._read_mains_online()
        if raw is None:
            return  # Keep last known state

        if raw == self._charger_pending:
            self._charger_pending_count += 1
        else:
            self._charger_pending = raw
            self._charger_pending_count = 1

        old_state = self._charger_state
        if self._charger_pending_count >= _CHARGER_SMOOTH_COUNT:
            self._charger_state = raw

        if self._charger_state != old_state:
            _power_log(f"CHARGER CHANGE: {old_state} -> {self._charger_state} "
                        f"(raw={raw}, pending_count={self._charger_pending_count})")

    def get_idle_sleep_threshold(self) -> int:
        """Get the idle seconds threshold for showing the sleep face.

        Depends on charger state: longer timeout when plugged in.
        """
        if self._charger_state is True:
            return CHARGER_IDLE_SLEEP
        return BATTERY_IDLE_SLEEP

    def get_idle_shutdown_threshold(self) -> int:
        """Get the idle seconds threshold for auto-shutdown.

        Longer timeout on charger (60 min) vs battery (10 min).
        """
        if self._charger_state is True:
            return CHARGER_IDLE_SHUTDOWN
        return BATTERY_IDLE_SHUTDOWN

    def shutdown(self) -> bool:
        """
        Initiate system shutdown.
        Returns True if command was sent (doesn't mean it worked).
        Falls back through multiple methods for maximum compatibility.

        Uses --force to skip clean service stop (faster shutdown).
        There's no user data to lose on a kids' computer, and clean
        shutdown can hang for 10-15 seconds waiting for services.

        Also spawns a watchdog process that force-powers-off after 15
        seconds, independent of the TUI event loop. This ensures
        shutdown completes even if systemd kills X11/Textual first.

        In demo mode (PURPLE_SLEEP_DEMO=1), just prints a message instead.
        """
        # Always log shutdown attempts (not just on debug ISO) for diagnostics.
        _power_diag(f"SHUTDOWN requested: idle={self.get_idle_seconds():.1f}s, "
                      f"charger={self._charger_state}")
        _power_log(f"SHUTDOWN requested: idle={self.get_idle_seconds():.1f}s, "
                   f"charger={self._charger_state}")

        # In demo mode, don't actually shut down!
        if os.environ.get("PURPLE_SLEEP_DEMO"):
            _power_log("SHUTDOWN: demo mode, not shutting down")
            print("\n" + "=" * 50)
            print("  DEMO MODE: Would shut down here")
            print("  (Press Ctrl+C to exit)")
            print("=" * 50 + "\n")
            return True

        if not self._poweroff_available:
            _power_log("SHUTDOWN: no poweroff command found, trying anyway")

        # Two-stage watchdog (detached process group, survives TUI death):
        #   Stage 1 (5s): systemctl --force (clean ACPI shutdown)
        #   Stage 2 (8s): sysrq poweroff (direct kernel call, no filesystem needed)
        # sysrq 'o' still goes through ACPI, unlike double --force which bypasses
        # ACPI and leaves Surface keyboards lit / devices in resume limbo.
        # sysrq works even if overlayfs is dead (USB removed during live boot).
        try:
            subprocess.Popen(
                ["sh", "-c",
                 "sleep 5 && sudo systemctl poweroff --force 2>/dev/null; "
                 "sleep 3 && echo 1 > /proc/sys/kernel/sysrq && "
                 "echo o > /proc/sysrq-trigger"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass

        # --force skips clean service stop (near-instant, no data to lose).
        # Always use sudo: non-sudo systemctl lacks permission on live USB,
        # but Popen doesn't fail (it spawns successfully), so we'd falsely
        # return True. Purple user has passwordless sudo everywhere
        # (see 00-build-golden-image.sh: /etc/sudoers.d/purple-nopasswd).
        commands = [
            ["sudo", "systemctl", "poweroff", "--force"],
            ["sudo", "poweroff", "-f"],
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
