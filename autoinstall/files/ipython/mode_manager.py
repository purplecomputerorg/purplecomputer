"""
Purple Computer IPython Startup - Mode Manager
Registers mode switching functions that kids can call
"""

import sys
import os

# Add the purple directory to path so we can import our modules
purple_dir = os.path.expanduser('~/.purple')
if purple_dir not in sys.path:
    sys.path.insert(0, purple_dir)

# Import mode classes (will be created in purple_repl/modes/)
try:
    from modes.speech import SpeechMode
    from modes.emoji import EmojiMode
    from modes.math import MathMode
    from modes.rainbow import RainbowMode
    from modes.surprise import SurpriseMode
except ImportError:
    # Fallback if modes aren't available yet
    class DummyMode:
        def __init__(self, name):
            self.name = name
        def activate(self):
            print(f"🎨 {self.name} mode activated!")

    SpeechMode = lambda: DummyMode("Speech")
    EmojiMode = lambda: DummyMode("Emoji")
    MathMode = lambda: DummyMode("Math")
    RainbowMode = lambda: DummyMode("Rainbow")
    SurpriseMode = lambda: DummyMode("Surprise")

# Global current mode
_current_mode = None

def speech():
    """Switch to speech mode - everything is read aloud"""
    global _current_mode
    _current_mode = SpeechMode()
    _current_mode.activate()

def emoji():
    """Switch to emoji mode - words become pictures"""
    global _current_mode
    _current_mode = EmojiMode()
    _current_mode.activate()

def math():
    """Switch to math mode - counting and patterns"""
    global _current_mode
    _current_mode = MathMode()
    _current_mode.activate()

def rainbow():
    """Switch to rainbow mode - colorful output"""
    global _current_mode
    _current_mode = RainbowMode()
    _current_mode.activate()

def surprise():
    """Switch to surprise mode - random fun!"""
    global _current_mode
    _current_mode = SurpriseMode()
    _current_mode.activate()

def normal():
    """Switch back to normal mode"""
    global _current_mode
    _current_mode = None
    print("✨ Back to normal mode!")

# Make mode functions available
__all__ = ['speech', 'emoji', 'math', 'rainbow', 'surprise', 'normal']
