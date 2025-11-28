"""
Purple Computer - Math Mode
Visual counting and simple math with emoji
"""

from colorama import Fore, Style
import sys
import os

# Import emoji_lib from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from emoji_lib import count_to, show_math, box_border


class MathMode:
    """Math mode - visual counting and patterns"""

    def __init__(self):
        self.name = "Math"
        # Build banner using box_border utility
        content_lines = [
            "",
            "🔢 MATH MODE ACTIVATED 🔢",
            "",
            "Count, add, and multiply visually!",
            "",
        ]
        self.banner = "\n" + box_border(
            content_lines,
            style='double',
            color=Fore.GREEN + Style.BRIGHT,
            center=True
        ) + "\n"

    def activate(self):
        """Called when entering math mode"""
        print(self.banner)
        print(f"{Fore.GREEN}Try these:{Style.RESET_ALL}")
        print(f"  • {Fore.YELLOW}count(5){Style.RESET_ALL} - Count to 5")
        print(f"  • {Fore.YELLOW}add(3, 2){Style.RESET_ALL} - Add visually")
        print(f"  • {Fore.YELLOW}multiply(4, 3){Style.RESET_ALL} - Multiply visually")
        print()

        # Add helper functions to global namespace
        try:
            from IPython import get_ipython
            ipython = get_ipython()

            if ipython:
                # Add math helper functions
                ipython.user_ns['count'] = self.count
                ipython.user_ns['add'] = self.add
                ipython.user_ns['subtract'] = self.subtract
                ipython.user_ns['multiply'] = self.multiply

        except Exception:
            pass

    def count(self, n, emoji="⭐"):
        """Count to n with emoji"""
        print(count_to(n, emoji))
        return f"Counted to {n}!"

    def add(self, a, b, emoji="🟣"):
        """Show addition visually"""
        if not isinstance(a, int) or not isinstance(b, int):
            return "Please use whole numbers!"

        if a < 0 or b < 0:
            return "Please use positive numbers!"

        if a > 20 or b > 20:
            return "Those numbers are too big! Try smaller ones."

        print(show_math(a, b, '+'))
        return f"{a} + {b} = {a + b}"

    def subtract(self, a, b, emoji="🟣"):
        """Show subtraction visually"""
        if not isinstance(a, int) or not isinstance(b, int):
            return "Please use whole numbers!"

        if a < b:
            return f"Can't take {b} from {a}! Try the other way around."

        if a > 20 or b > 20:
            return "Those numbers are too big! Try smaller ones."

        print(show_math(a, b, '-'))
        return f"{a} - {b} = {a - b}"

    def multiply(self, a, b, emoji="🟣"):
        """Show multiplication visually"""
        if not isinstance(a, int) or not isinstance(b, int):
            return "Please use whole numbers!"

        if a < 0 or b < 0:
            return "Please use positive numbers!"

        if a > 10 or b > 10:
            return "Those numbers are too big! Try smaller ones."

        print(show_math(a, b, '*'))
        return f"{a} × {b} = {a * b}"

    def process_input(self, text):
        """Process input before execution"""
        return text

    def process_output(self, result):
        """Process output before display"""
        return result


# Create a global instance
_math_mode = MathMode()


def MathMode():
    """Factory function for math mode"""
    return _math_mode
