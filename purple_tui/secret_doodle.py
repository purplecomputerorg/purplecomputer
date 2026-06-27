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

    # 6. Head (top-right) + neck
    pt(72, 1, '='); pt(73, 1, '=')                 # black drawing atop the head
    pt(71, 2, 'r'); pt(72, 2, 'z'); pt(73, 2, 'f')  # face row: red, blue, yellow,
    pt(74, 2, 'z'); pt(75, 2, 'f')                  #           blue, yellow
    pt(71, 3, 'r'); pt(73, 3, '=')                  # red below-left, black cheek
    v(74, 3, 4, 'z'); v(75, 3, 4, 'z')              # blue square
    pt(74, 5, 'f')
    v(72, 5, 6, 'z'); v(73, 5, 6, 'z'); pt(74, 6, 'z')  # wider blue block
    valt = ['r', 'r', 'f', 'r', 'r', 'f', 'r', 'r', 'f', 'r']  # red/yellow neck
    for i, k in enumerate(valt):
        pt(72, 7 + i, k)
        pt(73, 7 + i, k)

    # 7. Body (the back / table top) + neck junction
    green(64, 16)
    h(16, 64, 101, 'f')
    h(17, 64, 101, 'f')
    orange(100, 17); pt(101, 17, 'r')
    orange(70, 16); pt(71, 16, 'z')                 # neck meets the body

    # 8. Legs hanging under the body, with feet
    v(64, 18, 23, 'f'); v(65, 18, 23, 'f')          # front leg
    v(99, 18, 23, 'f'); v(100, 18, 23, 'f')         # back leg
    h(20, 65, 99, 'f')                              # belly stretcher
    pt(66, 20, '='); pt(67, 20, '=')                # black on the belly
    for x in range(68, 83):
        orange(x, 20)                               # orange belly
    pt(96, 19, 'z'); pt(96, 20, 'z')                # blue step up to back leg
    # front foot: cyan / red / black / blue / yellow cluster
    pt(63, 21, 'z'); pt(65, 21, 'z')
    pt(63, 22, '='); pt(64, 22, 'r'); pt(65, 22, 'f')
    pt(63, 23, 'z'); pt(64, 23, 'f'); pt(65, 23, 'r')
    h(23, 63, 66, 'f')
    # back foot
    v(97, 21, 23, 'z')
    h(23, 98, 101, 'f')

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
