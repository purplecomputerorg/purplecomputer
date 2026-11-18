"""Tests for instrument selection: aliases, prefix matching, fuzzy, and code runner commands."""

import asyncio

from purplecomputer.code_runner import MusicCodeRunner


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

    def test_play_misspelled_instrument_actually_switches(self):
        instruments = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: None,
            set_instrument_fn=lambda name: instruments.append(name),
        )
        asyncio.run(runner.run(["play marimab"]))
        assert instruments == ["marimba"]

    def test_play_notes(self):
        played = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: played.append(k),
        )
        asyncio.run(runner.run(["play qwe"]))
        assert played == ['Q', 'W', 'E']

    def test_choose_instrument_then_plays_trailing_notes(self):
        # Like the Art room ("green forward 10"), the instrument command peels
        # off the leading instrument word and plays the rest as notes.
        played = []
        instruments = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: played.append(k),
            set_instrument_fn=lambda name: instruments.append(name),
        )
        asyncio.run(runner.run(["choose uke asdf"]))
        assert instruments == ["ukulele"]
        assert played == ["A", "S", "D", "F"]

    def test_letters_then_keys_says_them(self):
        played = []
        runner = MusicCodeRunner(
            play_key_fn=lambda k, m: played.append((k, m)),
        )
        asyncio.run(runner.run(["letters banana"]))
        assert played == [(k, "letters") for k in "BANANA"]


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

    def test_misspelled_instrument_then_plays_trailing_notes(self):
        runner, state = _make_runner()
        asyncio.run(runner.run(["choose glockenppiel asdf"]))
        assert state["instruments"] == ["glockenspiel"]
        assert state["played"] == ["A", "S", "D", "F"]

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


class TestModeWordThenKeys:
    """A mode word then keys switches for good and plays them in that mode."""

    def _run(self, lines, mode):
        played, letters = [], []
        runner = MusicCodeRunner(play_key_fn=lambda k, m: played.append((k, m)), set_letters_fn=letters.append)
        asyncio.run(runner.run(lines, mode))
        return played, letters

    def test_music_then_keys_from_letters(self):
        played, letters = self._run(["music fast asd"], "letters")
        assert played == [(k, "music") for k in "ASD"] and letters == [False]

    def test_music_before_repeat_loops_every_clause(self):
        played, _ = self._run(["music repeat 2 as, d"], "letters")
        assert [k for k, _ in played] == list("ASDASD")

    def test_mode_stays_for_the_next_line(self):
        played, _ = self._run(["letters ab", "cd"], "music")
        assert {m for _, m in played} == {"letters"}


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


class TestNotesByNameAndVoices:
    """`notes` plays notes by name to the end of its line; `choose sounds` and `letters sounds` say what follows."""

    def _run(self, lines, mode="music"):
        from purplecomputer.music_constants import GRID_KEYS
        played, letters, sounds = [], [], []
        row = GRID_KEYS[2]
        names = dict(zip("CDEFGAB", row))   # the key of C: the middle row from its root
        runner = MusicCodeRunner(play_key_fn=lambda k, m: played.append((k, m)), set_letters_fn=letters.append,
                                 set_letter_sounds_fn=sounds.append, note_key_fn=names.get,
                                 set_instrument_fn=lambda name: None)
        asyncio.run(runner.run(lines, mode))
        return [k for k, _ in played], letters, sounds, played

    def test_notes_play_by_name_and_other_letters_play_as_keys(self):
        keys, *_ = self._run(["notes ccgh"])
        assert keys == ["A", "A", "G", "H"]

    def test_names_last_to_the_end_of_the_line_through_commas_loops_and_choose(self):
        keys, *_ = self._run(["notes repeat 2 c, g"])
        assert keys == ["A", "G", "A", "G"]
        keys, *_ = self._run(["notes fast c choose ukulele d"])
        assert keys == ["A", "S"]

    def test_the_next_line_plays_keys_again(self):
        keys, *_ = self._run(["notes c", "c"])
        assert keys == ["A", "C"]

    def test_letters_sounds_then_letters_says_them(self):
        keys, letters, sounds, played = self._run(["letters sounds ab"])
        assert keys == ["A", "B"] and letters == [True] and sounds == [True] and {m for _, m in played} == {"letters"}

    def test_choose_sounds_or_names_turns_letters_on_and_says_what_follows(self):
        keys, letters, sounds, played = self._run(["choose names cat"])
        assert keys == ["C", "A", "T"] and letters == [True] and sounds == [False]
        assert {m for _, m in played} == {"letters"}

    def test_sounds_alone_is_just_keys(self):
        keys, letters, *_ = self._run(["sounds"])
        assert keys == list("SOUNDS") and letters == []
