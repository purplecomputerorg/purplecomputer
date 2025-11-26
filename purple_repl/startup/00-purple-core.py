"""
Purple Computer Core Startup
Defines parent mode access and other core functions
"""

def parent():
    """Access parent mode (requires password)"""
    from purple_repl.repl import show_parent_menu
    show_parent_menu()
