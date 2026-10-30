# Studio's handle on the running Purple: lay out the family's pack as an installed pack, then have
# the running Purple read it, or start it again when its rooms changed, as it would after a reboot.
# Each Studio page then sets up the room it shows, with the same calls Purple's own menus and code
# panel make.
import ast
import asyncio
import builtins
import difflib
import re
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
    return [(room.key, room.digest) for room in content.get_content().rooms if TRYING not in room.path.parents]


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
        from purple_tui.content import picture_grid
        paint_cells(_app, picture["ops"], picture.get("letters", []), picture_grid(picture))
    if room == "art":
        _app.rooms["art"]._set_paint_mode(True)
    if family:
        from purple_tui.canvas.rooms.family_room import FamilyRoom
        _app.push(FamilyRoom(_app, _try(family)))
    _app.invalidate()
    return place()


def _try(family):
    """The family's rooms not in the pack and the one being tried, laid out beside the pack's and
    turned on, so the Esc menu lists them all and opens them again. Returns the one being tried."""
    shutil.rmtree(TRYING, ignore_errors=True)
    TRYING.mkdir(parents=True)
    for kind in ("images", "sounds", "room-voice"):
        link = TRYING.parent / kind
        link.unlink(missing_ok=True)
        link.symlink_to(PACKS / family["pack"] / "content" / kind)
    sources = {name: (source, icon) for name, source, icon in family.get("rooms") or ()}
    sources[family["name"]] = (family["source"], family["icon"])
    tried = [content.Room(name, TRYING / f"{name}.py", icon) for name, (_, icon) in sources.items()]
    for room in tried:
        room.path.write_text(sources[room.name][0])
        set_room_on(room.key, room.digest)
    loaded = content.get_content()
    loaded.rooms = [r for r in loaded.rooms if r.name not in sources and TRYING not in r.path.parents] + tried
    return next(r for r in tried if r.name == family["name"])


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


# Python's words for a line that isn't finished, as a parent would put them.
_UNFINISHED = [
    (re.compile(r"'(.)' was never closed"), "the {0} needs its closing one"),
    (re.compile(r"unterminated (triple-quoted )?string"), "the words need a closing quote"),
    (re.compile(r"expected ':'"), "the line needs a : at the end"),
    (re.compile(r"expected an indented block"), "the line after a : needs spaces in front"),
    (re.compile(r"unindent does not match|unexpected indent"), "the spaces in front don't line up with the lines around it"),
]


def _plain(msg):
    msg = re.sub(r" \(detected at line \d+\)", "", msg)
    for pattern, said in _UNFINISHED:
        if m := pattern.search(msg):
            return said.format(*m.groups())
    return f"Python can't read it yet (Technical: {msg})"


def _bound(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            yield node.id
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.alias):
            yield (node.asname or node.name).split(".")[0]
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            yield from node.names
        elif isinstance(node, ast.MatchMapping) and node.rest:
            yield node.rest


def check(source, purple_names):
    """Why the room can't run as written, as [text, line], or None. It's read, never run: Studio keeps
    the last version playing while someone is partway through a line or a name."""
    try:
        tree = ast.parse(source, "room.py")
    except SyntaxError as e:
        return [_plain(e.msg), e.lineno]
    if any(isinstance(n, ast.ImportFrom) and n.module != "purple" and n.names[0].name == "*" for n in ast.walk(tree)):
        return None
    known = set(purple_names) | set(_bound(tree))
    unknown = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
               and n.id not in known and not hasattr(builtins, n.id)]
    if not unknown:
        return None
    first = min(unknown, key=lambda n: (n.lineno, n.col_offset))
    close = difflib.get_close_matches(first.id, [*purple_names, *known], 1)
    return [f"{first.id} isn't a name Purple knows" + (f". Did you mean {close[0]}?" if close else "."), first.lineno]
