#!/usr/bin/env python3
"""
Purple Computer REPL
Main entry point for the kid-friendly Python environment
"""

import sys
import os
import signal
from pathlib import Path

# Configure IPython before importing it
os.environ['IPYTHONDIR'] = str(Path.home() / '.ipython')

try:
    from IPython import start_ipython
    from IPython.terminal.prompts import Prompts, Token
    from traitlets.config import Config
except ImportError:
    print("Error: IPython not installed")
    print("Install with: pip install ipython")
    sys.exit(1)

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class PurplePrompt(Prompts):
    """Custom prompt for Purple Computer"""

    def in_prompt_tokens(self):
        """The prompt shown before each input"""
        return [
            (Token.Prompt, '💜 '),
        ]

    def out_prompt_tokens(self):
        """The prompt shown before output"""
        return [
            (Token.OutPrompt, '✨ '),
        ]


def setup_timeout_handler():
    """Set up a timeout handler to prevent infinite loops"""

    def timeout_handler(signum, frame):
        raise TimeoutError("⏰ That took too long! Let's try something else.")

    signal.signal(signal.SIGALRM, timeout_handler)


def create_config():
    """Create IPython configuration for Purple Computer"""

    c = Config()

    # Appearance
    c.TerminalInteractiveShell.prompts_class = PurplePrompt
    c.TerminalInteractiveShell.highlighting_style = 'monokai'
    c.TerminalInteractiveShell.true_color = True

    # Behavior
    c.TerminalInteractiveShell.confirm_exit = False
    c.TerminalInteractiveShell.display_completions = 'readlinelike'
    c.TerminalInteractiveShell.autocall = 2  # Enable smart autocall for simple commands

    # History
    c.TerminalInteractiveShell.history_length = 100

    # Startup files - load our emoji and mode definitions
    startup_dir = Path.home() / '.ipython' / 'profile_default' / 'startup'
    if startup_dir.exists():
        c.InteractiveShellApp.exec_files = [
            str(f) for f in sorted(startup_dir.glob('*.py'))
        ]

    # Exception handling - make errors kid-friendly
    c.TerminalInteractiveShell.xmode = 'Plain'

    return c


def install_parent_escape():
    """Install the parent escape mechanism (Ctrl+Alt+P)"""

    # This is a placeholder - actual implementation would use
    # keyboard hooks or terminal control sequences
    # For now, we rely on the user pressing Ctrl+C to exit

    def show_parent_menu():
        """Display parent menu options"""
        print("\n" + "=" * 50)
        print("PURPLE COMPUTER - PARENT MENU")
        print("=" * 50)
        print("\n1. Return to Purple Computer")
        print("2. Open system shell")
        print("3. Shut down")
        print("4. Restart")
        print("\nEnter choice (1-4): ", end='')

        try:
            choice = input().strip()

            if choice == '1':
                print("\n✨ Returning to Purple Computer...\n")
                return

            elif choice == '2':
                print("\n🔧 Opening system shell...")
                print("Type 'exit' to return to Purple Computer\n")
                os.system('/bin/bash')
                print("\n✨ Returning to Purple Computer...\n")

            elif choice == '3':
                print("\n👋 Shutting down...")
                os.system('sudo shutdown -h now')

            elif choice == '4':
                print("\n🔄 Restarting...")
                os.system('sudo reboot')

            else:
                print("\n❌ Invalid choice. Returning to Purple Computer...\n")

        except (EOFError, KeyboardInterrupt):
            print("\n✨ Returning to Purple Computer...\n")

    # Note: In production, this would hook Ctrl+Alt+P
    # For development, we'll catch Ctrl+C
    import builtins

    original_input = builtins.input

    def wrapped_input(prompt=''):
        try:
            return original_input(prompt)
        except KeyboardInterrupt:
            show_parent_menu()
            return ''

    builtins.input = wrapped_input


def main():
    """Main entry point for Purple Computer REPL"""

    # Set up timeout handling
    setup_timeout_handler()

    # Install parent escape
    install_parent_escape()

    # Create config
    config = create_config()

    # Start IPython
    sys.exit(start_ipython(argv=[], config=config))


if __name__ == '__main__':
    main()
