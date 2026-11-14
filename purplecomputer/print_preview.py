"""What a pretend printer (PURPLE_FAKE_PRINTER=1, as the test VM runs) was sent, shown on screen."""

from . import palette as P
from .keyboard import ControlAction, NavigationAction
from .saves import fit
from .ui import Overlay, draw_key_hint


class PrintPreview(Overlay):
    scrim = False

    def __init__(self, app, pages):
        super().__init__(app)
        self.pages, self.at = pages, 0

    async def handle(self, action):
        if getattr(action, "is_repeat", False) or (isinstance(action, ControlAction) and not action.is_down):
            return
        if isinstance(action, NavigationAction):
            self.at = (self.at + (-1 if action.direction in ("left", "up") else 1)) % len(self.pages)
            self.app.invalidate()
        else:
            self.close()

    def draw(self, g):
        g.fill(P.BG)
        pic = fit(self.pages[self.at], g.vw(92), g.vh(80))
        g.surface.blit(pic, pic.get_rect(midtop=(g.w // 2, g.vh(3))))
        turn = f"Page {self.at + 1} of {len(self.pages)}: {{←}} {{→}}   " if len(self.pages) > 1 else ""
        draw_key_hint(g, f"Pretend printer. {turn}Any key closes", g.vh(2.4), g.w // 2, g.vh(90), P.TEXT, "midtop")
