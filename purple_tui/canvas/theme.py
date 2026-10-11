"""A family's colors from a pack's content/theme.json (studio/PACK_FORMAT.md): the ground
around the rooms, the Art canvas, and the letter-row colors every room paints with. The number
row stays gray. Without a theme, Purple's own colors stand.

Applied at startup over Purple's defaults; KEY_COLORS and ROW_LEGEND_COLORS are changed in place
because the rooms hold references to them."""

import re

from .. import palette as P
from ..content import _read_json, get_content
from .rooms import art_room

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LETTER_ROWS = [P.QWERTY_ROW, P.ASDF_ROW, P.ZXCV_ROW]
_DEFAULTS = {"BG": P.BG, "keys": dict(P.KEY_COLORS), "legend": [list(r) for r in P.ROW_LEGEND_COLORS],
             "canvas": (art_room.CANVAS_BG, art_room.CANVAS_ALT)}


def find() -> dict:
    """The theme of the most recently installed pack that has one, keeping only valid colors."""
    for content_dir in reversed(get_content().user_content):
        data = _read_json(content_dir / "theme.json")
        if isinstance(data, dict):
            keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
            row_keys = {k for row in LETTER_ROWS for k in row}
            return {
                "background": data.get("background") if HEX.match(str(data.get("background"))) else None,
                "surface": data.get("surface") if HEX.match(str(data.get("surface"))) else None,
                "keys": {k: v for k, v in keys.items() if k in row_keys and HEX.match(str(v))},
            }
    return {}


def _step(color: str, by: int = 6) -> str:
    """The checkerboard partner of a canvas color: the same small step Purple's own pair takes."""
    return "#" + "".join(f"{min(255, int(color[i:i + 2], 16) + by):02x}" for i in (1, 3, 5))


def apply(theme: dict) -> None:
    P.BG = theme.get("background") or _DEFAULTS["BG"]
    surface = theme.get("surface")
    art_room.CANVAS_BG, art_room.CANVAS_ALT = (surface, _step(surface)) if surface else _DEFAULTS["canvas"]
    P.KEY_COLORS.clear()
    P.KEY_COLORS.update(_DEFAULTS["keys"])
    P.KEY_COLORS.update(theme.get("keys", {}))
    P.KEY_COLORS["÷"] = P.KEY_COLORS["×"] = P.KEY_COLORS["/"]
    for r, row in enumerate(LETTER_ROWS, start=1):
        shades = [P.KEY_COLORS[row[i]] for i in (1, len(row) // 2, -2)]
        P.ROW_LEGEND_COLORS[r][:] = shades if theme.get("keys") else _DEFAULTS["legend"][r]


def legend_row(color: str) -> int:
    """Which legend row a painted color belongs to: by the key it came from, so family hues
    land on the right row too."""
    for r, row in enumerate(LETTER_ROWS, start=1):
        if any(P.KEY_COLORS.get(k, "").lower() == color.lower() for k in row):
            return r
    return P.get_legend_row_from_color(color)
