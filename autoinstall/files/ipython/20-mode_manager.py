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
_talk_mode_active = False
_speech_mode_active = False

# Create instances that auto-activate when accessed
class _AutoActivateMode:
    """Wrapper that activates mode when repr is called"""
    def __init__(self, mode_class, name):
        self.mode_class = mode_class
        self.name = name

    def __repr__(self):
        """Called when the object is displayed - activate the mode"""
        global _current_mode, _speech_mode_active
        _current_mode = self.mode_class()
        _current_mode.activate()

        # Special handling for speech mode - enable input reading
        if self.name == "speech":
            _speech_mode_active = True

        return ""  # Return empty string so nothing displays

    def __call__(self, *args):
        """Also allow being called as a function"""
        return self.__repr__()

# Create mode instances that auto-activate
speech = _AutoActivateMode(SpeechMode, "speech")
emoji = _AutoActivateMode(EmojiMode, "emoji")
math = _AutoActivateMode(MathMode, "math")
rainbow = _AutoActivateMode(RainbowMode, "rainbow")
surprise = _AutoActivateMode(SurpriseMode, "surprise")

def talk():
    """Switch to talk mode - everything you type is spoken"""
    global _talk_mode_active
    _talk_mode_active = True
    print("\n💬 TALK MODE - Everything you type will be spoken!")
    print("Type 'normal' to exit\n")
    return ""

def normal():
    """Switch back to normal mode"""
    global _current_mode, _talk_mode_active, _speech_mode_active
    _current_mode = None
    _talk_mode_active = False
    _speech_mode_active = False
    print("✨ Back to normal mode!")
    return ""

# Helper function for speaking text
def say(text):
    """Say something out loud"""
    try:
        import sys
        import os
        purple_dir = os.path.expanduser('~/.purple')
        if purple_dir not in sys.path:
            sys.path.insert(0, purple_dir)
        from tts import speak
        speak(str(text))
        return f"🔊 {text}"
    except:
        return f"🔇 (speech not available)"

# Talk/Speech mode input transformer
def transform_talk_or_speech_mode(lines):
    """In talk or speech mode, speak everything typed"""
    global _talk_mode_active, _speech_mode_active

    # Only active in talk or speech mode
    if not (_talk_mode_active or _speech_mode_active) or not lines:
        return lines

    text = lines[0].strip()

    # Check if switching back to normal or changing modes
    if text in ['normal', 'talk', 'speech', 'rainbow', 'surprise', 'emoji', 'math']:
        return lines

    # Skip if it's already a function call
    if '(' in text:
        return lines

    # Convert input to say() call
    if text:
        return [f'say("{text}")']

    return lines

# Install talk/speech mode transformer
try:
    from IPython import get_ipython
    ip = get_ipython()
    if ip:
        ip.input_transformers_post.append(transform_talk_or_speech_mode)
except:
    pass

# Inject into IPython user namespace
try:
    from IPython import get_ipython
    ipython = get_ipython()
    if ipython:
        ipython.push({
            'speech': speech,
            'emoji': emoji,
            'math': math,
            'rainbow': rainbow,
            'surprise': surprise,
            'talk': talk,
            'normal': normal,
            'say': say,
        })
except:
    pass

# Make mode functions and say available
__all__ = ['speech', 'emoji', 'math', 'rainbow', 'surprise', 'talk', 'normal', 'say']
