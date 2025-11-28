"""
Purple Computer Emoji Library
Extended emoji utilities and pattern generators
"""

import random
from colorama import Fore, Style


# Pattern generators
def repeat(emoji, count=5):
    """Repeat an emoji multiple times"""
    if not isinstance(count, int) or count < 0:
        count = 5
    if count > 100:  # Safety limit
        count = 100
    return emoji * count


def line(emoji, count=10):
    """Create a line of emoji"""
    return repeat(emoji, count)


def grid(emoji, rows=3, cols=5):
    """Create a grid of emoji"""
    if rows > 20 or cols > 20:  # Safety limits
        rows, cols = min(rows, 20), min(cols, 20)

    result = []
    for _ in range(rows):
        result.append(emoji * cols)
    return '\n'.join(result)


def pattern(*emojis):
    """Create a pattern from multiple emoji"""
    if not emojis:
        return ""
    return ''.join(emojis)


def rainbow_text(text):
    """Make text colorful like a rainbow"""
    colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.BLUE, Fore.MAGENTA]
    result = []
    for i, char in enumerate(text):
        color = colors[i % len(colors)]
        result.append(f"{color}{char}")
    result.append(Style.RESET_ALL)
    return ''.join(result)


def random_emoji():
    """Return a random emoji from our collection"""
    all_emojis = [
        # Animals
        "🐱", "🐶", "🐵", "🦁", "🐯", "🐮", "🐷", "🐸",
        "🐦", "🐔", "🐧", "🐠", "🐋", "🐬", "🦋", "🐝",

        # Nature
        "🌳", "🌸", "🌹", "🌻", "🌈", "☀️", "🌙", "⭐",
        "☁️", "🔥", "💧",

        # Food
        "🍎", "🍌", "🍊", "🍋", "🍇", "🍓", "🍒", "🍑",
        "🍕", "🍔", "🌭", "🌮", "🍰", "🍪", "🍩", "🍦",

        # Objects
        "⚽", "🎈", "🎁", "📚", "✏️", "🎨", "🎵", "🔔",
        "🚀", "🚗", "🚂", "✈️", "⛵", "🚲",

        # Symbols
        "❤️", "💕", "✨", "✅", "⭐", "🌟",

        # Faces
        "😊", "😄", "😂", "😍", "😎", "🤔", "😮", "🥳",
    ]
    return random.choice(all_emojis)


def random_pattern(length=10):
    """Generate a random pattern of emoji"""
    return ''.join(random_emoji() for _ in range(min(length, 50)))


def get_visual_width(text):
    """
    Get the visual width of text, accounting for emoji and wide characters.
    Uses wcwidth library for proper terminal width calculation.
    """
    import re

    # Strip ANSI codes first
    text = re.sub(r'\033\[[0-9;]*m', '', text)

    try:
        import wcwidth
        return wcwidth.wcswidth(text)
    except ImportError:
        # Fallback if wcwidth not available - just return length
        # This won't be perfect but will work
        return len(text)


def border(emoji, text=""):
    """Create a border around text with emoji"""
    if not text:
        return emoji * 20

    lines = text.split('\n')
    max_len = max(len(line) for line in lines) if lines else 0
    border_line = emoji * (max_len + 4)

    result = [border_line]
    for line in lines:
        padding = ' ' * (max_len - len(line))
        result.append(f"{emoji} {line}{padding} {emoji}")
    result.append(border_line)

    return '\n'.join(result)


