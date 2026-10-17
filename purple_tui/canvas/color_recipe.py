"""Mixing paint, drawn as a sum of keycaps in their sticker colors, so a kid
who can't read yet sees that one key and another make a third color. Art and
Blocks show an example in the hint row, and a '[R] + [?]' badge over the
spot a held letter would mix into."""

import pygame

from .. import palette as P
from ..color_mixing import mix_colors_paint
from ..palette import ASDF_ROW, QWERTY_ROW, ZXCV_ROW, get_key_color
from .ui import CODE_HINT, draw_key_hint

HUE_ROWS = [[k for k in row if k.isalpha()] for row in (QWERTY_ROW, ASDF_ROW, ZXCV_ROW)]   # red, yellow, blue
EXAMPLE_KEY = "f"


def partner(key: str) -> str:
    """The key in the next hue row at the same spot, so the example mixes two
    colors of like lightness into a clear third (red+yellow, yellow+blue, blue+red)."""
    for i, row in enumerate(HUE_ROWS):
        if key in row:
            nxt = HUE_ROWS[(i + 1) % len(HUE_ROWS)]
            return nxt[min(row.index(key), len(nxt) - 1)]
    return "r"          # a gray: anything shows the mix


def example(key: str) -> tuple:
    """(terms, result) mixing the brush's key, or a stand-in when the brush came from the wheel."""
    a = key if get_key_color(key) != P.UNMAPPED else EXAMPLE_KEY
    terms = [(k, get_key_color(k)) for k in (a, partner(a))]
    return terms, mix_colors_paint([c for _, c in terms])


def _pieces(terms, result, lead: str) -> list:
    """(text, fill) pieces: fill "" is a plain word, None an empty keycap."""
    out = [(lead, "")] if lead else []
    for i, (key, color) in enumerate(terms):
        out += ([("+", "")] if i else []) + [(key.upper(), color)]
    return out + ([("=", ""), ("", result)] if result else [])


def _widths(g, pieces, px: int) -> tuple:
    cap_h = g.measure("M", px, "mono")[1] + round(px * 0.56)
    ws = [g.measure(t, px, "mono")[0] if fill == "" else max(cap_h, g.measure(t, px, "mono")[0] + round(px * 1.4))
          for t, fill in pieces]
    return ws, cap_h, round(px * 0.5)


def recipe_size(g, terms, result, px: int, lead: str = "") -> tuple:
    ws, h, gap = _widths(g, _pieces(terms, result, lead), px)
    return sum(ws) + gap * (len(ws) - 1), h


def draw_recipe(g, terms, result, px: int, x: int, y: int, anchor="midright", ink=None, lead: str = "") -> pygame.Rect:
    """`terms` are (key, color) keycaps, a None color an empty keycap for the
    key still to come; '= result' follows as a blank keycap of the mixed color when given."""
    ink = ink or P.MUTED
    pieces = _pieces(terms, result, lead)
    ws, h, gap = _widths(g, pieces, px)
    box = pygame.Rect((0, 0), recipe_size(g, terms, result, px, lead))
    setattr(box, anchor, (x, y))
    left = box.x
    for (text, fill), w in zip(pieces, ws):
        cap = pygame.Rect(left, box.centery - h // 2, w, h)
        left += w + gap
        if fill == "":
            g.draw_text(text, px, cap.centerx, cap.centery, "mono", ink, anchor="center")
        elif fill is None:
            g.rect(P.LINE, cap, width=1, radius=round(px * 0.5))
            g.draw_text(text, px, cap.centerx, cap.centery, "mono", ink, anchor="center")
        else:
            draw_color_cap(g, text, fill, cap, px)
    return box


def draw_color_cap(g, text: str, fill: str, cap: pygame.Rect, px: int, radius: int | None = None):
    """A keycap filled with its sticker color, the letter in whichever ink reads on it."""
    g.rect(fill, cap, radius=round(px * 0.5) if radius is None else radius)
    g.draw_text(text, px, cap.centerx, cap.centery, "mono-bold", P.ON_PRIMARY if P.luminance(fill) > 0.5 else "#FFFFFF", anchor="center")


def hint_row(key: str) -> dict:
    """draw_recipe's arguments for the hint row's example."""
    terms, result = example(key)
    return dict(terms=terms, result=result, lead="Hold", ink=P.DIM)


def draw_foot_right(g, foot: pygame.Rect, code_hint: bool, recipe: dict | None):
    """The hint row's right end: the code line's hold hint, with the recipe before it."""
    px, right = g.vh(1.9), foot.right
    if code_hint:
        right = draw_key_hint(g, CODE_HINT, px, right, foot.centery, anchor="midright").x - 2 * px
    if recipe:
        draw_recipe(g, px=px, x=right, y=foot.centery, **recipe)


def held_key(app, last_key: str) -> str | None:
    """The letter held long enough to show the badge, when the next key would mix with it."""
    k = (app.held_letter or "").lower()
    return k if k and k == last_key and not app._littles_mode else None


def draw_hold_badge(g, key: str, px: int, target: pygame.Rect, bounds: pygame.Rect):
    """'[R] + [?]' on a plate just above `target`, the spot the next key would
    mix into, or below it when there is no room above."""
    terms = [(key, get_key_color(key)), ("?", None)]
    w, h = recipe_size(g, terms, None, px)
    pad = round(px * 0.6)
    plate = pygame.Rect(0, 0, w + 2 * pad, h + 2 * pad)
    plate.midbottom = (target.centerx, target.top - pad)
    if plate.top < bounds.top:
        plate.midtop = (target.centerx, target.bottom + pad)
    plate.clamp_ip(bounds)
    g.rect(P.SURFACE, plate, radius=pad)
    g.rect(P.LINE, plate, width=1, radius=pad)
    draw_recipe(g, terms, None, px, plate.centerx, plate.centery, anchor="center", ink=P.TEXT)
