"""The printed page: what the kid made, on white, without cursor or hints.

Every page carries a small maker's mark built from the computer's name.
A room that can print has paper(g, size, on_screen=False), which returns its work
drawn to fit size on a white ground (or None when there is nothing yet), and
LANDSCAPE. on_screen draws it in the screen's colors instead; screen_artwork is that
in the screen's shape, as the Saved toast and Open show it. Work that runs past one
page also has paper_pages(g, size), every page of it; paper() is then its first.
"""

import pygame

from .. import palette as P
from ..palette import rgb

PAGE = (1650, 1275)  # US Letter landscape at 150 dpi; the driver fits it to A4 too
MARGIN = 75          # half an inch
WHITE = (255, 255, 255)
# Ink for chrome-colored text (the screen's light-on-dark tokens) on paper
INK, INK_MUTED = "#1a1a1a", "#6b6b6b"
MARK_PX = 20  # about 10 pt


def can_print(room) -> bool:
    return hasattr(room, "paper")


def maker_mark(computer_name: str) -> str:
    """The line in the page's corner. The brand is always in it: each print on a fridge is how another family hears of Purple."""
    from .rooms.parent_menu import DEFAULT_COMPUTER_NAME
    if not computer_name or computer_name == DEFAULT_COMPUTER_NAME:
        return "Made on Purple Computer"
    if "purple" in computer_name.lower():
        return f"Made on {computer_name}"
    return f"Made on {computer_name} with Purple Computer"


def page_size(landscape: bool) -> tuple:
    return PAGE if landscape else PAGE[::-1]


def artwork(room, g, size=None, on_screen=False):
    """The room's work drawn to fill size (a page inside its margins), or None when there is nothing yet."""
    if not can_print(room):
        return None
    w, h = page_size(room.LANDSCAPE)
    return room.paper(g, size or (w - 2 * MARGIN, h - 2 * MARGIN), on_screen)


def screen_artwork(room, g):
    return artwork(room, g, (g.vw(40), g.vh(40)), on_screen=True)


def pages(room, g, computer_name: str = ""):
    """([page surfaces], landscape) for the room's work, or None when there is nothing to print."""
    if not can_print(room):
        return None
    if hasattr(room, "paper_pages"):
        w, h = page_size(room.LANDSCAPE)
        works = room.paper_pages(g, (w - 2 * MARGIN, h - 2 * MARGIN))
    else:
        works = [w for w in [artwork(room, g)] if w is not None]
    return ([compose(w, room.LANDSCAPE, g, computer_name)[0] for w in works], room.LANDSCAPE) if works else None


def compose(work, landscape: bool, g, computer_name: str = ""):
    """(page surface, landscape): the work centered on white with the maker's mark."""
    size = page_size(landscape)
    out = pygame.Surface(size)
    out.fill(WHITE)
    out.blit(work, work.get_rect(center=out.get_rect().center))
    mark = g.text(maker_mark(computer_name), MARK_PX, "mono", INK_MUTED)
    out.blit(mark, mark.get_rect(bottomright=(size[0] - MARGIN, size[1] - MARGIN // 3)))
    return out, landscape


def blank(size, on_screen=False) -> pygame.Surface:
    s = pygame.Surface(size)
    s.fill(rgb(P.SURFACE) if on_screen else WHITE)
    return s
