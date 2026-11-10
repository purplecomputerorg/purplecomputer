"""The rooms' real results for the cards. Each example the .typ files name goes through the room
itself and is drawn by its own print code, so a card always shows what Purple shows:
ex("..."), says("...") and result("...") are Play lines; art("...") and blocks("...") are code."""

import asyncio
import re
from pathlib import Path

EXAMPLE = re.compile(r'\b(ex|says|result|art|blocks)\("((?:[^"\\]|\\.)*)"')
ROOMS = ("play", "art", "blocks")
SIZE = (2732, 1536)  # twice the default screen, so answers stay sharp in print
EM_PT = 5.0          # one screen em on the card; theme.typ's result() trusts the PNG's dpi for this
ANSWER_EMS = 1.7     # one size for every answer: the screen gives emoji-only answers 2 and the rest 1.3
ABACUS_SCALE = 1.1    # the abacus keeps its own fixed size, small beside the answers above
CARD_EMS = 33       # answers wrap at the card's answer column, as they would on a screen that narrow
INK = ("#352a4a", "#6b5e7d", (255, 255, 255))  # theme.typ ink, ink-med, white panels
PAPER_LIGHTNESS = 0.64  # the abacus pastels are picked for the dark screen and wash out on white
ART_CELL_PX, ART_CELL_PT = 24, 5.4
ART_GROUND = ((246, 241, 252), (238, 231, 248))  # a pale checkerboard, so a gap in the paint still shows
BLOCKS_SIZE, BLOCKS_DPI = (1200, 800), 540
SETTLE_S = 1.5       # blocks drop in and fade up; draw them once they've landed


def for_paper(hex_color: str) -> str:
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    return "#" + "".join(f"{round(c * 255):02x}" for c in colorsys.hls_to_rgb(h, l * PAPER_LIGHTNESS, s))


def slug(code: str) -> str:
    """Matches result() in theme.typ."""
    return re.sub(r"[^a-z0-9]+", "-", code.lower())


def examples(typ_files) -> dict:
    """{room: [code, ...]} across the cards."""
    found = {room: set() for room in ROOMS}
    for f in typ_files:
        for m in EXAMPLE.finditer(Path(f).read_text()):
            found[m.group(1) if m.group(1) in ROOMS else "play"].add(m.group(2))
    for codes in found.values():
        if len({slug(c) for c in codes}) != len(codes):
            raise SystemExit(f"two examples share a file name: {sorted(codes)}")
    return {room: sorted(codes) for room, codes in found.items()}


async def _play(codes: list, out: Path) -> None:
    import pygame
    from purple_tui.canvas.harness import make_app
    from purple_tui.canvas.rooms import play_room
    from purple_tui.canvas.rooms.play_room import answer_parts
    from purple_tui.play_eval import SimpleEvaluator
    SimpleEvaluator.ABACUS_COLORS = [for_paper(c) for c in SimpleEvaluator.ABACUS_COLORS]
    play_room.abacus_group_gap = lambda g: 0  # the screen's comma gap reads as a glitch on one small card abacus

    app = make_app(size=SIZE, room="play")
    room, g = app.room, app.g
    room._answer_px = lambda g, e: g.em(ANSWER_EMS)
    width = g.em(CARD_EMS)
    dpi = 72 * g.em(1) / EM_PT
    for code in codes:
        room.clear()
        room._submit_line(code, allow_speak=False)
        e = room.history[-1]
        s = pygame.Surface((max(width, room._entry_width(g, e)), room._entry_height(g, e, width)))
        s.fill(INK[2])
        with g.drawing_on(s):
            room._draw_entry(g, e, 0, 0, s.get_width(), INK)
        abacus = any(isinstance(p, tuple) for p in answer_parts(e.markup))
        _save(s.subsurface(_ink_rect(s)), out / f"{slug(code)}.png", dpi / (ABACUS_SCALE if abacus else 1))


async def _ran(room: str, code: str):
    """A fresh app with the code run in the room."""
    from purple_tui.canvas.harness import make_app
    app = make_app(size=SIZE, room=room)
    await app.rooms[room].run_code([code])
    return app


async def _art(codes: list, out: Path) -> None:
    """The cells from where the brush starts to the far edge of the paint, on a pale checkerboard."""
    import pygame
    from purple_tui.canvas.rooms.art_room import COLS, ROWS
    c = ART_CELL_PX
    for code in codes:
        app = await _ran("art", code)
        room = app.rooms["art"]
        paint = room.paper(app.g, (COLS * c, ROWS * c))
        paint.set_colorkey(INK[2])
        cells = [xy for xy, cell in room._grid.items() if cell[0] not in ("", " ") or room._painted(cell)]
        w, h = (1 + max(p[i] for p in cells + [(0, 0)]) for i in (0, 1))
        s = pygame.Surface((w * c, h * c))
        for x in range(w):
            for y in range(h):
                s.fill(ART_GROUND[(x + y) % 2], (x * c, y * c, c, c))
        s.blit(paint, (0, 0))
        _save(s, out / f"{slug(code)}.png", 72 * c / ART_CELL_PT)


async def _blocks(codes: list, out: Path) -> None:
    """The build and its shadow, the floor left out."""
    for code in codes:
        app = await _ran("blocks", code)
        await asyncio.sleep(SETTLE_S)
        s = _without_floor(app.rooms["blocks"].paper(app.g, BLOCKS_SIZE))
        _save(s.subsurface(_ink_rect(s)), out / f"{slug(code)}.png", BLOCKS_DPI)


def _without_floor(s):
    """The pale gray floor turned white; blocks are colored and shadows darker."""
    import pygame
    px = pygame.surfarray.pixels3d(s)
    floor = (px.max(axis=2) - px.min(axis=2) < 12) & (px.min(axis=2) > 190)
    px[floor] = INK[2]
    del px
    return s


def _ink_rect(s):
    """The drawn part: everything that isn't the white ground."""
    import pygame
    mask = pygame.mask.from_threshold(s, (255, 255, 255), (1, 1, 1, 255))
    mask.invert()
    rects = mask.get_bounding_rects()
    return rects[0].unionall(rects[1:]) if rects else s.get_rect()


def _save(s, path: Path, dpi: float) -> None:
    import pygame
    from PIL import Image
    Image.frombytes("RGB", s.get_size(), pygame.image.tobytes(s, "RGB")).save(path, dpi=(dpi, dpi))


async def _render(found: dict, out: Path) -> None:
    for room, draw in (("play", _play), ("art", _art), ("blocks", _blocks)):
        (out / room).mkdir(parents=True, exist_ok=True)
        await draw(found[room], out / room)


def render(typ_files, out: Path) -> None:
    for old in out.glob("**/*.png"):
        old.unlink()
    asyncio.run(_render(examples(typ_files), out))
