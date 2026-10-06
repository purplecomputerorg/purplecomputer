"""The printed page: what the kid made, on white, without cursor or hints.

Every page carries a small maker's mark built from the computer's name.
A room that can print has paper(g, size), which returns its work drawn to fit
size on a white ground (or None when there is nothing yet), and LANDSCAPE.
"""

import pygame

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


def artwork(room, g):
    """The room's work drawn to fill a page inside its margins, or None when there is nothing yet."""
    if not can_print(room):
        return None
    w, h = page_size(room.LANDSCAPE)
    return room.paper(g, (w - 2 * MARGIN, h - 2 * MARGIN))


def page(room, g, computer_name: str = ""):
    """(surface, landscape) for the room's work, or None when there is nothing to print."""
    work = artwork(room, g)
    return None if work is None else compose(work, room.LANDSCAPE, g, computer_name)


def compose(work, landscape: bool, g, computer_name: str = ""):
    """(page surface, landscape): the work centered on white with the maker's mark."""
    size = page_size(landscape)
    out = pygame.Surface(size)
    out.fill(WHITE)
    out.blit(work, work.get_rect(center=out.get_rect().center))
    mark = g.text(maker_mark(computer_name), MARK_PX, "mono", INK_MUTED)
    out.blit(mark, mark.get_rect(bottomright=(size[0] - MARGIN, size[1] - MARGIN // 3)))
    return out, landscape


def blank(size) -> pygame.Surface:
    s = pygame.Surface(size)
    s.fill(WHITE)
    return s