def box_border(lines, style='double', color=None, center=True):
    """
    Create a box border around text lines with proper emoji width handling.

    Args:
        lines: List of text lines to put in the box
        style: 'single', 'double', or 'thick'
        color: Colorama color (e.g., Fore.CYAN + Style.BRIGHT)
        center: Whether to center the box on screen

    Returns:
        String with the bordered box
    """
    import re
    import shutil

    # Box drawing characters
    if style == 'double':
        tl, tr, bl, br = '╔', '╗', '╚', '╝'
        h, v = '═', '║'
    elif style == 'thick':
        tl, tr, bl, br = '┏', '┓', '┗', '┛'
        h, v = '━', '┃'
    else:  # single
        tl, tr, bl, br = '┌', '┐', '└', '┘'
        h, v = '─', '│'

    # Calculate max visual width of content
    max_width = 0
    for line in lines:
        width = get_visual_width(line)
        max_width = max(max_width, width)

    # Build the box
    result = []

    # Top border
    top = tl + (h * (max_width + 2)) + tr
    if color:
        top = color + top + Style.RESET_ALL
    result.append(top)

    # Content lines
    for line in lines:
        # Strip ANSI for width calculation but keep in output
        visual_width = get_visual_width(line)
        padding_needed = max_width - visual_width
        padded_line = f"{v} {line}{' ' * padding_needed} {v}"
        if color:
            padded_line = color + padded_line + Style.RESET_ALL
        result.append(padded_line)

    # Bottom border
    bottom = bl + (h * (max_width + 2)) + br
    if color:
        bottom = color + bottom + Style.RESET_ALL
    result.append(bottom)

    # Center if requested
    if center:
        term_width = shutil.get_terminal_size().columns
        centered = []
        for line in result:
            visual_width = get_visual_width(line)
            padding = max(0, (term_width - visual_width) // 2)
            centered.append(' ' * padding + line)
        return '\n'.join(centered)

    return '\n'.join(result)


def heart_pattern():
    """Create a heart pattern"""
    return """
  💜💜💜     💜💜💜
💜💜💜💜💜 💜💜💜💜💜
💜💜💜💜💜💜💜💜💜💜💜
💜💜💜💜💜💜💜💜💜💜💜
  💜💜💜💜💜💜💜💜💜
    💜💜💜💜💜💜💜
      💜💜💜💜💜
        💜💜💜
          💜
"""


def star_pattern():
    """Create a star pattern"""
    return """
        ⭐
       ⭐⭐⭐
      ⭐⭐⭐⭐⭐
     ⭐⭐⭐⭐⭐⭐⭐
    ⭐⭐⭐⭐⭐⭐⭐⭐⭐
       ⭐⭐⭐
       ⭐⭐⭐
       ⭐⭐⭐
"""


def tree_pattern():
    """Create a tree pattern"""
    return """
        🌟
       🌲🌲🌲
      🌲🌲🌲🌲🌲
     🌲🌲🌲🌲🌲🌲🌲
    🌲🌲🌲🌲🌲🌲🌲🌲🌲
        🟫🟫
        🟫🟫
"""


def rainbow_pattern():
    """Create a rainbow pattern"""
    return """
🔴🔴🔴🔴🔴🔴🔴🔴🔴🔴
🟠🟠🟠🟠🟠🟠🟠🟠🟠🟠
🟡🟡🟡🟡🟡🟡🟡🟡🟡🟡
🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢
🔵🔵🔵🔵🔵🔵🔵🔵🔵🔵
🟣🟣🟣🟣🟣🟣🟣🟣🟣🟣
"""


# Emoji counting helpers for math mode
def count_to(n, emoji="⭐"):
    """Count from 1 to n using emoji"""
    if not isinstance(n, int) or n < 1:
        n = 10
    if n > 50:  # Safety limit
        n = 50

    result = []
    for i in range(1, n + 1):
        result.append(f"{i}: {emoji * i}")
    return '\n'.join(result)


def show_math(a, b, op='+'):
    """Show math visually with emoji"""
    emoji = "🟣"  # Purple circles

    if op == '+':
        result = f"{emoji * a} + {emoji * b} = {emoji * (a + b)}"
    elif op == '-' and a >= b:
        result = f"{emoji * a} - {emoji * b} = {emoji * (a - b)}"
    elif op == '*':
        lines = [emoji * a for _ in range(b)]
        result = f"{a} × {b} =\n" + '\n'.join(lines) + f"\n= {emoji * (a * b)}"
    else:
        result = "🤔 Try + or * with small numbers!"

    return result


# Export all functions
__all__ = [
    'repeat', 'line', 'grid', 'pattern', 'rainbow_text',
    'random_emoji', 'random_pattern', 'border', 'box_border', 'get_visual_width',
    'heart_pattern', 'star_pattern', 'tree_pattern', 'rainbow_pattern',
    'count_to', 'show_math',
]
