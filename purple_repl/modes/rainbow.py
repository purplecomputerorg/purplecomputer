"""
Purple Computer - Rainbow Mode
Colorful, vibrant output with rainbow colors
"""

from colorama import Fore, Style
import sys
import os
import shutil
import re

# Import emoji_lib from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from emoji_lib import rainbow_text, rainbow_pattern


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


class RainbowMode:
    """Rainbow mode - everything is colorful!"""

    def __init__(self):
        self.name = "Rainbow"
        self.colors = [
            Fore.RED, Fore.YELLOW, Fore.GREEN,
            Fore.CYAN, Fore.BLUE, Fore.MAGENTA
        ]
        self.banner = self._make_rainbow_banner()

    def _make_rainbow_banner(self):
        """Create a colorful rainbow banner"""
        lines = [
            "╔═══════════════════════════════════════════╗",
            "║                                           ║",
            "║        🌈 RAINBOW MODE ACTIVATED 🌈       ║",
            "║                                           ║",
            "║         Everything is colorful!           ║",
            "║                                           ║",
            "╚═══════════════════════════════════════════╝",
        ]

        result = ["\n"]  # Start with newline
        for i, line in enumerate(lines):
            color = self.colors[i % len(self.colors)]
            colored_line = f"{color}{Style.BRIGHT}{line}{Style.RESET_ALL}"
            result.append(center_text(colored_line) + colored_line)

        return '\n'.join(result)

    def activate(self):
        """Called when entering rainbow mode"""
        print(self.banner)
        print()
        print(rainbow_pattern())
        print()
        print(rainbow_text("Everything you type will be colorful!"))
        print()

    def colorize(self, text):
        """Make text rainbow colored"""
        result = []
        color_index = 0

        for char in str(text):
            if char.strip():  # Only color non-whitespace
                color = self.colors[color_index % len(self.colors)]
                result.append(f"{color}{char}")
                color_index += 1
            else:
                result.append(char)

        result.append(Style.RESET_ALL)
        return ''.join(result)

    def process_input(self, text):
        """Process input before execution"""
        # Don't interfere with code execution
        return text

    def process_output(self, result):
        """Process output before display"""
        # Colorize the output
        if result is not None:
            colored = self.colorize(result)
            print(colored)
            return None  # Prevent double printing

        return result


# Create a global instance
_rainbow_mode = RainbowMode()


def RainbowMode():
    """Factory function for rainbow mode"""
    return _rainbow_mode
