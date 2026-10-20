# Studio's handle on the running Purple: lay out the family's pack as an installed pack, then have
# the running Purple read it, or start it again when its rooms changed, as it would after a reboot.
# Each Studio page then sets up the room it shows, with the same calls Purple's own menus and code
# panel make.
import asyncio
import shutil
from pathlib import Path

from purple_tui import content, i18n
from purple_tui.canvas.app import PurpleApp
from purple_tui.canvas.press import press
from purple_tui.pack_manager import check_pack
from purple_tui.settings import set_room_on

PACKS = Path.home() / ".purple" / "packs"
TRYING = Path("/tmp/studio-trying/content/rooms")
_app = None
_task = None


def _rooms():
    return [(room.key, room.digest) for room in content.get_content().rooms]


def install(pack_id=None, files=(), removed=(), fresh=True):
    """Studio's pack, installed: the files that changed since the last one, as (path, bytes), and the
    paths it dropped, or all of it when fresh (unpacking a whole pack stalls the page long enough to
    crackle Purple's sound). Also turns on every room in it: the parent made them, here in Studio.
    True when Purple has to start again to see it (its rooms changed); refresh() covers the rest."""
    before = _rooms()
    if fresh:
        shutil.rmtree(PACKS, ignore_errors=True)
    if pack_id:
        pack = PACKS / pack_id
        for path in removed:
            (pack / path).unlink(missing_ok=True)
        for path, data in files:
            (pack / path).parent.mkdir(parents=True, exist_ok=True)
            (pack / path).write_bytes(bytes(data))
        if problems := check_pack(pack):
            print(f"[studio] pack problems: {'; '.join(problems[:5])}")
    i18n.reload()
    content.reload_content()
    for key, digest in _rooms():
        set_room_on(key, digest)
    return _app is None or _rooms() != before


def refresh():
    """The new pack in the running Purple; install() already read it."""
    _app.refresh_packs(reread=False)


async def restart():
    global _app, _task
    room = _app.active_room if _app else "art"
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


def setup(room, letters=False, instrument=None, picture=None, family=None):
    """The room a Studio page shows: Music in Say Letters or playing an instrument, Art with a
    picture's paint ops and letters on it, the way Art's Open paints one, or a family room being
    tried, opened over the room the way the Esc menu opens one, drawing and playing its pack's files."""
    while _app.top:
        _app.pop(_app.top)
    if room != _app.active_room:
        _app.action_switch_room(room)
    if room == "music":
        music = _app.rooms["music"]
        music.letters_mode = letters
        music.set_instrument_by_name(instrument or "marimba")
    if picture:
        from purple_tui.canvas.secret_doodle import paint_cells
        paint_cells(_app, picture["ops"], picture.get("letters", []))
    if room == "art":
        _app.rooms["art"]._set_paint_mode(True)
    if family:
        from purple_tui.canvas.rooms.family_room import FamilyRoom
        TRYING.mkdir(parents=True, exist_ok=True)
        for kind in ("images", "sounds", "room-voice"):
            link = TRYING.parent / kind
            link.unlink(missing_ok=True)
            link.symlink_to(PACKS / family["pack"] / "content" / kind)
        path = TRYING / f"{family['name']}.py"
        path.write_text(family["source"])
        _app.push(FamilyRoom(_app, content.Room(family["name"], path)))
    _app.invalidate()
    return place()


async def key(name):
    """A key from the Studio page (typed there, or tapped on the pretend keyboard): a character,
    or space, enter, backspace, escape, tab, or an arrow."""
    await press(_app, name)
    return place()


def place():
    """Where Purple is: its room, whether a menu (the room picker, say) is open over it, the
    room's cursor as fractions of the screen, if it has one (a phone zooms in around it)."""
    vp, cursor = _app._viewport_rect(), _app._get_cursor_position()
    at = [(vp.x + cursor[0] * vp.w) / _app.g.w, (vp.y + cursor[1] * vp.h) / _app.g.h] if cursor else None
    return [_app.active_room, bool(_app.top), at]
