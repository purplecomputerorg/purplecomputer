"""Parent Menu QR screens (help, sharing what kids made), drawn from the
pre-baked matrices in qr_data.py."""

from .. import palette as P
from ..constants import SUPPORT_EMAIL
from ..keyboard import ControlAction
from ..qr_data import FRIDGE_QR_MATRIX, FRIDGE_QR_URL, HELP_QR_MATRIX, HELP_QR_URL
from ..ui import Dialog

_QR_DARK = "#1e1033"
_QR_LIGHT = "#f3eefb"


class QrScreen(Dialog):
    width_pct = 44
    caption = ""
    matrix: list = []
    url = ""

    @property
    def hint(self):
        return f"Questions? {SUPPORT_EMAIL}"

    def body_height(self, g):
        return g.vh(52)

    def draw_body(self, g, rect):
        g.draw_text(self.caption, g.em(0.92), rect.centerx, rect.y, "mono", P.MUTED, anchor="midtop")
        n = len(self.matrix)
        module = max(2, g.vh(40) // n)
        size = module * n
        x0, y0 = rect.centerx - size // 2, rect.y + g.vh(4)
        g.rect(_QR_LIGHT, (x0, y0, size, size))
        for r, row in enumerate(self.matrix):
            for c, bit in enumerate(row):
                if bit == "1":
                    g.rect(_QR_DARK, (x0 + c * module, y0 + r * module, module, module))
        g.draw_text(self.url.split("://", 1)[-1], g.em(0.98), rect.centerx, y0 + size + g.vh(2), "mono-heavy", P.TEXT, anchor="midtop")

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.is_down and action.action == "escape":
            self.close()


class HelpVideosScreen(QrScreen):
    title = "Help & Videos"
    caption = "Scan for videos and other help:"
    matrix = HELP_QR_MATRIX
    url = HELP_QR_URL


class FridgeScreen(QrScreen):
    title = "Share What They Made"
    caption = "Made something? I'd love to see it:"
    matrix = FRIDGE_QR_MATRIX
    url = FRIDGE_QR_URL
