"""
Purple Computer IPython Startup - Emoji Variables
Loads emoji from pack registry into the global namespace
"""

import sys
import os
from pathlib import Path

# Add purple_repl to path
purple_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if purple_dir not in sys.path:
    sys.path.insert(0, purple_dir)

# Load emoji from registry
try:
    from pack_manager import get_registry

    registry = get_registry()
    all_emoji = registry.get_all_emoji()

    # Add all registered emoji to globals
    globals().update(all_emoji)

    # Build __all__ from registry
    __all__ = list(all_emoji.keys())

except Exception:
    # Fallback: if registry isn't available, provide some defaults
    # This ensures Purple Computer works even without packs

    # Core emoji that should always be available
    cat = "🐱"
    dog = "🐶"
    heart = "❤️"
    star = "⭐"
    rainbow = "🌈"
    rocket = "🚀"
    sparkle = "✨"
    smile = "😊"
    tree = "🌳"
    flower = "🌸"

    __all__ = ['cat', 'dog', 'heart', 'star', 'rainbow', 'rocket',
               'sparkle', 'smile', 'tree', 'flower']
