"""Paths the canvas rooms build from __file__ must land on the repo root, not inside purplecomputer."""

from pathlib import Path

from purplecomputer import sounds
from purplecomputer.rooms import parent_menu


def test_music_sounds_are_found():
    assert (sounds.core_sounds() / "glockenspiel" / "c5.ogg").exists()


def test_parent_shell_rc_is_found():
    assert Path(parent_menu._term_rc()).exists()
