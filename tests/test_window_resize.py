"""The canvas follows the window when the screen changes size after startup
(spice-vdagent resizes the X screen in UTM/QEMU once the window is up)."""

import pygame

from purplecomputer import harness  # noqa: F401  (sets SDL dummy drivers)
from purplecomputer.gfx import Gfx
from purplecomputer.sdl_input import pump


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
        assert g.stage == pygame.Rect(0, 96, 1024, 576)   # the 16:9 stage, centered
        assert g.vh(50) == 288
    finally:
        pygame.display.quit()
