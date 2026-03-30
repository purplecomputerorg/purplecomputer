"""Tests for instrument selection: aliases, prefix matching, and code runner commands."""

import asyncio

from purple_tui.code_runner import MusicCodeRunner
from purple_tui.music_constants import INSTRUMENTS, INSTRUMENT_ALIASES


class TestIsInstrument:
    """MusicCodeRunner._is_instrument: exact, alias, and prefix matching."""

    def test_exact_id(self):
        assert MusicCodeRunner._is_instrument("ukulele")

    def test_exact_name(self):
        assert MusicCodeRunner._is_instrument("Ukulele")

    def test_alias_uke(self):
        assert MusicCodeRunner._is_instrument("uke")

    def test_prefix_mar(self):
        assert MusicCodeRunner._is_instrument("mar")

    def test_prefix_xylo(self):
        assert MusicCodeRunner._is_instrument("xylo")

    def test_prefix_music(self):
        assert MusicCodeRunner._is_instrument("music")

    def test_nonexistent(self):
        assert not MusicCodeRunner._is_instrument("guitar")

    def test_empty(self):
        assert not MusicCodeRunner._is_instrument("")

    def test_case_insensitive(self):
        assert MusicCodeRunner._is_instrument("MARIMBA")
        assert MusicCodeRunner._is_instrument("UKE")


class TestInstrumentAliases:
    """INSTRUMENT_ALIASES resolves correctly."""

    def test_uke_resolves(self):
        assert INSTRUMENT_ALIASES["uke"] == "ukulele"

    def test_alias_maps_to_valid_instrument(self):
        ids = {inst_id for inst_id, _ in INSTRUMENTS}
        for alias, target in INSTRUMENT_ALIASES.items():
            assert target in ids, f"Alias '{alias}' -> '{target}' not in INSTRUMENTS"


class TestChooseCommand:
    """MusicCodeRunner 'choose'/'select'/'use'/'play' commands set instrument."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _make_runner(self):
        self._selected = None
        def set_inst(name):
            from purple_tui.music_constants import INSTRUMENT_ALIASES
            resolved = INSTRUMENT_ALIASES.get(name.lower(), name.lower())
            for i, (inst_id, inst_name) in enumerate(INSTRUMENTS):
                if inst_name.lower() == resolved or inst_id == resolved:
                    self._selected = inst_id
                    return
                if inst_name.lower().startswith(resolved) or inst_id.startswith(resolved):
                    self._selected = inst_id
                    return
        return MusicCodeRunner(
            play_key_fn=lambda k, m: None,
            set_instrument_fn=set_inst,
        )

    def test_choose_ukulele(self):
        runner = self._make_runner()
        self._run(runner.run(["choose ukulele"]))
        assert self._selected == "ukulele"

    def test_choose_uke_alias(self):
        runner = self._make_runner()
        self._run(runner.run(["choose uke"]))
        assert self._selected == "ukulele"

    def test_select_uke(self):
        runner = self._make_runner()
        self._run(runner.run(["select uke"]))
        assert self._selected == "ukulele"

    def test_use_uke(self):
        runner = self._make_runner()
        self._run(runner.run(["use uke"]))
        assert self._selected == "ukulele"

    def test_play_uke_selects_instrument(self):
        runner = self._make_runner()
        self._run(runner.run(["play uke"]))
        assert self._selected == "ukulele"

    def test_choose_marimba(self):
        runner = self._make_runner()
        self._run(runner.run(["choose marimba"]))
        assert self._selected == "marimba"

    def test_choose_prefix_xylo(self):
        runner = self._make_runner()
        self._run(runner.run(["choose xylo"]))
        assert self._selected == "xylophone"

    def test_play_nonexistent_falls_through(self):
        """'play apple' should NOT set instrument (falls back to notes)."""
        runner = self._make_runner()
        self._run(runner.run(["play apple"]))
        assert self._selected is None
