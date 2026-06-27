"""A saved hand-drawn doodle, reproducible from the Secret Menu.

The strokes are stored as ordered (x, y, color_key) paint ops. Order matters:
base colors are painted first, then overlays mix (yellow 'f' + blue 'c' = green,
yellow 'f' + red 'r' = orange). Colors: z=light blue, c=med blue, f=yellow,
r=red, 1=white.
"""


def build_ops() -> list[tuple[int, int, str]]:
    ops: list[tuple[int, int, str]] = []

    def pt(x, y, k):
        ops.append((x, y, k))

    def h(y, x1, x2, k):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            pt(x, y, k)

    def v(x, y1, y2, k):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            pt(x, y, k)

    def green(x, y):
        pt(x, y, 'f'); pt(x, y, 'c')

    def orange(x, y):
        pt(x, y, 'f'); pt(x, y, 'r')

    # 1. Top-left bracket (staple, opening right)
    h(0, 1, 10, 'f')
    pt(1, 0, 'r'); pt(2, 0, 'z'); pt(3, 0, 'z')
    v(1, 0, 4, 'f')
    pt(1, 0, 'r')
    green(1, 4); pt(2, 4, 'r')

    # 2. Long light-blue line
    h(5, 3, 34, 'z')

    # 3. Top-middle comb (blue bar, white+green insets, 3 yellow up-prongs)
    h(4, 24, 48, 'z')
    h(4, 27, 34, '1')
    green(35, 4)
    v(24, 2, 4, 'f')
    v(36, 2, 4, 'f')
    v(47, 2, 4, 'f')

    # 4. Isolated red block
    pt(51, 4, 'r'); pt(51, 5, 'r')

    # 5. Blue staircase: line step-down then diagonal to junction
    v(34, 5, 8, 'z')
    h(8, 34, 54, 'z')
    pt(54, 7, 'f'); pt(54, 8, 'f')
    stair = [(54, 9), (55, 9), (55, 10), (56, 11), (57, 11), (57, 12), (58, 13),
             (59, 13), (60, 14), (61, 14), (61, 15), (62, 16), (63, 16), (64, 16),
             (65, 17), (66, 17)]
    for (x, y) in stair:
        pt(x, y, 'z')
    pt(57, 12, 'f'); pt(61, 14, 'f')
    green(65, 16); pt(66, 16, 'r')

    # 6. Top-center bar + red/yellow vertical line
    h(3, 71, 77, 'f')
    pt(71, 3, 'r'); pt(72, 3, 'z')
    for x in range(74, 78):
        v(x, 5, 6, 'z')
    valt = ['r', 'r', 'f', 'r', 'r', 'f', 'r', 'r', 'f']
    for i, k in enumerate(valt):
        pt(72, 8 + i, k)
        pt(73, 8 + i, k)
    pt(71, 16, 'r'); orange(67, 17); pt(68, 17, 'z')

    # 7. Yellow table / bench
    h(17, 64, 101, 'f')
    h(18, 64, 101, 'f')
    orange(100, 18); pt(101, 18, 'r')
    v(64, 18, 22, 'f')
    v(65, 18, 22, 'f')
    v(100, 19, 23, 'f')
    h(22, 64, 100, 'f')
    for x in range(69, 83):
        orange(x, 22)
    v(86, 21, 23, 'z')

    # 8. Junction / bottom-left cluster of the table
    pt(62, 21, 'z'); pt(63, 21, '1'); pt(62, 22, 'r'); pt(63, 22, 'f')
    pt(62, 23, 'z'); pt(63, 23, 'r')
    h(23, 92, 95, 'f')

    return ops


def paint_doodle(app) -> None:
    """Switch to the Art room and paint the saved doodle onto a fresh canvas.

    The Art room mounts its canvas lazily on first activation, so the paint is
    retried after each refresh until the canvas exists.
    """
    from .constants import ROOM_ART
    from .rooms.art_room import ArtMode, ArtCanvas
    from textual.css.query import NoMatches

    app.action_switch_room(ROOM_ART[0])

    def _paint(attempts_left: int = 30) -> None:
        try:
            art = app.query_one(ArtMode)
            canvas = art.query_one(ArtCanvas)
            ready = canvas.canvas_width > 50  # size 0 until first layout
        except NoMatches:
            canvas = None
            ready = False
        if not ready:
            if attempts_left > 0:
                app.call_after_refresh(_paint, attempts_left - 1)
            return
        art.clear_canvas()
        for x, y, k in build_ops():
            canvas.paint_at(x, y, k)
        canvas._invalidate_all()
        canvas.refresh()

    app.call_after_refresh(_paint)
