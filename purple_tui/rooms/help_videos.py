"""Help & Videos: a QR code to purplecomputer.org/help, drawn from the
pre-baked matrix in qr_data.py."""

from .. import palette as P
from ..constants import SUPPORT_EMAIL
from ..keyboard import ControlAction
from ..qr_data import HELP_QR_MATRIX, HELP_QR_URL
from ..ui import Dialog

_QR_DARK = "#1e1033"
_QR_LIGHT = "#f3eefb"


class HelpVideosScreen(Dialog):
    title = "Help & Videos"
    width_pct = 44

    @property
    def hint(self):
        return f"Questions? {SUPPORT_EMAIL}"

    def body_height(self, g):
        return g.vh(52)

    def draw_body(self, g, rect):
        g.draw_text("Scan for videos and other help:", g.vh(2.2), rect.centerx, rect.y, "sans", P.MUTED, anchor="midtop")
        n = len(HELP_QR_MATRIX)
        module = max(2, g.vh(40) // n)
        size = module * n
        x0, y0 = rect.centerx - size // 2, rect.y + g.vh(4)
        g.rect(_QR_LIGHT, (x0, y0, size, size))
        for r, row in enumerate(HELP_QR_MATRIX):
            for c, bit in enumerate(row):
                if bit == "1":
                    g.rect(_QR_DARK, (x0 + c * module, y0 + r * module, module, module))
        g.draw_text(HELP_QR_URL.split("://", 1)[-1], g.vh(2.4), rect.centerx, y0 + size + g.vh(2), "sans-heavy", P.TEXT, anchor="midtop")

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.is_down and action.action == "escape":
            self.close()
