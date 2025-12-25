"""
Purple Computer: Unified Keyboard Handling

Centralizes all keyboard input strategies:
- Shift strategies: sticky shift (grace period), double-tap, regular shift
- Caps lock detection (direct from hardware or terminal fallback)
- Long-hold detection for parent mode (Escape)
- F-key mode switching (F1-F3, F12)

On Linux with evdev: uses KeyboardNormalizer for hardware-level detection
On Mac/fallback: uses terminal-level detection with reduced robustness
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum


# ============================================================================
# Double-Tap Detection
# ============================================================================

# Characters that can be shifted via double-tap
SHIFT_MAP = {
    '-': '_', '=': '+', '[': '{', ']': '}', '\\': '|',
    ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
    '`': '~',
    # Numbers are NOT included. They're used in math expressions
}

# Reverse map for checking if a character is a shifted version
UNSHIFT_MAP = {v: k for k, v in SHIFT_MAP.items()}


class DoubleTapDetector:
    """
    Detects double-tap of the same key/character within a time threshold.

    Pure logic class with no I/O. Timestamp is injected for deterministic testing.

    Usage:
        detector = DoubleTapDetector(threshold=0.4, allowed_keys={'a', 'b', '-'})
        result = detector.check('a', timestamp=0.0)  # None (first tap)
        result = detector.check('a', timestamp=0.2)  # 'a' (double-tap detected!)
        result = detector.check('a', timestamp=0.8)  # None (too slow, new first tap)

    For evdev (keycodes):
        detector = DoubleTapDetector(threshold=0.4, allowed_keys={30, 31, 32})
        result = detector.check(30, timestamp=0.0)  # None
        result = detector.check(30, timestamp=0.2)  # 30 (double-tap!)

    Args:
        threshold: Maximum seconds between taps for double-tap detection
        allowed_keys: Set of keys that can trigger double-tap (None = all keys)
    """

    DEFAULT_THRESHOLD = 0.4  # seconds

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        allowed_keys: set = None,
    ):
        self.threshold = threshold
        self.allowed_keys = allowed_keys
        self._last_key = None
        self._last_time: float = 0.0

    def check(self, key, timestamp: float = None) -> bool:
        """
        Check if this key press completes a double-tap.

        Args:
            key: The key/character pressed (any hashable type)
            timestamp: Current time in seconds (uses time.time() if None)

        Returns:
            True if double-tap detected, False otherwise.
            Caller is responsible for applying the shift transformation.
        """
        if timestamp is None:
            timestamp = time.time()

        # Filter to allowed keys if specified
        if self.allowed_keys is not None and key not in self.allowed_keys:
            self._last_key = None
            return False

        # Check for double-tap
        if self._last_key == key and (timestamp - self._last_time) < self.threshold:
            # Double-tap detected!
            self._last_key = None  # Reset to prevent triple-tap
            return True

        # First tap or new key: remember it
        self._last_key = key
        self._last_time = timestamp
        return False

    def reset(self) -> None:
        """Reset detector state."""
        self._last_key = None
        self._last_time = 0.0


# ============================================================================
# Shift Strategies
# ============================================================================


class ShiftState:
    """
    Unified shift state tracking.

    Supports multiple shift strategies that can be used together:
    1. Sticky shift: Toggle on, stays on for grace period or until used
    2. Double-tap: Same key twice quickly = shifted version
    3. Regular shift: Physical shift key held (from hardware layer)
    """

    def __init__(
        self,
        sticky_grace_period: float = 1.0,
        double_tap_threshold: float = 0.5,
    ):
        # Sticky shift state
        self.sticky_active: bool = False
        self.sticky_activated_at: float = 0.0
        self.sticky_grace_period: float = sticky_grace_period

        # Double-tap detector (uses SHIFT_MAP keys as allowed set)
        self._double_tap = DoubleTapDetector(
            threshold=double_tap_threshold,
            allowed_keys=set(SHIFT_MAP.keys()),
        )

        # Physical shift (from hardware layer)
        self.physical_shift_held: bool = False

    @property
    def double_tap_threshold(self) -> float:
        """Get double-tap threshold."""
        return self._double_tap.threshold

    @double_tap_threshold.setter
    def double_tap_threshold(self, value: float) -> None:
        """Set double-tap threshold."""
        self._double_tap.threshold = value

    def should_shift(self) -> bool:
        """Check if next character should be shifted."""
        # Physical shift always works
        if self.physical_shift_held:
            return True

        # Sticky shift with grace period
        if self.sticky_active:
            elapsed = time.time() - self.sticky_activated_at
            if elapsed <= self.sticky_grace_period:
                return True
            else:
                # Grace period expired
                self.sticky_active = False

        return False

    def toggle_sticky(self) -> bool:
        """Toggle sticky shift. Returns new state."""
        self.sticky_active = not self.sticky_active
        if self.sticky_active:
            self.sticky_activated_at = time.time()
        return self.sticky_active

    def consume_sticky(self) -> None:
        """Consume sticky shift after using it for one character."""
        self.sticky_active = False

    def check_double_tap(self, char: str, timestamp: float = None) -> Optional[str]:
        """
        Check if this character completes a double-tap.

        Returns the shifted character if double-tap detected, None otherwise.
        """
        if self._double_tap.check(char, timestamp):
            return SHIFT_MAP.get(char)
        return None

    def reset(self) -> None:
        """Reset all shift state."""
        self.sticky_active = False
        self.sticky_activated_at = 0.0
        self._double_tap.reset()
        self.physical_shift_held = False


# ============================================================================
# Caps Lock
# ============================================================================

@dataclass
class CapsState:
    """
    Caps lock state tracking.

    On Linux: Detected directly from hardware via evdev
    On Mac/fallback: Not reliably detectable, starts off
    """
    caps_lock_on: bool = False

    # Callbacks to notify when caps changes
    _on_change: Optional[Callable[[bool], None]] = None

    def toggle(self) -> bool:
        """Toggle caps lock state. Returns new state."""
        self.caps_lock_on = not self.caps_lock_on
        if self._on_change:
            self._on_change(self.caps_lock_on)
        return self.caps_lock_on

    def set(self, on: bool) -> None:
        """Set caps lock state explicitly."""
        if on != self.caps_lock_on:
            self.caps_lock_on = on
            if self._on_change:
                self._on_change(self.caps_lock_on)

    def on_change(self, callback: Callable[[bool], None]) -> None:
        """Register callback for caps lock changes."""
        self._on_change = callback


# ============================================================================
# Long-Hold Detection
# ============================================================================

@dataclass
class HoldState:
    """
    Tracks key holds for triggering actions (like Escape for parent mode).
    """
    key: Optional[str] = None
    start_time: float = 0.0
    triggered: bool = False
    threshold: float = 1.0  # seconds

    def start(self, key: str) -> None:
        """Start tracking a key hold."""
        if key != self.key:
            self.key = key
            self.start_time = time.time()
            self.triggered = False

    def check(self, key: str) -> bool:
        """
        Check if hold threshold reached for given key.
        Returns True if threshold reached (only once per hold).
        """
        if key != self.key:
            self.reset()
            return False

        if self.triggered:
            return False  # Already triggered this hold

        elapsed = time.time() - self.start_time
        if elapsed >= self.threshold:
            self.triggered = True
            return True

        return False

    def reset(self) -> None:
        """Reset hold tracking."""
        self.key = None
        self.start_time = 0.0
        self.triggered = False


# ============================================================================
# Unified Keyboard State
# ============================================================================

class KeyboardMode(Enum):
    """Keyboard operation mode."""
    LINUX_EVDEV = "linux_evdev"  # Full hardware access
    TERMINAL_FALLBACK = "terminal_fallback"  # Mac/non-evdev


@dataclass
class KeyboardState:
    """
    Unified keyboard state for Purple Computer.

    Combines all keyboard tracking in one place:
    - Shift strategies
    - Caps lock
    - Long-hold detection
    - Mode (evdev vs fallback)
    """
    shift: ShiftState = field(default_factory=ShiftState)
    caps: CapsState = field(default_factory=CapsState)
    escape_hold: HoldState = field(default_factory=lambda: HoldState(threshold=1.0))
    mode: KeyboardMode = KeyboardMode.TERMINAL_FALLBACK

    def process_char(self, char: str, apply_shift: bool = True) -> str:
        """
        Process a character through shift strategies.

        Args:
            char: The raw character typed
            apply_shift: Whether to apply shift transformations

        Returns:
            The processed character (possibly shifted)
        """
        if not apply_shift or not char:
            return char

        # Check double-tap first (highest priority)
        shifted = self.shift.check_double_tap(char)
        if shifted:
            return shifted

        # Check if we should shift this character
        if self.shift.should_shift() and char in SHIFT_MAP:
            self.shift.consume_sticky()  # Use up sticky shift
            return SHIFT_MAP[char]

        # For letters, apply caps lock
        if char.isalpha() and self.caps.caps_lock_on:
            return char.upper()

        return char

    def handle_caps_lock_press(self) -> None:
        """Handle caps lock key press."""
        self.caps.toggle()

    def handle_sticky_shift_press(self) -> bool:
        """Handle sticky shift toggle key. Returns new sticky state."""
        return self.shift.toggle_sticky()

    def handle_escape_press(self) -> bool:
        """
        Handle escape key press for long-hold detection.
        Returns True if long-hold threshold reached (parent mode).
        """
        self.escape_hold.start("escape")
        return False  # Will return True on repeat when threshold reached

    def handle_escape_repeat(self) -> bool:
        """Handle escape key repeat. Returns True if threshold reached."""
        return self.escape_hold.check("escape")

    def handle_escape_release(self) -> None:
        """Handle escape key release."""
        self.escape_hold.reset()


# ============================================================================
# Factory Functions
# ============================================================================

def create_keyboard_state(
    sticky_grace_period: float = 1.0,
    double_tap_threshold: float = 0.5,
    escape_hold_threshold: float = 1.0,
) -> KeyboardState:
    """
    Create a new KeyboardState with custom timing parameters.

    Args:
        sticky_grace_period: How long sticky shift stays active (seconds)
        double_tap_threshold: Max time between taps for double-tap (seconds)
        escape_hold_threshold: How long to hold Escape for parent mode (seconds)
    """
    state = KeyboardState()
    state.shift.sticky_grace_period = sticky_grace_period
    state.shift.double_tap_threshold = double_tap_threshold
    state.escape_hold.threshold = escape_hold_threshold
    return state


def detect_keyboard_mode() -> KeyboardMode:
    """
    Detect which keyboard mode is available.

    Returns LINUX_EVDEV if evdev is available and we have permissions,
    otherwise TERMINAL_FALLBACK.
    """
    try:
        import evdev
        # Try to list devices - will fail without permissions
        devices = evdev.list_devices()
        if devices:
            return KeyboardMode.LINUX_EVDEV
    except (ImportError, PermissionError, OSError):
        pass

    return KeyboardMode.TERMINAL_FALLBACK


# ============================================================================
# Keyboard Normalizer Subprocess Management
# ============================================================================

import subprocess
import sys
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Virtual device name created by KeyboardNormalizer
NORMALIZER_DEVICE_NAME = "Purple Keyboard Normalizer"


def is_normalizer_running() -> bool:
    """
    Check if KeyboardNormalizer is already running.

    Looks for the virtual keyboard device it creates.
    """
    try:
        import evdev
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                if NORMALIZER_DEVICE_NAME in device.name:
                    return True
            except (PermissionError, OSError):
                continue
    except ImportError:
        pass
    return False


def find_normalizer_script() -> Optional[Path]:
    """Find the keyboard_normalizer.py script."""
    # Look relative to this file's location
    this_dir = Path(__file__).parent
    candidates = [
        this_dir.parent / "keyboard_normalizer.py",  # Project root
        Path("/opt/purple/keyboard_normalizer.py"),  # Installed location
        Path.home() / "purple" / "keyboard_normalizer.py",  # User location
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


def launch_keyboard_normalizer() -> Optional[subprocess.Popen]:
    """
    Launch KeyboardNormalizer as a background subprocess.

    Returns the Popen object if successful, None if failed or not needed.
    This function is designed to fail gracefully. It won't crash the app
    if the normalizer can't be started.
    """
    # Only relevant on Linux with evdev
    if detect_keyboard_mode() != KeyboardMode.LINUX_EVDEV:
        logger.debug("Not on Linux/evdev, skipping keyboard normalizer")
        return None

    # Check if already running
    if is_normalizer_running():
        logger.debug("Keyboard normalizer already running")
        return None

    # Find the script
    script_path = find_normalizer_script()
    if not script_path:
        logger.warning("Could not find keyboard_normalizer.py")
        return None

    # Launch as subprocess
    try:
        # Use the same Python interpreter
        python = sys.executable

        # Start the normalizer (it will grab the keyboard and run forever)
        process = subprocess.Popen(
            [python, str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            # Don't inherit stdin - we don't want it to compete for keyboard
            stdin=subprocess.DEVNULL,
            # Start in new process group so it doesn't get signals meant for TUI
            start_new_session=True,
        )

        # Give it a moment to start and check if it failed immediately
        import time
        time.sleep(0.2)

        if process.poll() is not None:
            # Process already exited - check stderr for error
            stderr = process.stderr.read().decode() if process.stderr else ""
            if "Permission denied" in stderr:
                logger.warning(
                    "Keyboard normalizer failed: permission denied. "
                    "Run with root or add user to 'input' group."
                )
            else:
                logger.warning(f"Keyboard normalizer failed to start: {stderr[:200]}")
            return None

        logger.info("Keyboard normalizer started successfully")
        return process

    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"Failed to start keyboard normalizer: {e}")
        return None


def stop_keyboard_normalizer(process: Optional[subprocess.Popen]) -> None:
    """Stop the keyboard normalizer subprocess if running."""
    if process is None:
        return

    try:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        logger.debug("Keyboard normalizer stopped")
    except (OSError, ProcessLookupError):
        pass  # Already stopped
