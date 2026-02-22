"""
Purple Computer: Unified Keyboard Handling

Requires Linux with evdev for direct keyboard access.
Reads raw key events via EvdevReader, processes through KeyboardStateMachine.

Features:
- Shift strategies: sticky shift (grace period), physical shift
- Caps lock toggle (double-tap Shift key)
- Long-hold detection for parent mode (Escape held > 1s)
- Space-hold for paint mode line drawing (release detection via evdev)
- F-key mode switching (F1-F3) and toggles (F9 theme, F10-F12 volume)

See guides/keyboard-architecture.md for architecture details.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from enum import Enum

from .constants import SUPPORT_EMAIL, MODE_EXPLORE, MODE_PLAY, MODE_DOODLE


# ============================================================================
# Shift Maps and Double-Tap Detection
# ============================================================================

# Characters that can be shifted (same as physical shift)
SHIFT_MAP = {
    # Letters
    'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E', 'f': 'F', 'g': 'G',
    'h': 'H', 'i': 'I', 'j': 'J', 'k': 'K', 'l': 'L', 'm': 'M', 'n': 'N',
    'o': 'O', 'p': 'P', 'q': 'Q', 'r': 'R', 's': 'S', 't': 'T', 'u': 'U',
    'v': 'V', 'w': 'W', 'x': 'X', 'y': 'Y', 'z': 'Z',
    # Number row symbols
    '1': '!', '2': '@', '3': '#', '4': '$', '5': '%',
    '6': '^', '7': '&', '8': '*', '9': '(', '0': ')',
    '-': '_', '=': '+',
    # Other symbols
    '[': '{', ']': '}', '\\': '|',
    ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
    '`': '~',
}

# Reverse map for checking if a character is a shifted version
UNSHIFT_MAP = {v: k for k, v in SHIFT_MAP.items()}


class DoubleTapDetector:
    """
    Detects double-tap of the same key/character within a time threshold.

    Pure logic class with no I/O. Timestamp is injected for deterministic testing.

    Double-tap only triggers when the FIRST tap comes after a pause or space,
    preventing accidental capitals when typing repeated letters like "pp" in "apple".

    Usage:
        detector = DoubleTapDetector(threshold=0.4, allowed_keys={'a', 'b', '-'})
        # After a pause, double-tap works:
        result = detector.check('a', timestamp=0.0, eligible=True)   # False (first tap)
        result = detector.check('a', timestamp=0.2, eligible=False)  # True! (double-tap)
        # Mid-word, double-tap is blocked:
        result = detector.check('p', timestamp=0.5, eligible=False)  # False (first tap, not eligible)
        result = detector.check('p', timestamp=0.7, eligible=False)  # False (blocked, first tap wasn't eligible)

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
        self._first_tap_eligible: bool = False  # Was first tap after pause/space?

    def check(self, key, timestamp: float = None, eligible: bool = True) -> bool:
        """
        Check if this key press completes a double-tap.

        Args:
            key: The key/character pressed (any hashable type)
            timestamp: Current time in seconds (uses time.time() if None)
            eligible: Whether this tap is "eligible" (after pause or space).
                      Only matters for the FIRST tap of a potential double-tap.
                      The second tap's eligibility is ignored.

        Returns:
            True if double-tap detected, False otherwise.
            Caller is responsible for applying the shift transformation.
        """
        if timestamp is None:
            timestamp = time.time()

        # Filter to allowed keys if specified
        if self.allowed_keys is not None and key not in self.allowed_keys:
            self._last_key = None
            self._first_tap_eligible = False
            return False

        # Check for double-tap (requires first tap to have been eligible)
        if (self._last_key == key and
            (timestamp - self._last_time) < self.threshold and
            self._first_tap_eligible):
            # Double-tap detected!
            self._last_key = None  # Reset to prevent triple-tap
            self._first_tap_eligible = False
            return True

        # First tap or new key: remember it and its eligibility
        self._last_key = key
        self._last_time = timestamp
        self._first_tap_eligible = eligible
        return False

    def reset(self) -> None:
        """Reset detector state."""
        self._last_key = None
        self._last_time = 0.0
        self._first_tap_eligible = False


