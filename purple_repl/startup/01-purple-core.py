"""
Purple Computer Core Startup
Defines parent mode access and other core functions
"""

def parent():
    """Access parent mode (requires password)"""
    import sys
    import os

    # Add parent directory to path so we can import repl
    purple_dir = os.path.expanduser('~/.purple')
    if purple_dir not in sys.path:
        sys.path.insert(0, purple_dir)

    from repl import show_parent_menu
    show_parent_menu()
