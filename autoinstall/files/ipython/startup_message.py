"""
Purple Computer IPython Startup - Welcome Message
This file is automatically loaded by IPython on startup
"""

from colorama import Fore, Style, init
import sys

# Initialize colorama
init(autoreset=True)

def show_welcome():
    """Display the Purple Computer welcome message"""

    welcome_text = f"""
{Fore.MAGENTA}{Style.BRIGHT}
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║              💜 PURPLE COMPUTER 💜                        ║
║                                                           ║
║              A Magical Place for Kids                     ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
{Style.RESET_ALL}

{Fore.CYAN}Hello! Welcome to your Purple Computer!{Style.RESET_ALL}

{Fore.YELLOW}Try these fun things:{Style.RESET_ALL}

  • Type {Fore.GREEN}cat{Style.RESET_ALL} and press Enter  {Fore.MAGENTA}→ 🐱{Style.RESET_ALL}
  • Type {Fore.GREEN}dog{Style.RESET_ALL} and press Enter  {Fore.MAGENTA}→ 🐶{Style.RESET_ALL}
  • Type {Fore.GREEN}star{Style.RESET_ALL} and press Enter {Fore.MAGENTA}→ ⭐{Style.RESET_ALL}

{Fore.YELLOW}Switch modes:{Style.RESET_ALL}

  • Type {Fore.GREEN}speech{Style.RESET_ALL}   → Everything is read aloud
  • Type {Fore.GREEN}emoji{Style.RESET_ALL}    → Words become pictures
  • Type {Fore.GREEN}rainbow{Style.RESET_ALL}  → Colorful output
  • Type {Fore.GREEN}surprise{Style.RESET_ALL} → Random fun!

{Fore.CYAN}Type anything and explore! You can't break anything.{Style.RESET_ALL}

{Fore.MAGENTA}✨ Let's have fun! ✨{Style.RESET_ALL}

"""
    print(welcome_text)

# Show welcome message on startup
show_welcome()

# Make the welcome function available
__all__ = ['show_welcome']
