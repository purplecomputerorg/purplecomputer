"""Mixing paint, drawn as a sum of keycaps in their sticker colors, so a kid
who can't read yet sees that one key and another make a third color. Art and
Blocks show an example in the hint row, and a badge over the brush: the chord
being painted, or '[R] + [?]' while one letter is held alone."""

import pygame

from .. import palette as P
from ..color_mixing import mix_colors_paint
from ..palette import ASDF_ROW, QWERTY_ROW, ZXCV_ROW, get_key_color
from .ui import CODE_HINT, draw_key_hint

HUE_ROWS = [[k for k in row if k.isalpha()] for row in (QWERTY_ROW, ASDF_ROW, ZXCV_ROW)]   # red, yellow, blue
EXAMPLE_KEY = "f"
MAX_TERMS = 3
NO_MIX = ((), None)
BADGE_DABS, BADGE_FADE = 10, 6   # dabs under one badge at full strength, then dabs it takes to fade


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


def chord(mix: tuple, brush: tuple, new: tuple) -> tuple:
    """(keycaps, color) once `new` (key, color) mixes into `brush`: the keycaps go on
    from `mix` while it is still the brush, and past three the mix so far folds into one blank swatch."""
    terms, made = mix
    if made != brush[1]:
        terms = [brush]
    elif len(terms) >= MAX_TERMS:
        terms = [("", made)]
    return [*terms, new], mix_colors_paint([brush[1], new[1]])


def dab(under: str | None, mix: tuple, brush: tuple) -> tuple | None:
    """(keycaps, color) a dab of `brush` (key, color) makes: its chord's keycaps while
    `mix` is still the brush, after a blank swatch of any paint `under` it. None when nothing mixed."""
    terms = list(mix[0]) if mix[1] == brush[1] else [brush]
    if under is None:
        return (terms, brush[1]) if len(terms) > 1 else None
    if len(terms) >= MAX_TERMS:
        terms = [("", brush[1])]
    return [("", under), *terms], mix_colors_paint([under, brush[1]])


def hint_row(key: str, mixed: tuple | None) -> dict:
    """draw_recipe's arguments for the hint row: what the last dab mixed, else an example
    to try (also when every term was the same color, since that mixed nothing)."""
    if mixed and len({c.lower() for _, c in mixed[0]}) > 1:
        return dict(terms=mixed[0], result=mixed[1], lead="You mixed", ink=P.MUTED)
    terms, result = example(key)
    return dict(terms=terms, result=result, lead="Hold", ink=P.MUTED)


def draw_foot_right(g, foot: pygame.Rect, code_hint: bool, recipe: dict | None):
    """The hint row's right end: the code line's hold hint, with the recipe before it."""
    px, right = g.vh(1.9), foot.right
    if code_hint:
        right = draw_key_hint(g, CODE_HINT, px, right, foot.centery, anchor="midright").x - 2 * px
    if recipe:
        draw_recipe(g, px=px, x=right, y=foot.centery, **recipe)


def _badge_recipe(app, last_key: str, mix: tuple, brush_color: str) -> tuple | None:
    """(terms, result) for the plate over the brush: the chord it is painting with,
    else '[R] + [?]' while one letter is held alone. None when no letter is held."""
    k = (app.held_letter or "").lower()
    if not k or app._littles_mode:
        return None
    terms, made = mix
    if len(terms) > 1 and made == brush_color:
        return tuple(terms), made
    return (((k, get_key_color(k)), ("?", None)), None) if k == last_key else None


class HoldBadge:
    """The plate over the brush. Once one recipe has painted BADGE_DABS dabs it
    fades out over BADGE_FADE more, so a long stroke isn't trailed by a sign."""

    def __init__(self):
        self._shown, self._dabs = None, 0

    def dabbed(self):
        self._dabs += 1

    def draw(self, g, app, last_key: str, mix: tuple, brush_color: str, target: pygame.Rect, bounds: pygame.Rect):
        recipe = _badge_recipe(app, last_key, mix, brush_color)
        if recipe != self._shown:
            self._shown, self._dabs = recipe, 0
        strength = min(1.0, 1 - (self._dabs - BADGE_DABS) / BADGE_FADE)
        if recipe and strength > 0:
            draw_hold_badge(g, *recipe, g.vh(1.9), target, bounds, strength)


def draw_hold_badge(g, terms, result, px: int, target: pygame.Rect, bounds: pygame.Rect, strength: float = 1.0):
    """The recipe on a plate just above `target`, the spot the brush last
    painted, or below it when there is no room above; `strength` is its opacity."""
    w, h = recipe_size(g, terms, result, px)
    pad = round(px * 0.6)
    plate = pygame.Rect(0, 0, w + 2 * pad, h + 2 * pad)
    plate.midbottom = (target.centerx, target.top - pad)
    if plate.top < bounds.top:
        plate.midtop = (target.centerx, target.bottom + pad)
    plate.clamp_ip(bounds)
    layer = pygame.Surface(plate.size, pygame.SRCALPHA)
    with g.drawing_on(layer):
        local = layer.get_rect()
        g.rect(P.SURFACE, local, radius=pad)
        g.rect(P.LINE, local, width=1, radius=pad)
        draw_recipe(g, terms, result, px, local.centerx, local.centery, anchor="center", ink=P.TEXT)
    layer.set_alpha(round(255 * strength))
    g.surface.blit(layer, plate)


class ChordStamps:
    """Undo for the last key's square, so a key pressed with it can mix into that square
    instead of stamping another. `save()` moves onto the next stamp spot and returns
    what `restore` needs to put it back."""

    def __init__(self, save, restore, stamp):
        self._save, self._restore, self._stamp = save, restore, stamp
        self._undo = None

    def clear(self):
        self._undo = None

    def press(self, mix_in: bool, *args):
        if mix_in and self._undo is not None:
            self._restore(self._undo)
        self._undo = self._save()
        self._stamp(*args)
