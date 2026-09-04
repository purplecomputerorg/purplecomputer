"""Room programs: the small declarative language behind family-made rooms.

A room is content/rooms/<name>.json in a pack: a title and a list of rules,
each "when <event>" with a list of things to do. No code runs; Purple walks
the JSON. studio/sdk/src/room.ts is the same interpreter in TypeScript, held
to this one by the trace in studio/tests/room-golden.json, so the room a
parent tries in Studio behaves the same on the laptop.

    {"name": "farm", "title": "Farm", "rules": [
      {"when": {"event": "key", "key": "c"},
       "do": [{"do": "show", "text": "🐄"}, {"do": "say", "text": "cow"},
              {"do": "play", "note": "C4", "instrument": "marimba"}]}]}

Events: start, key (with "key"), any_key, every (with "seconds").
Actions: show, add, say, play, drum, clear, background, wait, set, change,
if, repeat. Values: a number, a string, {"var": name}, {"key": true},
{"pick": [...]}, {"join": [...]}, {"random": {"from": a, "to": b}},
{"math": op, "a": x, "b": y}. Tests: {"compare": op, "a": x, "b": y},
{"and": [...]}, {"or": [...]}, {"not": t}.

Everything is clamped so a mashed keyboard or a runaway loop stays calm:
a bounded number of steps per event, short waits, short text.
"""

import math
import random
import re
from typing import Any, Callable, Protocol

ROOM_FORMAT = 1
EVENTS = ("start", "key", "any_key", "every")
ACTIONS = ("show", "add", "say", "play", "drum", "clear", "background", "wait", "set", "change", "if", "repeat")
MATH_OPS = ("+", "-", "*", "/")
COMPARE_OPS = ("=", "!=", "<", ">")
SPECIAL_KEYS = ("space", "enter", "up", "down", "left", "right")
LIMITS = {"steps": 500, "wait_seconds": 5.0, "text": 200, "repeat": 100, "depth": 8, "line": 400, "every_min_seconds": 0.5}

