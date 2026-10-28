"""Tries a Purple Pack's rooms the way Purple runs them, before the pack goes on a USB drive: checks
the pack as Purple's installer does, then plays each room on a fast clock with arrows, Space, Enter,
letters, typing, and a few hundred random keys, and says what went wrong and on which line.
--show prints each room's screen as text after every step of --keys.

Usage:  python3 purple-room-check.pyz [pack folder, .purplepack, or a room's .py] [--room NAME] [--keys "right right space"] [--show]
With nothing named, it lists the rooms it finds here, in Downloads, and in Purple's packs, and asks.
In Purple's repo: just check-room"""

import argparse
import inspect
import json
import math
import queue
import random
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from purple_tui.content import ROOM_LIB, ROOM_NAME, png_size, room_files
from purple_tui.pack_manager import check_pack, extract_pack
from purple_tui.roomkit import limits as L
from purple_tui.roomkit import purple as builtin_lib

SIZE = (240, 120)
CELL, LEFT, TOP = builtin_lib.CELL, (SIZE[0] - builtin_lib.W * builtin_lib.CELL) / 2, builtin_lib.TOP
KEYS = ["up", "down", "left", "right", "space", "enter", "backspace", *"abcdefghijklmnopqrstuvwxyz0123456789"]
TRY_KEYS = ("right right right down down space enter left up space a b c 1 2 3 y e s enter "
            "down down down down down down down down down down down down down right right right right right right right "
            "right right right right right right right right right right right right right right space").split()
RANDOM_KEYS = 300
PLACES = (Path.cwd(), Path.home() / "Downloads", Path.home() / ".purple" / "packs", Path.home() / ".purple" / "packs-waiting")
FINDS = ("*.purplepack", "content/rooms/*.py", "*/content/rooms/*.py", "*/*/content/rooms/*.py")
STEP_S = 0.15          # the room's clock between keys
IDLE_S = 20            # then this long with no keys at all
GUEST = "import sys; sys.path.insert(0, sys.argv[1]); from purple_tui.roomkit import runner; runner.serve(*runner.stdio())"


class Stopped(Exception):
    """The room stopped, as Purple would show it on the "this room needs fixing" card."""


