"""Paint the Secret Menu pictures (purple_tui.secret_doodle) onto the canvas Art room."""

from ..secret_doodle import build_ops
from ..secret_photo import OPS


def paint_picture(art, cells: list, letters: list = ()) -> None:
    """Paint (x, y, color) cells of the Art grid onto a fresh canvas, then write (x, y, char, ink) letters over them."""
    art.clear()
    for x, y, k in cells:
        art.paint_at(x, y, k)
    for x, y, ch, ink in letters:
        art.write_at(x, y, ch, ink)


def paint_cells(app, cells: list, letters: list = ()) -> None:
    app.action_switch_room("art")
    paint_picture(app.rooms["art"], cells, letters)
    app.invalidate()


def paint_ops(app, ops: list) -> None:
    """The Secret Menu pictures were authored on the old 132x25 terminal grid
    (2:1 cells), so they are scaled onto today's square grid keeping their proportions."""
    from .rooms.art_room import COLS
    s = COLS / 132
    paint_cells(app, [(round(x * s), round(y * 2 * s), k) for x, y, k in ops])


def paint_doodle(app) -> None:
    paint_ops(app, build_ops())


def paint_photo(app) -> None:
    paint_ops(app, OPS)