_NOTE = re.compile(r"^([A-Ga-g])(#?)(\d)$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

Value = float | str


class RoomError(ValueError):
    """A program that Purple will not run, with the reason."""


class Host(Protocol):
    def show(self, text: str) -> None: ...
    def add(self, text: str) -> None: ...
    def say(self, text: str) -> None: ...
    def play(self, note: str, instrument: str) -> None: ...
    def drum(self, name: str) -> None: ...
    def clear(self) -> None: ...
    def background(self, color: str) -> None: ...
    async def wait(self, seconds: float) -> None: ...


def parse_note(text: str) -> tuple[str, int] | None:
    """'C#4' -> ('C#', 4); None for anything that is not a note name."""
    m = _NOTE.match(text.strip())
    return (m.group(1).upper() + m.group(2), int(m.group(3))) if m else None


def parse(data: Any) -> dict:
    """Validate a room program and return it, or raise RoomError."""
    if not isinstance(data, dict):
        raise RoomError("a room is a JSON object")
    name = data.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        raise RoomError("name must be lowercase letters, digits, and dashes")
    if data.get("format", ROOM_FORMAT) != ROOM_FORMAT:
        raise RoomError(f"format must be {ROOM_FORMAT}")
    title = data.get("title", name)
    if not isinstance(title, str) or not title.strip() or len(title) > 40:
        raise RoomError("title must be a short string")
    background = data.get("background")
    if background is not None and not (isinstance(background, str) and _HEX.match(background)):
        raise RoomError("background must be #rrggbb")
    rules = data.get("rules")
    if not isinstance(rules, list) or len(rules) > 200:
        raise RoomError("rules must be a list")
    for i, rule in enumerate(rules):
        where = f"rule {i + 1}"
        if not isinstance(rule, dict) or not isinstance(rule.get("when"), dict) or not isinstance(rule.get("do"), list):
            raise RoomError(f"{where}: needs a when and a do list")
        _check_event(rule["when"], where)
        _check_actions(rule["do"], where, 0)
    return data


def _check_event(when: dict, where: str) -> None:
    event = when.get("event")
    if event not in EVENTS:
        raise RoomError(f"{where}: event must be one of {', '.join(EVENTS)}")
    if event == "key":
        key = when.get("key")
        if not isinstance(key, str) or not (len(key) == 1 or key in SPECIAL_KEYS):
            raise RoomError(f"{where}: key must be one character or one of {', '.join(SPECIAL_KEYS)}")
    if event == "every":
        seconds = when.get("seconds")
        if not _is_number(seconds) or seconds < LIMITS["every_min_seconds"] or seconds > 60:
            raise RoomError(f"{where}: every needs seconds between {LIMITS['every_min_seconds']} and 60")


def _check_actions(actions: list, where: str, depth: int) -> None:
    if depth > LIMITS["depth"]:
        raise RoomError(f"{where}: nested too deep")
    if len(actions) > LIMITS["steps"]:
        raise RoomError(f"{where}: too many actions")
    for action in actions:
        if not isinstance(action, dict) or action.get("do") not in ACTIONS:
            raise RoomError(f"{where}: each action needs a do that is one of {', '.join(ACTIONS)}")
        kind = action["do"]
        if kind in ("show", "add", "say"):
            _check_value(action.get("text"), where)
        elif kind == "play":
            _check_value(action.get("note"), where)
            if isinstance(action.get("note"), str) and parse_note(action["note"]) is None:
                raise RoomError(f"{where}: note must look like C4 or F#3")
            if "instrument" in action and not isinstance(action["instrument"], str):
                raise RoomError(f"{where}: instrument must be a name")
        elif kind == "drum":
            if not isinstance(action.get("name"), str):
                raise RoomError(f"{where}: drum needs a name")
        elif kind == "background":
            if not (isinstance(action.get("color"), str) and _HEX.match(action["color"])):
                raise RoomError(f"{where}: background color must be #rrggbb")
        elif kind == "wait":
            _check_value(action.get("seconds"), where)
        elif kind in ("set", "change"):
            if not isinstance(action.get("var"), str) or not action["var"]:
                raise RoomError(f"{where}: {kind} needs a var name")
            _check_value(action.get("value" if kind == "set" else "by"), where)
        elif kind == "if":
            _check_test(action.get("test"), where)
            for branch in ("then", "else"):
                if branch in action:
                    if not isinstance(action[branch], list):
                        raise RoomError(f"{where}: {branch} must be a list")
                    _check_actions(action[branch], where, depth + 1)
        elif kind == "repeat":
            _check_value(action.get("times"), where)
            if not isinstance(action.get("body"), list):
                raise RoomError(f"{where}: repeat needs a body list")
            _check_actions(action["body"], where, depth + 1)


def _check_value(value: Any, where: str) -> None:
    if _is_number(value) or isinstance(value, str):
        return
    if not isinstance(value, dict) or len(value) == 0:
        raise RoomError(f"{where}: expected a number, text, or a value block")
    if "var" in value:
        if not isinstance(value["var"], str):
            raise RoomError(f"{where}: var needs a name")
    elif "key" in value:
        pass
    elif "pick" in value or "join" in value:
        items = value.get("pick", value.get("join"))
        if not isinstance(items, list) or not items:
            raise RoomError(f"{where}: pick and join need a non-empty list")
        for item in items:
            _check_value(item, where)
    elif "random" in value:
        r = value["random"]
        if not isinstance(r, dict):
            raise RoomError(f"{where}: random needs from and to")
        _check_value(r.get("from"), where)
        _check_value(r.get("to"), where)
    elif "math" in value:
        if value["math"] not in MATH_OPS:
            raise RoomError(f"{where}: math must be one of {' '.join(MATH_OPS)}")
        _check_value(value.get("a"), where)
        _check_value(value.get("b"), where)
    else:
        raise RoomError(f"{where}: unknown value block {sorted(value)}")


def _check_test(test: Any, where: str) -> None:
    if not isinstance(test, dict):
        raise RoomError(f"{where}: if needs a test")
    if "compare" in test:
        if test["compare"] not in COMPARE_OPS:
            raise RoomError(f"{where}: compare must be one of {' '.join(COMPARE_OPS)}")
        _check_value(test.get("a"), where)
        _check_value(test.get("b"), where)
    elif "and" in test or "or" in test:
        items = test.get("and", test.get("or"))
        if not isinstance(items, list):
            raise RoomError(f"{where}: and/or need a list")
        for item in items:
            _check_test(item, where)
    elif "not" in test:
        _check_test(test["not"], where)
    else:
        raise RoomError(f"{where}: unknown test {sorted(test)}")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def format_value(v: Value) -> str:
    """Numbers read the way a kid would write them: 3, not 3.0; 2.5 stays 2.5."""
    if isinstance(v, str):
        return v
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def to_number(v: Value) -> float:
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return 0.0
    return float(v)


class Runner:
    """Runs one room program against a host. One instance per open room."""

    def __init__(self, program: dict, host: Host, rng: Callable[[], float] = random.random):
        self.program = program
        self.host = host
        self.rng = rng
        self.vars: dict[str, Value] = {}
        self._key = ""
        self._steps = 0

    def rules_for(self, event: str, key: str = "") -> list[dict]:
        key = key.lower()
        return [r for r in self.program["rules"]
                if r["when"]["event"] == event and (event != "key" or r["when"]["key"].lower() == key)]

    def every_rules(self) -> list[tuple[float, dict]]:
        return [(float(r["when"]["seconds"]), r) for r in self.program["rules"] if r["when"]["event"] == "every"]

    async def fire(self, event: str, key: str = "") -> None:
        """Run every rule for an event, in order. A key press fires its own
        key rules and then any_key."""
        self._key = key.lower()
        rules = self.rules_for(event, key)
        if event == "key":
            rules += self.rules_for("any_key")
        self._steps = 0
        for rule in rules:
            await self._run(rule["do"], 0)

    async def run_rule(self, rule: dict) -> None:
        self._steps = 0
        await self._run(rule["do"], 0)

    async def _run(self, actions: list, depth: int) -> None:
        if depth > LIMITS["depth"]:
            return
        for action in actions:
            self._steps += 1
            if self._steps > LIMITS["steps"]:
                return
            await self._do(action, depth)

    async def _do(self, action: dict, depth: int) -> None:
        kind = action["do"]
        if kind in ("show", "add", "say"):
            getattr(self.host, kind)(self.text(action["text"]))
        elif kind == "play":
            note = self.text(action["note"])
            if parse_note(note):
                self.host.play(note, action.get("instrument", "marimba"))
        elif kind == "drum":
            self.host.drum(action["name"])
        elif kind == "clear":
            self.host.clear()
        elif kind == "background":
            self.host.background(action["color"])
        elif kind == "wait":
            await self.host.wait(min(max(0.0, to_number(self.eval(action["seconds"]))), LIMITS["wait_seconds"]))
        elif kind == "set":
            self.vars[action["var"]] = self.eval(action["value"])
        elif kind == "change":
            self.vars[action["var"]] = to_number(self.vars.get(action["var"], 0.0)) + to_number(self.eval(action["by"]))
        elif kind == "if":
            branch = action.get("then" if self.test(action["test"]) else "else", [])
            await self._run(branch, depth + 1)
        elif kind == "repeat":
            times = int(min(max(0.0, to_number(self.eval(action["times"]))), LIMITS["repeat"]))
            for _ in range(times):
                if self._steps > LIMITS["steps"]:
                    return
                await self._run(action["body"], depth + 1)

    def text(self, value: Any) -> str:
        return format_value(self.eval(value))[:LIMITS["text"]]

    def eval(self, value: Any) -> Value:
        if isinstance(value, str):
            return value
        if _is_number(value):
            return float(value)
        if "var" in value:
            return self.vars.get(value["var"], 0.0)
        if "key" in value:
            return self._key
        if "pick" in value:
            items = value["pick"]
            return self.eval(items[int(self.rng() * len(items)) % len(items)])
        if "join" in value:
            return "".join(format_value(self.eval(item)) for item in value["join"])
        if "random" in value:
            lo = math.floor(to_number(self.eval(value["random"]["from"])))
            hi = math.floor(to_number(self.eval(value["random"]["to"])))
            if hi < lo:
                lo, hi = hi, lo
            return float(lo + int(self.rng() * (hi - lo + 1)) % (hi - lo + 1))
        if "math" in value:
            a, b = to_number(self.eval(value["a"])), to_number(self.eval(value["b"]))
            op = value["math"]
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            return a / b if b != 0 else 0.0
        return 0.0

    def test(self, test: dict) -> bool:
        if "compare" in test:
            a, b = self.eval(test["a"]), self.eval(test["b"])
            op = test["compare"]
            if isinstance(a, str) or isinstance(b, str):
                a, b = format_value(a), format_value(b)
                return (a == b) if op == "=" else (a != b) if op == "!=" else (a < b) if op == "<" else (a > b)
            return (a == b) if op == "=" else (a != b) if op == "!=" else (a < b) if op == "<" else (a > b)
        if "and" in test:
            return all(self.test(t) for t in test["and"])
        if "or" in test:
            return any(self.test(t) for t in test["or"])
        return not self.test(test["not"])


class TraceHost:
    """Records every host call, for tests and the Studio parity golden."""

    def __init__(self) -> None:
        self.trace: list[list] = []

    def show(self, text): self.trace.append(["show", text])
    def add(self, text): self.trace.append(["add", text])
    def say(self, text): self.trace.append(["say", text])
    def play(self, note, instrument): self.trace.append(["play", note, instrument])
    def drum(self, name): self.trace.append(["drum", name])
    def clear(self): self.trace.append(["clear"])
    def background(self, color): self.trace.append(["background", color])
    async def wait(self, seconds): self.trace.append(["wait", seconds])
