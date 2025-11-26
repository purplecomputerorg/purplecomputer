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

# Import Purple Computer modules
from pack_manager import PackManager, get_registry
from parent_auth import get_auth
from update_manager import create_update_manager


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
    c.TerminalInteractiveShell.true_color = True

    # Behavior
    c.TerminalInteractiveShell.confirm_exit = False
    c.TerminalInteractiveShell.display_completions = 'readlinelike'
    c.TerminalInteractiveShell.autocall = 2  # Full autocall - no parens needed for any commands

    # History
    c.TerminalInteractiveShell.history_length = 100

    # Startup files - load Purple Computer core functions and pack content
    startup_files = []

    # Load Purple Computer core startup (parent command, etc.)
    purple_startup_dir = Path(__file__).parent / 'startup'
    if purple_startup_dir.exists():
        startup_files.extend(sorted(purple_startup_dir.glob('*.py')))

    # Load user-installed pack content
    user_startup_dir = Path.home() / '.ipython' / 'profile_default' / 'startup'
    if user_startup_dir.exists():
        startup_files.extend(sorted(user_startup_dir.glob('*.py')))

    c.InteractiveShellApp.exec_files = [str(f) for f in startup_files]

    # Exception handling - no tracebacks for kids!
    c.TerminalInteractiveShell.xmode = 'Minimal'
    c.TerminalInteractiveShell.show_rewritten_input = False
    c.InteractiveShell.colors = 'NoColor'  # Simpler error colors

    return c


def show_parent_menu():
    """Display parent menu with password protection"""
    # Require parent authentication
    auth = get_auth()

    if not auth.prompt_for_password():
        print("\n❌ Access denied. Returning to Purple Computer...\n")
        return

    # Show parent menu
    while True:
        print("\n" + "=" * 50)
        print("PURPLE COMPUTER - PARENT MENU")
        print("=" * 50)
        print("\n1. Return to Purple Computer")
        print("2. Check for updates")
        print("3. Install packs")
        print("4. List installed packs")
        print("5. Change parent password")
        print("6. Open system shell (advanced)")
        print("7. Network settings (advanced)")
        print("8. Shut down")
        print("9. Restart")
        print("\nEnter choice (1-9): ", end='')

        try:
            choice = input().strip()

            if choice == '1':
                print("\n✨ Returning to Purple Computer...\n")
                return

            elif choice == '2':
                check_for_updates_menu()

            elif choice == '3':
                install_pack_menu()

            elif choice == '4':
                list_packs_menu()

            elif choice == '5':
                change_password_menu()

            elif choice == '6':
                print("\n🔧 Opening system shell...")
                print("Type 'exit' to return to parent menu\n")
                os.system('/bin/bash')

            elif choice == '7':
                print("\n🌐 Network Settings")
                print("Use 'nmtui' to configure network (if NetworkManager is installed)")
                input("\nPress Enter to continue...")

            elif choice == '8':
                confirm = input("\n⚠️  Really shut down? (yes/no): ")
                if confirm.lower() == 'yes':
                    print("\n👋 Shutting down...")
                    os.system('shutdown -h now')
                return

            elif choice == '9':
                confirm = input("\n⚠️  Really restart? (yes/no): ")
                if confirm.lower() == 'yes':
                    print("\n🔄 Restarting...")
                    os.system('reboot')
                return

            else:
                print("\n❌ Invalid choice. Try again.\n")

        except (EOFError, KeyboardInterrupt):
            print("\n✨ Returning to Purple Computer...\n")
            return


def install_parent_escape():
    """Install the parent escape mechanism (Ctrl+C and 'parent' command)"""
    # Install Ctrl+C handler as backup
    # Note: In production, this would hook Ctrl+Alt+P
    import builtins

    original_input = builtins.input

    def wrapped_input(prompt=''):
        try:
            return original_input(prompt)
        except KeyboardInterrupt:
            show_parent_menu()
            return ''

    builtins.input = wrapped_input

    return show_parent_menu


