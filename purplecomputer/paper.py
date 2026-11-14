"""The printed page: what the kid made, on white, without cursor or hints.

Every page is signed in its corner with the computer's name in handwriting, over the Purple bot and "made with Purple Computer".
A room that can print has paper(g, size, on_screen=False), which returns its work
drawn to fit size on a white ground (or None when there is nothing yet), and
LANDSCAPE. on_screen draws it in the screen's colors instead; screen_artwork is that
in the screen's shape, as the Saved toast and Open show it. Work that runs past one
page also has paper_pages(g, size), every page of it; paper() is then its first.
"""

import pygame

from . import palette as P
from .palette import rgb

DPI = 300  # printers print at 300 to 600; less shows as soft text and stepped edges


def pt(n: float) -> int:
    return round(n * DPI / 72)


PAGE = (pt(792), pt(612))  # US Letter landscape; the driver fits it to A4 too
MARGIN = pt(36)
WHITE = (255, 255, 255)
# Ink for chrome-colored text (the screen's light-on-dark tokens) on paper
INK, INK_MUTED = "#1a1a1a", "#6b6b6b"
MARK_PX = pt(10)
SIGN_PX = pt(19)  # Caveat runs small for its size
CORNER = MARGIN // 2  # the mark's inset from the right and bottom edges, inside every printer's reach
BOTTOM = pt(60)       # the work's bottom margin, keeping it clear of the mark


def can_print(room) -> bool:
    return hasattr(room, "paper")


BRAND = "made with Purple Computer"


def maker_mark(computer_name: str) -> tuple:
    """(signature, brand line) for the page's corner; either may be empty. The brand always shows: each print on a fridge is how another family hears of Purple."""
    from .rooms.parent_menu import DEFAULT_COMPUTER_NAME
    if not computer_name or computer_name == DEFAULT_COMPUTER_NAME:
        return "", BRAND
    if "purple" in computer_name.lower():
        return computer_name, ""
    return computer_name, BRAND


def _mark(g, computer_name: str) -> pygame.Surface:
    """The signature over the bot and brand, right-aligned; the bot leads the last line."""
    sign, brand = maker_mark(computer_name)
    lines = [s for s in (sign and g.text(sign, SIGN_PX, "hand", INK, tr=False),
                         brand and g.text(brand, MARK_PX, "sans", INK_MUTED)) if s]
    last = lines[-1]
    bot = g.image("bot.png", round(MARK_PX * 1.4))
    gap = MARK_PX // 2
    row = lines[-1] = pygame.Surface((bot.get_width() + gap + last.get_width(),
                                      max(bot.get_height(), last.get_height())), pygame.SRCALPHA)
    row.blit(bot, bot.get_rect(midleft=(0, row.get_height() // 2)))
    row.blit(last, last.get_rect(midright=(row.get_width(), row.get_height() // 2)))
    out = pygame.Surface((max(s.get_width() for s in lines), sum(s.get_height() for s in lines)), pygame.SRCALPHA)
    y = 0
    for s in lines:
        out.blit(s, (out.get_width() - s.get_width(), y))
        y += s.get_height()
    return out


def page_size(landscape: bool) -> tuple:
    return PAGE if landscape else PAGE[::-1]


def work_rect(landscape: bool) -> pygame.Rect:
    w, h = page_size(landscape)
    return pygame.Rect(MARGIN, MARGIN, w - 2 * MARGIN, h - MARGIN - BOTTOM)


def artwork(room, g, size=None, on_screen=False):
    """The room's work drawn to fill size (a page inside its margins), or None when there is nothing yet."""
    if not can_print(room):
        return None
    return room.paper(g, size or work_rect(room.LANDSCAPE).size, on_screen)


def screen_artwork(room, g):
    return artwork(room, g, (g.vw(40), g.vh(40)), on_screen=True)


def pages(room, g, computer_name: str = ""):
    """([page surfaces], landscape) for the room's work, or None when there is nothing to print."""
    if not can_print(room):
        return None
    if hasattr(room, "paper_pages"):
        works = room.paper_pages(g, work_rect(room.LANDSCAPE).size)
    else:
        works = [w for w in [artwork(room, g)] if w is not None]
    return ([compose(w, room.LANDSCAPE, g, computer_name)[0] for w in works], room.LANDSCAPE) if works else None


def compose(work, landscape: bool, g, computer_name: str = ""):
    """(page surface, landscape): the work centered on white with the maker's mark."""
    size = page_size(landscape)
    out = pygame.Surface(size)
    out.fill(WHITE)
    out.blit(work, work.get_rect(center=work_rect(landscape).center))
    mark = _mark(g, computer_name)
    out.blit(mark, mark.get_rect(bottomright=(size[0] - CORNER, size[1] - CORNER)))
    return out, landscape


def blank(size, on_screen=False) -> pygame.Surface:
    s = pygame.Surface(size)
    s.fill(rgb(P.SURFACE) if on_screen else WHITE)
    return s
