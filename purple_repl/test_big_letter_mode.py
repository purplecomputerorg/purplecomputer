#!/usr/bin/env python3
"""
Test script for Big Letter Mode
Verifies that Caps Lock detection and output transformation work correctly
"""

import sys
import os

# Add parent directory to path to import big_letter_mode
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'autoinstall', 'files', 'ipython'))

# Import the big_letter_mode module
import importlib.util
spec = importlib.util.spec_from_file_location(
    "big_letter_mode",
    os.path.join(os.path.dirname(__file__), '..', 'autoinstall', 'files', 'ipython', '00-big_letter_mode.py')
)
big_letter_mode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(big_letter_mode)

# Import functions from the module
is_mostly_uppercase = big_letter_mode.is_mostly_uppercase
detect_caps_lock_toggle = big_letter_mode.detect_caps_lock_toggle
uppercase_output = big_letter_mode.uppercase_output
get_big_letter_mode = big_letter_mode.get_big_letter_mode
set_big_letter_mode = big_letter_mode.set_big_letter_mode


def test_is_mostly_uppercase():
    """Test the is_mostly_uppercase function"""
    print("Testing is_mostly_uppercase()...")

    # All uppercase
    assert is_mostly_uppercase("HELLO WORLD") == True
    assert is_mostly_uppercase("ABC123") == True
    assert is_mostly_uppercase("TESTING!!!") == True

    # All lowercase
    assert is_mostly_uppercase("hello world") == False
    assert is_mostly_uppercase("abc123") == False

    # Mixed (should be False if less than 70% uppercase)
    assert is_mostly_uppercase("Hello World") == False
    assert is_mostly_uppercase("HeLLo") == False  # 3/5 = 60% uppercase
    assert is_mostly_uppercase("HELLO") == True  # 5/5 = 100% uppercase

    # Edge cases
    assert is_mostly_uppercase("123 456") == False  # No letters
    assert is_mostly_uppercase("") == False  # Empty
    assert is_mostly_uppercase("   ") == False  # Only spaces

    print("  ✓ is_mostly_uppercase tests passed")


def test_uppercase_output():
    """Test the uppercase_output function"""
    print("Testing uppercase_output()...")

    # Enable big letter mode for this test
    set_big_letter_mode(True)

    # String
    assert uppercase_output("hello") == "HELLO"

    # List
    result = uppercase_output(["hello", "world"])
    assert result == ["HELLO", "WORLD"]

    # Tuple
    result = uppercase_output(("hello", "world"))
    assert result == ("HELLO", "WORLD")

    # Dict
    result = uppercase_output({"key": "value"})
    assert result == {"KEY": "VALUE"}

    # Number (converted to string)
    assert uppercase_output(123) == "123"

    # Disable big letter mode
    set_big_letter_mode(False)

    # Should return unchanged when mode is off
    assert uppercase_output("hello") == "hello"

    print("  ✓ uppercase_output tests passed")


def test_toggle_detection():
    """Test Caps Lock toggle detection"""
    print("Testing Caps Lock toggle detection...")

    # Reset state by setting the mode to False
    set_big_letter_mode(False)
    # Also reset the tracking variable by simulating lowercase input first
    detect_caps_lock_toggle("initialization")

    # Simulate typing in lowercase (Caps Lock OFF)
    print("  Simulating lowercase input...")
    detect_caps_lock_toggle("hello world")
    assert get_big_letter_mode() == False

    # Simulate typing in uppercase (Caps Lock ON)
    print("  Simulating uppercase input (should trigger BIG LETTERS ON)...")
    detect_caps_lock_toggle("HELLO WORLD")
    assert get_big_letter_mode() == True

    # Continue with uppercase (should stay on, no toggle message)
    detect_caps_lock_toggle("MORE TEXT")
    assert get_big_letter_mode() == True

    # Switch back to lowercase (Caps Lock OFF)
    print("  Simulating lowercase input (should trigger big letters off)...")
    detect_caps_lock_toggle("back to normal")
    assert get_big_letter_mode() == False

    print("  ✓ Toggle detection tests passed")


def test_manual_control():
    """Test manual set_big_letter_mode function"""
    print("Testing manual control...")

    # Manual enable
    print("  Testing manual enable...")
    set_big_letter_mode(True)
    assert get_big_letter_mode() == True

    # Manual disable
    print("  Testing manual disable...")
    set_big_letter_mode(False)
    assert get_big_letter_mode() == False

    print("  ✓ Manual control tests passed")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Big Letter Mode Test Suite")
    print("=" * 60)
    print()

    try:
        test_is_mostly_uppercase()
        print()

        test_uppercase_output()
        print()

        test_toggle_detection()
        print()

        test_manual_control()
        print()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print()
        print("=" * 60)
        print("✗ TEST FAILED")
        print("=" * 60)
        print(f"Error: {e}")
        return 1

    except Exception as e:
        print()
        print("=" * 60)
        print("✗ UNEXPECTED ERROR")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