# ============================================================================
# Key Repeat Suppression
# ============================================================================


class KeyRepeatSuppressor:
    """
    Suppresses key repeat when a key is held down.

    Pure logic class with no I/O. Timestamp is injected for deterministic testing.

    Usage:
        suppressor = KeyRepeatSuppressor(threshold=0.1)
        suppressor.should_suppress('a', timestamp=0.0)   # False (first press)
        suppressor.should_suppress('a', timestamp=0.05)  # True (repeat, suppress)
        suppressor.should_suppress('a', timestamp=0.15)  # True (still repeating)
        suppressor.should_suppress('b', timestamp=0.20)  # False (different key)

    Works with any key identifier (characters, key names like 'backspace', etc.)
    """

    DEFAULT_THRESHOLD = 0.1  # 100ms between same key = repeat

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold
        self._last_key: str | None = None
        self._last_time: float = 0.0
        self._suppressing: bool = False

    def should_suppress(
        self,
        key: str,
        timestamp: float | None = None,
    ) -> bool:
        """
        Check if this key event should be suppressed (is a repeat).

        Args:
            key: Key identifier (character or key name like 'backspace')
            timestamp: Event time (uses time.time() if not provided)

        Returns:
            True if key should be suppressed (is a repeat), False otherwise
        """
        if timestamp is None:
            timestamp = time.time()

        # Different key: not a repeat
        if key != self._last_key:
            self._last_key = key
            self._last_time = timestamp
            self._suppressing = False
            return False

        # Same key within threshold: suppress
        if (timestamp - self._last_time) < self.threshold:
            self._last_time = timestamp  # Update time for continuous hold
            self._suppressing = True
            return True

        # Same key but enough time passed: allow (user lifted and pressed again)
        self._last_time = timestamp
        self._suppressing = False
        return False

    def reset(self) -> None:
        """Reset suppressor state."""
        self._last_key = None
        self._last_time = 0.0
        self._suppressing = False


# ============================================================================
# Shift Strategies
# ============================================================================


class ShiftState:
    """
    Unified shift state tracking.

    Supports multiple shift strategies that can be used together:
    1. Sticky shift: Toggle on, stays on for grace period or until used
    2. Regular shift: Physical shift key held (from hardware layer)
    """

    def __init__(
        self,
        sticky_grace_period: float = 1.0,
    ):
        # Sticky shift state
        self.sticky_active: bool = False
        self.sticky_activated_at: float = 0.0
        self.sticky_grace_period: float = sticky_grace_period

        # Physical shift (from hardware layer)
        self.physical_shift_held: bool = False

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

    def reset(self) -> None:
        """Reset all shift state."""
        self.sticky_active = False
        self.sticky_activated_at = 0.0
        self.physical_shift_held = False


# ============================================================================
# Caps Lock
# ============================================================================

