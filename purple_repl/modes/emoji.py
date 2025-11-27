"""
Purple Computer - Emoji Mode
Converts words to emoji automatically
"""

from colorama import Fore, Style
import shutil
import re


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


class EmojiMode:
    """Emoji mode - converts words to emoji"""

    def __init__(self):
        self.name = "Emoji"
        # Build banner dynamically with centering
        lines = [
            "",
            f"{Fore.YELLOW}{Style.BRIGHT}╔═══════════════════════════════════════════╗{Style.RESET_ALL}",
            f"{Fore.YELLOW}{Style.BRIGHT}║                                           ║{Style.RESET_ALL}",
            f"{Fore.YELLOW}{Style.BRIGHT}║          ✨ EMOJI MODE ACTIVATED ✨       ║{Style.RESET_ALL}",
            f"{Fore.YELLOW}{Style.BRIGHT}║                                           ║{Style.RESET_ALL}",
            f"{Fore.YELLOW}{Style.BRIGHT}║      Type words and see them become       ║{Style.RESET_ALL}",
            f"{Fore.YELLOW}{Style.BRIGHT}║              emoji magic!                 ║{Style.RESET_ALL}",
            f"{Fore.YELLOW}{Style.BRIGHT}║                                           ║{Style.RESET_ALL}",
            f"{Fore.YELLOW}{Style.BRIGHT}╚═══════════════════════════════════════════╝{Style.RESET_ALL}",
            "",
        ]
        self.banner = '\n'.join([center_text(line) + line for line in lines])

        # Word to emoji mapping
        self.word_map = {
            # Animals
            'cat': '🐱', 'cats': '🐱🐱🐱',
            'dog': '🐶', 'dogs': '🐶🐶🐶',
            'monkey': '🐵', 'lion': '🦁', 'tiger': '🐯',
            'cow': '🐮', 'pig': '🐷', 'frog': '🐸',
            'bird': '🐦', 'chicken': '🐔', 'penguin': '🐧',
            'fish': '🐠', 'whale': '🐋', 'dolphin': '🐬',
            'butterfly': '🦋', 'bee': '🐝', 'bug': '🐛',

            # Nature
            'tree': '🌳', 'trees': '🌳🌳🌳',
            'flower': '🌸', 'flowers': '🌸🌸🌸',
            'rose': '🌹', 'sunflower': '🌻',
            'rainbow': '🌈', 'sun': '☀️', 'moon': '🌙',
            'star': '⭐', 'stars': '⭐⭐⭐',
            'cloud': '☁️', 'clouds': '☁️☁️☁️',
            'fire': '🔥', 'water': '💧',

            # Food
            'apple': '🍎', 'banana': '🍌', 'orange': '🍊',
            'lemon': '🍋', 'grape': '🍇', 'strawberry': '🍓',
            'pizza': '🍕', 'burger': '🍔', 'hotdog': '🌭',
            'cake': '🍰', 'cookie': '🍪', 'donut': '🍩',
            'icecream': '🍦', 'candy': '🍬',

            # Objects
            'ball': '⚽', 'balloon': '🎈', 'gift': '🎁',
            'book': '📚', 'pencil': '✏️', 'paint': '🎨',
            'music': '🎵', 'bell': '🔔', 'key': '🔑',
            'crown': '👑', 'rocket': '🚀', 'car': '🚗',
            'train': '🚂', 'airplane': '✈️', 'boat': '⛵',

            # Feelings
            'happy': '😄', 'sad': '😢', 'love': '😍',
            'laugh': '😂', 'cool': '😎', 'party': '🥳',
            'heart': '❤️', 'hearts': '💕💕💕',

            # Actions
            'yes': '✅', 'no': '❌', 'ok': '👌',
            'good': '👍', 'bad': '👎', 'clap': '👏',
            'wave': '👋',

            # Common words
            'hello': '👋', 'hi': '👋',
            'goodbye': '👋', 'bye': '👋',
            'thanks': '🙏', 'thank you': '🙏',
            'please': '🥺',
        }

    def activate(self):
        """Called when entering emoji mode"""
        print(self.banner)
        print(f"{Fore.GREEN}Try typing: cat, dog, rainbow, heart, rocket!{Style.RESET_ALL}\n")

    def convert_to_emoji(self, text):
        """Convert words to emoji"""
        words = text.lower().split()
        result = []

        for word in words:
            # Remove common punctuation
            clean_word = word.strip('.,!?;:')

            if clean_word in self.word_map:
                result.append(self.word_map[clean_word])
            else:
                result.append(word)

        return ' '.join(result)

    def process_input(self, text):
        """Process input before execution"""
        # Don't convert if it looks like code (has parentheses, equals, etc.)
        if any(char in text for char in '()=[]{}'):
            return text

        # Convert words to emoji
        converted = self.convert_to_emoji(text)
        if converted != text:
            print(f"{Fore.MAGENTA}✨ {converted}{Style.RESET_ALL}")
            return f'"{converted}"'  # Return as a string to display

        return text

    def process_output(self, result):
        """Process output before display"""
        return result


# Create a global instance
_emoji_mode = EmojiMode()


def EmojiMode():
    """Factory function for emoji mode"""
    return _emoji_mode
