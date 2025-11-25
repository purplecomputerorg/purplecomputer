"""
Purple Computer - Surprise Mode
Random fun and delightful chaos!
"""

from colorama import Fore, Style
import random
import sys
import os

# Import utilities from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from emoji_lib import (
    random_emoji, random_pattern, heart_pattern,
    star_pattern, tree_pattern, rainbow_pattern
)


class SurpriseMode:
    """Surprise mode - random delightful things!"""

    def __init__(self):
        self.name = "Surprise"
        self.banner = f"""
{Fore.MAGENTA}{Style.BRIGHT}
╔═══════════════════════════════════════════╗
║                                           ║
║        ✨ SURPRISE MODE ACTIVATED ✨      ║
║                                           ║
║          Expect the unexpected!           ║
║                                           ║
╚═══════════════════════════════════════════╝
{Style.RESET_ALL}
"""

        self.surprises = [
            self._emoji_explosion,
            self._color_dance,
            self._pattern_show,
            self._emoji_rain,
            self._rainbow_message,
            self._random_compliment,
        ]

    def activate(self):
        """Called when entering surprise mode"""
        print(self.banner)
        print(f"{Fore.YELLOW}✨ Anything can happen! ✨{Style.RESET_ALL}\n")

        # Do a random surprise
        surprise = random.choice(self.surprises)
        surprise()

    def _emoji_explosion(self):
        """Show an explosion of random emoji"""
        print(f"{Fore.YELLOW}💥 EMOJI EXPLOSION! 💥{Style.RESET_ALL}\n")
        for _ in range(5):
            print(random_pattern(20))
        print()

    def _color_dance(self):
        """Show colorful dancing text"""
        colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.BLUE, Fore.MAGENTA]
        message = "✨ ★ SURPRISE! ★ ✨"

        for _ in range(3):
            for color in colors:
                print(f"\r{color}{Style.BRIGHT}{message}{Style.RESET_ALL}", end='', flush=True)
            print()

    def _pattern_show(self):
        """Show a random pattern"""
        patterns = [heart_pattern, star_pattern, tree_pattern, rainbow_pattern]
        pattern_func = random.choice(patterns)
        print(pattern_func())

    def _emoji_rain(self):
        """Make it rain emoji"""
        emoji = random_emoji()
        print(f"{Fore.CYAN}It's raining {emoji}!{Style.RESET_ALL}\n")

        for i in range(1, 8):
            spaces = " " * random.randint(0, 10)
            count = random.randint(1, 5)
            print(f"{spaces}{emoji * count}")

        print()

    def _rainbow_message(self):
        """Show a rainbow colored message"""
        messages = [
            "You're amazing!",
            "Keep exploring!",
            "You're so creative!",
            "That's wonderful!",
            "You're doing great!",
            "How magical!",
            "Wow, look at you go!",
        ]

        message = random.choice(messages)
        colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.BLUE, Fore.MAGENTA]

        result = []
        for i, char in enumerate(message):
            color = colors[i % len(colors)]
            result.append(f"{color}{Style.BRIGHT}{char}")

        print(''.join(result) + Style.RESET_ALL)
        print()

    def _random_compliment(self):
        """Give a random compliment with emoji"""
        compliments = [
            ("You're a star!", "⭐"),
            ("You're brilliant!", "💡"),
            ("You rock!", "🎸"),
            ("You're super!", "🦸"),
            ("You're wonderful!", "🌟"),
            ("You're fantastic!", "🎆"),
            ("You're awesome!", "😎"),
        ]

        compliment, emoji = random.choice(compliments)
        print(f"{Fore.MAGENTA}{emoji} {compliment} {emoji}{Style.RESET_ALL}\n")

    def random_surprise(self):
        """Trigger a random surprise"""
        surprise = random.choice(self.surprises)
        surprise()

    def process_input(self, text):
        """Process input - sometimes add surprises!"""

        # 30% chance of a random surprise
        if random.random() < 0.3:
            self.random_surprise()

        return text

    def process_output(self, result):
        """Process output - make it fun!"""

        # Sometimes add emoji decoration
        if result is not None and random.random() < 0.5:
            emoji = random_emoji()
            print(f"{emoji} {result} {emoji}")
            return None

        return result


# Create a global instance
_surprise_mode = SurpriseMode()


def SurpriseMode():
    """Factory function for surprise mode"""
    return _surprise_mode
