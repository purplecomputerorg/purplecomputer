"""Tests for instrument selection: aliases, prefix matching, fuzzy, and code runner commands."""

import asyncio

from purple_tui.code_runner import MusicCodeRunner


class TestResolveInstrument:
    """MusicCodeRunner._resolve_instrument: exact, alias, prefix, and fuzzy matching."""

    def test_exact_id(self):
        assert MusicCodeRunner._resolve_instrument("ukulele") is not None

    def test_exact_name(self):
        assert MusicCodeRunner._resolve_instrument("Ukulele") is not None

    def test_alias_uke(self):
        assert MusicCodeRunner._resolve_instrument("uke") is not None

    def test_prefix_mar(self):
        assert MusicCodeRunner._resolve_instrument("mar") is not None

    def test_prefix_acc(self):
        assert MusicCodeRunner._resolve_instrument("acc") is not None

    def test_prefix_glock(self):
        assert MusicCodeRunner._resolve_instrument("glock") is not None

    def test_nonexistent(self):
        assert MusicCodeRunner._resolve_instrument("guitar") is None

    def test_empty(self):
        assert MusicCodeRunner._resolve_instrument("") is None

    def test_case_insensitive(self):
        assert MusicCodeRunner._resolve_instrument("MARIMBA") is not None
        assert MusicCodeRunner._resolve_instrument("UKE") is not None

    def test_fuzzy_accordian(self):
        assert MusicCodeRunner._resolve_instrument("accordian") is not None

    def test_fuzzy_marimab(self):
        assert MusicCodeRunner._resolve_instrument("marimab") is not None


class TestCodeRunnerInstrumentChange:
    """Integration tests for instrument change via code runner."""

    def test_choose_command(self):
        instruments = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: None,
            set_instrument_fn=lambda name: instruments.append(name),
        )
        asyncio.run(runner.run(["choose marimba"]))
        assert len(instruments) == 1

    def test_instrument_command(self):
        instruments = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: None,
            set_instrument_fn=lambda name: instruments.append(name),
        )
        asyncio.run(runner.run(["instrument accordion"]))
        assert len(instruments) == 1

    def test_play_instrument(self):
        instruments = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: None,
            set_instrument_fn=lambda name: instruments.append(name),
        )
        asyncio.run(runner.run(["play ukulele"]))
        assert len(instruments) == 1

    def test_play_notes(self):
        played = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: played.append(k),
        )
        asyncio.run(runner.run(["play qwe"]))
        assert played == ['Q', 'W', 'E']

    def test_choose_with_junk_argument_plays_no_notes(self):
        played = []
        instruments = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: played.append(k),
            set_instrument_fn=lambda name: instruments.append(name),
        )
        asyncio.run(runner.run(["choose uke fdasfdsa"]))
        assert played == []
        assert instruments == []

    def test_letters_with_bad_argument_plays_no_notes(self):
        played = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: played.append(k),
        )
        asyncio.run(runner.run(["letters banana"]))
        assert played == []


def _make_runner():
    state = {"played": [], "instruments": [], "letters": []}
    runner = MusicCodeRunner(
        play_key_fn=lambda k, m: state["played"].append(k),
        set_instrument_fn=lambda name: state["instruments"].append(name),
        set_letters_fn=lambda on: state["letters"].append(on),
    )
    return runner, state


class TestDispatchClaimsKeywords:
    """A recognized command keyword claims the line: it never falls through to
    being sounded out note by note, whether or not its argument resolves."""

    def test_every_instrument_keyword_with_junk_plays_no_notes(self):
        for keyword in ("choose", "instrument", "select", "use"):
            runner, state = _make_runner()
            asyncio.run(runner.run([f"{keyword} zzzqqq"]))
            assert state["played"] == [], keyword
            assert state["instruments"] == [], keyword

    def test_play_with_junk_still_plays_notes(self):
        # `play` is intentionally dual-purpose: an unresolved argument plays as
        # notes (only the valid note letters), not as an instrument switch.
        runner, state = _make_runner()
        asyncio.run(runner.run(["play qwe"]))
        assert state["played"] == ["Q", "W", "E"]
        assert state["instruments"] == []

    def test_play_keyword_itself_never_sounded(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["play zzz"]))
        # Only the argument is played, never the word "play".
        assert state["played"] == ["Z", "Z", "Z"]

    def test_plain_letters_line_plays_as_notes(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["qwerty"]))
        assert state["played"] == ["Q", "W", "E", "R", "T", "Y"]


class TestFuzzyKeywordCorrection:
    """Misspelled command keywords are fuzzy-corrected, then claimed."""

    def test_misspelled_choose_switches_instrument(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["chooze marimba"]))
        assert state["instruments"] == ["marimba"]
        assert state["played"] == []
        assert ("chooze marimba", "choose marimba") in runner.corrections

    def test_misspelled_choose_with_bad_instrument_plays_no_notes(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["chooze zzzqqq"]))
        assert state["played"] == []
        assert state["instruments"] == []
        # The keyword fix is still recorded for the "did you mean" display.
        assert ("chooze zzzqqq", "choose zzzqqq") in runner.corrections


class TestLettersToggle:
    """`letters on/off` toggles letters mode via the callback."""

    def test_letters_on_then_off(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["letters on", "letters off"]))
        assert state["letters"] == [True, False]
        assert state["played"] == []

    def test_letters_fuzzy_on(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["letters onn"]))
        assert state["letters"] == [True]


class TestSpeedPrefix:
    """Speed prefixes route to note playback, not the command table."""

    def test_fast_prefix_plays_argument_notes(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["fast qwe"]))
        assert state["played"] == ["Q", "W", "E"]

    def test_slow_prefix_plays_argument_notes(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["slow qwe"]))
        assert state["played"] == ["Q", "W", "E"]