def check_for_updates_menu():
    """Check for and install updates"""
    print("\n" + "=" * 50)
    print("CHECKING FOR UPDATES")
    print("=" * 50)

    try:
        update_mgr = create_update_manager()
        print("\nFetching update feed...")

        success, updates = update_mgr.check_for_updates()

        if not success:
            print("❌ Could not connect to update server.")
            print("Check your internet connection.\n")
            input("Press Enter to continue...")
            return

        if not updates:
            print("✓ Purple Computer is up to date!\n")
            input("Press Enter to continue...")
            return

        print(f"\n✓ Found {len(updates)} update(s):\n")

        for i, update in enumerate(updates, 1):
            if update['type'] == 'new_pack':
                print(f"{i}. NEW: {update['name']} v{update['version']}")
            elif update['type'] == 'pack_update':
                print(f"{i}. UPDATE: {update['name']} {update['old_version']} → {update['new_version']}")
            elif update['type'] == 'core_update':
                print(f"{i}. CORE: {update['path']} v{update['version']}")

            if update.get('description'):
                print(f"   {update['description']}")

        print("\nInstall all updates? (yes/no): ", end='')
        confirm = input().strip()

        if confirm.lower() != 'yes':
            print("\nUpdates cancelled.\n")
            input("Press Enter to continue...")
            return

        print("\nInstalling updates...\n")
        results = update_mgr.install_all_updates(updates)

        for (success, msg), update in zip(results, updates):
            if success:
                print(f"✓ {msg}")
            else:
                print(f"❌ {msg}")

        print("\n")
        input("Press Enter to continue...")

    except Exception as e:
        print(f"\n❌ Error checking updates: {str(e)}\n")
        input("Press Enter to continue...")


def install_pack_menu():
    """Install a pack from a file"""
    print("\n" + "=" * 50)
    print("INSTALL PACK FROM FILE")
    print("=" * 50)

    pack_path = input("\nEnter path to .purplepack file: ").strip()

    if not pack_path:
        return

    try:
        registry = get_registry()
        pack_mgr = PackManager(Path.home() / '.purple' / 'packs', registry)

        success, msg = pack_mgr.install_pack_from_file(Path(pack_path))

        if success:
            print(f"\n✓ {msg}\n")
        else:
            print(f"\n❌ {msg}\n")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}\n")

    input("Press Enter to continue...")


def list_packs_menu():
    """List installed packs"""
    print("\n" + "=" * 50)
    print("INSTALLED PACKS")
    print("=" * 50)

    registry = get_registry()
    packs = registry.list_packs()

    if not packs:
        print("\nNo packs installed yet.\n")
    else:
        print()
        for pack in packs:
            print(f"• {pack['name']} v{pack['version']} ({pack['type']})")
        print()

    input("Press Enter to continue...")


def change_password_menu():
    """Change parent password"""
    print("\n" + "=" * 50)
    print("CHANGE PARENT PASSWORD")
    print("=" * 50)

    auth = get_auth()

    import getpass

    old_pass = getpass.getpass("\nCurrent password: ")
    new_pass = getpass.getpass("New password (4+ chars): ")
    confirm = getpass.getpass("Confirm new password: ")

    if new_pass != confirm:
        print("\n❌ Passwords don't match.\n")
        input("Press Enter to continue...")
        return

    hint = input("Password hint (optional): ").strip()
    hint = hint if hint else None

    success, msg = auth.change_password(old_pass, new_pass, hint)

    if success:
        print(f"\n✓ {msg}\n")
    else:
        print(f"\n❌ {msg}\n")

    input("Press Enter to continue...")


def main():
    """Main entry point for Purple Computer REPL"""

    # Load packs at startup
    purple_dir = Path.home() / '.purple'
    packs_dir = purple_dir / 'packs'

    registry = get_registry()
    pack_mgr = PackManager(packs_dir, registry)

    # Load all installed packs
    results = pack_mgr.load_all_packs()

    # Silently load packs (no output for kids)
    # But log errors if any
    for success, msg in results:
        if not success:
            # Log to a file, don't print to console
            log_file = purple_dir / 'pack_errors.log'
            with open(log_file, 'a') as f:
                f.write(f"{msg}\n")

    # Set up timeout handling
    setup_timeout_handler()

    # Install Ctrl+C handler for parent mode
    install_parent_escape()

    # Create config
    config = create_config()

    # Start IPython (parent command loaded via startup files)
    sys.exit(start_ipython(argv=[], config=config))


if __name__ == '__main__':
    main()
