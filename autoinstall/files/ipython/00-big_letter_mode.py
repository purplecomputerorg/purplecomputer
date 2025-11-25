"""
Purple Computer IPython Startup - Big Letter Mode
Detects Caps Lock and transforms output to uppercase when active
"""

# Global state for big letter mode
_big_letter_mode = False
_last_input_was_uppercase = False


def is_mostly_uppercase(text):
    """
    Check if text is mostly uppercase (indicating Caps Lock is on).
    Ignores numbers, spaces, and punctuation.
    """
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False

    uppercase_count = sum(1 for c in letters if c.isupper())
    # Consider it uppercase if more than 70% of letters are uppercase
    return uppercase_count / len(letters) > 0.7


def detect_caps_lock_toggle(cell_text):
    """
    Detect if Caps Lock has been toggled based on input case pattern.
    Updates the global big_letter_mode state and prints toggle messages.
    """
    global _big_letter_mode, _last_input_was_uppercase

    # Skip empty or whitespace-only input
    if not cell_text or not cell_text.strip():
        return

    current_is_uppercase = is_mostly_uppercase(cell_text)

    # Detect transition from lowercase to uppercase (Caps Lock turned ON)
    if current_is_uppercase and not _last_input_was_uppercase:
        _big_letter_mode = True
        _last_input_was_uppercase = True
        print("\n🔠 BIG LETTERS ON\n")

    # Detect transition from uppercase to lowercase (Caps Lock turned OFF)
    elif not current_is_uppercase and _last_input_was_uppercase:
        _big_letter_mode = False
        _last_input_was_uppercase = False
        print("\n🔡 big letters off\n")

    # Update tracking state
    else:
        _last_input_was_uppercase = current_is_uppercase


def uppercase_output(obj):
    """
    Transform output to uppercase if big_letter_mode is active.
    """
    if not _big_letter_mode:
        return obj

    # Handle different object types
    if isinstance(obj, str):
        return obj.upper()
    elif isinstance(obj, (list, tuple)):
        return type(obj)(uppercase_output(item) for item in obj)
    elif isinstance(obj, dict):
        return {uppercase_output(k): uppercase_output(v) for k, v in obj.items()}
    else:
        # For other types, convert to string and uppercase
        return str(obj).upper()


def install_big_letter_mode():
    """
    Install Big Letter Mode hooks into IPython.
    """
    try:
        from IPython import get_ipython
        ipython = get_ipython()

        if not ipython:
            return

        # Hook 1: Detect Caps Lock state before code execution
        def pre_run_cell_hook(info):
            """Called before each cell execution"""
            detect_caps_lock_toggle(info.raw_cell)

        ipython.events.register('pre_run_cell', pre_run_cell_hook)

        # Hook 2: Transform output to uppercase when big_letter_mode is on
        original_displayhook = ipython.displayhook

        class BigLetterDisplayHook:
            """Custom display hook that uppercases output in big letter mode"""

            def __init__(self, original):
                self.original = original

            def __call__(self, obj):
                if obj is not None and _big_letter_mode:
                    # Transform the object before displaying
                    obj = uppercase_output(obj)
                return self.original(obj)

        ipython.displayhook = BigLetterDisplayHook(original_displayhook)

    except Exception as e:
        # Silently fail if IPython is not available
        pass


# Install the hooks
install_big_letter_mode()


def get_big_letter_mode():
    """Get the current state of big letter mode"""
    return _big_letter_mode


def set_big_letter_mode(enabled):
    """
    Manually set big letter mode state.
    This is a helper for testing or manual control.
    """
    global _big_letter_mode
    _big_letter_mode = enabled
    if enabled:
        print("\n🔠 BIG LETTERS ON\n")
    else:
        print("\n🔡 big letters off\n")


# Make the state accessor available
__all__ = ['get_big_letter_mode', 'set_big_letter_mode']