class Room:
    """One room in its own process, spoken to as Purple speaks to it, on a clock that only moves when told."""

    def __init__(self, images: dict):
        self.t, self.next_tick, self.scene, self.max_shapes, self.heard, self.just_heard = 0.0, None, [], 0, set(), []
        self.images = images
        root = Path(__file__).resolve().parents[2]
        self.proc = subprocess.Popen(L.sealed() or [sys.executable, "-I", "-S", "-c", GUEST, str(root)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(line) for line in self.proc.stdout] + [self.lines.put(None)],
                         daemon=True).start()
        self.prints: list = []
        self.printer = threading.Thread(target=lambda: self.prints.extend(self.proc.stderr), daemon=True)
        self.printer.start()

    def start(self, path: Path, lib: str, sounds: list):
        self.send({"ev": "start", "t": 0, "api": 3, "size": list(SIZE), "keep": {}, "lib": lib,
                   "source": path.read_text(encoding="utf-8"), "images": {n: list(s) for n, s in self.images.items()},
                   "sounds": sounds}, L.START_TIMEOUT_S)

    def send(self, event: dict, timeout=None):
        timeout = timeout or L.STEP_TIMEOUT_S
        try:
            self.proc.stdin.write(json.dumps({**event, "t": round(self.t, 3)}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            line = self.lines.get(timeout=timeout)
        except BrokenPipeError:
            line = None
        except queue.Empty:
            what = f"the {event['key']} key" if "key" in event else "its timer" if event["ev"] == "tick" else "starting"
            raise Stopped(f"it took more than {timeout:g} seconds to answer {what}") from None
        if line is None:
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                pass
            raise Stopped(f"its process ended, exit status {self.proc.returncode} (226 means systemd couldn't seal it)")
        if len(line) > L.MAX_REPLY_CHARS:
            raise Stopped("its reply was too long")
        self.take(json.loads(line))

    def take(self, reply: dict):
        if error := reply.get("error"):
            raise Stopped(f"line {error['line']}: {error['text']}" if error.get("line") else error["text"])
        if "scene" in reply:
            if len(reply["scene"]) > L.MAX_SHAPES:
                raise Stopped(f"it drew {len(reply['scene'])} shapes at once; Purple stops a room at {L.MAX_SHAPES}")
            self.scene = reply["scene"]
            self.max_shapes = max(self.max_shapes, len(self.scene))
            missing = {s[5] for s in self.scene if s[0] == "image" and isinstance(s[5], str) and s[5] not in self.images}
            if missing:
                raise Stopped(f"it drew pictures the pack doesn't have: {', '.join(sorted(missing))}")
        if "keep" in reply and len(json.dumps(reply["keep"]).encode()) > L.KEEP_MAX_BYTES:
            raise Stopped(f"keep holds at most {L.KEEP_MAX_BYTES // 1024} KB")
        heard = [" ".join(map(str, s[:2])) for s in (reply.get("sounds") or [])[:L.MAX_SOUNDS]]
        self.heard.update(heard)
        self.just_heard += heard
        wake = reply.get("wake")
        self.next_tick = self.t + min(max(L.MIN_WAKE_S, wake), L.MAX_WAKE_S) if isinstance(wake, (int, float)) else None

    def wait(self, seconds: float):
        """The room's clock moves on, firing its timers as Purple would."""
        end = self.t + seconds
        while self.next_tick is not None and self.next_tick <= end:
            self.t = self.next_tick
            self.send({"ev": "tick"})
        self.t = end

    def press(self, key: str):
        self.send({"ev": "key", "key": key, **({"char": key} if len(key) == 1 else {})})
        self.wait(0.05)
        self.send({"ev": "keyup", "key": key})
        self.wait(STEP_S)

    def close(self):
        """Closing stdin ends a sealed room (runner._watch); then its last prints are read."""
        self.proc.stdin.close()
        self.proc.kill()
        self.printer.join(1)


def _picture_name(source) -> str:
    if isinstance(source, str):
        return f"picture {source}"
    rows = source.get("rows") or [""]
    return f"pixels {max(map(len, rows))} by {len(rows)}, top row {rows[0]!r}"


def screen(scene: list) -> str:
    """The scene as text: the 24 by 12 grid, a character or emoji a square, each picture as a letter
    (named under the grid), then the words over it."""
    grid = [["  "] * builtin_lib.W for _ in range(builtin_lib.H)]
    words, letters, used = [], {}, False
    for shape in scene[1:]:
        kind, x, y = shape[:3]
        gx, gy = (x - LEFT) / CELL, (y - TOP) / CELL
        col, row = math.floor(gx), math.floor(gy)
        inside = 0 <= row < len(grid) and 0 <= col < len(grid[0])
        on_grid = inside and abs(gx - col) + abs(gy - row) < 0.01
        if kind == "rect" and len(shape) > 7 and shape[7]:
            words.append(f"(a ring around square {col}, {row})")
        elif kind == "image" and not on_grid:
            words.append(f"({_picture_name(shape[5])}, in the middle)")
        elif kind == "image":
            name = _picture_name(shape[5])
            mark = letters.setdefault(name, chr(ord("A") + len(letters) % 26)) + " "
            for r in range(row, min(len(grid), row + round(shape[4] / CELL))):
                for c in range(col, min(len(grid[0]), col + round(shape[3] / CELL))):
                    grid[r][c] = mark
            used = True
        elif kind == "rect" and inside:
            grid[row][col], used = "▪ ", True
        elif kind == "text" and len(shape) == 6 and inside and abs(gx - col - 0.5) < 0.02:
            grid[row][col], used = shape[4] if len(shape[4]) > 1 or not shape[4].isascii() else shape[4] + " ", True
        elif kind == "text":
            words.append(shape[4])
    edge = "+" + "-" * 48 + "+"
    key = ["▪ is a square of color" + "".join(f"; {m} is {n}" for n, m in letters.items())]
    rows = [edge, *(f"|{''.join(r).rstrip()}" for r in grid), edge, *key] if used else []
    return "\n".join(rows + words) or "(nothing on screen)"


def unpack(path: Path, scratch: Path) -> tuple[Path, list]:
    if path.is_dir():
        return path, check_pack(path)
    if problem := extract_pack(path, scratch):
        return scratch, [problem]
    return scratch, check_pack(scratch)


def findable() -> list[Path]:
    """Rooms and packs near at hand, newest first."""
    found = {p.resolve() for place in PLACES for pattern in FINDS for p in place.glob(pattern)
             if p.suffix == ".purplepack" or ROOM_NAME.match(p.stem)}
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def ask() -> Path:
    found = findable()
    for n, p in enumerate(found[:30], 1):
        print(f"{n:3}. {p.stem:24} {p.parent}")
    print("" if found else "No rooms here, in Downloads, or in Purple's packs.")
    answer = input("Which one? Type its number, or a path" + (" (Enter for 1): " if found else ": ")).strip().strip("'\"")
    if not (answer or found):
        sys.exit(1)
    if answer.isdigit() and 0 < int(answer) <= len(found):
        return found[int(answer) - 1]
    if not answer and found:
        return found[0]
    return Path(answer).expanduser()


def gather(path: Path, scratch: Path, only) -> tuple[list, Path, list]:
    """The rooms to try, their content folder, and why Purple would refuse their pack."""
    if path.suffix == ".py":
        path = path.resolve()
        pack = next((p for p in path.parents if (p / "manifest.json").is_file()), None)
        if not pack:  # a room on its own, with no pack to check
            return [path], path.parent.parent, []
        path, only = pack, path.stem
    pack, problems = unpack(path, scratch)
    return [p for p in room_files(pack / "content") if not only or p.stem == only], pack / "content", problems


def try_room(path: Path, content: Path, keys: list, show: bool) -> bool:
    images = {p.stem: size for p in sorted((content / "images").glob("*.png")) if (size := png_size(p))}
    sounds = sorted(p.stem for p in (content / "sounds").glob("*.wav"))
    lib_path = content / "rooms" / ROOM_LIB
    lib = lib_path.read_text(encoding="utf-8") if lib_path.is_file() else inspect.getsource(builtin_lib)
    print(f"\n{path.stem}:")
    room = Room(images)
    try:
        room.start(path, lib, sounds)
        for key in [None, *keys]:
            if key:
                room.press(key)
            if show:
                print(f"{f'After {key}' if key else 'At the start'}:\n{screen(room.scene)}")
                print(f"Sounds: {', '.join(room.just_heard)}" if room.just_heard else "Sounds: none")
            room.just_heard = []
        if not show:
            rng = random.Random(7)
            for _ in range(RANDOM_KEYS):
                room.press(rng.choice(KEYS))
            room.wait(IDLE_S)
    except Stopped as stopped:
        print(f"  NEEDS FIXING: {stopped}")
        print("  Last screen:\n" + "\n".join("    " + line for line in screen(room.scene).splitlines()))
        return False
    finally:
        room.close()
        if room.prints:
            print("  It printed:\n" + "".join(f"    {line}" for line in room.prints[-10:]))
    if not show:
        print(f"  OK: {len(keys) + RANDOM_KEYS} keys and {IDLE_S} seconds of waiting; at most {room.max_shapes} shapes "
              f"(Purple allows {L.MAX_SHAPES}).")
        heard = sorted(room.heard)
        print(f"  Sounds it made: {', '.join(heard[:12]) or 'none'}{f', and {len(heard) - 12} more' if len(heard) > 12 else ''}")
        print("  Last screen:\n" + "\n".join("    " + line for line in screen(room.scene).splitlines()))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack", type=Path, nargs="?", help="the pack folder (with manifest.json and content/), a .purplepack, or one room's .py; leave it out to pick from a list")
    ap.add_argument("--room", help="only this room")
    ap.add_argument("--keys", default=" ".join(TRY_KEYS), help="keys to press, by name, separated by spaces")
    ap.add_argument("--show", action="store_true", help="print the screen after each key instead of trying random keys")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as scratch:
        rooms, content, problems = gather(args.pack or ask(), Path(scratch), args.room)
        for problem in problems:
            print(f"Purple would refuse this pack: {problem}")
        if not rooms:
            print("No rooms found: they go in content/rooms/<name>.py")
        ok = [try_room(p, content, args.keys.split(), args.show) for p in rooms]
    print("\nAll good." if ok and all(ok) and not problems else "\nSomething needs fixing; see above.")
    return 0 if ok and all(ok) and not problems else 1


if __name__ == "__main__":
    sys.exit(main())
