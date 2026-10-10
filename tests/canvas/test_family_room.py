"""Family rooms: a pack's rooms/<name>.py runs in its own process and Purple
draws what it asks for; a stuck, broken, or flooding room gets the "needs
fixing" card instead of taking Purple down; Esc always leaves; the Esc menu
lists family rooms in their own row unless the parent turns them off."""

import asyncio
import json

import pytest

from purple_tui import content as content_mod
from purple_tui import settings
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.room_picker import FAMILY, RoomPicker
from purple_tui.canvas.rooms import family_room
from purple_tui.canvas.rooms.family_room import FamilyRoom
from purple_tui.content import ContentManager

SNAKE = '''from purple import *
snake, heading = [(5, 5)], (1, 0)
TURNS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

def on_key(key):
    global heading
    heading = TURNS.get(key, heading)

def step():
    x, y = snake[0]
    head = ((x + heading[0]) % grid.w, (y + heading[1]) % grid.h)
    snake.insert(0, head)
    grid.erase(snake.pop())
    grid.set(head, "🟩")

grid.set(snake[0], "🟩")
every(0.1, step)
'''


@pytest.fixture
def pack(tmp_path, monkeypatch):
    """Installs rooms into a throwaway pack and settings file; returns a writer for more rooms."""
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    pack_dir = tmp_path / "packs" / "family"
    (pack_dir / "content" / "rooms").mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(json.dumps({"id": "family", "name": "F", "version": "1.0.0", "type": "emoji"}))

    def add(name, source):
        (pack_dir / "content" / "rooms" / f"{name}.py").write_text(source)
        cm = ContentManager(packs_dir=tmp_path / "packs")
        cm.load_all()
        monkeypatch.setattr(content_mod, "_content", cm)
    return add


async def until(check, timeout=5.0):
    for _ in range(int(timeout / 0.02)):
        if check():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out")


def _open(app, name):
    app.open_family_room(name)
    room = app.top
    assert isinstance(room, FamilyRoom)
    return room


def test_snake_moves_on_its_timer_and_turns_with_arrows(pack):
    pack("snake", SNAKE)

    async def go():
        app = make_app()
        room = _open(app, "snake")
        await until(lambda: room.cells and next(iter(room.cells))[0] >= 7)
        (x, y), = room.cells
        assert y == 5 and room.cells[(x, y)] == "🟩"
        await press(app, "down")
        await until(lambda: next(iter(room.cells))[1] >= 7)
        assert room.fault is None
        await press(app, "escape")
        assert app.top is None and room._proc is None
    run(go())


def test_ask_waits_for_a_typed_answer(pack):
    pack("quiz", 'from purple import *\nshow("🦖")\nanswer = ask("Who has tiny arms?")\nwrite("You said " + answer)\n')

    async def go():
        app = make_app()
        room = _open(app, "quiz")
        await until(lambda: room.prompt == "Who has tiny arms?")
        assert room.big == "🦖"
        await type_text(app, "T rex", enter=True)
        await until(lambda: room.lines == ["You said T rex"])
        room.close()
    run(go())


def test_a_room_that_never_answers_gets_the_fixing_card(pack, monkeypatch):
    monkeypatch.setattr(family_room, "STEP_TIMEOUT_S", 0.3)
    pack("stuck", "from purple import *\ndef on_key(key):\n    while True:\n        pass\n")

    async def go():
        app = make_app()
        room = _open(app, "stuck")
        await until(lambda: not room._busy)
        await press(app, "a")
        await until(lambda: room.fault is not None)
        assert "too long" in room.fault and room._proc is None
        app._draw()
        await press(app, "escape")
        assert app.top is None
    run(go())


def test_errors_name_the_line(pack):
    pack("oops", "from purple import *\n\ndef on_key(key):\n    show(1 / 0)\n")

    async def go():
        app = make_app()
        room = _open(app, "oops")
        await until(lambda: not room._busy)
        await press(app, "a")
        await until(lambda: room.fault is not None)
        assert room.fault == "ZeroDivisionError: division by zero (line 4)"
        room.close()
    run(go())


def test_a_flood_of_messages_is_stopped(pack, monkeypatch):
    monkeypatch.setattr(family_room, "MAX_MESSAGES_PER_STEP", 50)
    pack("flood", "from purple import *\nfor i in range(1000):\n    show(i)\n")

    async def go():
        app = make_app()
        room = _open(app, "flood")
        await until(lambda: room.fault is not None)
        assert "too many" in room.fault
        room.close()
    run(go())


def test_background_changes_are_spaced_out(pack):
    pack("strobe", 'from purple import *\nfor c in ["#ff0000", "#00ff00", "#0000ff"]:\n    background(c)\n')

    async def go():
        app = make_app()
        room = _open(app, "strobe")
        await until(lambda: room.bg == "#ff0000")
        await asyncio.sleep(0.1)
        assert room.bg == "#ff0000"
        await until(lambda: room.bg == "#0000ff", timeout=2)
        room.close()
    run(go())


def test_game_over_waits_for_a_key_then_starts_fresh(pack):
    pack("once", 'from purple import *\nshow("go")\ndef on_key(key):\n    game_over("Again?")\n')

    async def go():
        app = make_app()
        room = _open(app, "once")
        await until(lambda: room.big == "go" and not room._busy)
        await press(app, "a")
        await until(lambda: room.over == "Again?")
        assert room._proc is None
        await press(app, "b")
        await until(lambda: room.big == "go" and room.over is None)
        room.close()
    run(go())


def test_esc_menu_lists_family_rooms_and_enter_opens_one(pack):
    pack("snake", SNAKE)

    async def go():
        app = make_app()
        await press(app, "escape")
        picker = app.top
        assert isinstance(picker, RoomPicker) and [r.name for r in picker.family] == ["snake"]
        app._draw()
        await press(app, "down")
        assert picker.row == FAMILY
        await press(app, "enter")
        assert isinstance(app.top, FamilyRoom) and app.top.room.name == "snake"
        app.top.close()
    run(go())


def test_parent_can_hide_family_rooms(pack):
    pack("snake", SNAKE)
    settings.set_family_rooms(False)

    async def go():
        app = make_app()
        await press(app, "escape")
        assert app.top.family == [] and FAMILY not in app.top.rows
    run(go())


def test_on_the_iso_rooms_start_as_purple_room_with_the_sudoers_command(monkeypatch):
    rule = next(line for line in open("build-scripts/00-build-golden-image.sh") if line.startswith("purple ALL=(purple-room)"))
    monkeypatch.setattr(family_room.pwd, "getpwnam", lambda name: object())
    monkeypatch.setattr(family_room, "RUNNER", family_room.Path("/opt/purple/purple_tui/roomkit/runner.py"))
    cmd = family_room.command()
    assert cmd[:5] == ["sudo", "-n", "-u", "purple-room", "/usr/bin/python3"]
    assert rule.split("NOPASSWD: ")[1].strip() == " ".join(cmd[4:])
