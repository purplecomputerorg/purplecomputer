"""
Purple Computer - Speech Mode
Everything typed is read aloud with text-to-speech
"""

from colorama import Fore, Style
import sys
import os
import shutil
import re

# Import TTS from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tts import speak


def center_text(text):
    """
    Center text based on terminal width.
    Strips ANSI codes when calculating width.
    """
    term_width = shutil.get_terminal_size().columns
    # Strip ANSI codes for width calculation
    visible_text = re.sub(r'\033\[[0-9;]*m', '', text)
    text_width = len(visible_text)
    padding = max(0, (term_width - text_width) // 2)
    return ' ' * padding


class SpeechMode:
    """Speech mode - reads everything aloud"""

    def __init__(self):
        self.name = "Speech"
        # Build banner dynamically with centering
        lines = [
            "",
            f"{Fore.CYAN}{Style.BRIGHT}╔═══════════════════════════════════════════╗{Style.RESET_ALL}",
            f"{Fore.CYAN}{Style.BRIGHT}║                                           ║{Style.RESET_ALL}",
            f"{Fore.CYAN}{Style.BRIGHT}║         🔊 SPEECH MODE ACTIVATED 🔊       ║{Style.RESET_ALL}",
            f"{Fore.CYAN}{Style.BRIGHT}║                                           ║{Style.RESET_ALL}",
            f"{Fore.CYAN}{Style.BRIGHT}║    Everything you type will be spoken!    ║{Style.RESET_ALL}",
            f"{Fore.CYAN}{Style.BRIGHT}║                                           ║{Style.RESET_ALL}",
            f"{Fore.CYAN}{Style.BRIGHT}╚═══════════════════════════════════════════╝{Style.RESET_ALL}",
            "",
        ]
        self.banner = '\n'.join([center_text(line) + line for line in lines])

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
