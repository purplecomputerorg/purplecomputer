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

    def test_prefix_org(self):
        assert MusicCodeRunner._resolve_instrument("org") is not None

    def test_prefix_music(self):
        assert MusicCodeRunner._resolve_instrument("music") is not None

    def test_nonexistent(self):
        assert MusicCodeRunner._resolve_instrument("guitar") is None

    def test_empty(self):
        assert MusicCodeRunner._resolve_instrument("") is None

    def test_case_insensitive(self):
        assert MusicCodeRunner._resolve_instrument("MARIMBA") is not None
        assert MusicCodeRunner._resolve_instrument("UKE") is not None

    def test_fuzzy_organn(self):
        assert MusicCodeRunner._resolve_instrument("organn") is not None

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
        asyncio.run(runner.run(["instrument organ"]))
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
