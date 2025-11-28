"""
Purple Computer - Rainbow Mode
Colorful, vibrant output with rainbow colors
"""

from colorama import Fore, Style
import sys
import os

# Import emoji_lib from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from emoji_lib import rainbow_text, rainbow_pattern, box_border, get_visual_width
import shutil


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
        """Create a colorful rainbow banner with rainbow colored border"""
        content_lines = [
            "",
            "🌈 RAINBOW MODE ACTIVATED 🌈",
            "",
            "Everything is colorful!",
            "",
        ]

        # Create the box without color first
        from emoji_lib import box_border
        import re

        # Box drawing characters
        tl, tr, bl, br = '╔', '╗', '╚', '╝'
        h, v = '═', '║'

        # Calculate max visual width of content
        max_width = 0
        for line in content_lines:
            width = get_visual_width(line)
            max_width = max(max_width, width)

        # Build the box with rainbow colors
        result = ["\n"]

        # Top border (rainbow colored)
        top = tl + (h * (max_width + 2)) + tr
        color = self.colors[0]
        result.append(f"{color}{Style.BRIGHT}{top}{Style.RESET_ALL}")

        # Content lines (rainbow colored borders)
        for i, line in enumerate(content_lines):
            visual_width = get_visual_width(line)
            padding_needed = max_width - visual_width
            padded_line = f"{v} {line}{' ' * padding_needed} {v}"
            color = self.colors[(i + 1) % len(self.colors)]
            result.append(f"{color}{Style.BRIGHT}{padded_line}{Style.RESET_ALL}")

        # Bottom border (rainbow colored)
        bottom = bl + (h * (max_width + 2)) + br
        color = self.colors[(len(content_lines) + 1) % len(self.colors)]
        result.append(f"{color}{Style.BRIGHT}{bottom}{Style.RESET_ALL}")

        # Center everything
        term_width = shutil.get_terminal_size().columns
        centered = []
        for line in result:
            visual_width = get_visual_width(line)
            padding = max(0, (term_width - visual_width) // 2)
            centered.append(' ' * padding + line)

        return '\n'.join(centered)

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
