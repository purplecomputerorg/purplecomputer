"""Family rooms: a pack's rooms/<name>.py runs in its own process, answers each
event with one reply, and Purple draws the scene it sends; a stuck, broken, or
greedy room gets the "needs fixing" card instead of taking Purple down; no
scene can flash more than three times a second; Esc always leaves; the Esc
menu lists only the rooms a parent turned on."""

import asyncio
import json
import os
import subprocess
import sys
import time

import pygame
import pytest

from purple_tui import content as content_mod
from purple_tui import settings
from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.canvas.room_picker import FAMILY, RoomPicker
from purple_tui.canvas import theme
from purple_tui.canvas.rooms import family_room
from purple_tui.canvas.rooms.family_room import FamilyRoom
from purple_tui.canvas.rooms.parent_menu import FamilyRoomsScreen
from purple_tui.content import ContentManager
from purple_tui.keyboard import ControlAction, NavigationAction
from purple_tui.music_constants import PERCUSSION
from purple_tui.roomkit import purple as purple_lib

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

# A pack's own library, speaking the protocol directly: whatever it sends, Purple draws.
LIB = '''def run(start):
    _send(REPLY)
    while True:
        _recv()
        _send({})
'''


@pytest.fixture
def pack(tmp_path, monkeypatch):
    """Installs rooms into a throwaway pack and settings file; returns a writer for more rooms."""
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setenv("PURPLE_ROOMS_DIR", str(tmp_path / "rooms-kept"))
    pack_dir = tmp_path / "packs" / "family"
    (pack_dir / "content" / "rooms").mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(json.dumps({"id": "family", "name": "F", "version": "1.0.0", "type": "emoji"}))

    def add(name, source, lib=None):
        rooms = pack_dir / "content" / "rooms"
        (rooms / f"{name}.py").write_text(source)
        if lib is not None:
            (rooms / "purple.py").write_text(lib)
        cm = ContentManager(packs_dir=tmp_path / "packs")
        cm.load_all()
        monkeypatch.setattr(content_mod, "_content", cm)
        return next(r for r in cm.rooms if r.name == name)
    return add


def lib_sending(reply: dict) -> str:
    return f"REPLY = {reply!r}\n" + LIB


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


def texts(room) -> list:
    return [line for s in room.scene if s[0] == "text" for line in s[4].split("\n")]


