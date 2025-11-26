"""
Purple Computer - Speech Mode
Everything typed is read aloud with text-to-speech
"""

from colorama import Fore, Style
import sys
import os

# Import TTS from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tts import speak


class SpeechMode:
    """Speech mode - reads everything aloud"""

    def __init__(self):
        self.name = "Speech"
        self.banner = f"""
{Fore.CYAN}{Style.BRIGHT}
╔═══════════════════════════════════════════╗
║                                           ║
║         🔊 SPEECH MODE ACTIVATED 🔊       ║
║                                           ║
║    Everything you type will be spoken!    ║
║                                           ║
╚═══════════════════════════════════════════╝
{Style.RESET_ALL}
"""

    def activate(self):
        """Called when entering speech mode"""
        print(self.banner)
        print("Type 'normal' to exit\n")
        speak("Speech mode activated! I will read everything you type.")

    def process_input(self, text):
        """Process input before execution"""
        # Speak the input
        if text.strip():
            speak(text)
        return text

    def process_output(self, result):
        """Process output before display"""
        # Output is already spoken by display hook
        return result


# Create a global instance
_speech_mode = SpeechMode()


def SpeechMode():
    """Factory function for speech mode"""
    return _speech_mode
