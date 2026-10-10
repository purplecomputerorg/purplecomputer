"""Paths the canvas rooms build from __file__ must land on the repo root, not inside purple_tui."""

from pathlib import Path

from purple_tui.canvas import sounds
from purple_tui.canvas.rooms import parent_menu


def test_music_sounds_are_found():
    assert (sounds.core_sounds() / "glockenspiel" / "c5.ogg").exists()


def test_parent_shell_rc_is_found():
    assert Path(parent_menu._term_rc()).exists()
