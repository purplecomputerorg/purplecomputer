"""Entry point so `python -m purple_tui` loads the app module exactly once.

Running `python -m purple_tui.canvas.app` would register the same file twice
in sys.modules (as `__main__` and as `purple_tui.canvas.app`), giving us two
copies of every class and module-level global.

PURPLE_UX=tui runs the Textual UI that ships from release/1.x; anything else
runs the canvas UI.
"""

import os

if os.environ.get("PURPLE_UX") == "tui":
    from purple_tui import mixer
    from purple_tui.rooms import music_room
    mixer.bind_frontend_copy(music_room)
    from purple_tui.purple_tui import main
else:
    from purple_tui.canvas.app import main

if __name__ == "__main__":
    main()
