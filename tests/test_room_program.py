"""The room language: what parses, what runs, and what stays calm."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.room_program import LIMITS, RoomError, Runner, TraceHost, format_value, parse, parse_note  # noqa: E402


def run(program, *events, rng=lambda: 0.0):
    host = TraceHost()
    runner = Runner(parse(program), host, rng=rng)

    async def go():
        for event in events:
            await runner.fire(*event)
    asyncio.run(go())
    return host.trace, runner


def room(*rules, **extra):
    return {"name": "test", "title": "Test", "rules": list(rules), **extra}


def when_key(key, *actions):
    return {"when": {"event": "key", "key": key}, "do": list(actions)}


class TestParse:
    def test_notes_and_values(self):
        assert parse_note("C4") == ("C", 4)
        assert parse_note("f#3") == ("F#", 3)
        assert parse_note("H2") is None and parse_note("C") is None
        assert format_value(3.0) == "3" and format_value(2.5) == "2.5" and format_value(1 / 3) == "0.3333" and format_value("x") == "x"

    @pytest.mark.parametrize("bad, message", [
        ({"name": "Bad Name", "rules": []}, "lowercase"),
        ({"name": "ok", "rules": [{"when": {"event": "jump"}, "do": []}]}, "event must be"),
        ({"name": "ok", "rules": [{"when": {"event": "key", "key": "ab"}, "do": []}]}, "one character"),
        ({"name": "ok", "rules": [{"when": {"event": "every", "seconds": 0.1}, "do": []}]}, "seconds between"),
        ({"name": "ok", "rules": [when_key("a", {"do": "fly"})]}, "one of show"),
        ({"name": "ok", "rules": [when_key("a", {"do": "play", "note": "H9"})]}, "note must look like"),
        ({"name": "ok", "rules": [when_key("a", {"do": "background", "color": "red"})]}, "#rrggbb"),
        ({"name": "ok", "rules": [when_key("a", {"do": "if", "test": {"compare": "~", "a": 1, "b": 2}})]}, "compare must be"),
        ({"name": "ok", "rules": [when_key("a", {"do": "show", "text": {"wat": 1}})]}, "unknown value block"),
        ({"name": "ok", "format": 2, "rules": []}, "format must be"),
    ])
    def test_refuses(self, bad, message):
        with pytest.raises(RoomError, match=message):
            parse(bad)

    def test_accepts_a_full_program(self):
        parse(room(
            {"when": {"event": "start"}, "do": [{"do": "set", "var": "n", "value": 0}]},
            when_key("c", {"do": "show", "text": "🐄"}, {"do": "say", "text": {"join": ["cow ", {"var": "n"}]}}),
            {"when": {"event": "any_key"}, "do": [{"do": "change", "var": "n", "by": 1}, {"do": "if", "test": {"compare": ">", "a": {"var": "n"}, "b": 3}, "then": [{"do": "clear"}], "else": [{"do": "wait", "seconds": 0.2}]}]},
            {"when": {"event": "every", "seconds": 2}, "do": [{"do": "repeat", "times": 3, "body": [{"do": "drum", "name": "kick"}]}]},
            background="#1e1033",
        ))


class TestRun:
    def test_key_rules_then_any_key(self):
        trace, _ = run(room(
            when_key("c", {"do": "show", "text": "🐄"}, {"do": "play", "note": "C4"}),
            {"when": {"event": "any_key"}, "do": [{"do": "add", "text": {"key": True}}]},
        ), ("key", "C"), ("key", "x"))
        assert trace == [["show", "🐄"], ["play", "C4", "marimba"], ["add", "c"], ["add", "x"]]

    def test_variables_math_and_branches(self):
        prog = room(
            {"when": {"event": "start"}, "do": [{"do": "set", "var": "n", "value": 1}]},
            {"when": {"event": "any_key"}, "do": [
                {"do": "change", "var": "n", "by": {"math": "*", "a": 2, "b": 1.5}},
                {"do": "if", "test": {"compare": ">", "a": {"var": "n"}, "b": 5}, "then": [{"do": "say", "text": {"join": ["big ", {"var": "n"}]}}], "else": [{"do": "say", "text": "small"}]},
            ]},
        )
        trace, runner = run(prog, ("start",), ("key", "a"), ("key", "b"))
        assert trace == [["say", "small"], ["say", "big 7"]]
        assert runner.vars["n"] == 7

    def test_pick_and_random_follow_the_rng(self):
        seq = iter([0.99, 0.0, 0.5])
        trace, _ = run(room(when_key("a",
            {"do": "show", "text": {"pick": ["x", "y", "z"]}},
            {"do": "show", "text": {"random": {"from": 3, "to": 5}}},
            {"do": "show", "text": {"random": {"from": 3, "to": 5}}},
        )), ("key", "a"), rng=lambda: next(seq))
        assert trace == [["show", "z"], ["show", "3"], ["show", "4"]]

    def test_repeat_and_wait_are_clamped(self):
        trace, _ = run(room(when_key("a",
            {"do": "wait", "seconds": 99},
            {"do": "repeat", "times": 1000, "body": [{"do": "drum", "name": "kick"}]},
        )), ("key", "a"))
        assert trace[0] == ["wait", LIMITS["wait_seconds"]]
        assert len(trace) - 1 <= LIMITS["steps"]

    def test_unknown_note_at_runtime_is_ignored(self):
        trace, _ = run(room(when_key("a", {"do": "play", "note": {"var": "nope"}})), ("key", "a"))
        assert trace == []

    def test_string_compare_and_division_by_zero(self):
        trace, _ = run(room(when_key("a",
            {"do": "if", "test": {"compare": "=", "a": {"key": True}, "b": "a"}, "then": [{"do": "say", "text": "yes"}]},
            {"do": "show", "text": {"math": "/", "a": 1, "b": 0}},
            {"do": "if", "test": {"not": {"and": [{"compare": "<", "a": 1, "b": 2}, {"or": [{"compare": "!=", "a": 1, "b": 1}]}]}}, "then": [{"do": "say", "text": "not"}]},
        )), ("key", "a"))
        assert trace == [["say", "yes"], ["show", "0"], ["say", "not"]]
