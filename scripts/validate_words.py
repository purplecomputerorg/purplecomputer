#!/usr/bin/env python3
"""
Validate words.json - ensures every entry has a definition.

Usage: python scripts/validate_words.py
"""

import json
import sys
from pathlib import Path

WORDS_FILE = Path(__file__).parent.parent / "packs" / "core-words" / "content" / "words.json"


def validate():
    """Validate the words.json file"""
    if not WORDS_FILE.exists():
        print(f"ERROR: {WORDS_FILE} not found")
        return False

    with open(WORDS_FILE) as f:
        words = json.load(f)

    errors = []
    warnings = []

    for word, entry in words.items():
        # Definition is required
        if "definition" not in entry:
            errors.append(f"  {word}: missing 'definition' (required)")
        elif not entry["definition"].strip():
            errors.append(f"  {word}: empty 'definition'")

        # Emoji is optional but if present should be non-empty
        if "emoji" in entry and not entry["emoji"].strip():
            warnings.append(f"  {word}: empty 'emoji' (remove if not needed)")

    # Summary
    total = len(words)
    with_emoji = sum(1 for e in words.values() if "emoji" in e)
    without_emoji = total - with_emoji

    print(f"Words: {total} total ({with_emoji} with emoji, {without_emoji} definition-only)")
    print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(e)
        print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(w)
        print()

    if errors:
        print("FAILED: Fix errors above")
        return False
    else:
        print("PASSED: All words have definitions")
        return True


if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
