"""Entry point so `python -m purple_tui` loads the module exactly once.

Running `python -m purple_tui.purple_tui` would register the same file twice
in sys.modules (as `__main__` and as `purple_tui.purple_tui`), giving us two
copies of every class and module-level global.
"""

from purple_tui.purple_tui import main

if __name__ == "__main__":
    main()
