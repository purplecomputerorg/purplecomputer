"""A family's colors from a pack's content/theme.json (studio/PACK_FORMAT.md): the screen's
palette (ground, panels, text), the Art canvas, and the letter-row colors every room paints with.
The number row stays gray. Without a theme, Purple's own colors stand.

Applied at startup over Purple's defaults. Palette roles are module attributes read at draw
time; KEY_COLORS is changed in place because rooms hold references."""

import re

from .. import palette as P
from ..content import _read_json, get_content
from .rooms import art_room

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
ROLES = ["bg", "surface", "tile", "field", "hair", "line", "primary", "on_primary", "accent", "text", "muted", "dim"]
LETTER_ROWS = [P.QWERTY_ROW, P.ASDF_ROW, P.ZXCV_ROW]
_DEFAULTS = {"roles": {r: getattr(P, r.upper()) for r in ROLES}, "keys": dict(P.KEY_COLORS),
             "canvas": (art_room.CANVAS_BG, art_room.CANVAS_ALT)}


def _colors(data, allowed) -> dict:
    return {k: v for k, v in data.items() if k in allowed and HEX.match(str(v))} if isinstance(data, dict) else {}


def find() -> dict:
    """The theme of the most recently installed pack that has one, keeping only valid colors."""
    for content_dir in reversed(get_content().user_content):
        data = _read_json(content_dir / "theme.json")
        if isinstance(data, dict):
            canvas = data.get("canvas")
            return {"colors": _colors(data.get("colors"), ROLES), "canvas": canvas if HEX.match(str(canvas)) else None,
                    "keys": _colors(data.get("keys"), {k for row in LETTER_ROWS for k in row})}
    return {}


def _step(color: str, by: int = 6) -> str:
    """The checkerboard partner of a canvas color: the same small step Purple's own pair takes."""
    return "#" + "".join(f"{max(0, min(255, int(color[i:i + 2], 16) + by)):02x}" for i in (1, 3, 5))


def apply(theme: dict) -> None:
    for role, default in _DEFAULTS["roles"].items():
        setattr(P, role.upper(), theme.get("colors", {}).get(role, default))
    canvas = theme.get("canvas")
    art_room.CANVAS_BG, art_room.CANVAS_ALT = (canvas, _step(canvas, -6 if P.luminance(canvas) > 0.5 else 6)) if canvas else _DEFAULTS["canvas"]
    P.KEY_COLORS.clear()
    P.KEY_COLORS.update(_DEFAULTS["keys"])
    P.KEY_COLORS.update(theme.get("keys", {}))
    P.KEY_COLORS["÷"] = P.KEY_COLORS["×"] = P.KEY_COLORS["/"]
