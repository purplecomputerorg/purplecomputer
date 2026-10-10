"""Paint the Secret Menu pictures (purple_tui.secret_doodle) onto the canvas Art room."""

from ..secret_doodle import build_ops
from ..secret_photo import OPS


def paint_ops(app, ops: list) -> None:
    """Switch to the Art room and paint ops onto a fresh canvas. The ops were
    authored on the old 132x25 terminal grid (2:1 cells), so they are scaled
    onto today's square grid keeping their proportions."""
    from .rooms.art_room import COLS
    app.action_switch_room("art")
    art = app.rooms["art"]
    art.clear()
    s = COLS / 132
    for x, y, k in ops:
        art.paint_at(round(x * s), round(y * 2 * s), k)
    app.invalidate()


def paint_doodle(app) -> None:
    paint_ops(app, build_ops())


def paint_photo(app) -> None:
    paint_ops(app, OPS)
