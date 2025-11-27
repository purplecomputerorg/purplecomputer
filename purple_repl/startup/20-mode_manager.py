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

        return ""  # Return empty string so IPython doesn't show None

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
    return None

def normal():
    """Switch back to normal mode"""
    global _current_mode, _talk_mode_active, _speech_mode_active
    _current_mode = None
    _talk_mode_active = False
    _speech_mode_active = False
    print("✨ Back to normal mode!")
    return None

# Helper function to sanitize text for kids (handle keyboard mashing)
def sanitize_for_speech(text):
    """Clean up text for speech - keep safe chars, remove junk"""
    import re

    # Convert to string just in case
    text = str(text)

    # Remove outer quotes if present (they're syntax, not content)
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]

    # Keep only: letters, numbers, spaces, and natural punctuation
    # Safe punctuation: ! ? . , - ' (apostrophes for contractions)
    # This prevents code injection and handles keyboard mashing
    text = re.sub(r'[^a-zA-Z0-9\s!?.,\-\'\s]+', '', text)

    # Clean up excessive whitespace
    text = ' '.join(text.split())

    # Limit length (prevent super long mashing)
    if len(text) > 200:
        text = text[:200]

    return text.strip()

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

        # Sanitize the text before speaking
        clean_text = sanitize_for_speech(text)

        # Only speak if there's actual content left
        if clean_text:
            speak(clean_text)
            return None  # Don't echo the text back
        else:
            return None
    except:
        return None

# Combined input transformer for say/talk/speech
def transform_say_and_modes(lines):
    """Handle 'say word' and talk/speech modes"""
    global _talk_mode_active, _speech_mode_active

    if not lines:
        return lines

    # Handle both string and list input
    if isinstance(lines, str):
        lines = [lines]

    if not lines or not lines[0]:
        return lines

    text = lines[0].strip()

    # First priority: Handle 'say word' syntax (works in any mode)
    import re

    # Match: say word word (before autocall transforms it)
    say_match = re.match(r'^say\s+(.+)$', text)
    if say_match:
        words = say_match.group(1).strip()
        # Skip if already has parens/quotes
        if not (words.startswith('(') or words.startswith('"') or words.startswith("'")):
            return [f'say("{words}")']

    # Also match: say(word) or say(multiple words) - after autocall has transformed it
    autocall_match = re.match(r'^say\(([^"\'()].+?)\)$', text)
    if autocall_match:
        words = autocall_match.group(1).strip()
        return [f'say("{words}")']

    # Second priority: Talk or speech mode
    if _talk_mode_active or _speech_mode_active:
        # Check if switching back to normal or changing modes
        if text in ['normal', 'talk', 'speech', 'rainbow', 'surprise', 'emoji', 'math']:
            return lines

        # Skip if it's already a function call
        if '(' in text and not text.startswith('"') and not text.startswith("'"):
            return lines

        # Handle quoted strings - extract the content
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            # Remove outer quotes
            inner_text = text[1:-1]
            return [f'say("{inner_text}")']

        # Convert input to say() call
        if text:
            return [f'say("{text}")']

    return lines

# Install combined say/talk/speech mode transformer
try:
    from IPython import get_ipython
    ip = get_ipython()
    if ip:
        ip.input_transformers_post.append(transform_say_and_modes)
except Exception:
    pass

# Load pack-based modes from registry
def load_pack_modes():
    """Load modes from installed packs"""
    try:
        # Import pack registry
        import sys
        import os
        purple_dir = os.path.expanduser('~/.purple')
        repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Add paths for imports
        if repo_dir not in sys.path:
            sys.path.insert(0, repo_dir)
        if purple_dir not in sys.path:
            sys.path.insert(0, purple_dir)

        from pack_manager import get_registry

        registry = get_registry()
        pack_modes = {}

        # Get all modes from the registry
        for mode_name, mode_func in registry.modes.items():
            # Create a simple wrapper that calls the mode function
            class _PackModeWrapper:
                def __init__(self, func, name):
                    self.func = func
                    self.name = name

                def __repr__(self):
                    """Called when accessed in IPython"""
                    self.func()
                    return ""

                def __call__(self):
                    """Allow calling as function"""
                    self.func()
                    return None

            pack_modes[mode_name] = _PackModeWrapper(mode_func, mode_name)

        return pack_modes
    except Exception as e:
        # Silently fail if pack modes can't be loaded
        return {}

# Load pack-based modes
pack_modes = load_pack_modes()

# Inject into IPython user namespace
try:
    from IPython import get_ipython
    ipython = get_ipython()
    if ipython:
        # Built-in modes
        namespace = {
            'speech': speech,
            'emoji': emoji,
            'math': math,
            'rainbow': rainbow,
            'surprise': surprise,
            'talk': talk,
            'normal': normal,
            'say': say,
        }

        # Add pack-based modes
        namespace.update(pack_modes)

        ipython.push(namespace)
except:
    pass

# Make mode functions and say available
__all__ = ['speech', 'emoji', 'math', 'rainbow', 'surprise', 'talk', 'normal', 'say'] + list(pack_modes.keys())