def cells(room) -> dict:
    """The grid's squares, from the shapes the library drew (a cell is 10 units, the grid fills the surface)."""
    return {(int(s[1] // 10), int(s[2] // 10)): s[4] if s[0] == "text" else s[5] for s in room.scene[1:]}


def test_snake_moves_on_its_timer_and_turns_with_arrows(pack):
    pack("snake", SNAKE)

    async def go():
        app = make_app()
        room = _open(app, "snake")
        await until(lambda: cells(room) and next(iter(cells(room)))[0] >= 7)
        (x, y), = cells(room)
        assert y == 5 and cells(room)[(x, y)] == "🟩"
        await press(app, "down")
        await until(lambda: next(iter(cells(room)))[1] >= 7)
        assert room.fault is None
        await press(app, "escape")
        assert app.top is None and room._guest is None
    run(go())


def test_esc_that_closes_the_parent_menu_leaves_the_room_open(pack):
    pack("snake", SNAKE)

    async def go():
        app = make_app()
        room = _open(app, "snake")
        await app._dispatch_keyboard_action(ControlAction(action="escape", is_down=True))
        app.action_parent_menu()  # what holding Esc does
        await app._dispatch_keyboard_action(ControlAction(action="escape", is_down=False))
        await press(app, "escape")
        assert app.top is room
        await press(app, "escape")
        assert app.top is None
    run(go())


def test_ask_waits_for_a_typed_answer(pack):
    pack("quiz", 'from purple import *\nshow("🦖")\nanswer = ask("Who has tiny arms?")\nwrite("You said " + answer)\n')

    async def go():
        app = make_app()
        room = _open(app, "quiz")
        await until(lambda: "Who has tiny arms?" in texts(room))
        assert "🦖" in texts(room)
        await type_text(app, "T rex", enter=True)
        await until(lambda: "You said T rex" in texts(room))
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
        assert "too long" in room.fault and room._guest is None
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


def test_the_packs_own_library_runs_and_unknown_shapes_and_fields_are_skipped(pack):
    pack("custom", "", lib=lib_sending({"scene": [["star", 1, 2], ["text", 120, 60, 20, "From the pack", "accent"]],
                                         "sparkles": True}))

    async def go():
        app = make_app()
        room = _open(app, "custom")
        await until(lambda: room.scene)
        assert room.scene == [("text", 120.0, 60.0, 20.0, "From the pack", "accent", "center", 0.0, 0.0, None, 0.0, 0.0)] and room.fault is None
        app._draw()
        room.close()
    run(go())


def test_too_many_shapes_is_stopped(pack):
    pack("greedy", "", lib=lib_sending({"scene": [["rect", 0, 0, 1, 1, "#000000"]] * (family_room.MAX_SHAPES + 1)}))

    async def go():
        app = make_app()
        room = _open(app, "greedy")
        await until(lambda: room.fault is not None)
        assert "too much" in room.fault
        room.close()
    run(go())


def test_a_room_cant_flash_more_than_three_times_a_second(pack):
    flicker = 'from purple import *\ncolors = ["#000000", "#ffffff"]\ndef flip():\n    background(colors[0])\n    colors.reverse()\nevery(0.1, flip)\n'
    pack("flicker", flicker)

    async def go():
        app = make_app()
        room = _open(app, "flicker")
        await until(lambda: room.scene)
        shown, last, end = 0, room.scene, time.monotonic() + 1.5
        while time.monotonic() < end:
            if room.scene != last:
                shown, last = shown + 1, room.scene
            await asyncio.sleep(0.01)
        assert 2 <= shown <= 5
        room.close()
    run(go())


def test_small_changes_are_never_held_back(pack):
    pack("blink", 'from purple import *\ndef flip():\n    grid.erase(0, 0) if grid.get(0, 0) else grid.set(0, 0, "#ffffff")\nevery(0.1, flip)\n')

    async def go():
        app = make_app()
        room = _open(app, "blink")
        await until(lambda: room.scene)
        shown, last, end = 0, room.scene, time.monotonic() + 1.5
        while time.monotonic() < end:
            if room.scene != last:
                shown, last = shown + 1, room.scene
            await asyncio.sleep(0.01)
        assert shown >= 8
        room.close()
    run(go())


def test_a_room_remembers_what_it_keeps(pack):
    pack("visits", 'from purple import *\nkeep["visits"] = keep.get("visits", 0) + 1\nshow(keep["visits"])\n')

    async def go():
        app = make_app()
        room = _open(app, "visits")
        await until(lambda: texts(room) == ["1"])
        room.close()
        room = _open(app, "visits")
        await until(lambda: texts(room) == ["2"])
        room.close()
    run(go())


def test_game_over_waits_for_a_key_then_starts_fresh(pack):
    pack("once", 'from purple import *\nshow("go")\ndef on_key(key):\n    game_over("Again?")\n')

    async def go():
        app = make_app()
        room = _open(app, "once")
        await until(lambda: texts(room) == ["go"] and not room._busy)
        await press(app, "a")
        await until(lambda: "Again?" in texts(room))
        await press(app, "b")
        await until(lambda: texts(room) == ["go"])
        room.close()
    run(go())


def test_a_room_hears_keys_go_up_and_knows_which_are_held(pack):
    pack("hold", 'from purple import *\ndef on_key(key):\n    write(f"down {key} {held(key)}")\n'
                 'def on_key_up(key):\n    write(f"up {key} {held(key)}")\n')

    async def go():
        app = make_app()
        room = _open(app, "hold")
        await until(lambda: not room._busy)
        await press(app, "right", hold=0.1)
        await press(app, "!")
        await until(lambda: texts(room)[-1:] == ["up 1 False"])
        assert texts(room) == ["down right True", "up right False", "down 1 True", "up 1 False"]
        room.close()
    run(go())


def test_math_keys_reach_a_room_as_themselves(pack):
    pack("hold", 'from purple import *\ndef on_key(key):\n    write(f"down {key}")\n'
                 'def on_key_up(key):\n    write(f"up {key} {held(key)}")\n')

    async def go():
        app = make_app()
        room = _open(app, "hold")
        await until(lambda: not room._busy)
        await press(app, "/")
        await press(app, "*")
        await until(lambda: texts(room)[-1:] == ["up 8 False"])
        assert texts(room)[-4:] == ["down /", "up / False", "down 8", "up 8 False"]
        room.close()
    run(go())


def test_held_keys_go_up_when_something_covers_the_room(pack):
    pack("hold", 'from purple import *\ndef on_key(key):\n    write("down")\ndef on_key_up(key):\n    write("up")\nevery(0.1, lambda: None)\n')

    async def go():
        app = make_app()
        room = _open(app, "hold")
        await until(lambda: not room._busy)
        await app._dispatch_keyboard_action(NavigationAction(direction="left"))
        await until(lambda: texts(room) == ["down"])
        app.push(FamilyRoomsScreen(app))
        await until(lambda: texts(room) == ["down", "up"])
        app.top.close()
        room.close()
    run(go())


def test_pictures_draw_from_the_pack_or_from_pixels(pack):
    room_file = pack("pics", 'from purple import *\ngrid.set(0, 0, picture("hero"))\n'
                             'grid.set(1, 0, pixels(["XX", "XX"], {"X": "#00ff00"}))\n')
    images = room_file.path.parents[1] / "images"
    images.mkdir()
    red = pygame.Surface((4, 4))
    red.fill((255, 0, 0))
    pygame.image.save(red, str(images / "hero.png"))

    async def go():
        app = make_app()
        room = _open(app, "pics")
        await until(lambda: room.scene)
        pictures = [s for s in room.scene if s[0] == "image"]
        assert [s[5] for s in pictures] == ["hero", ("pixels", ("XX", "XX"), (("X", "#00ff00"),))]
        app._draw()
        k = room._surface.get_width() / family_room.SIZE[0]
        assert room._surface.get_at((int(5 * k), int(5 * k)))[:3] == (255, 0, 0)
        assert room._surface.get_at((int(15 * k), int(5 * k)))[:3] == (0, 255, 0)
        room.close()
    run(go())


def test_the_grid_has_a_floor_a_cursor_big_pictures_and_text_over_it(pack):
    pack("garden", 'from purple import *\ngrid.floor.set(0, 0, "#00aa00")\ngrid.set(0, 0, "🌻")\ngrid.cursor(0, 0)\n'
                   'grid.set(2, 2, pixels(["XX", "XX", "XX", "XX"], {"X": "#ff0000"}, 2))\n'
                   'status("Score 3")\nwrite("Plant a seed")\nshow("Hi")\n')

    async def go():
        app = make_app()
        room = _open(app, "garden")
        await until(lambda: room.scene)
        kinds = [s[0] for s in room.scene]
        assert kinds == ["rect", "rect", "text", "image", "rect", "text", "text", "text"]
        floor, flower, picture, ring = room.scene[1], room.scene[2], room.scene[3], room.scene[4]
        assert floor[5] == "#00aa00" and flower[4] == "🌻"
        assert picture[1:5] == (20.0, 20.0, 20.0, 40.0)
        assert ring[5:] == ("accent", 10 / 6, 1.0)
        big, lines, status = room.scene[5:]
        assert (big[4], lines[4], status[4]) == ("Hi", "Plant a seed", "Score 3")
        assert status[6] == "top" and status[9] == "surface"
        app._draw()
        room.close()
    run(go())


def test_text_on_a_rooms_own_background_stays_readable(pack):
    pack("light", 'from purple import *\nbackground("#f5d7a8")\nshow("Biscuit")\n')

    async def go():
        app = make_app()
        room = _open(app, "light")
        await until(lambda: texts(room))
        assert room.scene[1][5] == purple_lib._INKS[True]["text"]
        room.close()
    run(go())


def test_long_text_wraps_and_shrinks_into_its_box(pack):
    words = " ".join(["word"] * 60)
    pack("custom", "", lib=lib_sending({"scene": [["text", 120, 60, 30, words, "text", {"width": 200, "height": 40, "box": "#ff0000", "pad": 2}],
                                                   ["text", 120, 110, 8, "[bold]as typed", "text", {"anchor": "nowhere"}]]}))

    async def go():
        app = make_app()
        room = _open(app, "custom")
        await until(lambda: room.scene)
        assert room.scene[1][6:] == ("center", 0.0, 0.0, None, 0.0, 0.0)
        app._draw()
        k = room._surface.get_width() / family_room.SIZE[0]
        red = [y for y in range(room._surface.get_height()) if room._surface.get_at((int(120 * k), y))[:3] == (255, 0, 0)]
        assert red and (red[-1] - red[0]) / k <= 44
        lines = room._fit("[bold]as typed", 40, "#ffffff", 0, 0, 1000)
        assert len(lines) == 1 and len(lines[0][2]) == 1
        room.close()
    run(go())


def test_a_picture_the_pack_doesnt_have_is_skipped(pack):
    pack("custom", "", lib=lib_sending({"scene": [["image", 0, 0, 10, 10, "nope"], ["image", 0, 0, 10, 10, {"rows": "XX"}]]}))

    async def go():
        app = make_app()
        room = _open(app, "custom")
        await until(lambda: not room._busy)
        assert room.scene == [] and room.fault is None
        room.close()
    run(go())


def test_a_room_plays_its_packs_own_sounds(pack, monkeypatch):
    room_file = pack("meow", 'from purple import *\ndef on_key(key):\n    sound("meow")\n    sound("woof") if key == "w" else None\n')
    meow = room_file.path.parents[1] / "sounds" / "meow.wav"
    meow.parent.mkdir()
    meow.write_bytes(b"")
    played = []
    monkeypatch.setattr(family_room, "play_safe", played.append)
    monkeypatch.setattr(family_room.SoundBank, "file", lambda self, path: path)

    async def go():
        app = make_app()
        room = _open(app, "meow")
        await until(lambda: not room._busy)
        await press(app, "a")
        await until(lambda: played)
        assert played == [meow]
        await press(app, "w")
        await until(lambda: room.fault)
        assert room.fault == "ValueError: the pack has no sound called 'woof' (line 4)"
        room.close()
    run(go())


def test_everything_one_key_says_is_spoken_in_order(pack, monkeypatch):
    pack("chatty", 'from purple import *\ndef on_key(key):\n    say("A pair!")\n    say("Go again.")\n')
    spoken = []
    monkeypatch.setattr(family_room.tts, "speak_many", lambda texts, gap, on_done, room_voice: spoken.append((texts, room_voice)))
    monkeypatch.setattr(FamilyRoom, "_audible", lambda self: True)

    async def go():
        app = make_app()
        room = _open(app, "chatty")
        await until(lambda: not room._busy)
        await press(app, "a")
        await until(lambda: spoken)
        assert spoken == [(["A pair!", "Go again."], room.room.voice)]
        room.close()
    run(go())


def test_a_line_still_being_said_is_not_restarted(pack, monkeypatch):
    pack("cow", 'from purple import *\ndef on_key(key):\n    say("Moo" if key == "m" else "Baa")\n')
    spoken, done = [], []

    def speak_many(texts, gap, on_done, room_voice):
        spoken.append(texts)
        done.append(on_done)
        return True
    monkeypatch.setattr(family_room.tts, "speak_many", speak_many)
    monkeypatch.setattr(FamilyRoom, "_audible", lambda self: True)

    async def go():
        app = make_app()
        room = _open(app, "cow")
        await until(lambda: not room._busy)
        for key in "mm":
            await press(app, key)
            await until(lambda: not room._queue and not room._busy)
        assert spoken == [["Moo"]]
        await press(app, "b")
        await until(lambda: len(spoken) == 2)
        done[0]()  # the cut off Moo finishing must not let a Baa still playing restart
        await press(app, "b")
        await until(lambda: not room._queue and not room._busy)
        assert spoken == [["Moo"], ["Baa"]]
        done[1]()
        await press(app, "b")
        await until(lambda: len(spoken) == 3)
        room.close()
    run(go())


def test_the_library_knows_purples_drums():
    assert sorted(purple_lib.DRUMS) == sorted(PERCUSSION.values())


def test_the_library_knows_the_theme_colors():
    assert list(purple_lib.ROLES) == theme.ROLES


def test_theme_colors_paint_the_grid_and_the_background(pack):
    pack("themed", 'from purple import *\nbackground("surface")\ngame = state(at=1)\ngame.at += 1\n'
                   'grid.set(game.at, 0, "tile")\ngrid.set(0, 0, "Q")\n')

    async def go():
        app = make_app()
        room = _open(app, "themed")
        await until(lambda: room.scene)
        assert room.scene[0][5] == "surface"
        assert room.scene[1][:3] == ("rect", 20.5, 0.5) and room.scene[1][5] == "tile"
        assert room.scene[2][4] == "Q"
        room.close()
    run(go())


def test_esc_menu_lists_only_rooms_a_parent_turned_on(pack):
    snake = pack("snake", SNAKE)

    async def go():
        app = make_app()
        await press(app, "escape")
        assert app.top.family == [] and FAMILY not in app.top.rows
        app.top.close()
        settings.set_room_on(snake.key, snake.digest)
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


def test_a_changed_room_waits_to_be_turned_on_again(pack):
    snake = pack("snake", SNAKE)
    settings.set_room_on(snake.key, snake.digest)
    pack("snake", SNAKE + "\n# a different snake\n")

    async def go():
        app = make_app()
        await press(app, "escape")
        assert app.top.family == []
    run(go())


def test_parent_menu_turns_rooms_on_and_off(pack):
    pack("snake", SNAKE)
    pack("worm", SNAKE)

    async def go():
        app = make_app()
        screen = FamilyRoomsScreen(app)
        app.push(screen)
        assert [o[1:] for o in screen.options] == [("Snake", "Off"), ("Worm", "Off"), ("Done",)]
        app._draw()  # draws an unselected room row too
        await press(app, "enter")
        assert screen.options[0][2] == "On: in the Esc menu"
        assert [r.name for r in RoomPicker(app).family] == ["snake"]
        await press(app, "enter")
        assert RoomPicker(app).family == []
    run(go())


def test_a_long_room_list_scrolls_inside_the_screen(pack):
    for n in range(15):
        pack(f"room{n}", SNAKE)

    async def go():
        app = make_app(size=(1366, 768))
        screen = FamilyRoomsScreen(app)
        app.push(screen)
        app._draw()
        assert 0 <= screen.box.top and screen.box.bottom <= app.g.h
        shown = screen._shown(app.g)
        assert shown < len(screen.options)
        await press(app, "up")  # wraps to Done
        app._draw()
        assert screen._first == len(screen.options) - shown
        await press(app, "down")
        app._draw()
        assert screen._first == 0
    run(go())


def test_on_the_iso_rooms_start_through_the_sealed_launcher(monkeypatch, tmp_path):
    script = open("build-scripts/00-build-golden-image.sh").read()
    rule = next(line for line in script.splitlines() if line.startswith("purple ALL=(root)"))
    assert "install -m 755 /purple-src/scripts/purple-room-run.sh \"$MOUNT_DIR/usr/local/bin/purple-room-run\"" in script
    monkeypatch.setattr(family_room, "RUN_ROOM", tmp_path / "purple-room-run")
    family_room.RUN_ROOM.touch()
    cmd = family_room.command()
    assert cmd == ["sudo", "-n", str(family_room.RUN_ROOM)]
    assert rule.split("NOPASSWD: ")[1] == '/usr/local/bin/purple-room-run ""'
    assert "-p User=purple-room" in open("scripts/purple-room-run.sh").read()


def _children(pid: int) -> list:
    kids = []
    for entry in os.listdir("/proc"):
        try:
            if entry.isdigit() and int(open(f"/proc/{entry}/stat").read().rsplit(")", 1)[1].split()[1]) == pid:
                kids.append(int(entry))
        except (OSError, IndexError, ValueError):
            pass
    return kids


def test_letting_go_of_a_spinning_room_ends_it():
    """Killing sudo or systemd-run never reaches a sealed room, so the runner watches its stdin."""
    proc = subprocess.Popen([sys.executable, "-I", "-S", str(family_room.RUNNER)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    start = {"ev": "start", "t": 0, "lib": family_room.BUILTIN_LIB.read_text(), "source": "while True:\n    pass\n"}
    proc.stdin.write(json.dumps(start) + "\n")
    proc.stdin.flush()
    for _ in range(100):
        if room := _children(proc.pid):
            break
        time.sleep(0.02)
    assert room
    proc.stdin.close()
    proc.wait(timeout=5)
    time.sleep(0.1)
    assert not os.path.exists(f"/proc/{room[0]}") or "Z" in open(f"/proc/{room[0]}/stat").read().rsplit(")", 1)[1].split()[0]
