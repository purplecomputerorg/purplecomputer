"""The canvas follows the window when the screen changes size after startup
(spice-vdagent resizes the X screen in UTM/QEMU once the window is up)."""

import pygame

from purple_tui import harness  # noqa: F401  (sets SDL dummy drivers)
from purple_tui.gfx import Gfx
from purple_tui.sdl_input import pump


def test_window_size_change_resizes_canvas():
    g = Gfx(size=(800, 600), windowed=True)
    try:
        g.dirty = False
        pygame.display.set_mode((1024, 768))
        pygame.event.post(pygame.event.Event(pygame.WINDOWSIZECHANGED, x=1024, y=768))
        assert list(pump(g)) == []
        assert (g.w, g.h) == (1024, 768)
        assert g.surface.get_size() == (1024, 768)
        assert g.dirty
        assert g.vh(50) == 384
    finally:
        pygame.display.quit()
