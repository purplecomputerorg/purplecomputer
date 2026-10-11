# Studio's handle on the running Purple: install the family's pack the way the USB updater does,
# then start Purple again so it reads it, as it would after a reboot. Each Studio page then sets up
# the room it shows, with the same calls Purple's own menus and code panel make.
import asyncio
import shutil
from pathlib import Path

from purple_tui import content
from purple_tui.canvas.app import PurpleApp
from purple_tui.keyboard import CharacterAction
from purple_tui.pack_manager import PackInstaller

PACKS = Path.home() / ".purple" / "packs"
_app = None
_task = None


def install(path):
    shutil.rmtree(PACKS, ignore_errors=True)
    if path:
        ok, message = PackInstaller(PACKS).install_pack(Path(path), replace=True)
        print(f"[studio] {message}")


async def restart():
    global _app, _task
    room = _app.active_room if _app else "play"
    if _app:
        _app.exit()
        await _task
    content._content = None
    _app = PurpleApp(windowed=True, size=(1366, 768))
    _app.active_room = room  # _main enters it
    _task = asyncio.ensure_future(_app._main())
    # _main restores each room's saved state on the way in; a room set up before then would be
    # undone. Its last step before drawing is the battery timer.
    while not hasattr(_app, "_battery_timer") and not _task.done():
        await asyncio.sleep(0.01)


def setup(room, letters=False, instrument=None, picture=None):
    """The room a Studio page shows: Music in Say Letters or playing an instrument, or Art with a
    pack picture painted on it, the way the parent menu's Pictures paints one."""
    while _app.top:
        _app.pop(_app.top)
    if room != _app.active_room:
        _app.action_switch_room(room)
    if room == "music":
        music = _app.rooms["music"]
        music.letters_mode = letters
        music.set_instrument_by_name(instrument or "marimba")
    if picture:
        found = next((p for p in content.get_content().pictures if p.name == picture), None)
        if found:
            from purple_tui.canvas.secret_doodle import paint_cells
            paint_cells(_app, found.ops)
    _app.invalidate()


async def key(char):
    """A key typed on the Studio page, sent the way Purple's keyboard sends one."""
    await _app._dispatch_keyboard_action(CharacterAction(char=char, shifted=False))
