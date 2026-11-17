"""Parent Menu help screen: QR codes for the help hub and for sharing what
kids made, drawn from the pre-baked matrices in qr_data.py."""

from .. import palette as P
from ..constants import SUPPORT_EMAIL
from ..keyboard import ControlAction
from ..qr_data import FRIDGE_QR_MATRIX, FRIDGE_QR_URL, HELP_QR_MATRIX, HELP_QR_URL
from ..ui import Dialog

_QR_DARK = "#1e1033"
_QR_LIGHT = "#f3eefb"

_CODES = (
    ("Scan for videos and other help:", HELP_QR_MATRIX, HELP_QR_URL),
    ("Made something? We'd love to see it:", FRIDGE_QR_MATRIX, FRIDGE_QR_URL),
)


class HelpVideosScreen(Dialog):
    title = "Help & Share What They Made"
    width_pct = 64

    @property
    def hint(self):
        return f"Questions? {SUPPORT_EMAIL}"

    def body_height(self, g):
        return g.vh(42)

    def draw_body(self, g, rect):
        col_w = rect.w // len(_CODES)
        for i, (caption, matrix, url) in enumerate(_CODES):
            self._draw_code(g, rect.x + i * col_w, rect.y, col_w, caption, matrix, url)

    def _draw_code(self, g, x, y, w, caption, matrix, url):
        cx = x + w // 2
        g.draw_markup(caption, g.em(0.92), x + g.vw(1), y, "mono", P.MUTED, w - g.vw(2), "center", P.SURFACE)
        module = max(2, g.vh(26) // len(matrix))
        size = module * len(matrix)
        x0, y0 = cx - size // 2, y + g.vh(8)
        g.rect(_QR_LIGHT, (x0, y0, size, size))
        for r, row in enumerate(matrix):
            for c, bit in enumerate(row):
                if bit == "1":
                    g.rect(_QR_DARK, (x0 + c * module, y0 + r * module, module, module))
        g.draw_text(url.split("://", 1)[-1], g.em(0.98), cx, y0 + size + g.vh(2), "mono-heavy", P.TEXT, anchor="midtop")

    async def handle(self, action):
        if isinstance(action, ControlAction) and action.is_down and action.action == "escape":
            self.close()