@dataclass
class CapsState:
    """
    Caps lock state tracking.

    Detected directly from hardware via evdev.
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
    """Keyboard operation mode. Currently only evdev is supported."""
    LINUX_EVDEV = "linux_evdev"  # Full hardware access via evdev


@dataclass
class KeyboardState:
    """
    Unified keyboard state for Purple Computer.

    Combines all keyboard tracking in one place:
    - Shift strategies
    - Caps lock
    - Long-hold detection

    Requires evdev (Linux) for proper keyboard handling.
    """
    shift: ShiftState = field(default_factory=ShiftState)
    caps: CapsState = field(default_factory=CapsState)
    escape_hold: HoldState = field(default_factory=lambda: HoldState(threshold=1.0))
    mode: KeyboardMode = KeyboardMode.LINUX_EVDEV

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
    escape_hold_threshold: float = 1.0,
) -> KeyboardState:
    """
    Create a new KeyboardState with custom timing parameters.

    Args:
        sticky_grace_period: How long sticky shift stays active (seconds)
        escape_hold_threshold: How long to hold Escape for parent mode (seconds)
    """
    state = KeyboardState()
    state.shift.sticky_grace_period = sticky_grace_period
    state.escape_hold.threshold = escape_hold_threshold
    return state


def detect_keyboard_mode() -> KeyboardMode:
    """
    Verify evdev is available. Raises RuntimeError if not.

    Purple Computer requires evdev (Linux) for direct keyboard access.
    """
    try:
        import evdev
        devices = evdev.list_devices()
        if devices:
            return KeyboardMode.LINUX_EVDEV
    except ImportError:
        raise RuntimeError(
            "Purple Computer needs to be set up before it can run.\n\n"
            f"Please contact {SUPPORT_EMAIL} for help.\n\n"
            "(Technical: evdev library not installed)"
        )
    except PermissionError:
        raise RuntimeError(
            "Purple Computer doesn't have permission to use the keyboard.\n\n"
            "Please restart your Purple Computer. If this keeps happening,\n"
            f"contact {SUPPORT_EMAIL}\n\n"
            "(Technical: user not in 'input' group)"
        )
    except OSError as e:
        raise RuntimeError(
            "Purple Computer had trouble accessing the keyboard.\n\n"
            "Please restart your Purple Computer. If this keeps happening,\n"
            f"contact {SUPPORT_EMAIL}\n\n"
            f"(Technical: {e})"
        )

    raise RuntimeError(
        "Could not find your keyboard.\n"
        "Please make sure a keyboard is connected.\n\n"
        f"If this keeps happening, contact {SUPPORT_EMAIL}"
    )


# ============================================================================
# Keyboard State Machine
# ============================================================================

import logging
from typing import List
from .input import RawKeyEvent, KeyCode

logger = logging.getLogger(__name__)


class KeyAction:
    """Base class for keyboard actions emitted by the state machine."""
    pass


@dataclass
class CharacterAction(KeyAction):
    """A printable character was typed."""
    char: str
    shifted: bool = False  # Was the character transformed (by shift, caps, or double-tap)?
    shift_held: bool = False  # Was physical shift key held? (not caps lock)
    is_repeat: bool = False  # Is this a key repeat?
    arrow_held: str | None = None  # Arrow direction held when this action fired


@dataclass
class NavigationAction(KeyAction):
    """Arrow key movement."""
    direction: str  # 'up', 'down', 'left', 'right'
    space_held: bool = False  # True when painting (space down)
    is_repeat: bool = False  # Is this a key repeat?
    other_arrows_held: set = field(default_factory=set)  # Other arrow directions currently held


@dataclass
class ModeAction(KeyAction):
    """Mode switch requested."""
    mode: str  # 'explore' (F1), 'play' (F2), 'doodle' (F3), 'parent' (long Escape)


@dataclass
class ControlAction(KeyAction):
    """Control key action."""
    action: str  # 'backspace', 'enter', 'tab', 'escape', 'space'
    is_down: bool = True  # Key press (True) or release (False)
    arrow_held: str | None = None  # Arrow direction held when this action fired
    is_repeat: bool = False  # Is this a key repeat?


@dataclass
class ShiftAction(KeyAction):
    """Shift key state change."""
    is_down: bool


@dataclass
class CapsLockAction(KeyAction):
    """Caps lock toggled."""
    pass


@dataclass
class LongHoldAction(KeyAction):
    """Long hold threshold reached."""
    key: str  # e.g., 'escape'


class KeyboardStateMachine:
    """
    Consumes RawKeyEvent from EvdevReader, produces high-level KeyAction.

    Handles:
    - Key state tracking (pressed/released)
    - Modifier state (shift, caps lock)
    - Sticky shift (quick-tap Shift key)
    - Double-tap Shift for caps lock toggle
    - Long-hold detection (Escape for parent mode)
    - Space-hold detection (for paint mode drawing)
    - Character translation (keycode to character)

    Usage:
        state_machine = KeyboardStateMachine()

        async def handle_raw(event: RawKeyEvent):
            for action in state_machine.process(event):
                await handle_action(action)

        reader = EvdevReader(handle_raw)
        await reader.start()
    """

    # Timing thresholds
    ESCAPE_HOLD_THRESHOLD = 1.0  # seconds for parent mode
    STICKY_SHIFT_GRACE = 1.0     # seconds sticky shift stays active

    def __init__(self):
        # Key press state: keycode -> timestamp
        self._pressed: dict[int, float] = {}

        # Modifier state
        self._shift_held = False
        self._caps_lock_on = False
        self._space_held = False

        # Sticky shift
        self._sticky_shift_active = False
        self._sticky_shift_time = 0.0
        self._shift_used_for_char = False  # Track if physical shift was used for a character

        # Double-tap Shift key for caps lock
        self._shift_double_tap = DoubleTapDetector(
            threshold=0.4,
            allowed_keys={'shift'},
        )
        self._on_sticky_shift_change: Callable[[bool], None] | None = None

        # Long-hold tracking for Escape
        self._escape_hold_triggered = False
        self._escape_press_time: float | None = None  # time.time() when escape pressed

    def on_sticky_shift_change(self, callback: Callable[[bool], None]) -> None:
        """Register callback for sticky shift state changes."""
        self._on_sticky_shift_change = callback

    def process(self, event: RawKeyEvent) -> List[KeyAction]:
        """
        Process a raw key event and return a list of actions.

        Most events produce 0-1 actions, but some (like character with
        double-tap) may produce multiple.
        """
        actions = []

        if event.is_down:
            actions.extend(self._handle_key_down(event))
        else:
            actions.extend(self._handle_key_up(event))

        return actions

    def _handle_key_down(self, event: RawKeyEvent) -> List[KeyAction]:
        """Handle key press or repeat."""
        actions = []
        keycode = event.keycode
        timestamp = event.timestamp
        is_repeat = event.is_repeat

        # Track pressed state (only on fresh press, not repeat)
        if not is_repeat:
            self._pressed[keycode] = timestamp

        # Handle modifiers (only on fresh press)
        if not is_repeat:
            if keycode in (KeyCode.KEY_LEFTSHIFT, KeyCode.KEY_RIGHTSHIFT, KeyCode.KEY_CAPSLOCK):
                self._shift_held = True
                actions.append(ShiftAction(is_down=True))
                return actions

        # Handle Escape (only on fresh press for long-hold tracking)
        if keycode == KeyCode.KEY_ESC:
            if not is_repeat:
                self._escape_hold_triggered = False
                self._escape_press_time = time.time()  # Use wall clock for consistent timing
            actions.append(ControlAction(action='escape', is_down=True, is_repeat=is_repeat))
            return actions

        # Handle Space
        if keycode == KeyCode.KEY_SPACE:
            if not is_repeat:
                self._space_held = True
            actions.append(ControlAction(
                action='space',
                is_down=True,
                arrow_held=self.held_arrow_direction,
                is_repeat=is_repeat,
            ))
            return actions

        # Handle arrow keys (repeats allowed, supports diagonal movement)
        arrow_directions = {
            KeyCode.KEY_UP: 'up',
            KeyCode.KEY_DOWN: 'down',
            KeyCode.KEY_LEFT: 'left',
            KeyCode.KEY_RIGHT: 'right',
        }
        if keycode in arrow_directions:
            direction = arrow_directions[keycode]
            other_arrows = self.all_held_arrows() - {direction}
            actions.append(NavigationAction(
                direction=direction,
                space_held=self._space_held,
                is_repeat=is_repeat,
                other_arrows_held=other_arrows,
            ))
            return actions

        # Handle other control keys (repeats allowed)
        if keycode == KeyCode.KEY_BACKSPACE:
            actions.append(ControlAction(action='backspace', is_down=True, is_repeat=is_repeat))
            return actions
        if keycode == KeyCode.KEY_ENTER:
            actions.append(ControlAction(action='enter', is_down=True, is_repeat=is_repeat))
            return actions
        if keycode == KeyCode.KEY_TAB:
            actions.append(ControlAction(action='tab', is_down=True, is_repeat=is_repeat))
            return actions

        # Handle F-keys for mode switching and volume (no repeats)
        if not is_repeat:
            if keycode == KeyCode.KEY_F1:
                actions.append(ModeAction(mode=MODE_EXPLORE[0]))
                return actions
            if keycode == KeyCode.KEY_F2:
                actions.append(ModeAction(mode=MODE_PLAY[0]))
                return actions
            if keycode == KeyCode.KEY_F3:
                actions.append(ModeAction(mode=MODE_DOODLE[0]))
                return actions
            if keycode == KeyCode.KEY_F9:
                actions.append(ControlAction(action='theme_toggle', is_down=True))
                return actions
            if keycode == KeyCode.KEY_F10:
                actions.append(ControlAction(action='volume_mute', is_down=True))
                return actions
            if keycode == KeyCode.KEY_F11:
                actions.append(ControlAction(action='volume_down', is_down=True))
                return actions
            if keycode == KeyCode.KEY_F12:
                actions.append(ControlAction(action='volume_up', is_down=True))
                return actions

        # Handle printable characters
        char = event.char
        if char:
            # Apply shift/caps
            final_char = self._apply_shift(char)
            actions.append(CharacterAction(
                char=final_char,
                shifted=(final_char != char),
                shift_held=self._shift_held,
                is_repeat=is_repeat,
                arrow_held=self.held_arrow_direction,
            ))

            # Track if physical shift was used for this character (prevents sticky activation)
            if self._shift_held and not is_repeat:
                self._shift_used_for_char = True

            # Consume sticky shift (only on fresh press)
            if not is_repeat and self._sticky_shift_active:
                self._sticky_shift_active = False
                if self._on_sticky_shift_change:
                    self._on_sticky_shift_change(False)

        return actions

    def _handle_key_up(self, event: RawKeyEvent) -> List[KeyAction]:
        """Handle key release."""
        actions = []
        keycode = event.keycode

        # Remove from pressed state
        press_time = self._pressed.pop(keycode, None)

        # Handle modifier releases (Shift keys and Caps Lock, which is remapped to Shift)
        if keycode in (KeyCode.KEY_LEFTSHIFT, KeyCode.KEY_RIGHTSHIFT, KeyCode.KEY_CAPSLOCK):
            # Check for sticky shift or double-tap caps lock (quick tap, only if shift wasn't used for a character)
            if press_time and not self._shift_used_for_char:
                hold_duration = event.timestamp - press_time
                if hold_duration < 0.3:  # Quick tap
                    if self._shift_double_tap.check('shift', event.timestamp):
                        # Double-tap shift: toggle caps lock
                        self._sticky_shift_active = False
                        if self._on_sticky_shift_change:
                            self._on_sticky_shift_change(False)
                        self._caps_lock_on = not self._caps_lock_on
                        actions.append(CapsLockAction())
                    else:
                        # Single tap: activate sticky shift
                        self._sticky_shift_active = True
                        self._sticky_shift_time = event.timestamp
                        if self._on_sticky_shift_change:
                            self._on_sticky_shift_change(True)
            self._shift_held = False
            self._shift_used_for_char = False  # Reset for next shift press
            actions.append(ShiftAction(is_down=False))
            return actions

        # Handle Escape release (check for long-hold)
        # Uses dedicated _escape_press_time (wall clock) instead of _pressed dict (evdev timestamp)
        # to avoid race conditions with the timer-based check in check_escape_hold().
        # Both mechanisms now use time.time() consistently.
        if keycode == KeyCode.KEY_ESC:
            if self._escape_press_time is not None:
                hold_duration = time.time() - self._escape_press_time
                if hold_duration >= self.ESCAPE_HOLD_THRESHOLD and not self._escape_hold_triggered:
                    self._escape_hold_triggered = True
                    actions.append(LongHoldAction(key='escape'))
                    actions.append(ModeAction(mode='parent'))
                self._escape_press_time = None  # Clear on release
            actions.append(ControlAction(action='escape', is_down=False))
            return actions

        # Handle Space release
        if keycode == KeyCode.KEY_SPACE:
            self._space_held = False
            actions.append(ControlAction(action='space', is_down=False))
            return actions

        # Handle other control key releases
        if keycode == KeyCode.KEY_BACKSPACE:
            actions.append(ControlAction(action='backspace', is_down=False))
            return actions

        return actions

    def _apply_shift(self, char: str) -> str:
        """Apply shift/caps transformations to a character."""
        should_shift = self._shift_held

        # Check sticky shift with grace period
        if self._sticky_shift_active:
            elapsed = time.time() - self._sticky_shift_time
            if elapsed <= self.STICKY_SHIFT_GRACE:
                should_shift = True
            else:
                self._sticky_shift_active = False
                if self._on_sticky_shift_change:
                    self._on_sticky_shift_change(False)

        if should_shift and char in SHIFT_MAP:
            return SHIFT_MAP[char]

        # Apply caps lock to letters
        if char.isalpha() and self._caps_lock_on:
            return char.upper()

        return char

    def check_escape_hold(self, threshold: float | None = None) -> bool:
        """
        Check if Escape is currently held past threshold.
        Call this periodically (e.g., every 100ms) while Escape is pressed.
        Returns True once when threshold is first reached.

        Args:
            threshold: Custom threshold in seconds. If None, uses default (1.0s).
                       Custom thresholds don't set the triggered flag, allowing
                       multiple thresholds to be checked independently.
        """
        # Use dedicated escape press time (set with time.time() for consistency)
        if self._escape_press_time is None:
            return False

        elapsed = time.time() - self._escape_press_time

        # Custom threshold: just check elapsed time (no triggered flag)
        if threshold is not None:
            return elapsed >= threshold

        # Default threshold: use triggered flag to fire only once
        if self._escape_hold_triggered:
            return False  # Already triggered

        if elapsed >= self.ESCAPE_HOLD_THRESHOLD:
            self._escape_hold_triggered = True
            return True

        return False

    @property
    def space_held(self) -> bool:
        """Check if space is currently held."""
        return self._space_held

    @property
    def shift_held(self) -> bool:
        """Check if shift is currently held."""
        return self._shift_held

    @property
    def caps_lock_on(self) -> bool:
        """Check if caps lock is on."""
        return self._caps_lock_on

    @property
    def held_arrow_direction(self) -> str | None:
        """Get the currently held arrow direction, if any."""
        arrow_keys = [
            (KeyCode.KEY_UP, 'up'),
            (KeyCode.KEY_DOWN, 'down'),
            (KeyCode.KEY_LEFT, 'left'),
            (KeyCode.KEY_RIGHT, 'right'),
        ]
        for keycode, direction in arrow_keys:
            if keycode in self._pressed:
                return direction
        return None

    def all_held_arrows(self) -> set[str]:
        """Get all currently held arrow directions as a set."""
        arrow_keys = [
            (KeyCode.KEY_UP, 'up'),
            (KeyCode.KEY_DOWN, 'down'),
            (KeyCode.KEY_LEFT, 'left'),
            (KeyCode.KEY_RIGHT, 'right'),
        ]
        held = set()
        for keycode, direction in arrow_keys:
            if keycode in self._pressed:
                held.add(direction)
        return held

    def reset(self) -> None:
        """Reset all state."""
        self._pressed.clear()
        self._shift_held = False
        self._caps_lock_on = False
        self._space_held = False
        self._sticky_shift_active = False
        self._shift_double_tap.reset()
        self._escape_hold_triggered = False
        self._escape_press_time = None
