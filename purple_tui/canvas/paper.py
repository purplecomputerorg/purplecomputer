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


def page(room, g, computer_name: str = ""):
    """(surface, landscape) for the room's work, or None when there is nothing to print."""
    if not can_print(room):
        return None
    landscape = room.LANDSCAPE
    size = PAGE if landscape else PAGE[::-1]
    work = room.paper(g, (size[0] - 2 * MARGIN, size[1] - 2 * MARGIN))
    if work is None:
        return None
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
