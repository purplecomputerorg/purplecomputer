"""
Purple Computer - Unified Keyboard Handling

Centralizes all keyboard input strategies:
- Shift strategies: sticky shift (grace period), double-tap, regular shift
- Caps lock detection (direct from hardware or terminal fallback)
- Long-hold detection for parent mode (Escape)
- F-key mode switching (F1-F4, F12)

On Linux with evdev: uses KeyboardNormalizer for hardware-level detection
On Mac/fallback: uses terminal-level detection with reduced robustness
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum


# ============================================================================
# Shift Strategies
# ============================================================================

# Characters that can be shifted via double-tap
SHIFT_MAP = {
    '-': '_', '=': '+', '[': '{', ']': '}', '\\': '|',
    ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
    '`': '~',
    # Numbers are NOT included - they're used in math expressions
}

# Reverse map for checking if a character is a shifted version
UNSHIFT_MAP = {v: k for k, v in SHIFT_MAP.items()}


@dataclass
class ShiftState:
    """
    Unified shift state tracking.

    Supports multiple shift strategies that can be used together:
    1. Sticky shift: Toggle on, stays on for grace period or until used
    2. Double-tap: Same key twice quickly = shifted version
    3. Regular shift: Physical shift key held (from hardware layer)
    """
    # Sticky shift state
    sticky_active: bool = False
    sticky_activated_at: float = 0.0
    sticky_grace_period: float = 1.0  # seconds

    # Double-tap state
    last_char: Optional[str] = None
    last_char_time: float = 0.0
    double_tap_threshold: float = 0.5  # seconds

    # Physical shift (from hardware layer)
    physical_shift_held: bool = False

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

    def check_double_tap(self, char: str) -> Optional[str]:
        """
        Check if this character completes a double-tap.

        Returns the shifted character if double-tap detected, None otherwise.
        Also updates tracking state for next check.
        """
        now = time.time()

        if char in SHIFT_MAP:
            if (self.last_char == char and
                (now - self.last_char_time) < self.double_tap_threshold):
                # Double-tap detected!
                self.last_char = None
                return SHIFT_MAP[char]
            else:
                # First tap - remember it
                self.last_char = char
                self.last_char_time = now
        else:
            # Different character - reset
            self.last_char = None

        return None

    def reset(self) -> None:
        """Reset all shift state."""
        self.sticky_active = False
        self.sticky_activated_at = 0.0
        self.last_char = None
        self.last_char_time = 0.0
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
