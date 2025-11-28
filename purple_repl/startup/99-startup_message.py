"""
Purple Computer IPython Startup - Welcome Message
This file is automatically loaded by IPython on startup
"""

from colorama import Fore, Style, init
import sys
import os
import shutil

# Initialize colorama
init(autoreset=True)

# Import emoji_lib utilities
purple_dir = os.path.expanduser('~/.purple')
if purple_dir not in sys.path:
    sys.path.insert(0, purple_dir)

try:
    from emoji_lib import box_border, get_visual_width
except ImportError:
    # Fallback if emoji_lib not available
    def box_border(lines, style='double', color=None, center=True):
        return '\n'.join(lines)
    def get_visual_width(text):
        import re
        return len(re.sub(r'\033\[[0-9;]*m', '', text))


def center_text(text):
    """
    Center text based on terminal width.
    Returns padding spaces needed to center the text.
    """
    term_width = shutil.get_terminal_size().columns
    visual_width = get_visual_width(text)
    padding = max(0, (term_width - visual_width) // 2)
    return ' ' * padding

def show_welcome():
    """Display the Purple Computer welcome message"""

    # Build welcome message with dynamic centering
    lines = []
    lines.append("")  # Empty line at top

    # Header box using box_border utility
    header_lines = [
        "",
        "💜 PURPLE COMPUTER 💜",
        "",
        "A Magical Place for Kids",
        "",
    ]
    header_box = box_border(
        header_lines,
        style='double',
        color=Fore.MAGENTA + Style.BRIGHT,
        center=True
    )
    lines.append(header_box)
    lines.append("")

    lines.append(f"{Fore.CYAN}Hello! Welcome to your Purple Computer!{Style.RESET_ALL}")
    lines.append("")

    lines.append(f"{Fore.YELLOW}Try these fun things:{Style.RESET_ALL}")
    lines.append("")
    lines.append(f"• Type {Fore.GREEN}cat{Style.RESET_ALL} and press Enter  {Fore.MAGENTA}→ 🐱{Style.RESET_ALL}")
    lines.append(f"• Type {Fore.GREEN}dog{Style.RESET_ALL} and press Enter  {Fore.MAGENTA}→ 🐶{Style.RESET_ALL}")
    lines.append(f"• Type {Fore.GREEN}star{Style.RESET_ALL} and press Enter {Fore.MAGENTA}→ ⭐{Style.RESET_ALL}")
    lines.append("")

    lines.append(f"{Fore.YELLOW}Talk out loud:{Style.RESET_ALL}")
    lines.append("")
    lines.append(f"• Type {Fore.GREEN}say hello{Style.RESET_ALL} → Hear \"hello\" spoken!")
    lines.append(f"• Type {Fore.GREEN}talk{Style.RESET_ALL} → Enter TALK MODE (everything spoken)")
    lines.append("")

    lines.append(f"{Fore.YELLOW}Fun modes:{Style.RESET_ALL}")
    lines.append("")
    lines.append(f"• Type {Fore.GREEN}speech{Style.RESET_ALL}   → Read output aloud")
    lines.append(f"• Type {Fore.GREEN}rainbow{Style.RESET_ALL}  → Colorful display")
    lines.append(f"• Type {Fore.GREEN}normal{Style.RESET_ALL}   → Return to normal")
    lines.append("")

    lines.append(f"{Fore.CYAN}Type anything and explore! You can't break anything.{Style.RESET_ALL}")
    lines.append("")
    lines.append(f"{Fore.MAGENTA}✨ Let's have fun! ✨{Style.RESET_ALL}")
    lines.append("")

    # Print each line with dynamic centering
    for line in lines:
        print(center_text(line) + line)

# Show welcome message on startup
show_welcome()

# Make the welcome function available
__all__ = ['show_welcome']
